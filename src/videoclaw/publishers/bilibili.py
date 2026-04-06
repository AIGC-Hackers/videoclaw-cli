"""Bilibili publisher — upload videos to bilibili.com.

Status: NOT IMPLEMENTED. Requires Bilibili Open Platform API credentials.
See: https://open.bilibili.com/
"""

from __future__ import annotations

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus

_NOT_IMPLEMENTED_MSG = (
    "Bilibili publisher is not yet implemented. "
    "Requires Bilibili Open Platform API credentials (SESSDATA). "
    "Contributions welcome — implement the Publisher protocol in this file."
)


class BilibiliPublisher:
    """Bilibili video publisher (not yet implemented)."""

    platform_name = "bilibili"

    def __init__(self, sessdata: str | None = None) -> None:
        self._sessdata = sessdata

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
