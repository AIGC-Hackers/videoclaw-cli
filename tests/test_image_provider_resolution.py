"""Tests for drama image provider resolution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from videoclaw.drama.character_designer import CharacterDesigner
from videoclaw.drama.scene_designer import SceneDesigner
from videoclaw.generation import image_provider as image_provider_module
from videoclaw.generation.image_provider import (
    ImageChoice,
    default_image_candidates,
    resolve_image_generator,
)


def test_default_candidates_prefer_evolink_gpt_image_2_before_byteplus() -> None:
    choices = default_image_candidates()

    assert choices == [
        ImageChoice(provider="evolink", model="gpt-image-2"),
        ImageChoice(provider="byteplus", model="seedream-5.0-lite"),
    ]


def test_explicit_byteplus_tries_byteplus_then_evolink_fallback() -> None:
    choices = default_image_candidates(
        ImageChoice(provider="byteplus", model="seedream-5.0-lite")
    )

    assert choices == [
        ImageChoice(provider="byteplus", model="seedream-5.0-lite"),
        ImageChoice(provider="evolink", model="gpt-image-2"),
    ]


def test_explicit_evolink_gpt_image_2_has_no_silent_fallback() -> None:
    choices = default_image_candidates(
        ImageChoice(provider="evolink", model="gpt-image-2")
    )

    assert choices == [ImageChoice(provider="evolink", model="gpt-image-2")]


def test_resolver_keeps_byteplus_optional_when_no_byteplus_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key=None,
        ),
    )

    generator = resolve_image_generator()

    assert generator.choices == [ImageChoice(provider="evolink", model="gpt-image-2")]


def test_resolver_includes_byteplus_fallback_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key="byteplus-key",
        ),
    )

    generator = resolve_image_generator()

    assert generator.choices == [
        ImageChoice(provider="evolink", model="gpt-image-2"),
        ImageChoice(provider="byteplus", model="seedream-5.0-lite"),
    ]


def test_resolver_honors_configured_default_provider_before_evolink(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key="byteplus-key",
            default_image_provider="byteplus",
            default_image_model="seedream-5.0-lite",
        ),
    )

    generator = resolve_image_generator()

    assert generator.choices == [
        ImageChoice(provider="byteplus", model="seedream-5.0-lite"),
        ImageChoice(provider="evolink", model="gpt-image-2"),
    ]


def test_resolver_uses_provider_default_when_only_provider_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key="byteplus-key",
            default_image_provider="byteplus",
            default_image_model="gpt-image-2",
        ),
    )

    generator = resolve_image_generator()

    assert generator.choices[0] == ImageChoice(
        provider="byteplus",
        model="seedream-5.0-lite",
    )


def test_character_designer_without_injected_generator_uses_resolver(monkeypatch) -> None:
    resolved = MagicMock()

    monkeypatch.setattr(
        "videoclaw.drama.character_designer.resolve_image_generator",
        lambda **kwargs: resolved,
    )

    designer = CharacterDesigner(image_provider="byteplus", image_model="seedream-5.0-lite")

    assert designer._ensure_generator() is resolved


def test_scene_designer_without_injected_generator_uses_resolver(monkeypatch) -> None:
    resolved = MagicMock()

    monkeypatch.setattr(
        "videoclaw.drama.scene_designer.resolve_image_generator",
        lambda **kwargs: resolved,
    )

    designer = SceneDesigner(image_provider="byteplus", image_model="seedream-5.0-lite")

    assert designer._ensure_generator() is resolved


def test_injected_generators_are_preserved() -> None:
    injected = MagicMock()

    assert CharacterDesigner(image_generator=injected)._ensure_generator() is injected
    assert SceneDesigner(image_generator=injected)._ensure_generator() is injected


@pytest.mark.asyncio
async def test_explicit_byteplus_generation_falls_back_to_evolink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "image.png"
    output_path.write_bytes(b"image")
    byteplus = MagicMock()
    byteplus.generate = AsyncMock(side_effect=RuntimeError("byteplus failed"))
    evolink = MagicMock()
    evolink.last_image_url = "https://example.com/image.png"
    evolink.generate = AsyncMock(return_value=output_path)

    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key="byteplus-key",
        ),
    )
    monkeypatch.setattr(
        image_provider_module,
        "_build_generator",
        lambda choice: byteplus if choice.provider == "byteplus" else evolink,
    )

    generator = resolve_image_generator(
        image_provider="byteplus",
        image_model="seedream-5.0-lite",
    )

    result = await generator.generate(
        "prompt",
        output_dir=tmp_path,
        filename="image.png",
        size="3:4",
    )

    assert result == output_path
    byteplus.generate.assert_awaited_once()
    evolink.generate.assert_awaited_once()
    assert evolink.generate.await_args.kwargs["model"] == "gpt-image-2"
    assert generator.last_image_url == "https://example.com/image.png"


@pytest.mark.asyncio
async def test_explicit_evolink_generation_failure_does_not_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    evolink = MagicMock()
    evolink.generate = AsyncMock(side_effect=RuntimeError("evolink failed"))

    monkeypatch.setattr(
        "videoclaw.generation.image_provider.get_config",
        lambda: SimpleNamespace(
            evolink_api_key="evolink-key",
            byteplus_api_key="byteplus-key",
        ),
    )
    monkeypatch.setattr(
        image_provider_module,
        "_build_generator",
        lambda choice: evolink,
    )

    generator = resolve_image_generator(
        image_provider="evolink",
        image_model="gpt-image-2",
    )

    with pytest.raises(RuntimeError, match="evolink failed"):
        await generator.generate(
            "prompt",
            output_dir=tmp_path,
            filename="image.png",
        )

    assert generator.choices == [ImageChoice(provider="evolink", model="gpt-image-2")]
    evolink.generate.assert_awaited_once()
