"""Tests for shot-level incremental review directory updates + --shot-breakpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videoclaw.drama.checkpoint import (
    CheckpointManager,
    _scene_slug,
    review_dir_for_episode,
)
from videoclaw.drama.models import DramaScene, DramaSeries, Episode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_series(tmp_path: Path) -> DramaSeries:
    """Minimal DramaSeries with one episode and two scenes."""
    series = DramaSeries(
        series_id="test_series_001",
        title="Test Drama",
        model_id="mock",
        aspect_ratio="9:16",
    )
    ep = Episode(number=1, title="Pilot")
    ep.scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="Poolside arrival",
            duration_seconds=5.0,
        ),
        DramaScene(
            scene_id="ep01_s02",
            description="Rooftop confrontation",
            duration_seconds=5.0,
        ),
    ]
    series.episodes = [ep]
    return series


def _setup_video_src(tmp_path: Path) -> Path:
    """Create a fake video file and return its path."""
    src = tmp_path / "projects" / "shots" / "ep01_s01_abc.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 16)
    return src


def _setup_audio_src(tmp_path: Path, suffix: str = "_dialogue.mp3") -> Path:
    src = tmp_path / "projects" / "audio" / f"ep01_s01{suffix}"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 8)
    return src


# ---------------------------------------------------------------------------
# 1. link_shot_asset — video symlink
# ---------------------------------------------------------------------------


def test_link_shot_asset_video_creates_symlink(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_video_src(tmp_path)

    mgr = CheckpointManager(base_dir=tmp_path)
    dst = mgr.link_shot_asset(
        series, ep, scene, "video", src, base_dir=tmp_path / "deliverables",
    )

    assert dst.exists()
    assert dst.is_symlink()
    assert "videos" in str(dst)
    assert dst.name.startswith("s01_")
    assert dst.suffix == ".mp4"


# ---------------------------------------------------------------------------
# 2. link_shot_asset — tts_dialogue naming
# ---------------------------------------------------------------------------


def test_link_shot_asset_tts_dialogue_naming(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_audio_src(tmp_path, "_dialogue.mp3")

    mgr = CheckpointManager(base_dir=tmp_path)
    dst = mgr.link_shot_asset(
        series, ep, scene, "tts_dialogue", src, base_dir=tmp_path / "deliverables",
    )

    assert dst.exists()
    assert "audio" in str(dst)
    assert "_dialogue" in dst.name
    assert dst.suffix == ".mp3"


# ---------------------------------------------------------------------------
# 3. link_shot_asset — tts_narration naming
# ---------------------------------------------------------------------------


def test_link_shot_asset_tts_narration_naming(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_audio_src(tmp_path, "_narration.wav")

    mgr = CheckpointManager(base_dir=tmp_path)
    dst = mgr.link_shot_asset(
        series, ep, scene, "tts_narration", src, base_dir=tmp_path / "deliverables",
    )

    assert dst.exists()
    assert "_narration" in dst.name
    assert dst.suffix == ".wav"


# ---------------------------------------------------------------------------
# 4. link_shot_asset — idempotent (call twice, no error)
# ---------------------------------------------------------------------------


def test_link_shot_asset_idempotent(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_video_src(tmp_path)

    mgr = CheckpointManager(base_dir=tmp_path)
    dst1 = mgr.link_shot_asset(
        series, ep, scene, "video", src, base_dir=tmp_path / "deliverables",
    )
    dst2 = mgr.link_shot_asset(
        series, ep, scene, "video", src, base_dir=tmp_path / "deliverables",
    )

    assert dst1 == dst2
    assert dst2.is_symlink()


# ---------------------------------------------------------------------------
# 5. link_shot_asset — preserves user-placed regular file
# ---------------------------------------------------------------------------


def test_link_shot_asset_preserves_user_file(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_video_src(tmp_path)

    mgr = CheckpointManager(base_dir=tmp_path)
    # Pre-place a regular file at the destination
    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    videos_dir = review_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    slug = _scene_slug(0, scene.description)
    user_file = videos_dir / f"{slug}.mp4"
    user_file.write_text("user content")

    dst = mgr.link_shot_asset(
        series, ep, scene, "video", src, base_dir=tmp_path / "deliverables",
    )

    # User file should be backed up
    backup = user_file.with_name(user_file.name + ".user.bak")
    assert backup.exists()
    assert backup.read_text() == "user content"
    assert dst.is_symlink()


# ---------------------------------------------------------------------------
# 6. link_shot_asset — naming matches _update_review_dir convention
# ---------------------------------------------------------------------------


def test_link_shot_asset_reuses_scene_slug(tmp_path: Path) -> None:
    """Incremental symlink name must match the stage-end full rebuild."""
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    scene = ep.scenes[0]
    src = _setup_video_src(tmp_path)

    mgr = CheckpointManager(base_dir=tmp_path)
    dst = mgr.link_shot_asset(
        series, ep, scene, "video", src, base_dir=tmp_path / "deliverables",
    )

    # The name should follow _scene_slug convention
    expected_slug = _scene_slug(0, scene.description)
    assert dst.name == f"{expected_slug}.mp4"


# ---------------------------------------------------------------------------
# 7. runner subscribes to TASK_COMPLETED → calls link_shot_asset
# ---------------------------------------------------------------------------


async def test_runner_subscribes_task_completed(tmp_path: Path) -> None:
    """When a video_ task completes, link_shot_asset should be called."""
    series = _make_series(tmp_path)
    ep = series.episodes[0]
    src = _setup_video_src(tmp_path)

    from videoclaw.drama.runner import DramaRunner

    mgr_mock = MagicMock()
    mgr_mock.save = MagicMock()
    mgr_mock.save_async = AsyncMock()
    mgr_mock.base_dir = tmp_path

    runner = DramaRunner(drama_manager=mgr_mock)

    # Patch link_shot_asset to track calls
    with patch.object(
        CheckpointManager, "link_shot_asset", return_value=tmp_path / "dummy.mp4",
    ) as mock_link:
        # Simulate what run_episode does: subscribe + emit
        from videoclaw.core.events import TASK_COMPLETED, EventBus

        bus = EventBus()
        runner._subscribe_shot_review(
            bus, series, ep, base_dir=tmp_path / "deliverables",
        )

        await bus.emit(TASK_COMPLETED, {
            "node_id": "video_ep01_s01",
            "task_type": "video_gen",
            "result": {"asset_path": str(src)},
        })

        mock_link.assert_called_once()
        call_kwargs = mock_link.call_args
        assert call_kwargs[0][3] == "video"  # kind arg


# ---------------------------------------------------------------------------
# 8. runner skips link when result missing path
# ---------------------------------------------------------------------------


async def test_runner_skips_link_when_result_missing_path(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]

    from videoclaw.drama.runner import DramaRunner

    mgr_mock = MagicMock()
    mgr_mock.base_dir = tmp_path
    runner = DramaRunner(drama_manager=mgr_mock)

    with patch.object(
        CheckpointManager, "link_shot_asset", return_value=tmp_path / "dummy.mp4",
    ) as mock_link:
        from videoclaw.core.events import TASK_COMPLETED, EventBus

        bus = EventBus()
        runner._subscribe_shot_review(
            bus, series, ep, base_dir=tmp_path / "deliverables",
        )

        # Result without asset_path — should NOT call link_shot_asset
        await bus.emit(TASK_COMPLETED, {
            "node_id": "video_ep01_s01",
            "task_type": "video_gen",
            "result": {},
        })

        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# 9. shot_breakpoint disabled → no prompt
# ---------------------------------------------------------------------------


async def test_shot_breakpoint_disabled_no_prompt(tmp_path: Path) -> None:
    from videoclaw.drama.runner import _maybe_shot_breakpoint

    scene = DramaScene(scene_id="ep01_s01", description="Test")
    dst = tmp_path / "dummy.mp4"

    # Should not block or raise when disabled
    await _maybe_shot_breakpoint(scene, dst, enabled=False)


# ---------------------------------------------------------------------------
# 10. shot_breakpoint continue → no exception
# ---------------------------------------------------------------------------


async def test_shot_breakpoint_continue(tmp_path: Path) -> None:
    from videoclaw.drama.runner import _maybe_shot_breakpoint

    scene = DramaScene(scene_id="ep01_s01", description="Test")
    dst = tmp_path / "dummy.mp4"

    with patch("videoclaw.drama.runner.Prompt") as mock_prompt_cls:
        mock_prompt_cls.ask.return_value = "C"
        await _maybe_shot_breakpoint(scene, dst, enabled=True)
        # No exception means continue was chosen


# ---------------------------------------------------------------------------
# 11. shot_breakpoint abort → raises ShotBreakpointError
# ---------------------------------------------------------------------------


async def test_shot_breakpoint_abort_raises(tmp_path: Path) -> None:
    from videoclaw.drama.runner import ShotBreakpointError, _maybe_shot_breakpoint

    scene = DramaScene(scene_id="ep01_s01", description="Test")
    dst = tmp_path / "dummy.mp4"

    with patch("videoclaw.drama.runner.Prompt") as mock_prompt_cls:
        mock_prompt_cls.ask.return_value = "A"
        with pytest.raises(ShotBreakpointError):
            await _maybe_shot_breakpoint(scene, dst, enabled=True)


# ---------------------------------------------------------------------------
# 12. breakpoint only fires on video, NOT tts
# ---------------------------------------------------------------------------


async def test_shot_breakpoint_only_fires_on_video_not_tts(tmp_path: Path) -> None:
    series = _make_series(tmp_path)
    ep = series.episodes[0]

    from videoclaw.drama.runner import DramaRunner

    mgr_mock = MagicMock()
    mgr_mock.base_dir = tmp_path
    runner = DramaRunner(drama_manager=mgr_mock)

    with patch.object(
        CheckpointManager, "link_shot_asset", return_value=tmp_path / "dummy.mp4",
    ), patch("videoclaw.drama.runner._maybe_shot_breakpoint", new_callable=AsyncMock) as mock_bp:
        from videoclaw.core.events import TASK_COMPLETED, EventBus

        bus = EventBus()
        runner._subscribe_shot_review(
            bus, series, ep, base_dir=tmp_path / "deliverables",
            shot_breakpoint=True,
        )

        # TTS event should NOT trigger breakpoint
        await bus.emit(TASK_COMPLETED, {
            "node_id": "tts_ep01_s01",
            "task_type": "per_scene_tts",
            "result": {"scene_id": "ep01_s01", "audio_paths": []},
        })

        mock_bp.assert_not_called()
