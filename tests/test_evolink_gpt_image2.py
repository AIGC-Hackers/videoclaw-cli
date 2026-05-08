from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from videoclaw.config import get_config
from videoclaw.generation import evolink_image
from videoclaw.generation.evolink_image import EvolinkImageGenerator


def test_config_exposes_evolink_gpt_image2_defaults(monkeypatch):
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_IMAGE_PROVIDER", raising=False)
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_IMAGE_RESOLUTION", raising=False)
    monkeypatch.delenv("VIDEOCLAW_DEFAULT_IMAGE_QUALITY", raising=False)
    get_config.cache_clear()

    try:
        cfg = get_config()

        assert cfg.default_image_provider == "evolink"
        assert cfg.default_image_model == "gpt-image-2"
        assert cfg.default_image_resolution == "1K"
        assert cfg.default_image_quality == "medium"
    finally:
        get_config.cache_clear()


@pytest.mark.asyncio
async def test_evolink_gpt_image2_payload_polls_and_downloads(
    tmp_path: Path,
    monkeypatch,
):
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class FakeResponse:
        def __init__(
            self,
            *,
            status_code: int = 200,
            json_data: dict[str, Any] | None = None,
            content: bytes = b"",
        ) -> None:
            self.status_code = status_code
            self._json_data = json_data or {}
            self.content = content
            self.text = str(self._json_data)

        def json(self) -> dict[str, Any]:
            return self._json_data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise AssertionError(f"unexpected status {self.status_code}")

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> FakeResponse:
            calls.append(("POST", url, json))
            return FakeResponse(json_data={"task_id": "task-123"})

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            timeout: float | None = None,
        ) -> FakeResponse:
            calls.append(("GET", url, None))
            if url.endswith("/tasks/task-123"):
                return FakeResponse(
                    json_data={
                        "status": "completed",
                        "results": ["https://cdn.example.com/result.png"],
                    }
                )
            if url == "https://cdn.example.com/result.png":
                return FakeResponse(content=b"png-bytes")
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(evolink_image.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(EvolinkImageGenerator, "_poll_interval", 0.0)

    generator = EvolinkImageGenerator(
        api_key="test-key",
        api_base="https://api.evolink.test/v1",
    )

    output_path = await generator.generate(
        "cinematic character sheet",
        output_dir=tmp_path,
        reference_urls=["https://cdn.example.com/ref.png"],
    )

    assert output_path == tmp_path / "image.png"
    assert output_path.read_bytes() == b"png-bytes"
    assert generator.last_image_url == "https://cdn.example.com/result.png"

    assert calls[0] == (
        "POST",
        "https://api.evolink.test/v1/images/generations",
        {
            "model": "gpt-image-2",
            "prompt": "cinematic character sheet",
            "size": "3:4",
            "resolution": "1K",
            "quality": "medium",
            "n": 1,
            "image_urls": ["https://cdn.example.com/ref.png"],
        },
    )
    assert calls[1] == ("GET", "https://api.evolink.test/v1/tasks/task-123", None)
    assert calls[2] == ("GET", "https://cdn.example.com/result.png", None)


@pytest.mark.asyncio
async def test_evolink_gpt_image2_accepts_image_urls_alias(
    tmp_path: Path,
    monkeypatch,
):
    payloads: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 200
        content = b"png-bytes"
        text = "{}"

        def __init__(self, json_data: dict[str, Any] | None = None) -> None:
            self._json_data = json_data or {}

        def json(self) -> dict[str, Any]:
            return self._json_data

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> FakeResponse:
            payloads.append(json)
            return FakeResponse(json_data={"data": [{"url": "https://cdn.example.com/result.png"}]})

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            timeout: float | None = None,
        ) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(evolink_image.httpx, "AsyncClient", FakeAsyncClient)

    generator = EvolinkImageGenerator(
        api_key="test-key",
        api_base="https://api.evolink.test/v1",
    )

    await generator.generate(
        "edit this reference",
        output_dir=tmp_path,
        image_urls=["https://cdn.example.com/ref.png"],
    )

    assert payloads[0]["image_urls"] == ["https://cdn.example.com/ref.png"]
