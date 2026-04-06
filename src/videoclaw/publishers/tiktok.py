"""TikTok publisher — upload videos to TikTok.

Status: NOT IMPLEMENTED. Requires TikTok Content Posting API v2 credentials.
See: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

_NOT_IMPLEMENTED_MSG = (
    "TikTok publisher is not yet implemented. "
    "Requires TikTok Content Posting API v2 credentials "
    "(access_token, client_key, client_secret). "
    "Apply at: https://developers.tiktok.com/"
)


class TikTokPublisher:
    """TikTok video publisher (not yet implemented)."""

    platform_name = "tiktok"

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token

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
