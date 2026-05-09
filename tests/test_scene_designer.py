"""Tests for scene/environment reference image generation."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from videoclaw.drama.models import DramaScene, DramaSeries, Episode, ShotScale, ShotType
from videoclaw.drama.scene_designer import SceneDesigner, extract_locations, extract_props


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


def test_extract_locations_prefers_establishing_shot_for_scene_group() -> None:
    """Close-up/detail prompts should not become the location reference anchor."""
    episode = Episode(
        number=1,
        scenes=[
            DramaScene(
                scene_id="ep01_s01",
                description="咖啡馆内，苏念念发现桌上的合约。",
                visual_prompt="Close-up of a contract folder on a cafe table, shallow depth of field",
                scene_group="A",
                shot_scale=ShotScale.CLOSE_UP,
                shot_type=ShotType.DETAIL,
                time_of_day="day",
            ),
            DramaScene(
                scene_id="ep01_s02",
                description="咖啡馆内，苏念念和陆北辰对峙。",
                visual_prompt="Cozy cafe interior with round tables and warm window light, empty scene",
                scene_group="A",
                shot_scale=ShotScale.WIDE,
                shot_type=ShotType.ESTABLISHING,
                time_of_day="day",
            ),
        ],
    )

    locations = extract_locations([episode])

    assert len(locations) == 1
    assert locations[0].name == "cozy_cafe_interior_with_round_tables_and_warm_window_light"
    assert "wide" in locations[0].description
    assert "day" in locations[0].description


def test_extract_props_includes_single_detail_shot_objects() -> None:
    """A one-off object in a detail shot still needs a prop reference asset."""
    episode = Episode(
        number=1,
        scenes=[
            DramaScene(
                scene_id="ep01_s01",
                description="特写：桌上的合约文件夹露出关键签名。",
                visual_prompt="Close-up of a red contract folder with a visible signature on a cafe table",
                shot_scale=ShotScale.CLOSE_UP,
                shot_type=ShotType.DETAIL,
            )
        ],
    )

    props = extract_props([episode])

    assert [p.name for p in props] == ["folder"]
    assert props[0].scenes_used == ["ep01_s01"]
