"""YouTube publisher — upload videos via YouTube Data API v3.

Authentication
--------------
Requires an OAuth2 **access token** with the ``youtube.upload`` scope.
Set ``YOUTUBE_ACCESS_TOKEN`` in the environment or pass ``access_token``
to the constructor.

OAuth2 setup (once per channel):
  1. Create a project at https://console.cloud.google.com/
  2. Enable "YouTube Data API v3"
  3. Create OAuth2 credentials (Desktop App type)
  4. Run the authorization flow::

       from google_auth_oauthlib.flow import InstalledAppFlow
       flow = InstalledAppFlow.from_client_secrets_file(
           "client_secrets.json",
           scopes=["https://www.googleapis.com/auth/youtube.upload"],
       )
       credentials = flow.run_local_server(port=0)
       print(credentials.token)  # ← set as YOUTUBE_ACCESS_TOKEN

API reference: https://developers.google.com/youtube/v3/guides/uploading_a_video
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

logger = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com"
_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"

# Privacy status values accepted by YouTube
_PRIVACY_PUBLIC = "public"
_PRIVACY_PRIVATE = "private"
_PRIVACY_UNLISTED = "unlisted"

_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB (must be multiple of 256 KB)


class YouTubePublisher:
    """YouTube video publisher using Data API v3 resumable upload.

    Parameters
    ----------
    access_token:
        OAuth2 access token with ``youtube.upload`` scope.
        Falls back to ``YOUTUBE_ACCESS_TOKEN`` environment variable.
    privacy_status:
        One of ``"public"``, ``"private"``, ``"unlisted"``.
        Defaults to ``"private"`` (safer default — avoids accidental public posts).
    category_id:
        YouTube video category.  ``"22"`` = People & Blogs (common for drama).
        See https://developers.google.com/youtube/v3/docs/videoCategories for the full list.
    """

    platform_name = "youtube"

    def __init__(
        self,
        access_token: str | None = None,
        privacy_status: str = _PRIVACY_PRIVATE,
        category_id: str = "22",
    ) -> None:
        self._token = access_token or os.environ.get("YOUTUBE_ACCESS_TOKEN")
        self._privacy_status = privacy_status
        self._category_id = category_id

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def publish(self, request: PublishRequest) -> PublishResult:
        """Upload a video to YouTube using a resumable upload session.

        Flow:
          1. Initialize upload session → get session URI
          2. Upload video in chunks via PUT to session URI
          3. Return video_id and URL once upload completes
        """
        if not self._token:
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=(
                    "YouTube access token not configured. "
                    "Set YOUTUBE_ACCESS_TOKEN environment variable or pass "
                    "access_token to YouTubePublisher()."
                ),
            )

        video_path = Path(request.video_path)
        if not video_path.exists():
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=f"Video file not found: {video_path}",
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                session_uri = await self._init_upload_session(client, request, video_path)
                video_id = await self._upload_video(client, session_uri, video_path)

            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.PROCESSING,
                platform_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "[youtube] Publish failed: %s — %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            )
        except (httpx.HTTPError, OSError) as exc:
            logger.error("[youtube] Publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=str(exc),
            )

    async def get_status(self, platform_id: str) -> PublishResult:
        """Check video processing status by video ID."""
        if not self._token:
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error="YouTube access token not configured",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{_API_BASE}/youtube/v3/videos",
                headers=self._auth_headers(),
                params={"id": platform_id, "part": "status,snippet"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])

        if not items:
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                platform_id=platform_id,
                error="Video not found",
            )

        item = items[0]
        upload_status = item.get("status", {}).get("uploadStatus", "")
        status_map = {
            "uploaded": PublishStatus.PROCESSING,
            "processed": PublishStatus.PUBLISHED,
            "failed": PublishStatus.FAILED,
            "rejected": PublishStatus.FAILED,
            "deleted": PublishStatus.FAILED,
        }
        status = status_map.get(upload_status, PublishStatus.PROCESSING)
        return PublishResult(
            platform=self.platform_name,
            status=status,
            platform_id=platform_id,
            url=f"https://www.youtube.com/watch?v={platform_id}",
            error=item.get("status", {}).get("rejectionReason"),
        )

    async def health_check(self) -> bool:
        """Returns True when an access token is configured."""
        return bool(self._token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _init_upload_session(
        self,
        client: httpx.AsyncClient,
        request: PublishRequest,
        video_path: Path,
    ) -> str:
        """Initialize a resumable upload session. Returns the session URI."""
        video_size = video_path.stat().st_size

        metadata: dict = {
            "snippet": {
                "title": request.title[:100],  # YouTube limit: 100 chars
                "description": request.description[:5000],
                "tags": request.tags[:500],  # YouTube limit: 500 tag chars total
                "categoryId": self._category_id,
            },
            "status": {
                "privacyStatus": self._privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        if request.schedule_at and self._privacy_status != _PRIVACY_PUBLIC:
            # Scheduled publishing requires privacyStatus="private" with publishAt
            metadata["status"]["publishAt"] = request.schedule_at

        resp = await client.post(
            f"{_UPLOAD_BASE}/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                **self._auth_headers(),
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_size),
                "Content-Type": "application/json; charset=UTF-8",
            },
            content=json.dumps(metadata).encode(),
        )
        resp.raise_for_status()

        session_uri: str | None = resp.headers.get("Location")
        if not session_uri:
            raise RuntimeError("YouTube resumable upload init returned no Location header")

        logger.info("[youtube] Upload session initialized for %s (%d bytes)", video_path.name, video_size)
        return session_uri

    async def _upload_video(
        self,
        client: httpx.AsyncClient,
        session_uri: str,
        video_path: Path,
    ) -> str:
        """Upload video in chunks to the session URI. Returns YouTube video ID."""
        video_size = video_path.stat().st_size
        chunk_size = _UPLOAD_CHUNK_SIZE
        video_id: str | None = None

        with video_path.open("rb") as fh:
            offset = 0
            while offset < video_size:
                chunk = fh.read(chunk_size)
                end = offset + len(chunk) - 1

                resp = await client.put(
                    session_uri,
                    headers={
                        "Content-Range": f"bytes {offset}-{end}/{video_size}",
                        "Content-Type": "video/mp4",
                    },
                    content=chunk,
                    timeout=300.0,
                )

                if resp.status_code == 308:
                    # Incomplete — continue
                    logger.debug(
                        "[youtube] Uploaded %d-%d / %d (%.0f%%)",
                        offset, end, video_size, (end + 1) / video_size * 100,
                    )
                elif resp.status_code in (200, 201):
                    # Complete
                    data = resp.json()
                    video_id = data.get("id")
                    logger.info("[youtube] Upload complete: video_id=%s", video_id)
                    break
                else:
                    resp.raise_for_status()

                offset += len(chunk)

        if not video_id:
            raise RuntimeError("YouTube upload completed but no video_id returned")
        return video_id
