"""Tests for ``claw drama edit-shot`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import typer.testing

from videoclaw.cli._app import app
from videoclaw.drama.models import DramaScene, DramaSeries, Episode

runner = typer.testing.CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_series(
    series_id: str = "test-series",
    episode_num: int = 1,
    scene_ids: list[str] | None = None,
) -> DramaSeries:
    """Build a minimal DramaSeries with one episode and N scenes."""
    if scene_ids is None:
        scene_ids = ["ep01_s01", "ep01_s02", "ep01_s03"]
    scenes = [
        DramaScene(
            scene_id=sid,
            visual_prompt=f"prompt for {sid}",
            enhanced_visual_prompt=f"enhanced prompt for {sid}",
            duration_seconds=5.0,
        )
        for sid in scene_ids
    ]
    ep = Episode(number=episode_num, title="Test Episode", scenes=scenes)
    return DramaSeries(
        series_id=series_id,
        title="Test Series",
        model_id="mock",
        episodes=[ep],
    )


def _patch_load(series: DramaSeries | None = None, raise_not_found: bool = False):
    """Patch DramaManager.load to return *series* or raise FileNotFoundError."""
    if raise_not_found:
        return patch(
            "videoclaw.drama.models.DramaManager",
            return_value=MagicMock(load=MagicMock(side_effect=FileNotFoundError("not found"))),
        )
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")
    return patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock)


# ---------------------------------------------------------------------------
# 1. Series not found
# ---------------------------------------------------------------------------


def test_edit_shot_series_not_found() -> None:
    with _patch_load(raise_not_found=True):
        result = runner.invoke(app, ["drama", "edit-shot", "nonexistent", "-s", "ep01_s01"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


# ---------------------------------------------------------------------------
# 2. Episode not found
# ---------------------------------------------------------------------------


def test_edit_shot_episode_not_found() -> None:
    series = _make_series()
    with _patch_load(series):
        result = runner.invoke(
            app, ["drama", "edit-shot", "test-series", "-s", "ep01_s01", "-e", "99"],
        )
    assert result.exit_code == 1
    assert "episode" in result.stdout.lower() or "not found" in result.stdout.lower()


# ---------------------------------------------------------------------------
# 3. Scene not found — error lists available IDs
# ---------------------------------------------------------------------------


def test_edit_shot_scene_not_found() -> None:
    series = _make_series(scene_ids=["ep01_s01", "ep01_s02"])
    with _patch_load(series):
        result = runner.invoke(app, ["drama", "edit-shot", "test-series", "-s", "ep01_s99"])
    assert result.exit_code == 1
    assert "ep01_s99" in result.stdout
    assert "ep01_s01" in result.stdout
    assert "ep01_s02" in result.stdout


# ---------------------------------------------------------------------------
# 4. Prompt changed → triggers regen
# ---------------------------------------------------------------------------


def test_edit_shot_prompt_changed_triggers_regen() -> None:
    series = _make_series()
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")

    regen_state = MagicMock()
    regen_state.status.value = "completed"
    regen_state.cost_total = 0.05

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock),
        patch("videoclaw.drama.prompt_enhancer.PromptEnhancer") as enh_cls,
        patch("videoclaw.drama.prompt_review.PromptReviewer") as rev_cls,
        patch("videoclaw.drama.runner.DramaRunner") as runner_cls,
    ):
        enh_cls.return_value.enhance_all_scenes = MagicMock()
        rev_cls.return_value.edit_single = MagicMock(return_value="NEW PROMPT TEXT")
        runner_inst = runner_cls.return_value
        runner_inst.regenerate_scene = AsyncMock(return_value=regen_state)

        result = runner.invoke(app, ["drama", "edit-shot", "test-series", "-s", "ep01_s02"])

    assert result.exit_code == 0
    mgr_mock.save.assert_called()
    runner_inst.regenerate_scene.assert_awaited_once()
    call_args = runner_inst.regenerate_scene.call_args
    assert call_args[0][2] == "ep01_s02"  # scene_id
    assert call_args[0][3] is False  # recompose=False


# ---------------------------------------------------------------------------
# 5. No change → skips regen
# ---------------------------------------------------------------------------


def test_edit_shot_no_change_skips_regen() -> None:
    series = _make_series()
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock),
        patch("videoclaw.drama.prompt_enhancer.PromptEnhancer") as enh_cls,
        patch("videoclaw.drama.prompt_review.PromptReviewer") as rev_cls,
        patch("videoclaw.drama.runner.DramaRunner") as runner_cls,
    ):
        enh_cls.return_value.enhance_all_scenes = MagicMock()
        rev_cls.return_value.edit_single = MagicMock(return_value=None)
        runner_inst = runner_cls.return_value
        runner_inst.regenerate_scene = AsyncMock()

        result = runner.invoke(app, ["drama", "edit-shot", "test-series", "-s", "ep01_s01"])

    assert result.exit_code == 0
    runner_inst.regenerate_scene.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. --recompose flag passed through
# ---------------------------------------------------------------------------


def test_edit_shot_recompose_flag_passed() -> None:
    series = _make_series()
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")

    regen_state = MagicMock()
    regen_state.status.value = "completed"
    regen_state.cost_total = 0.05

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock),
        patch("videoclaw.drama.prompt_enhancer.PromptEnhancer") as enh_cls,
        patch("videoclaw.drama.prompt_review.PromptReviewer") as rev_cls,
        patch("videoclaw.drama.runner.DramaRunner") as runner_cls,
    ):
        enh_cls.return_value.enhance_all_scenes = MagicMock()
        rev_cls.return_value.edit_single = MagicMock(return_value="CHANGED")
        runner_inst = runner_cls.return_value
        runner_inst.regenerate_scene = AsyncMock(return_value=regen_state)

        result = runner.invoke(
            app,
            ["drama", "edit-shot", "test-series", "-s", "ep01_s01", "--recompose"],
        )

    assert result.exit_code == 0
    call_args = runner_inst.regenerate_scene.call_args
    assert call_args[0][3] is True  # recompose=True


# ---------------------------------------------------------------------------
# 7. --no-regenerate saves but doesn't regen
# ---------------------------------------------------------------------------


def test_edit_shot_no_regenerate_flag_saves_only() -> None:
    series = _make_series()
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock),
        patch("videoclaw.drama.prompt_enhancer.PromptEnhancer") as enh_cls,
        patch("videoclaw.drama.prompt_review.PromptReviewer") as rev_cls,
        patch("videoclaw.drama.runner.DramaRunner") as runner_cls,
    ):
        enh_cls.return_value.enhance_all_scenes = MagicMock()
        rev_cls.return_value.edit_single = MagicMock(return_value="EDITED PROMPT")
        runner_inst = runner_cls.return_value
        runner_inst.regenerate_scene = AsyncMock()

        result = runner.invoke(
            app,
            ["drama", "edit-shot", "test-series", "-s", "ep01_s01", "--no-regenerate"],
        )

    assert result.exit_code == 0
    mgr_mock.save.assert_called()
    runner_inst.regenerate_scene.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. --json output contains required fields
# ---------------------------------------------------------------------------


def test_edit_shot_json_output() -> None:
    series = _make_series()
    mgr_mock = MagicMock()
    mgr_mock.load.return_value = series
    mgr_mock.save.return_value = Path("/tmp/fake/series.json")

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr_mock),
        patch("videoclaw.drama.prompt_enhancer.PromptEnhancer") as enh_cls,
        patch("videoclaw.drama.prompt_review.PromptReviewer") as rev_cls,
        patch("videoclaw.drama.runner.DramaRunner") as runner_cls,
    ):
        enh_cls.return_value.enhance_all_scenes = MagicMock()
        rev_cls.return_value.edit_single = MagicMock(return_value=None)
        runner_inst = runner_cls.return_value
        runner_inst.regenerate_scene = AsyncMock()

        result = runner.invoke(
            app,
            ["--json", "drama", "edit-shot", "test-series", "-s", "ep01_s01"],
        )

    assert result.exit_code == 0
    data: dict[str, Any] = json.loads(result.stdout)
    assert data["data"]["shot"] == "ep01_s01"
    assert "prompt_changed" in data["data"]
    assert "regenerated" in data["data"]
