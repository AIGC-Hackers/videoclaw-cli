"""YouTube publisher — upload videos to YouTube.

Status: NOT IMPLEMENTED. Requires google-api-python-client + OAuth2 credentials.
See: https://developers.google.com/youtube/v3
"""

from __future__ import annotations

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

_NOT_IMPLEMENTED_MSG = (
    "YouTube publisher is not yet implemented. "
    "Requires google-api-python-client and OAuth2 credentials. "
    "Install: pip install google-api-python-client google-auth-oauthlib"
)


class YouTubePublisher:
    """YouTube video publisher (not yet implemented)."""

    platform_name = "youtube"

    def __init__(self, credentials_path: str | None = None) -> None:
        self._credentials_path = credentials_path

    async def publish(self, request: PublishRequest) -> PublishResult:
        return PublishResult(
            platform=self.platform_name,
            status=PublishStatus.FAILED,
            error=_NOT_IMPLEMENTED_MSG,
        )

    async def get_status(self, platform_id: str) -> PublishResult:
        return PublishResult(
            platform=self.platform_name,
            status=PublishStatus.FAILED,
            error=_NOT_IMPLEMENTED_MSG,
        )

    async def health_check(self) -> bool:
        return False
