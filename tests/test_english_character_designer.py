"""Tests for locale-aware character image prompt generation (B4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from videoclaw.drama.character_designer import (
    CHARACTER_IMAGE_PROMPT,
    CHARACTER_IMAGE_PROMPT_SINGLE,
    CharacterDesigner,
    sanitize_for_image_api,
)
from videoclaw.drama.models import Character, DramaManager, DramaSeries


def _make_series(language: str) -> DramaSeries:
    series = DramaSeries(
        series_id="test_series",
        title="Test Drama",
        language=language,
        style="cinematic",
    )
    series.characters = [
        Character(
            name="Alice",
            visual_prompt="Tall woman with brown hair, wearing a red coat",
        )
    ]
    return series


@pytest.fixture
def mock_drama_manager(tmp_path):
    mgr = MagicMock(spec=DramaManager)
    mgr.base_dir = tmp_path
    mgr.save = MagicMock()
    return mgr


@pytest.fixture
def mock_image_generator():
    gen = MagicMock()
    gen.generate = AsyncMock(return_value=Path("/tmp/alice.png"))
    return gen


@pytest.mark.asyncio
async def test_english_series_gets_3d_cgi_turnaround_prompt(mock_image_generator, mock_drama_manager):
    """English series generates a 3D CGI turnaround sheet prompt."""
    designer = CharacterDesigner(
        image_generator=mock_image_generator,
        drama_manager=mock_drama_manager,
    )
    series = _make_series("en")

    await designer.design_characters(series)

    assert mock_image_generator.generate.called
    call_args = mock_image_generator.generate.call_args
    prompt = call_args[0][0]  # first positional arg

    # Turnaround sheet format: 3D CGI, Unreal Engine, MetaHuman
    assert "3D CGI" in prompt
    assert "Unreal Engine" in prompt
    assert "MetaHuman" in prompt
    assert "cinematic" in prompt.lower()
    # Three-panel layout
    assert "front view" in prompt
    assert "back view" in prompt


@pytest.mark.asyncio
async def test_chinese_series_gets_3d_cgi_turnaround_prompt(mock_image_generator, mock_drama_manager):
    """Chinese series also generates a 3D CGI turnaround sheet prompt."""
    designer = CharacterDesigner(
        image_generator=mock_image_generator,
        drama_manager=mock_drama_manager,
    )
    series = _make_series("zh")

    await designer.design_characters(series)

    assert mock_image_generator.generate.called
    call_args = mock_image_generator.generate.call_args
    prompt = call_args[0][0]

    # Same 3D CGI turnaround format for both languages
    assert "3D CGI" in prompt
    assert "Unreal Engine" in prompt
    assert "cinematic" in prompt.lower()


@pytest.mark.asyncio
async def test_prompt_contains_appearance(mock_image_generator, mock_drama_manager):
    """The character appearance text appears in the generated prompt."""
    designer = CharacterDesigner(
        image_generator=mock_image_generator,
        drama_manager=mock_drama_manager,
    )
    series = _make_series("en")

    await designer.design_characters(series)

    prompt = mock_image_generator.generate.call_args[0][0]
    assert "brown hair" in prompt
    assert "red coat" in prompt


@pytest.mark.asyncio
async def test_character_image_prompt_uses_style_line_placeholder():
    """CHARACTER_IMAGE_PROMPT template uses {style_line} not {style}."""
    assert "{style_line}" in CHARACTER_IMAGE_PROMPT
    assert "{style_line}" in CHARACTER_IMAGE_PROMPT_SINGLE
    assert "{style} Chinese drama" not in CHARACTER_IMAGE_PROMPT


@pytest.mark.asyncio
async def test_skips_character_with_existing_image(mock_image_generator, mock_drama_manager):
    """Characters with existing reference_image are skipped."""
    designer = CharacterDesigner(
        image_generator=mock_image_generator,
        drama_manager=mock_drama_manager,
    )
    series = _make_series("en")
    series.characters[0].reference_image = "/existing/path.png"
    series.characters[0].reference_images = ["/existing/front.png", "/existing/3q.png", "/existing/full.png"]

    await designer.design_characters(series)

    mock_image_generator.generate.assert_not_called()


# ---------------------------------------------------------------------------
# sanitize_for_image_api — content-filter safe prompts
# ---------------------------------------------------------------------------


def test_sanitize_strips_sharp_jawline():
    """Colton-style photorealistic male descriptors are stripped."""
    raw = (
        "Tall imposing man, 30, dark hair slicked back, sharp jawline, "
        "high-bridged nose, piercing ice-cold eyes."
    )
    result = sanitize_for_image_api(raw)
    assert "sharp jawline" not in result
    assert "high-bridged nose" not in result
    assert "piercing" not in result
    # Non-risky parts preserved
    assert "Tall imposing man" in result
    assert "30" in result
    assert "dark hair slicked back" in result


def test_sanitize_strips_sexualized_female_descriptors():
    """Chloe-style sexualised female descriptors are stripped."""
    raw = (
        "Young woman, 28, short sleek stylish hair, heavy glamorous makeup "
        "with bold lips, wearing a sexy strappy designer outfit. "
        "Expressive face, heiress energy."
    )
    result = sanitize_for_image_api(raw)
    assert "sexy" not in result.lower()
    assert "bold lips" not in result
    assert "heavy glamorous makeup" not in result
    assert "expressive face" not in result.lower()
    # Non-risky parts preserved
    assert "28" in result
    assert "stylish hair" in result
    assert "strappy designer outfit" in result
    assert "heiress energy" in result


def test_sanitize_preserves_wholesome_descriptors():
    """Ivy-style wholesome descriptors pass through unchanged."""
    raw = (
        "Young woman, 26, blonde hair, sun-kissed skin, bright expressive "
        "eyes, athletic build, natural beauty, minimal makeup."
    )
    result = sanitize_for_image_api(raw)
    assert "26" in result
    assert "blonde hair" in result
    assert "sun-kissed skin" in result
    assert "athletic build" in result
    assert "natural beauty" in result


def test_sanitize_cleans_double_commas():
    """After removing descriptors, punctuation artifacts are cleaned up."""
    raw = "Woman, sharp jawline, stylish hair, bold lips, tall."
    result = sanitize_for_image_api(raw)
    assert ", ," not in result
    assert "  " not in result
    assert "stylish hair" in result
