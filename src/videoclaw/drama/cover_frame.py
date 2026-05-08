"""Cover frame generator -- produces TikTok thumbnail images for episodes.

Each episode requires a dedicated 3:4 portrait cover frame displayed on
TikTok's feed before the user taps play. This is the primary driver of
click-through rate.

Cover frame spec:
- Dimensions: 3:4 portrait ratio (NOT 9:16)
- Elements: main character face, episode number, series title
- Expression: drama, tension, intrigue -- never neutral
- Appears as frame 1 of video for <=1 second
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from videoclaw.drama.models import DramaManager, DramaSeries
from videoclaw.generation.image_provider import resolve_image_generator

if TYPE_CHECKING:
    from videoclaw.drama.character_designer import ImageGenerator
    from videoclaw.drama.models import Episode

logger = logging.getLogger(__name__)


COVER_FRAME_PROMPT = """\
TikTok drama series cover frame, portrait 3:4 aspect ratio,
dramatic key art for social media thumbnail,
3D CGI character render, Unreal Engine quality, NOT a real photo,

Main character: {character_appearance}
Expression: intense dramatic tension -- NOT neutral, NOT smiling.

Composition:
- Character face fills upper 60% of frame, sharp focus, centered.
- Dark cinematic background with dramatic side lighting.
- Space reserved at bottom third for text overlay.
- All key elements within center safe zone (10% margin from edges).

Text overlay (rendered in the image):
- Top of frame: "EP{episode_number:02d}" in bold white text.
- Below character: "{series_title}" in large bold serif font.

Style: cinematic movie poster, dramatic rim lighting, shallow depth of field.
Quality: highest detail, professional marketing asset, 8K.\
"""


class CoverFrameGenerator:
    """Generates episode cover frames (TikTok thumbnails)."""

    def __init__(
        self,
        image_generator: ImageGenerator | None = None,
        drama_manager: DramaManager | None = None,
        image_provider: str | None = None,
        image_model: str | None = None,
    ) -> None:
        self._img_gen = image_generator
        self._drama_mgr = drama_manager or DramaManager()
        self._image_provider = image_provider
        self._image_model = image_model

    def _ensure_generator(self) -> ImageGenerator:
        if self._img_gen is None:
            self._img_gen = resolve_image_generator(
                image_provider=self._image_provider,
                image_model=self._image_model,
            )
            choices = getattr(self._img_gen, "choices", [])
            logger.info("Using image provider candidates for cover frames: %s", choices)
        return self._img_gen

    async def generate_cover(
        self,
        series: DramaSeries,
        episode: Episode,
        *,
        force: bool = False,
    ) -> Path:
        """Generate a 3:4 cover frame for the episode."""
        if not force and episode.cover_frame_path:
            path = Path(episode.cover_frame_path)
            if path.exists():
                logger.info("Skipping cover frame (already exists): %s", path)
                return path

        gen = self._ensure_generator()
        cover_dir = self._drama_mgr.base_dir / series.series_id / "covers"
        cover_dir.mkdir(parents=True, exist_ok=True)

        prompt = self._build_prompt(series, episode)
        filename = f"ep{episode.number:02d}_cover.png"

        logger.info("Generating cover frame for EP%02d...", episode.number)
        path = await gen.generate(
            prompt,
            output_dir=cover_dir,
            filename=filename,
            size="3:4",
        )

        episode.cover_frame_path = str(path)
        await self._drama_mgr.save_async(series)
        logger.info("Cover frame saved: %s", path)
        return path

    def _build_prompt(self, series: DramaSeries, episode: Episode) -> str:
        """Build the cover frame image generation prompt."""
        # Pick the main character (most frequently appearing, or first)
        main_char = None
        if series.characters:
            if episode.scenes:
                # Count character appearances
                counts: dict[str, int] = {}
                for scene in episode.scenes:
                    for name in scene.characters_present:
                        counts[name] = counts.get(name, 0) + 1
                char_map = {c.name: c for c in series.characters}
                if counts:
                    top_name = max(counts, key=counts.get)  # type: ignore[arg-type]
                    main_char = char_map.get(top_name)
            if main_char is None:
                main_char = series.characters[0]

        appearance = "dramatic character in cinematic lighting"
        if main_char and main_char.visual_prompt:
            # Clean camera language from visual_prompt
            from videoclaw.drama.character_designer import clean_visual_prompt
            appearance = clean_visual_prompt(main_char.visual_prompt)

        return COVER_FRAME_PROMPT.format(
            character_appearance=appearance,
            episode_number=episode.number,
            series_title=series.title,
        )
