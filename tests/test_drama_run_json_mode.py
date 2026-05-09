from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from videoclaw.cli import app
from videoclaw.cli._output import get_output
from videoclaw.drama.models import DramaScene, DramaSeries, Episode, EpisodeStatus


def _reset_output() -> None:
    out = get_output()
    out.json_mode = False
    out._command = ""
    out._result = None
    out._error = None
    out._exit_code = 0


def test_json_drama_run_disables_interactive_review() -> None:
    _reset_output()
    series = DramaSeries(
        series_id="abc123",
        title="Test",
        model_id="mock",
        episodes=[
            Episode(
                number=1,
                title="Ep 1",
                scenes=[DramaScene(scene_id="ep01_s01", visual_prompt="prompt")],
            )
        ],
    )
    mgr = MagicMock()
    mgr.load.return_value = series
    mgr.base_dir = Path("/tmp/video-claw-test")

    async def _mark_completed(*_args, **_kwargs) -> None:
        series.episodes[0].status = EpisodeStatus.COMPLETED

    run_async = AsyncMock(side_effect=_mark_completed)
    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr),
        patch("videoclaw.cli.drama._generate._drama_run_async", run_async),
    ):
        result = CliRunner().invoke(app, ["--json", "drama", "run", "abc123"])

    assert result.exit_code == 0
    _, kwargs = run_async.call_args
    assert kwargs["review"] is False
    assert kwargs["shot_breakpoint"] is False


def test_json_drama_run_returns_error_when_episode_failed() -> None:
    _reset_output()
    series = DramaSeries(
        series_id="abc123",
        title="Test",
        model_id="mock",
        episodes=[
            Episode(
                number=1,
                title="Ep 1",
                scenes=[DramaScene(scene_id="ep01_s01", visual_prompt="prompt")],
            )
        ],
    )
    mgr = MagicMock()
    mgr.load.return_value = series
    mgr.base_dir = Path("/tmp/video-claw-test")

    async def _mark_failed(*_args, **_kwargs) -> None:
        series.episodes[0].status = EpisodeStatus.FAILED

    with (
        patch("videoclaw.drama.models.DramaManager", return_value=mgr),
        patch("videoclaw.cli.drama._generate._drama_run_async", side_effect=_mark_failed),
    ):
        result = CliRunner().invoke(
            app, ["--json", "drama", "run", "abc123", "--episode", "1"]
        )

    assert result.exit_code == 1
    assert '"ok": false' in result.stdout
    assert "Episode generation failed: episode 1" in result.stdout
