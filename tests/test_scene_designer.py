"""Tests for scene/environment reference image generation."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from videoclaw.drama.models import DramaScene, DramaSeries, Episode
from videoclaw.drama.scene_designer import SceneDesigner


class _DummyDramaManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.saved_series: DramaSeries | None = None

    async def save_async(self, series: DramaSeries) -> Path:
        self.saved_series = series
        return Path("series.json")


@pytest.mark.asyncio
async def test_design_scenes_retries_transient_image_generation_failure(tmp_path: Path) -> None:
    image_path = tmp_path / "scene.png"
    image_path.write_bytes(b"fake image")

    image_generator = AsyncMock()
    image_generator.last_image_url = "https://example.com/scene.png"
    image_generator.generate = AsyncMock(side_effect=[
        OSError("EndOfStream"),
        image_path,
    ])
    manager = _DummyDramaManager(tmp_path)
    designer = SceneDesigner(image_generator=image_generator, drama_manager=manager)  # type: ignore[arg-type]
    series = DramaSeries(
        series_id="retry-series",
        episodes=[
            Episode(
                number=1,
                scenes=[
                    DramaScene(
                        scene_id="ep01_s01",
                        visual_prompt="Shanghai restaurant interior, warm lights",
                        description="餐厅相亲场景",
                    )
                ],
            )
        ],
    )

    locations = await designer.design_scenes(series)

    assert image_generator.generate.await_count == 2
    assert locations[0].reference_image == str(image_path)
    assert locations[0].reference_image_url == "https://example.com/scene.png"
    assert manager.saved_series is series
