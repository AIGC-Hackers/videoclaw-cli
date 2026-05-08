"""Tests for cover frame generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from videoclaw.drama.cover_frame import COVER_FRAME_PROMPT, CoverFrameGenerator
from videoclaw.drama.models import Character, DramaScene, DramaSeries, Episode, ShotScale


def _make_series() -> DramaSeries:
    return DramaSeries(
        title="Test Drama",
        genre="drama",
        synopsis="A test drama for cover frame generation.",
        language="en",
        characters=[
            Character(
                name="Hero",
                description="A brave hero who secretly harbours doubt",
                visual_prompt="Tall man, dark hair, sharp jaw, tailored suit",
            ),
        ],
    )

def _make_episode() -> Episode:
    return Episode(
        number=1,
        title="Pilot",
        opening_hook="A shocking discovery",
        scenes=[
            DramaScene(
                scene_id="s01",
                description="Hero enters",
                visual_prompt="Man walking into room",
                shot_scale=ShotScale.CLOSE_UP,
                characters_present=["Hero"],
            ),
        ],
    )


class TestCoverFrameGenerator:

    def test_build_prompt_contains_series_title(self):
        gen = CoverFrameGenerator()
        series = _make_series()
        ep = _make_episode()
        prompt = gen._build_prompt(series, ep)
        assert "Test Drama" in prompt

    def test_build_prompt_contains_episode_number(self):
        gen = CoverFrameGenerator()
        series = _make_series()
        ep = _make_episode()
        prompt = gen._build_prompt(series, ep)
        assert "EP01" in prompt

    def test_build_prompt_contains_character(self):
        gen = CoverFrameGenerator()
        series = _make_series()
        ep = _make_episode()
        prompt = gen._build_prompt(series, ep)
        assert "Tall man" in prompt or "dark hair" in prompt

    def test_build_prompt_3_4_aspect(self):
        """The prompt template specifies 3:4 portrait."""
        assert "3:4" in COVER_FRAME_PROMPT

    def test_without_injected_generator_uses_image_provider_resolver(self, monkeypatch):
        resolved = MagicMock()
        resolver = MagicMock(return_value=resolved)
        fallback = MagicMock()

        monkeypatch.setattr(
            "videoclaw.drama.cover_frame.resolve_image_generator",
            resolver,
            raising=False,
        )
        monkeypatch.setattr(
            "videoclaw.config.get_config",
            lambda: MagicMock(byteplus_api_key=None, evolink_api_key="evolink-key"),
        )
        monkeypatch.setattr(
            "videoclaw.generation.evolink_image.EvolinkImageGenerator",
            lambda: fallback,
        )

        assert CoverFrameGenerator()._ensure_generator() is resolved
        resolver.assert_called_once_with(image_provider=None, image_model=None)

    @pytest.mark.asyncio
    async def test_generate_cover_calls_generator(self, tmp_path):
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=tmp_path / "cover.png")
        mock_mgr = MagicMock()
        mock_mgr.base_dir = tmp_path
        mock_mgr.save_async = AsyncMock()

        gen = CoverFrameGenerator(image_generator=mock_gen, drama_manager=mock_mgr)
        series = _make_series()
        ep = _make_episode()

        await gen.generate_cover(series, ep)
        mock_gen.generate.assert_called_once()
        call_kwargs = mock_gen.generate.call_args
        assert call_kwargs.kwargs.get("size") == "3:4"

    @pytest.mark.asyncio
    async def test_skip_when_cover_exists(self, tmp_path):
        existing = tmp_path / "existing_cover.png"
        existing.write_text("fake image")

        mock_gen = AsyncMock()
        mock_mgr = MagicMock()
        mock_mgr.base_dir = tmp_path

        gen = CoverFrameGenerator(image_generator=mock_gen, drama_manager=mock_mgr)
        series = _make_series()
        ep = _make_episode()
        ep.cover_frame_path = str(existing)

        result = await gen.generate_cover(series, ep)
        assert result == existing
        mock_gen.generate.assert_not_called()
