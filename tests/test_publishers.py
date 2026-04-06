"""Tests for TikTok and YouTube publishers (P3#11 and P3#12)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videoclaw.publishers.base import PublishRequest, PublishResult, PublishStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_video(tmp_path: Path, name: str = "video.mp4") -> Path:
    """Create a small fake video file for testing."""
    p = tmp_path / name
    p.write_bytes(b"FAKE_VIDEO_DATA" * 100)
    return p


def _make_request(video_path: Path) -> PublishRequest:
    return PublishRequest(
        video_path=video_path,
        title="Satan in a Suit EP01",
        description="AI drama test upload",
        tags=["drama", "AI"],
    )


# ---------------------------------------------------------------------------
# TikTok Publisher
# ---------------------------------------------------------------------------


class TestTikTokPublisher:
    @pytest.mark.asyncio
    async def test_health_check_false_without_token(self):
        """health_check() returns False when no token configured."""
        from videoclaw.publishers.tiktok import TikTokPublisher

        pub = TikTokPublisher(access_token=None)
        assert await pub.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_true_with_token(self):
        from videoclaw.publishers.tiktok import TikTokPublisher

        pub = TikTokPublisher(access_token="fake-token")
        assert await pub.health_check() is True

    @pytest.mark.asyncio
    async def test_publish_fails_without_token(self, tmp_path: Path):
        """publish() returns FAILED when no access token is set."""
        from videoclaw.publishers.tiktok import TikTokPublisher

        pub = TikTokPublisher(access_token=None)
        req = _make_request(_make_video(tmp_path))
        result = await pub.publish(req)

        assert result.status == PublishStatus.FAILED
        assert "access token" in result.error.lower()

    @pytest.mark.asyncio
    async def test_publish_fails_if_video_missing(self, tmp_path: Path):
        """publish() returns FAILED when video file does not exist."""
        from videoclaw.publishers.tiktok import TikTokPublisher

        pub = TikTokPublisher(access_token="tok")
        req = PublishRequest(
            video_path=tmp_path / "nonexistent.mp4",
            title="Test",
        )
        result = await pub.publish(req)
        assert result.status == PublishStatus.FAILED
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_publish_success_flow(self, tmp_path: Path):
        """publish() returns PROCESSING with publish_id on successful init."""
        from videoclaw.publishers.tiktok import TikTokPublisher

        video = _make_video(tmp_path)
        pub = TikTokPublisher(access_token="tok")

        # Mock the two HTTP calls: init and status
        init_resp = MagicMock()
        init_resp.raise_for_status = MagicMock()
        init_resp.json.return_value = {"data": {"publish_id": "pub-123", "upload_url": None}}

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {"data": {"upload_url": None}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=init_resp)
        mock_client.get = AsyncMock(return_value=status_resp)

        with patch("videoclaw.publishers.tiktok.httpx.AsyncClient", return_value=mock_client):
            result = await pub.publish(_make_request(video))

        assert result.status == PublishStatus.PROCESSING
        assert result.platform_id == "pub-123"
        assert result.platform == "tiktok"

    @pytest.mark.asyncio
    async def test_publish_handles_http_error(self, tmp_path: Path):
        """publish() wraps HTTPStatusError as FAILED result."""
        import httpx
        from videoclaw.publishers.tiktok import TikTokPublisher

        video = _make_video(tmp_path)
        pub = TikTokPublisher(access_token="tok")

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
        )

        with patch("videoclaw.publishers.tiktok.httpx.AsyncClient", return_value=mock_client):
            result = await pub.publish(_make_request(video))

        assert result.status == PublishStatus.FAILED
        assert "401" in result.error

    @pytest.mark.asyncio
    async def test_get_status_published(self):
        """get_status() maps PUBLISH_COMPLETE → PUBLISHED."""
        from videoclaw.publishers.tiktok import TikTokPublisher

        pub = TikTokPublisher(access_token="tok")

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {
            "data": {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": ["vid-456"],
            }
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=status_resp)

        with patch("videoclaw.publishers.tiktok.httpx.AsyncClient", return_value=mock_client):
            result = await pub.get_status("pub-123")

        assert result.status == PublishStatus.PUBLISHED
        assert "tiktok.com/video/vid-456" in result.url


# ---------------------------------------------------------------------------
# YouTube Publisher
# ---------------------------------------------------------------------------


class TestYouTubePublisher:
    @pytest.mark.asyncio
    async def test_health_check_false_without_token(self):
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token=None)
        assert await pub.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_true_with_token(self):
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token="ya29.fake")
        assert await pub.health_check() is True

    @pytest.mark.asyncio
    async def test_publish_fails_without_token(self, tmp_path: Path):
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token=None)
        result = await pub.publish(_make_request(_make_video(tmp_path)))

        assert result.status == PublishStatus.FAILED
        assert "access token" in result.error.lower()

    @pytest.mark.asyncio
    async def test_publish_fails_if_video_missing(self, tmp_path: Path):
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token="tok")
        req = PublishRequest(video_path=tmp_path / "nope.mp4", title="Test")
        result = await pub.publish(req)
        assert result.status == PublishStatus.FAILED
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_publish_success_flow(self, tmp_path: Path):
        """publish() returns PROCESSING with video_id after successful chunked upload."""
        from videoclaw.publishers.youtube import YouTubePublisher

        video = _make_video(tmp_path)
        pub = YouTubePublisher(access_token="ya29.tok")

        # Init response: returns Location header
        init_resp = MagicMock()
        init_resp.status_code = 200
        init_resp.raise_for_status = MagicMock()
        init_resp.headers = {"Location": "https://upload.googleapis.com/session/abc123"}

        # Upload response: 200 complete with video id
        upload_resp = MagicMock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = {"id": "yt-video-001"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=init_resp)
        mock_client.put = AsyncMock(return_value=upload_resp)

        with patch("videoclaw.publishers.youtube.httpx.AsyncClient", return_value=mock_client):
            result = await pub.publish(_make_request(video))

        assert result.status == PublishStatus.PROCESSING
        assert result.platform_id == "yt-video-001"
        assert "youtube.com/watch?v=yt-video-001" in result.url

    @pytest.mark.asyncio
    async def test_get_status_processed(self):
        """get_status() maps uploadStatus=processed → PUBLISHED."""
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token="tok")

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {
            "items": [{
                "id": "yt-001",
                "status": {"uploadStatus": "processed", "privacyStatus": "public"},
            }]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=status_resp)

        with patch("videoclaw.publishers.youtube.httpx.AsyncClient", return_value=mock_client):
            result = await pub.get_status("yt-001")

        assert result.status == PublishStatus.PUBLISHED
        assert "watch?v=yt-001" in result.url

    @pytest.mark.asyncio
    async def test_get_status_not_found(self):
        """get_status() returns FAILED when video id not found."""
        from videoclaw.publishers.youtube import YouTubePublisher

        pub = YouTubePublisher(access_token="tok")

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {"items": []}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=status_resp)

        with patch("videoclaw.publishers.youtube.httpx.AsyncClient", return_value=mock_client):
            result = await pub.get_status("nonexistent")

        assert result.status == PublishStatus.FAILED

    def test_platform_names(self):
        from videoclaw.publishers.tiktok import TikTokPublisher
        from videoclaw.publishers.youtube import YouTubePublisher

        assert TikTokPublisher().platform_name == "tiktok"
        assert YouTubePublisher().platform_name == "youtube"
