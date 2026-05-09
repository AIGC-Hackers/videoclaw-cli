"""Tests for SeedanceVideoAdapter — persistent HTTP client and core behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from videoclaw.models.adapters.seedance import SeedanceVideoAdapter


class TestSeedancePersistentClient:
    """P1#5: adapter must reuse a single AsyncClient across requests."""

    def _make_adapter(self, api_key: str = "test-key") -> SeedanceVideoAdapter:
        from videoclaw.models.adapters.seedance import SeedanceVideoAdapter
        return SeedanceVideoAdapter(api_key=api_key)

    def test_client_is_none_before_first_use(self):
        """_http_client must start as None (lazy init)."""
        adapter = self._make_adapter()
        assert adapter._http_client is None

    def test_client_created_on_first_call(self):
        """_client() must create and cache an AsyncClient on first invocation."""
        import httpx
        adapter = self._make_adapter()
        client = adapter._client()
        assert isinstance(client, httpx.AsyncClient)
        assert adapter._http_client is client

    def test_client_reused_on_subsequent_calls(self):
        """_client() must return the exact same instance every time."""
        adapter = self._make_adapter()
        c1 = adapter._client()
        c2 = adapter._client()
        assert c1 is c2

    def test_separate_adapters_have_independent_clients(self):
        """Two adapter instances must not share their HTTP client."""
        adapter_a = self._make_adapter()
        adapter_b = self._make_adapter()
        c_a = adapter_a._client()
        c_b = adapter_b._client()
        assert c_a is not c_b


class TestSeedanceAdapterProperties:
    """Basic property smoke tests."""

    def _make_adapter(self) -> SeedanceVideoAdapter:
        from videoclaw.models.adapters.seedance import SeedanceVideoAdapter
        return SeedanceVideoAdapter(api_key="test-key")

    def test_model_id(self):
        assert self._make_adapter().model_id == "seedance-2.0"

    def test_capabilities_include_video(self):
        from videoclaw.models.protocol import ModelCapability
        caps = self._make_adapter().capabilities
        assert ModelCapability.TEXT_TO_VIDEO in caps

    def test_execution_mode_is_cloud(self):
        from videoclaw.models.protocol import ExecutionMode
        assert self._make_adapter().execution_mode == ExecutionMode.CLOUD

    def test_poll_timeout_can_be_overridden_by_env(self, monkeypatch):
        from videoclaw.models.adapters.seedance import _poll_timeout_s

        monkeypatch.setenv("VIDEOCLAW_VIDEO_POLL_TIMEOUT_S", "0")
        assert _poll_timeout_s() == 0.0

    def test_invalid_poll_timeout_uses_default(self, monkeypatch):
        from videoclaw.models.adapters.seedance import (
            _POLL_TIMEOUT_S,
            _poll_timeout_s,
        )

        monkeypatch.setenv("VIDEOCLAW_VIDEO_POLL_TIMEOUT_S", "not-a-number")
        assert _poll_timeout_s() == _POLL_TIMEOUT_S


class TestSeedanceContentBuilder:
    def _make_adapter(self) -> SeedanceVideoAdapter:
        from videoclaw.models.adapters.seedance import SeedanceVideoAdapter
        return SeedanceVideoAdapter(api_key="test-key")

    def test_prompt_segments_are_flattened_to_single_text_content(self):
        from videoclaw.drama.prompt_segments import PromptSegment, ReferenceMedia
        from videoclaw.models.protocol import GenerationRequest

        request = GenerationRequest(
            prompt="unused when prompt_segments exist",
            extra={
                "prompt_segments": [
                    PromptSegment(
                        text="Character A enters.",
                        reference=ReferenceMedia(
                            ref_type="character",
                            key="A",
                            url="https://example.com/a.png",
                        ),
                    ),
                    PromptSegment(
                        text="Character B reacts.",
                        reference=ReferenceMedia(
                            ref_type="character",
                            key="B",
                            url="https://example.com/b.png",
                        ),
                    ),
                    PromptSegment(text="They face the contract."),
                ],
            },
        )

        content = self._make_adapter()._build_content(request)

        text_entries = [item for item in content if item["type"] == "text"]
        image_entries = [item for item in content if item["type"] == "image_url"]
        assert len(text_entries) == 1
        assert text_entries[0]["text"] == (
            "Character A enters. Character B reacts. They face the contract."
        )
        assert [item["image_url"]["url"] for item in image_entries] == [
            "https://example.com/a.png",
            "https://example.com/b.png",
        ]

    def test_reference_audio_requires_media_reference(self):
        from videoclaw.models.protocol import GenerationRequest

        request = GenerationRequest(
            prompt="Character speaks with a voice reference.",
            extra={
                "reference_audios": [
                    {"url": "https://example.com/voice.mp3"},
                ],
            },
        )

        content = self._make_adapter()._build_content(request)

        assert not [item for item in content if item["type"] == "audio_url"]

    def test_reference_audio_rejects_non_http_urls(self):
        from videoclaw.models.protocol import GenerationRequest

        request = GenerationRequest(
            prompt="Character speaks with a voice reference.",
            extra={
                "image_urls": [
                    {"url": "https://example.com/character.png", "role": "reference_image"},
                ],
                "reference_audios": [
                    {"url": "/tmp/voice.mp3"},
                    {"url": "https://example.com/voice.mp3"},
                ],
            },
        )

        content = self._make_adapter()._build_content(request)
        audio_urls = [
            item["audio_url"]["url"]
            for item in content
            if item["type"] == "audio_url"
        ]

        assert audio_urls == ["https://example.com/voice.mp3"]

    def test_reference_video_rejects_non_http_urls(self):
        from videoclaw.models.protocol import GenerationRequest

        request = GenerationRequest(
            prompt="Use this motion reference.",
            extra={
                "reference_videos": [
                    {"url": "file:///tmp/reference.mp4"},
                    {"url": "https://example.com/reference.mp4"},
                ],
            },
        )

        content = self._make_adapter()._build_content(request)
        video_urls = [
            item["video_url"]["url"]
            for item in content
            if item["type"] == "video_url"
        ]

        assert video_urls == ["https://example.com/reference.mp4"]

    def test_payload_generates_audio_by_default(self):
        from videoclaw.models.protocol import GenerationRequest

        payload = self._make_adapter()._build_payload(
            GenerationRequest(prompt="Dialogue line.", duration_seconds=6)
        )

        assert payload["generate_audio"] is True

    @pytest.mark.asyncio
    async def test_download_video_follows_redirects(self, monkeypatch):
        adapter = self._make_adapter()

        class FakeResponse:
            content = b"mp4-bytes"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self):
                self.follow_redirects = None

            async def get(self, url, *, follow_redirects=False):
                self.follow_redirects = follow_redirects
                return FakeResponse()

        client = FakeClient()
        monkeypatch.setattr(adapter, "_client", lambda: client)

        assert await adapter._download_video("https://example.com/video.mp4") == b"mp4-bytes"
        assert client.follow_redirects is True

    @pytest.mark.asyncio
    async def test_generate_retries_without_reference_images_on_privacy_filter(
        self,
        monkeypatch,
    ):
        from videoclaw.drama.prompt_segments import PromptSegment, ReferenceMedia
        from videoclaw.models.protocol import GenerationRequest

        adapter = self._make_adapter()
        submitted = []

        async def fake_create_task(request):
            submitted.append(request)
            return f"task-{len(submitted)}"

        async def fake_poll(task_id):
            if task_id == "task-1":
                raise RuntimeError(
                    "Seedance generation failed: "
                    "InputImageSensitiveContentDetected.PrivacyInformation"
                )
            return "https://example.com/video.mp4"

        async def fake_download(url):
            return b"mp4-bytes"

        monkeypatch.setattr(adapter, "_create_task", fake_create_task)
        monkeypatch.setattr(adapter, "_poll_until_done", fake_poll)
        monkeypatch.setattr(adapter, "_download_video", fake_download)

        request = GenerationRequest(
            prompt="Hero enters [ref:hero]",
            reference_image=b"image-bytes",
            extra={
                "image_urls": [
                    {"url": "https://example.com/hero.png", "role": "reference_image"},
                ],
                "prompt_segments": [
                    PromptSegment(
                        text="Hero enters",
                        reference=ReferenceMedia(
                            ref_type="character",
                            key="hero",
                            url="https://example.com/hero.png",
                        ),
                    ),
                ],
            },
        )

        result = await adapter.generate(request)

        assert result.video_data == b"mp4-bytes"
        assert len(submitted) == 2
        fallback = submitted[1]
        assert fallback.reference_image is None
        assert "image_urls" not in fallback.extra
        assert "prompt_segments" not in fallback.extra
        assert "[ref:" not in fallback.prompt
