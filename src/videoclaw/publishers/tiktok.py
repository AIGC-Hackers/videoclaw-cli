"""TikTok publisher (placeholder -- requires TikTok API credentials)."""

from __future__ import annotations

import logging

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

logger = logging.getLogger(__name__)


class TikTokPublisher:
    platform_name = "tiktok"

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token

    async def publish(self, request: PublishRequest) -> PublishResult:
        logger.warning("TikTok publish not yet implemented, returning stub")
        return PublishResult(
            platform=self.platform_name,
            status=PublishStatus.FAILED,
            error="TikTok publisher not yet implemented.",
        )

    async def get_status(self, platform_id: str) -> PublishResult:
        return PublishResult(
            platform=self.platform_name,
            status=PublishStatus.FAILED,
            error="Not implemented",
        )

    async def health_check(self) -> bool:
        return False
