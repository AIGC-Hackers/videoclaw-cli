"""Tests for the checkpoint / breakpoint system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoclaw.drama.checkpoint import (
    CheckpointAction,
    CheckpointController,
    CheckpointManager,
    CheckpointSnapshot,
    CheckpointStage,
    _scene_slug,
    _slugify,
    resolve_skip_flags,
    restore_from_checkpoint,
)


# ---------------------------------------------------------------------------
# CheckpointSnapshot serialization
# ---------------------------------------------------------------------------


def _make_snapshot(**overrides) -> CheckpointSnapshot:
    defaults = {
        "checkpoint_id": "abcdef123456",
        "stage": CheckpointStage.AFTER_DESIGN,
        "series_id": "test_series_001",
        "episode_number": 1,
        "created_at": "2026-04-10T12:00:00+00:00",
        "series_state": {"title": "Test Series", "series_id": "test_series_001"},
        "project_state": None,
        "dag_state": None,
        "assets": {"characters/hero.png": "dramas/test_series_001/characters/hero.png"},
        "stage_result": {"characters": 3},
        "cost_usd": 0.25,
        "pipeline_config": {"concurrency": 4},
        "remaining_stages": ["refresh-urls", "run", "audit-regen"],
    }
    defaults.update(overrides)
    return CheckpointSnapshot(**defaults)


def test_snapshot_roundtrip():
    snapshot = _make_snapshot()
    data = snapshot.to_dict()
    restored = CheckpointSnapshot.from_dict(data)

    assert restored.checkpoint_id == snapshot.checkpoint_id
    assert restored.stage == CheckpointStage.AFTER_DESIGN
    assert restored.series_id == "test_series_001"
    assert restored.episode_number == 1
    assert restored.cost_usd == 0.25
    assert restored.assets == snapshot.assets
    assert restored.remaining_stages == ["refresh-urls", "run", "audit-regen"]


def test_snapshot_from_dict_defaults():
    """from_dict should handle missing optional fields gracefully."""
    minimal = {
        "checkpoint_id": "abc123",
        "stage": "after_refresh",
        "series_id": "s1",
        "episode_number": 2,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    snap = CheckpointSnapshot.from_dict(minimal)
    assert snap.stage == CheckpointStage.AFTER_REFRESH
    assert snap.series_state == {}
    assert snap.project_state is None
    assert snap.assets == {}
    assert snap.cost_usd == 0.0
    assert snap.remaining_stages == []


# ---------------------------------------------------------------------------
# CheckpointManager CRUD
# ---------------------------------------------------------------------------


def test_manager_save_and_load(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)
    snapshot = _make_snapshot()

    path = mgr.save(snapshot)
    assert path.exists()
    assert path.suffix == ".json"
    assert "abcdef123456" in path.name

    loaded = mgr.load("test_series_001", "abcdef123456")
    assert loaded.checkpoint_id == "abcdef123456"
    assert loaded.stage == CheckpointStage.AFTER_DESIGN
    assert loaded.series_state["title"] == "Test Series"


def test_manager_save_compact_json(tmp_path: Path):
    """save() must write compact JSON (no indentation)."""
    mgr = CheckpointManager(base_dir=tmp_path)
    snapshot = _make_snapshot()
    path = mgr.save(snapshot)

    raw = path.read_text(encoding="utf-8")
    assert "\n" not in raw  # compact = single line
    data = json.loads(raw)
    assert data["checkpoint_id"] == "abcdef123456"


def test_manager_list_checkpoints(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)

    snap1 = _make_snapshot(
        checkpoint_id="aaa111",
        stage=CheckpointStage.AFTER_DESIGN,
        created_at="2026-04-10T10:00:00+00:00",
    )
    snap2 = _make_snapshot(
        checkpoint_id="bbb222",
        stage=CheckpointStage.AFTER_REFRESH,
        created_at="2026-04-10T11:00:00+00:00",
    )
    snap3 = _make_snapshot(
        checkpoint_id="ccc333",
        stage=CheckpointStage.AFTER_GENERATION,
        episode_number=2,
        created_at="2026-04-10T12:00:00+00:00",
    )
    mgr.save(snap1)
    mgr.save(snap2)
    mgr.save(snap3)

    # List all
    all_ckpts = mgr.list_checkpoints("test_series_001")
    assert len(all_ckpts) == 3
    assert all_ckpts[0]["checkpoint_id"] == "aaa111"  # sorted by created_at

    # Filter by episode
    ep1 = mgr.list_checkpoints("test_series_001", episode=1)
    assert len(ep1) == 2

    # Filter by stage
    design_only = mgr.list_checkpoints(
        "test_series_001", stage=CheckpointStage.AFTER_DESIGN
    )
    assert len(design_only) == 1
    assert design_only[0]["stage"] == "after_design"


def test_manager_latest(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)

    snap1 = _make_snapshot(
        checkpoint_id="old1",
        created_at="2026-04-10T10:00:00+00:00",
    )
    snap2 = _make_snapshot(
        checkpoint_id="new2",
        created_at="2026-04-10T14:00:00+00:00",
    )
    mgr.save(snap1)
    mgr.save(snap2)

    latest = mgr.latest("test_series_001", episode=1)
    assert latest is not None
    assert latest.checkpoint_id == "new2"


def test_manager_latest_none(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)
    assert mgr.latest("nonexistent", episode=1) is None


def test_manager_delete(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)
    snapshot = _make_snapshot()
    mgr.save(snapshot)

    mgr.delete("test_series_001", "abcdef123456")
    with pytest.raises(FileNotFoundError):
        mgr.load("test_series_001", "abcdef123456")


def test_manager_load_not_found(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.load("nonexistent_series", "nonexistent_id")


def test_manager_list_empty(tmp_path: Path):
    mgr = CheckpointManager(base_dir=tmp_path)
    assert mgr.list_checkpoints("nonexistent") == []


# ---------------------------------------------------------------------------
# CheckpointController (auto mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_controller_auto_mode_saves_and_continues(tmp_path: Path):
    """In auto mode (breakpoints=[]), checkpoint is saved but returns CONTINUE."""
    from videoclaw.drama.models import DramaSeries, Episode

    series = DramaSeries(
        series_id="ctrl_test_001",
        title="Controller Test",
        genre="test",
        synopsis="test",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Test EP",
        synopsis="test",
        opening_hook="",
    )
    series.episodes.append(episode)

    from videoclaw.drama.models import DramaManager

    drama_mgr = DramaManager(base_dir=tmp_path)
    drama_mgr.save(series)

    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=[],  # auto mode
        interactive=False,
    )

    action = await ctrl.checkpoint(
        CheckpointStage.AFTER_DESIGN,
        stage_result={"characters": 3},
        cost_usd=0.5,
        remaining_stages=["refresh-urls", "run"],
    )

    assert action == CheckpointAction.CONTINUE

    # Verify checkpoint was saved
    summaries = ckpt_mgr.list_checkpoints("ctrl_test_001")
    assert len(summaries) == 1
    assert summaries[0]["stage"] == "after_design"


@pytest.mark.asyncio
async def test_controller_does_not_pause_when_non_interactive(tmp_path: Path):
    """Even with breakpoints set, non-interactive mode should not pause."""
    from videoclaw.drama.models import DramaSeries, Episode, DramaManager

    series = DramaSeries(
        series_id="ctrl_test_002",
        title="Non-interactive Test",
        genre="test",
        synopsis="test",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Test",
        synopsis="",
        opening_hook="",
    )
    series.episodes.append(episode)

    drama_mgr = DramaManager(base_dir=tmp_path)
    drama_mgr.save(series)

    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=None,  # all breakpoints
        interactive=False,  # but non-interactive
    )

    action = await ctrl.checkpoint(
        CheckpointStage.AFTER_GENERATION,
        cost_usd=1.0,
        remaining_stages=["audit-regen"],
    )

    assert action == CheckpointAction.CONTINUE


# ---------------------------------------------------------------------------
# resolve_skip_flags
# ---------------------------------------------------------------------------


def test_resolve_skip_flags_all_remaining():
    flags = resolve_skip_flags(["design-characters", "refresh-urls", "run", "audit-regen"])
    assert flags == {
        "skip_design": False,
        "skip_refresh": False,
        "skip_run": False,
        "skip_audit": False,
    }


def test_resolve_skip_flags_partial():
    flags = resolve_skip_flags(["run", "audit-regen"])
    assert flags["skip_design"] is True
    assert flags["skip_refresh"] is True
    assert flags["skip_run"] is False
    assert flags["skip_audit"] is False


def test_resolve_skip_flags_empty():
    flags = resolve_skip_flags([])
    assert all(v is True for v in flags.values())


# ---------------------------------------------------------------------------
# restore_from_checkpoint
# ---------------------------------------------------------------------------


def test_restore_from_checkpoint():
    from videoclaw.drama.models import DramaSeries

    series = DramaSeries(
        series_id="restore_test",
        title="Restore Test",
        genre="drama",
        synopsis="test synopsis",
    )
    snapshot = _make_snapshot(series_state=series.to_dict())

    restored = restore_from_checkpoint(snapshot)
    assert isinstance(restored, DramaSeries)
    assert restored.series_id == "restore_test"
    assert restored.title == "Restore Test"


# ---------------------------------------------------------------------------
# DAGExecutor phase boundary detection
# ---------------------------------------------------------------------------


def test_executor_classify_node_phase():
    """Verify node-to-phase classification."""
    from videoclaw.core.executor import DAGExecutor
    from videoclaw.core.planner import DAG
    from videoclaw.core.state import ProjectState

    dag = DAG()
    state = ProjectState(prompt="test")
    executor = DAGExecutor(dag=dag, state=state)

    assert executor._classify_node_phase("script_gen") == "storyboard"
    assert executor._classify_node_phase("storyboard") == "storyboard"
    assert executor._classify_node_phase("scene_validate") == "storyboard"
    assert executor._classify_node_phase("video_ep01_s01") == "video_tts"
    assert executor._classify_node_phase("tts_ep01_s01") == "video_tts"
    assert executor._classify_node_phase("compose") == "compose"
    assert executor._classify_node_phase("render") is None
    assert executor._classify_node_phase("music") is None
    assert executor._classify_node_phase("subtitle_gen") is None


def test_executor_is_phase_complete():
    """Phase should be complete only when all nodes in it are COMPLETED."""
    from videoclaw.core.executor import DAGExecutor
    from videoclaw.core.planner import DAG, NodeStatus, TaskNode, TaskType
    from videoclaw.core.state import ProjectState

    dag = DAG()
    dag.add_node(TaskNode(node_id="script_gen", task_type=TaskType.SCRIPT_GEN))
    dag.add_node(TaskNode(node_id="storyboard", task_type=TaskType.STORYBOARD, depends_on=["script_gen"]))
    dag.add_node(TaskNode(node_id="scene_validate", task_type=TaskType.SCENE_VALIDATE, depends_on=["storyboard"]))

    state = ProjectState(prompt="test")
    executor = DAGExecutor(dag=dag, state=state)

    # Initially not complete
    assert executor._is_phase_complete("storyboard") is False

    # Mark some as complete
    dag.mark_complete("script_gen")
    dag.mark_complete("storyboard")
    assert executor._is_phase_complete("storyboard") is False  # scene_validate still pending

    dag.mark_complete("scene_validate")
    assert executor._is_phase_complete("storyboard") is True


# ---------------------------------------------------------------------------
# CheckpointStage enum
# ---------------------------------------------------------------------------


def test_checkpoint_stage_values():
    assert CheckpointStage.AFTER_DESIGN == "after_design"
    assert CheckpointStage.AFTER_REFRESH == "after_refresh"
    assert CheckpointStage.AFTER_GENERATION == "after_generation"
    assert CheckpointStage.AFTER_AUDIT == "after_audit"
    assert CheckpointStage.AFTER_STORYBOARD == "after_storyboard"
    assert CheckpointStage.AFTER_VIDEO_TTS == "after_video_tts"
    assert CheckpointStage.AFTER_COMPOSE == "after_compose"


def test_checkpoint_action_values():
    assert CheckpointAction.CONTINUE == "continue"
    assert CheckpointAction.REDO == "redo"
    assert CheckpointAction.ABORT == "abort"


# ---------------------------------------------------------------------------
# Semantic naming helpers
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert _slugify("Poolside  Confrontation!") == "poolside_confrontation"


def test_slugify_chinese():
    assert _slugify("池畔对峙 Scene") == "池畔对峙_scene"


def test_slugify_empty():
    assert _slugify("") == ""


def test_slugify_max_len():
    result = _slugify("a very long description that should be truncated", max_len=10)
    assert len(result) <= 10


def test_scene_slug():
    assert _scene_slug(0, "Poolside arrival") == "s01_poolside_arrival"
    assert _scene_slug(2, "Eye contact across the pool") == "s03_eye_contact_across_the_pool"


def test_scene_slug_empty_description():
    assert _scene_slug(0, "") == "s01_scene"


def test_scene_slug_special_chars():
    assert _scene_slug(4, "Lucian's gaze (close-up)") == "s05_lucians_gaze_close_up"


# ---------------------------------------------------------------------------
# Review directory (snapshot with review_dir)
# ---------------------------------------------------------------------------


def test_snapshot_roundtrip_with_review_dir():
    snap = _make_snapshot(review_dir="/tmp/review/ep01")
    data = snap.to_dict()
    assert data["review_dir"] == "/tmp/review/ep01"

    restored = CheckpointSnapshot.from_dict(data)
    assert restored.review_dir == "/tmp/review/ep01"


@pytest.mark.asyncio
async def test_controller_cumulative_review_dir(tmp_path: Path):
    """Two checkpoints on the same episode share one review/ep01/ directory.

    after_design populates characters/ (not prompts/).
    after_storyboard populates prompts/ (keeps characters/).
    """
    from videoclaw.drama.models import DramaManager, DramaSeries, DramaScene, Episode

    series = DramaSeries(
        series_id="cumul_test",
        title="Cumulative Test",
        genre="test",
        synopsis="test",
    )
    scene1 = DramaScene(
        scene_id="ep01_s01",
        description="Poolside arrival at sunset",
        visual_prompt="A man walks to the pool at sunset.",
    )
    scene2 = DramaScene(
        scene_id="ep01_s02",
        description="Eye contact across pool",
        visual_prompt="Two characters lock eyes across the water.",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=[scene1, scene2],
    )
    series.episodes.append(episode)

    drama_mgr = DramaManager(base_dir=tmp_path)
    drama_mgr.save(series)

    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=[],
        interactive=False,
    )

    # --- Checkpoint 1: after_design (populates characters/) ---
    await ctrl.checkpoint(
        CheckpointStage.AFTER_DESIGN,
        cost_usd=0.1,
        remaining_stages=["run"],
    )

    review_dir = tmp_path / "dramas" / "cumul_test" / "review" / "ep01"
    assert review_dir.is_dir()

    # All subdirs should exist (created on first call)
    for subdir in ("characters", "prompts", "videos", "audio", "audit", "composed"):
        assert (review_dir / subdir).is_dir()

    # Prompts should be EMPTY (after_design doesn't populate prompts)
    assert list((review_dir / "prompts").iterdir()) == []

    # --- Checkpoint 2: after_storyboard (populates prompts/) ---
    await ctrl.checkpoint(
        CheckpointStage.AFTER_STORYBOARD,
        cost_usd=0.2,
        remaining_stages=["run"],
    )

    # Review dir is the SAME path (cumulative, not a new directory)
    assert review_dir.is_dir()

    # Prompts should now have files
    prompt_files = sorted((review_dir / "prompts").iterdir())
    assert len(prompt_files) == 2
    assert "s01_poolside_arrival_at_sunset" in prompt_files[0].name
    assert "s02_eye_contact_across_pool" in prompt_files[1].name

    # _REVIEW.txt should reflect latest state
    summary = review_dir / "_REVIEW.txt"
    assert summary.exists()
    content = summary.read_text()
    assert "Cumulative Test" in content
    assert "after_storyboard" in content  # last stage
    assert "prompts/" in content
    assert "characters/" in content


@pytest.mark.asyncio
async def test_version_existing_on_redo(tmp_path: Path):
    """When a video symlink already exists, redo should version the old one."""
    from videoclaw.drama.checkpoint import _version_existing

    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()

    # Create initial file
    original = videos_dir / "s03_poolside.mp4"
    original.write_bytes(b"video_v0")

    # First version
    _version_existing(original)
    assert not original.exists()
    assert (videos_dir / "s03_poolside_v1.mp4").exists()
    assert (videos_dir / "s03_poolside_v1.mp4").read_bytes() == b"video_v0"

    # Create another file at the same path
    original.write_bytes(b"video_v1")
    _version_existing(original)
    assert not original.exists()
    assert (videos_dir / "s03_poolside_v2.mp4").exists()
    assert (videos_dir / "s03_poolside_v2.mp4").read_bytes() == b"video_v1"


@pytest.mark.asyncio
async def test_review_summary_is_cumulative(tmp_path: Path):
    """_REVIEW.txt should show file counts across ALL subdirectories."""
    from videoclaw.drama.models import DramaManager, DramaSeries, DramaScene, Episode

    series = DramaSeries(
        series_id="summary_test",
        title="Summary Test",
        genre="test",
        synopsis="test",
    )
    scene = DramaScene(
        scene_id="ep01_s01",
        description="Opening scene",
        visual_prompt="A dramatic opening.",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=[scene],
    )
    series.episodes.append(episode)

    drama_mgr = DramaManager(base_dir=tmp_path)
    drama_mgr.save(series)

    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=[],
        interactive=False,
    )

    # Checkpoint 1: after_storyboard → populates prompts/
    await ctrl.checkpoint(CheckpointStage.AFTER_STORYBOARD, cost_usd=0.1)

    review_dir = tmp_path / "dramas" / "summary_test" / "review" / "ep01"
    content = (review_dir / "_REVIEW.txt").read_text()
    assert "prompts/" in content
    assert "1 files" in content  # 1 prompt file

    # Checkpoint 2: after_audit → populates audit/ (empty in this case)
    await ctrl.checkpoint(CheckpointStage.AFTER_AUDIT, cost_usd=0.3)

    content2 = (review_dir / "_REVIEW.txt").read_text()
    # Should still show prompts count from earlier stage
    assert "prompts/" in content2
    assert "1 files" in content2  # prompts still counted
    assert "after_audit" in content2  # last stage updated
