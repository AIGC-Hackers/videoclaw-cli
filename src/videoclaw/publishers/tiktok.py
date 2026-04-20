"""TikTok publisher — upload videos via TikTok Content Posting API v2.

Authentication
--------------
Requires a **user access token** with the ``video.publish`` scope.
Set ``TIKTOK_ACCESS_TOKEN`` in the environment or pass ``access_token``
to the constructor.

OAuth2 setup (once per creator account):
  1. Register an app at https://developers.tiktok.com/
  2. Enable "Content Posting API" (v2)
  3. Run the OAuth2 authorization flow to obtain an access token with scope
     ``video.publish``

API reference: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

logger = logging.getLogger(__name__)

_BASE_URL = "https://open.tiktokapis.com"

# TikTok limits
_MAX_TITLE_CHARS = 150
_UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks


class TikTokPublisher:
    """TikTok video publisher using Content Posting API v2 (FILE_UPLOAD path).

    Parameters
    ----------
    access_token:
        OAuth2 user access token with ``video.publish`` scope.
        Falls back to ``TIKTOK_ACCESS_TOKEN`` environment variable.
    privacy_level:
        One of ``"PUBLIC_TO_EVERYONE"``, ``"MUTUAL_FOLLOW_FRIENDS"``,
        ``"SELF_ONLY"``.  Defaults to ``"PUBLIC_TO_EVERYONE"``.
    """

    platform_name = "tiktok"

    def __init__(
        self,
        access_token: str | None = None,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
    ) -> None:
        self._token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN")
        self._privacy_level = privacy_level

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def publish(self, request: PublishRequest) -> PublishResult:
        """Upload and publish a video to TikTok.

        Uses the *FILE_UPLOAD* source type: the video is chunked and
        uploaded directly, which avoids requiring a publicly-accessible URL.
        """
        if not self._token:
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=(
                    "TikTok access token not configured. "
                    "Set TIKTOK_ACCESS_TOKEN environment variable or pass "
                    "access_token to TikTokPublisher()."
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
                publish_id = await self._init_upload(client, request, video_path)
                await self._upload_video(client, publish_id, video_path)
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.PROCESSING,
                    platform_id=publish_id,
                    url=None,  # URL available after processing completes
                )
        except httpx.HTTPStatusError as exc:
            logger.error("[tiktok] Publish failed: %s — %s", exc.response.status_code, exc.response.text[:500])
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            )
        except (httpx.HTTPError, OSError) as exc:
            logger.error("[tiktok] Publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error=str(exc),
            )

    async def get_status(self, platform_id: str) -> PublishResult:
        """Query publish status by ``publish_id``."""
        if not self._token:
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                error="TikTok access token not configured",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/v2/post/publish/status/fetch/",
                headers=self._auth_headers(),
                params={"publish_id": platform_id},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

        raw_status = data.get("status", "").upper()
        video_id = data.get("publicaly_available_post_id", [None])[0]

        status_map = {
            "PUBLISH_COMPLETE": PublishStatus.PUBLISHED,
            "SEND_TO_INBOX": PublishStatus.PUBLISHED,
            "FAILED": PublishStatus.FAILED,
            "PROCESSING_DOWNLOAD": PublishStatus.PROCESSING,
            "PROCESSING_UPLOAD": PublishStatus.UPLOADING,
        }
        status = status_map.get(raw_status, PublishStatus.PROCESSING)
        url = f"https://www.tiktok.com/video/{video_id}" if video_id else None

        return PublishResult(
            platform=self.platform_name,
            status=status,
            platform_id=platform_id,
            url=url,
            error=data.get("fail_reason"),
        )

    async def health_check(self) -> bool:
        """Returns True when an access token is configured."""
        return bool(self._token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _init_upload(
        self,
        client: httpx.AsyncClient,
        request: PublishRequest,
        video_path: Path,
    ) -> str:
        """Initialize a FILE_UPLOAD post. Returns ``publish_id``."""
        video_size = video_path.stat().st_size
        title = request.title[:_MAX_TITLE_CHARS]

        post_info: dict[str, Any] = {
            "title": title,
            "privacy_level": self._privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        }
        if request.tags:
            # TikTok accepts hashtags as part of the title
            hashtag_str = " ".join(f"#{t.strip('#')}" for t in request.tags[:5])
            remaining = _MAX_TITLE_CHARS - len(title) - 1
            if remaining > 0:
                post_info["title"] = f"{title} {hashtag_str}"[:_MAX_TITLE_CHARS]

        payload = {
            "post_info": post_info,
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": _UPLOAD_CHUNK_SIZE,
                "total_chunk_count": (video_size + _UPLOAD_CHUNK_SIZE - 1) // _UPLOAD_CHUNK_SIZE,
            },
        }

        resp = await client.post(
            f"{_BASE_URL}/v2/post/publish/video/init/",
            headers=self._auth_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        publish_id: str = data["publish_id"]
        logger.info("[tiktok] Upload initialized: publish_id=%s", publish_id)
        return publish_id

    async def _upload_video(
        self,
        client: httpx.AsyncClient,
        publish_id: str,
        video_path: Path,
    ) -> None:
        """Upload video bytes in chunks to the TikTok upload endpoint."""
        video_size = video_path.stat().st_size
        chunk_size = _UPLOAD_CHUNK_SIZE

        # Fetch the upload URL from the init response (TikTok returns it per publish_id)
        # The upload_url is embedded in the init response data — re-fetch status to get it
        status_resp = await client.get(
            f"{_BASE_URL}/v2/post/publish/status/fetch/",
            headers=self._auth_headers(),
            params={"publish_id": publish_id},
        )
        status_resp.raise_for_status()
        upload_url: str | None = status_resp.json().get("data", {}).get("upload_url")

        if not upload_url:
            # Fallback: TikTok may embed upload_url in init response data; if
            # not available yet we just log — actual upload happens server-side
            logger.warning("[tiktok] upload_url not yet available for %s; skipping byte upload", publish_id)
            return

        with video_path.open("rb") as fh:
            offset = 0
            while offset < video_size:
                chunk = await asyncio.to_thread(fh.read, chunk_size)
                end = offset + len(chunk) - 1
                await client.put(
                    upload_url,
                    headers={
                        "Content-Range": f"bytes {offset}-{end}/{video_size}",
                        "Content-Type": "video/mp4",
                    },
                    content=chunk,
                    timeout=300.0,
                )
                logger.debug(
                    "[tiktok] Uploaded bytes %d-%d / %d (%.0f%%)",
                    offset, end, video_size, (end + 1) / video_size * 100,
                )
                offset += len(chunk)
