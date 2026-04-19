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
    generate_storyboard_md,
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
        deliverables_dir=tmp_path,
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
        deliverables_dir=tmp_path,
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
    """Two checkpoints on the same episode share one cumulative review directory.

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
        deliverables_dir=tmp_path,
    )

    # --- Checkpoint 1: after_design (populates no subdirs — empty) ---
    await ctrl.checkpoint(
        CheckpointStage.AFTER_DESIGN,
        cost_usd=0.1,
        remaining_stages=["run"],
    )

    review_dir = tmp_path / "cumulative_test" / "ep01_pilot"
    assert review_dir.is_dir()
    assert (review_dir / "storyboard.md").exists()
    assert (review_dir / "_REVIEW.txt").exists()

    # --- Pre-checkpoint 2: simulate generated videos by setting scene.video_asset_path ---
    fake_video1 = tmp_path / "fake_s01.mp4"
    fake_video2 = tmp_path / "fake_s02.mp4"
    fake_video1.write_bytes(b"v1")
    fake_video2.write_bytes(b"v2")
    scene1.video_asset_path = str(fake_video1)
    scene2.video_asset_path = str(fake_video2)

    # --- Checkpoint 2: after_generation (populates videos/) ---
    await ctrl.checkpoint(
        CheckpointStage.AFTER_GENERATION,
        cost_usd=0.2,
        remaining_stages=[],
    )

    # Review dir is the SAME path (cumulative, not a new directory)
    assert review_dir.is_dir()

    # Videos should now have files (populated by after_generation)
    videos_dir = review_dir / "videos"
    assert videos_dir.is_dir()
    video_files = sorted(videos_dir.iterdir())
    assert len(video_files) == 2
    assert "s01_poolside_arrival_at_sunset" in video_files[0].name
    assert "s02_eye_contact_across_pool" in video_files[1].name

    # _REVIEW.txt reflects latest state
    summary = review_dir / "_REVIEW.txt"
    assert summary.exists()
    content = summary.read_text()
    assert "Cumulative Test" in content
    assert "after_generation" in content  # last stage
    assert "videos/" in content


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
        deliverables_dir=tmp_path,
    )

    # Checkpoint 1: pre-set video path and call after_generation → populates videos/
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"v")
    scene.video_asset_path = str(fake_video)

    await ctrl.checkpoint(CheckpointStage.AFTER_GENERATION, cost_usd=0.1)

    review_dir = tmp_path / "summary_test" / "ep01_pilot"
    content = (review_dir / "_REVIEW.txt").read_text()
    assert "videos/" in content
    assert "1 files" in content  # 1 video file
    assert "after_generation" in content

    # Checkpoint 2: after_audit → no audit files, but summary still cumulative
    await ctrl.checkpoint(CheckpointStage.AFTER_AUDIT, cost_usd=0.3)

    content2 = (review_dir / "_REVIEW.txt").read_text()
    # Videos count from earlier stage still reflected (cumulative)
    assert "videos/" in content2
    assert "1 files" in content2
    assert "after_audit" in content2  # last stage updated


# ---------------------------------------------------------------------------
# Storyboard document generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storyboard_md_generated(tmp_path: Path):
    """storyboard.md should be generated with analysis + scene details."""
    from videoclaw.drama.models import (
        DramaManager, DramaSeries, DramaScene, Episode,
    )
    from videoclaw.drama.models import ShotScale

    series = DramaSeries(
        series_id="storyboard_test",
        title="Storyboard Test Drama",
        genre="male_power_fantasy",
        synopsis="A test drama.",
        aspect_ratio="9:16",
        model_id="seedance-2.0",
    )
    scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="Lucian arrives at the pool",
            visual_prompt="Tall man in suit walks toward pool.",
            duration_seconds=5.0,
            shot_scale=ShotScale.WIDE,
            camera_movement="slow_push",
            characters_present=["Lucian", "Ivy"],
            speaking_character="Lucian",
            dialogue="I didn't expect to see you here.",
            emotion="tense",
            act_number="act_1",
            scene_group="A",
            shot_role="hook",
        ),
        DramaScene(
            scene_id="ep01_s02",
            description="Eye contact across the pool",
            visual_prompt="Two characters lock eyes.",
            duration_seconds=4.0,
            shot_scale=ShotScale.CLOSE_UP,
            camera_movement="static",
            characters_present=["Lucian", "Ivy"],
            emotion="curious",
            act_number="act_1",
            scene_group="A",
        ),
        DramaScene(
            scene_id="ep01_s03",
            description="Ivy turns away sharply",
            visual_prompt="Woman turns her back.",
            duration_seconds=3.0,
            shot_scale=ShotScale.MEDIUM,
            camera_movement="pan_right",
            characters_present=["Ivy"],
            emotion="defiant",
            act_number="act_2",
            scene_group="B",
        ),
    ]
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=scenes,
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
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_STORYBOARD, cost_usd=0.0)

    review_dir = tmp_path / "storyboard_test_drama" / "ep01_pilot"
    storyboard = review_dir / "storyboard.md"
    assert storyboard.exists()

    content = storyboard.read_text()

    # Title
    assert "Storyboard Test Drama" in content
    assert "EP01 分镜表" in content

    # Production analysis
    assert "制作分析" in content
    assert "时长分布" in content
    assert "景别分布" in content
    assert "角色出镜" in content

    # Duration: 5 + 4 + 3 = 12s
    assert "12" in content

    # Shot scale labels in Chinese
    assert "特写" in content       # close_up
    assert "全景" in content       # wide
    assert "中景" in content       # medium

    # Character screentime
    assert "Lucian" in content
    assert "Ivy" in content

    # Scene details — grouped by act
    assert "Act 1" in content
    assert "Act 2" in content
    assert "场景组 A" in content
    assert "场景组 B" in content

    # Scene metadata
    assert "slow_push" in content          # camera movement
    assert "hook" in content               # shot_role
    assert "I didn't expect" in content    # dialogue
    assert "tense" in content              # emotion


@pytest.mark.asyncio
async def test_generate_storyboard_md_standalone(tmp_path: Path):
    """generate_storyboard_md() should work without a CheckpointController."""
    from videoclaw.drama.models import DramaScene, DramaSeries, Episode, ShotScale

    series = DramaSeries(
        series_id="standalone_test",
        title="Standalone Storyboard",
        genre="thriller",
        synopsis="Test standalone generation.",
        aspect_ratio="9:16",
        model_id="seedance-2.0",
    )
    scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="A man walks into a bar",
            visual_prompt="Man enters bar.",
            duration_seconds=6.0,
            shot_scale=ShotScale.MEDIUM,
            camera_movement="static",
            characters_present=["Jake"],
            act_number="act_1",
        ),
    ]
    episode = Episode(
        episode_id="ep1", number=1, title="Pilot",
        synopsis="test", opening_hook="", scenes=scenes,
    )
    series.episodes.append(episode)

    review_dir = tmp_path / "review" / "ep01"
    sb_path = generate_storyboard_md(series, episode, review_dir=review_dir)

    assert sb_path.exists()
    content = sb_path.read_text()
    assert "Standalone Storyboard" in content
    assert "EP01 分镜表" in content
    assert "Jake" in content
    assert "6" in content  # duration


# ---------------------------------------------------------------------------
# Base dir required invariant (prevents test leakage into real deliverables dir)
# ---------------------------------------------------------------------------


def test_review_dir_for_episode_requires_base_dir():
    """review_dir_for_episode must require explicit base_dir.

    Without this, callers silently fall back to ``get_config().deliverables_dir``
    which is the real ``docs/deliverables/`` — causing test fixtures to leak
    into the production review directory.
    """
    from videoclaw.drama.checkpoint import review_dir_for_episode
    from videoclaw.drama.models import DramaSeries, Episode

    series = DramaSeries(
        series_id="req_bd_test",
        title="Req BaseDir Test",
        genre="test",
        synopsis="test",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="",
        opening_hook="",
        scenes=[],
    )

    with pytest.raises(TypeError, match="base_dir"):
        review_dir_for_episode(series, episode)  # type: ignore[call-arg]


def test_generate_storyboard_md_requires_review_dir():
    """generate_storyboard_md must require explicit review_dir.

    No silent fallback to config-driven paths — the caller must supply
    the exact directory to write into.
    """
    from videoclaw.drama.models import DramaSeries, Episode

    series = DramaSeries(
        series_id="req_rd_test",
        title="Req ReviewDir Test",
        genre="test",
        synopsis="test",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="",
        opening_hook="",
        scenes=[],
    )

    with pytest.raises(TypeError, match="review_dir"):
        generate_storyboard_md(series, episode)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Lazy subdir creation (no empty placeholder directories)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lazy_subdir_creation_after_design(tmp_path: Path):
    """after_design stage should only create subdirs that actually receive content.

    Previously, ALL subdirectories (characters, videos, audio, audit, final, scenes)
    were mkdir'd up-front, leaving empty placeholder folders. This created
    visual noise and made ``ls`` output misleading.

    New contract: a subdirectory exists if and only if it has at least one
    file or symlink in it.
    """
    from videoclaw.drama.models import DramaManager, DramaScene, DramaSeries, Episode

    series = DramaSeries(
        series_id="lazy_mkdir_test",
        title="Lazy Mkdir Test",
        genre="test",
        synopsis="test",
    )
    scene = DramaScene(
        scene_id="ep01_s01",
        description="A quiet moment",
        visual_prompt="A silent room.",
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
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_DESIGN, cost_usd=0.1)

    review_dir = tmp_path / "lazy_mkdir_test" / "ep01_pilot"
    assert review_dir.is_dir()
    assert (review_dir / "storyboard.md").exists()
    assert (review_dir / "_REVIEW.txt").exists()

    # Subdirs that have no content must NOT exist on disk
    for empty in ("characters", "videos", "audio", "audit", "final", "scenes"):
        assert not (review_dir / empty).exists(), (
            f"{empty}/ should not exist when stage produced no content"
        )

    # And the old layout's dirs must never appear
    assert not (review_dir / "prompts").exists()
    assert not (review_dir / "composed").exists()


# ---------------------------------------------------------------------------
# Incremental asset sync at checkpoint time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_syncs_video_asset_path_from_project_state(
    tmp_path, monkeypatch,
):
    """After generation, checkpoint copies Shot.asset_path → DramaScene.video_asset_path.

    Without this sync, the review directory would see ``scene_status=pending``
    even after videos were successfully written to disk by the DAG executor.
    """
    from videoclaw.config import get_config
    from videoclaw.core.state import ProjectState, Shot, ShotStatus, StateManager
    from videoclaw.drama.models import (
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    # Redirect projects_dir to tmp_path via config singleton
    monkeypatch.setattr(get_config(), "projects_dir", tmp_path)
    drama_mgr = DramaManager(base_dir=tmp_path)

    series = DramaSeries(
        series_id="sync_test",
        title="Sync Test",
        genre="test",
        synopsis="test",
    )
    scene1 = DramaScene(
        scene_id="ep01_s01",
        description="Opening shot",
        visual_prompt="A dramatic opening.",
    )
    scene2 = DramaScene(
        scene_id="ep01_s02",
        description="Second shot",
        visual_prompt="A reaction.",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=[scene1, scene2],
        project_id="test_proj_001",
    )
    series.episodes.append(episode)
    drama_mgr.save(series)

    # Create fake generated videos on disk
    proj_dir = tmp_path / "test_proj_001"
    shots_dir = proj_dir / "shots"
    shots_dir.mkdir(parents=True)
    video1 = shots_dir / "ep01_s01_abc123.mp4"
    video2 = shots_dir / "ep01_s02_def456.mp4"
    video1.write_bytes(b"fake_video_1")
    video2.write_bytes(b"fake_video_2")

    # Create ProjectState with shots pointing to those videos
    state = ProjectState(project_id="test_proj_001", prompt="test")
    state.storyboard = [
        Shot(
            shot_id="ep01_s01",
            description="",
            prompt="test",
            asset_path=str(video1),
            status=ShotStatus.COMPLETED,
        ),
        Shot(
            shot_id="ep01_s02",
            description="",
            prompt="test",
            asset_path=str(video2),
            status=ShotStatus.COMPLETED,
        ),
    ]
    sm = StateManager(projects_dir=tmp_path)
    sm.save(state)

    # Pre-sync: scene paths should still be None
    assert scene1.video_asset_path is None
    assert scene2.video_asset_path is None

    # Run a checkpoint → triggers sync
    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=[],
        interactive=False,
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(
        CheckpointStage.AFTER_GENERATION,
        cost_usd=1.0,
        remaining_stages=[],
    )

    # Post-sync: scene paths populated + status updated
    assert scene1.video_asset_path == str(video1)
    assert scene2.video_asset_path == str(video2)
    assert scene1.scene_status == "completed"
    assert scene2.scene_status == "completed"

    # Persistence check
    reloaded = drama_mgr.load("sync_test")
    assert reloaded.episodes[0].scenes[0].video_asset_path == str(video1)
    assert reloaded.episodes[0].scenes[1].video_asset_path == str(video2)


@pytest.mark.asyncio
async def test_checkpoint_sync_skips_when_no_project_id(tmp_path: Path):
    """Sync is a no-op for episodes without project_id (pre-generation)."""
    from videoclaw.drama.models import (
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    series = DramaSeries(
        series_id="noproj_test",
        title="No Project Test",
        genre="test",
        synopsis="test",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="",
        opening_hook="",
        scenes=[DramaScene(scene_id="ep01_s01", description="test")],
        # no project_id — no pipeline run yet
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
        deliverables_dir=tmp_path,
    )

    # Should not raise — pre-generation stages just skip sync
    action = await ctrl.checkpoint(
        CheckpointStage.AFTER_DESIGN,
        cost_usd=0.0,
    )
    assert action == CheckpointAction.CONTINUE


@pytest.mark.asyncio
async def test_checkpoint_syncs_audio_files(tmp_path, monkeypatch):
    """Audio files in projects/{project_id}/audio/ are matched to scenes by filename."""
    from videoclaw.config import get_config
    from videoclaw.core.state import ProjectState, StateManager
    from videoclaw.drama.models import (
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    monkeypatch.setattr(get_config(), "projects_dir", tmp_path)
    drama_mgr = DramaManager(base_dir=tmp_path)

    series = DramaSeries(
        series_id="audio_sync_test",
        title="Audio Sync Test",
        genre="test",
        synopsis="test",
    )
    scene = DramaScene(
        scene_id="ep01_s01",
        description="Dialogue shot",
        visual_prompt="A character speaks.",
        dialogue="Hello world",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=[scene],
        project_id="audio_proj_001",
    )
    series.episodes.append(episode)
    drama_mgr.save(series)

    # Create audio files on disk
    audio_dir = tmp_path / "audio_proj_001" / "audio"
    audio_dir.mkdir(parents=True)
    dialogue_wav = audio_dir / "ep01_s01_dialogue.wav"
    dialogue_wav.write_bytes(b"fake_audio")

    # Create empty ProjectState (sync still reads audio dir directly)
    state = ProjectState(project_id="audio_proj_001", prompt="test")
    StateManager(projects_dir=tmp_path).save(state)

    ckpt_mgr = CheckpointManager(base_dir=tmp_path)
    ctrl = CheckpointController(
        series=series,
        episode=episode,
        manager=ckpt_mgr,
        drama_manager=drama_mgr,
        breakpoints=[],
        interactive=False,
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_GENERATION, cost_usd=0.5)

    assert scene.dialogue_audio_path == str(dialogue_wav)


# ---------------------------------------------------------------------------
# scenes/ subdir — 景别图 / 场景参考图 from ConsistencyManifest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenes_subdir_populated_from_consistency_manifest(tmp_path: Path):
    """after_design should symlink scene_references into scenes/.

    The ConsistencyManifest.scene_references dict is populated by
    scene_designer.py during the design stage; review_dir should surface
    those images as ``scenes/<loc_slug>.<ext>``.
    """
    from videoclaw.drama.models import (
        ConsistencyManifest,
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    # Fake location reference images on disk
    pool_ref = tmp_path / "pool_deck_reference.png"
    mansion_ref = tmp_path / "mansion_hall_reference.png"
    pool_ref.write_bytes(b"pool_png")
    mansion_ref.write_bytes(b"mansion_png")

    series = DramaSeries(
        series_id="scenes_test",
        title="Scenes Test",
        genre="test",
        synopsis="test",
    )
    series.consistency_manifest = ConsistencyManifest(
        scene_references={
            "Pool deck at sunset": str(pool_ref),
            "Mansion hall": str(mansion_ref),
        },
    )

    scene = DramaScene(
        scene_id="ep01_s01",
        description="Intro",
        visual_prompt="A wide shot.",
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
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_DESIGN, cost_usd=0.05)

    review_dir = tmp_path / "scenes_test" / "ep01_pilot"
    scenes_dir = review_dir / "scenes"

    assert scenes_dir.is_dir()

    # Both locations should be symlinked with slugified names
    expected_files = {"pool_deck_at_sunset.png", "mansion_hall.png"}
    actual_files = {f.name for f in scenes_dir.iterdir()}
    assert actual_files == expected_files

    # Each entry must be a symlink pointing at the original file
    assert (scenes_dir / "pool_deck_at_sunset.png").is_symlink()
    assert (scenes_dir / "pool_deck_at_sunset.png").resolve() == pool_ref.resolve()
    assert (scenes_dir / "mansion_hall.png").resolve() == mansion_ref.resolve()


@pytest.mark.asyncio
async def test_scenes_subdir_absent_without_manifest(tmp_path: Path):
    """scenes/ subdir must not exist when consistency_manifest has no refs."""
    from videoclaw.drama.models import DramaManager, DramaScene, DramaSeries, Episode

    series = DramaSeries(
        series_id="no_scenes_test",
        title="No Scenes Test",
        genre="test",
        synopsis="test",
    )
    # No consistency_manifest.scene_references populated — default empty

    scene = DramaScene(
        scene_id="ep01_s01",
        description="Intro",
        visual_prompt="A shot.",
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
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_DESIGN, cost_usd=0.05)

    review_dir = tmp_path / "no_scenes_test" / "ep01_pilot"
    assert not (review_dir / "scenes").exists()


# ---------------------------------------------------------------------------
# storyboard.md — 台词逐字稿 section (subtitle replacement)
# ---------------------------------------------------------------------------


def test_storyboard_includes_dialogue_transcript(tmp_path: Path):
    """storyboard.md must contain a ## 台词逐字稿 section with every
    dialogue/narration line, so the producer has a single source of
    truth for subtitles (Seedance bakes them into the video, so there
    is no separate subtitles/ directory).
    """
    from videoclaw.drama.models import DramaScene, DramaSeries, Episode

    series = DramaSeries(
        series_id="transcript_test",
        title="Transcript Test",
        genre="drama",
        synopsis="test",
    )
    scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="Ivy enters the ballroom",
            visual_prompt="A woman enters.",
            speaking_character="Ivy",
            dialogue="I know what you did.",
            duration_seconds=4.0,
        ),
        DramaScene(
            scene_id="ep01_s02",
            description="Narrator introduces the setting",
            visual_prompt="Wide shot of mansion.",
            narration="One month earlier, everything was different.",
            narration_type="voiceover",
            duration_seconds=5.0,
        ),
        DramaScene(
            scene_id="ep01_s03",
            description="Silent close-up of a glass",
            visual_prompt="A glass tips over.",
            duration_seconds=2.0,
        ),  # no dialogue, no narration — should be skipped
    ]
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=scenes,
    )
    series.episodes.append(episode)

    review_dir = tmp_path / "review" / "ep01"
    sb_path = generate_storyboard_md(series, episode, review_dir=review_dir)

    content = sb_path.read_text()

    # Section header must be present
    assert "## 台词逐字稿" in content

    # Every line with dialogue or narration appears verbatim
    assert "I know what you did." in content
    assert "One month earlier, everything was different." in content

    # Speaker / narration type labeling
    assert "Ivy" in content  # speaker label
    # Narration should be marked as voiceover ("旁白") in the transcript
    # (not the earlier scene-detail block)
    transcript_start = content.index("## 台词逐字稿")
    transcript_section = content[transcript_start:]
    assert "旁白" in transcript_section

    # Scene 3 has no dialogue/narration → its description must NOT appear
    # inside the transcript section (it still appears earlier in scene details)
    assert "Silent close-up of a glass" not in transcript_section


# ---------------------------------------------------------------------------
# _REVIEW.txt — Sources section (symlink target transparency)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_txt_has_sources_section(tmp_path: Path):
    """_REVIEW.txt must include a === Sources === section that lists,
    for each non-empty subdirectory, the parent directory that the first
    symlink points at.  This lets auditors see the source-of-truth path
    (usually ``projects/<uuid>/shots/``) without running ``ls -la``.
    """
    from videoclaw.drama.models import (
        Character,
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    # Set up a fake character turnaround file outside the review dir
    src_dir = tmp_path / "src_storage" / "characters"
    src_dir.mkdir(parents=True)
    turnaround = src_dir / "hero_turnaround.png"
    turnaround.write_bytes(b"fake_png")

    series = DramaSeries(
        series_id="sources_test",
        title="Sources Test",
        genre="test",
        synopsis="test",
    )
    series.characters.append(
        Character(
            name="Hero",
            description="protagonist",
            reference_image=str(turnaround),
        )
    )
    scene = DramaScene(
        scene_id="ep01_s01",
        description="Opening",
        visual_prompt="test",
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
        deliverables_dir=tmp_path,
    )

    await ctrl.checkpoint(CheckpointStage.AFTER_DESIGN, cost_usd=0.1)

    review_dir = tmp_path / "sources_test" / "ep01_pilot"
    content = (review_dir / "_REVIEW.txt").read_text()

    # Header present
    assert "=== Sources ===" in content

    # Extract the sources block
    sources_start = content.index("=== Sources ===")
    # Sources section runs until the next === header or EOF
    next_header = content.find("===", sources_start + len("=== Sources ==="))
    sources_block = (
        content[sources_start:next_header] if next_header != -1
        else content[sources_start:]
    )

    # The populated subdir (characters/) must list the true source parent
    assert "characters/" in sources_block
    assert str(src_dir) in sources_block or "src_storage/characters" in sources_block

    # Empty subdirs either display (empty) or are absent from the block
    # (implementation choice — either is acceptable as long as they do not
    # display a misleading source). Use a loose check:
    for subdir in ("videos", "audio", "audit", "final", "scenes"):
        # If the subdir is listed at all, it must be marked empty
        lines = [
            line for line in sources_block.splitlines()
            if line.strip().startswith(subdir + "/")
        ]
        for line in lines:
            assert "(empty)" in line, (
                f"Empty subdir {subdir}/ should be marked (empty), got: {line!r}"
            )


# ---------------------------------------------------------------------------
# build_review_dir — shared entry point for checkpoint + export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_review_dir_populates_all_subdirs(tmp_path: Path):
    """build_review_dir is a stage-agnostic builder that populates every
    subdirectory the pipeline can produce, in a single call.

    It is the public entry point shared by CheckpointController and
    ``claw drama export`` so both systems produce the identical layout.
    """
    from videoclaw.drama.checkpoint import build_review_dir
    from videoclaw.drama.models import (
        Character,
        ConsistencyManifest,
        DramaManager,
        DramaScene,
        DramaSeries,
        Episode,
    )

    # Character turnaround
    turnaround = tmp_path / "hero.png"
    turnaround.write_bytes(b"png")

    # Location reference
    loc_ref = tmp_path / "pool.png"
    loc_ref.write_bytes(b"loc")

    # Video file on disk (as if written by the executor)
    project_id = "build_proj_001"
    shots_dir = tmp_path / project_id / "shots"
    shots_dir.mkdir(parents=True)
    video_file = shots_dir / "ep01_s01_abcd1234.mp4"
    video_file.write_bytes(b"mp4")

    series = DramaSeries(
        series_id="build_test",
        title="Build Test",
        genre="test",
        synopsis="test",
    )
    series.characters.append(
        Character(
            name="Hero",
            description="p",
            reference_image=str(turnaround),
        )
    )
    series.consistency_manifest = ConsistencyManifest(
        scene_references={"Pool deck": str(loc_ref)},
    )
    scene = DramaScene(
        scene_id="ep01_s01",
        description="Arrival",
        visual_prompt="A shot.",
    )
    episode = Episode(
        episode_id="ep1",
        number=1,
        title="Pilot",
        synopsis="test",
        opening_hook="",
        scenes=[scene],
        project_id=project_id,
    )
    series.episodes.append(episode)

    drama_mgr = DramaManager(base_dir=tmp_path)
    drama_mgr.save(series)

    # Single call — must populate characters/, scenes/, videos/
    review_dir = build_review_dir(
        series,
        episode,
        deliverables_dir=tmp_path / "deliverables",
        projects_dir=tmp_path,
    )

    assert review_dir == tmp_path / "deliverables" / "build_test" / "ep01_pilot"
    assert (review_dir / "storyboard.md").exists()
    assert (review_dir / "characters" / "hero_turnaround.png").is_symlink()
    assert (review_dir / "scenes" / "pool_deck.png").is_symlink()
    videos = sorted((review_dir / "videos").iterdir())
    assert len(videos) == 1
    assert "s01_arrival" in videos[0].name

    # No empty placeholders
    for empty in ("audio", "audit", "final"):
        assert not (review_dir / empty).exists()


# ---------------------------------------------------------------------------
# _normalize_char_name — case-insensitive char-name → filename slug
# (Series-View plan Task 1)
# ---------------------------------------------------------------------------


class TestNormalizeCharName:
    def test_lowercase_collapses_to_slug(self):
        from videoclaw.drama.checkpoint import _normalize_char_name
        assert _normalize_char_name("Ivy") == "ivy"
        assert _normalize_char_name("IVY") == "ivy"

    def test_spaces_become_underscores(self):
        from videoclaw.drama.checkpoint import _normalize_char_name
        assert _normalize_char_name("Ivy Chen") == "ivy_chen"

    def test_strips_trailing_underscore(self):
        from videoclaw.drama.checkpoint import _normalize_char_name
        assert _normalize_char_name("Ivy ") == "ivy"

    def test_equivalence_with_slugify_for_clean_names(self):
        # Audit A2: prove byte-equivalence to _slugify for names without
        # leading punctuation. Documents that the migration in Task 5/10 is
        # safe for typical inputs.
        from videoclaw.drama.checkpoint import _normalize_char_name, _slugify
        for name in ["Ivy", "Ivy Chen", "Bob the Builder", "Marcus_Aurelius"]:
            assert _normalize_char_name(name) == _slugify(name), (
                f"divergence on {name!r}: "
                f"normalize={_normalize_char_name(name)!r} slugify={_slugify(name)!r}"
            )

    def test_diverges_from_slugify_on_leading_punct(self):
        # Audit A2: document the strip('_') divergence — only meaningful
        # for names with leading non-alnum chars (rare in practice but
        # explicit to guard future regressions).
        from videoclaw.drama.checkpoint import _normalize_char_name, _slugify
        # _slugify lower-cases + strips non-word chars + rstrips '_'; so
        # leading punctuation becomes a leading '_'. _normalize strips both.
        slug = _slugify("!Ivy")
        norm = _normalize_char_name("!Ivy")
        # if _slugify produces a leading underscore, _normalize must remove it
        if slug.startswith("_"):
            assert norm == slug.lstrip("_")
        else:
            assert norm == slug


# ---------------------------------------------------------------------------
# _episode_locations — extract per-episode location keys from scene descriptions
# (Series-View plan Task 2, with A9 whole-word upgrade)
# ---------------------------------------------------------------------------


class TestEpisodeLocations:
    def _make_ep(self, descriptions: list[str]):
        from videoclaw.drama.models import Episode, DramaScene
        ep = Episode(number=1)
        ep.scenes = [DramaScene(description=d) for d in descriptions]
        return ep

    def test_extracts_locations_via_whole_word_match(self):
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep([
            "Ivy stands by the Pool deck at sunset",
            "Colton enters the Server room",
        ])
        scene_ref_keys = {"Pool deck", "Server room", "Mansion lobby"}
        assert _episode_locations(ep, scene_ref_keys) == {"Pool deck", "Server room"}

    def test_returns_empty_when_no_match(self):
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep(["random scene unrelated to known locations"])
        assert _episode_locations(ep, {"Pool deck"}) == set()

    def test_case_insensitive(self):
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep(["walking by the pool deck area"])
        assert _episode_locations(ep, {"Pool deck"}) == {"Pool deck"}

    def test_empty_keys_returns_empty(self):
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep(["any description"])
        assert _episode_locations(ep, set()) == set()

    def test_whole_word_avoids_false_match(self):
        # Audit A9 regression: naive substring would match "carpool" → "pool";
        # whole-word regex must reject. Likewise "decking" must not match "deck".
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep(["the carpool deckhand walked away"])
        # "Pool deck" should NOT match "carpool deckhand" under whole-word rule
        assert _episode_locations(ep, {"Pool deck"}) == set()

    def test_multi_scene_aggregation(self):
        from videoclaw.drama.checkpoint import _episode_locations
        ep = self._make_ep([
            "Scene one in the Pool deck",
            "Scene two in the Mansion lobby",
            "Scene three back in the Pool deck",
        ])
        keys = {"Pool deck", "Mansion lobby", "Server room"}
        assert _episode_locations(ep, keys) == {"Pool deck", "Mansion lobby"}


# ---------------------------------------------------------------------------
# _episode_status — composed > audited > generating > pending
# (Series-View plan Task 3, with A7 enum fallback)
# ---------------------------------------------------------------------------


class TestEpisodeStatus:
    def test_pending_when_no_files(self, tmp_path):
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode
        ep = Episode(number=1)
        assert _episode_status(ep, tmp_path / "ep01") == "pending"

    def test_generating_when_videos_but_no_audit(self, tmp_path):
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode
        ep_dir = tmp_path / "ep01"
        (ep_dir / "videos").mkdir(parents=True)
        (ep_dir / "videos" / "s01.mp4").write_bytes(b"x")
        ep = Episode(number=1)
        assert _episode_status(ep, ep_dir) == "generating"

    def test_audited_when_videos_and_audit(self, tmp_path):
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode
        ep_dir = tmp_path / "ep01"
        (ep_dir / "videos").mkdir(parents=True)
        (ep_dir / "videos" / "s01.mp4").write_bytes(b"x")
        (ep_dir / "audit").mkdir(parents=True)
        (ep_dir / "audit" / "round_1.json").write_text("{}")
        ep = Episode(number=1)
        assert _episode_status(ep, ep_dir) == "audited"

    def test_composed_when_final_present(self, tmp_path):
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode
        ep_dir = tmp_path / "ep01"
        (ep_dir / "final").mkdir(parents=True)
        (ep_dir / "final" / "ep01_final.mp4").write_bytes(b"x")
        ep = Episode(number=1)
        assert _episode_status(ep, ep_dir) == "composed"

    def test_enum_completed_overrides_empty_disk(self, tmp_path):
        # Audit A7: when episode.status == COMPLETED, return "completed" even
        # if disk is empty (e.g., fresh checkpoint dir hasn't been built yet).
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode, EpisodeStatus
        ep = Episode(number=1)
        ep.status = EpisodeStatus.COMPLETED
        # ep_dir doesn't even exist on disk
        assert _episode_status(ep, tmp_path / "missing_ep") == "completed"

    def test_enum_failed_overrides_disk(self, tmp_path):
        # FAILED is a terminal state; disk evidence shouldn't override.
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode, EpisodeStatus
        ep_dir = tmp_path / "ep01"
        (ep_dir / "videos").mkdir(parents=True)
        (ep_dir / "videos" / "s01.mp4").write_bytes(b"x")
        ep = Episode(number=1)
        ep.status = EpisodeStatus.FAILED
        assert _episode_status(ep, ep_dir) == "failed"

    def test_enum_generating_yields_to_disk_detail(self, tmp_path):
        # GENERATING is an in-progress state; let disk refine to the
        # specific stage if there's more evidence.
        from videoclaw.drama.checkpoint import _episode_status
        from videoclaw.drama.models import Episode, EpisodeStatus
        ep_dir = tmp_path / "ep01"
        (ep_dir / "final").mkdir(parents=True)
        (ep_dir / "final" / "ep01.mp4").write_bytes(b"x")
        ep = Episode(number=1)
        ep.status = EpisodeStatus.GENERATING
        # disk shows composed; we trust disk for in-progress refinement
        assert _episode_status(ep, ep_dir) == "composed"


# ---------------------------------------------------------------------------
# _relative_symlink_to_series_root — episode dirs symlink back to series root
# (Series-View plan Task 4, with A4 user-file preservation)
# ---------------------------------------------------------------------------


class TestRelativeSymlinkToSeriesRoot:
    def test_creates_relative_symlink(self, tmp_path):
        from videoclaw.drama.checkpoint import _relative_symlink_to_series_root
        series_root = tmp_path / "series"
        chars = series_root / "characters"
        chars.mkdir(parents=True)
        src = chars / "ivy.png"
        src.write_bytes(b"x")
        dst = series_root / "ep01" / "characters" / "ivy.png"
        _relative_symlink_to_series_root(src, dst)
        import os
        assert dst.is_symlink()
        assert os.readlink(dst) == "../../characters/ivy.png"
        assert dst.resolve() == src.resolve()

    def test_replaces_existing_symlink(self, tmp_path):
        from videoclaw.drama.checkpoint import _relative_symlink_to_series_root
        series_root = tmp_path / "s"
        (series_root / "characters").mkdir(parents=True)
        src = series_root / "characters" / "ivy.png"
        src.write_bytes(b"x")
        dst = series_root / "ep01" / "characters" / "ivy.png"
        dst.parent.mkdir(parents=True)
        # Stale flat symlink (legacy migration case)
        old_target = tmp_path / "old_target.png"
        old_target.write_bytes(b"old")
        dst.symlink_to(old_target)
        _relative_symlink_to_series_root(src, dst)
        import os
        assert os.readlink(dst) == "../../characters/ivy.png"

    def test_preserves_user_placed_real_file(self, tmp_path, caplog):
        # Audit A4: a real file at dst means the human edited it during
        # an audit pause. Must NEVER silently delete; rename to .user.bak
        # and log a warning so the user can recover.
        import logging
        from videoclaw.drama.checkpoint import _relative_symlink_to_series_root

        series_root = tmp_path / "s"
        (series_root / "characters").mkdir(parents=True)
        src = series_root / "characters" / "ivy.png"
        src.write_bytes(b"new")

        dst = series_root / "ep01" / "characters" / "ivy.png"
        dst.parent.mkdir(parents=True)
        # Simulate human placing a real file (not a symlink) at dst
        dst.write_bytes(b"user_swap")

        with caplog.at_level(logging.WARNING, logger="videoclaw.drama.checkpoint"):
            _relative_symlink_to_series_root(src, dst)

        # Original user file must survive as .user.bak
        backup = dst.parent / "ivy.png.user.bak"
        assert backup.exists(), "user file must be preserved as .user.bak"
        assert backup.read_bytes() == b"user_swap"

        # New symlink in place pointing at the series root file
        assert dst.is_symlink()
        assert dst.resolve() == src.resolve()

        # Warning was logged so user can find the backup
        assert any("user file" in r.message.lower() for r in caplog.records), (
            "must warn about preserved user file"
        )

    def test_creates_parent_dir_if_missing(self, tmp_path):
        from videoclaw.drama.checkpoint import _relative_symlink_to_series_root
        series_root = tmp_path / "s"
        (series_root / "characters").mkdir(parents=True)
        src = series_root / "characters" / "ivy.png"
        src.write_bytes(b"x")
        # dst's parent doesn't exist yet
        dst = series_root / "ep_new" / "characters" / "ivy.png"
        _relative_symlink_to_series_root(src, dst)
        assert dst.is_symlink()


# ---------------------------------------------------------------------------
# Series-level real-source dirs (Tasks 5 & 6)
# ---------------------------------------------------------------------------


class TestUpdateSeriesCharactersDir:
    def test_creates_symlinks_for_each_character(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_characters_dir
        from videoclaw.drama.models import DramaSeries, Character
        src_dir = tmp_path / "projects" / "characters"
        src_dir.mkdir(parents=True)
        ivy_src = src_dir / "ivy.png"
        ivy_src.write_bytes(b"x")
        colton_src = src_dir / "colton.png"
        colton_src.write_bytes(b"y")
        series = DramaSeries(title="t", series_id="abc")
        series.characters = [
            Character(name="Ivy", reference_image=str(ivy_src)),
            Character(name="Colton", reference_image=str(colton_src)),
        ]
        chars_dir = tmp_path / "deliverables" / "t" / "characters"
        _update_series_characters_dir(series, chars_dir)
        assert (chars_dir / "ivy_turnaround.png").is_symlink()
        assert (chars_dir / "colton_turnaround.png").is_symlink()

    def test_writes_url_file_when_present(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_characters_dir
        from videoclaw.drama.models import DramaSeries, Character
        series = DramaSeries(title="t", series_id="abc")
        series.characters = [
            Character(name="Ivy", reference_image_url="https://x/ivy.png"),
        ]
        chars_dir = tmp_path / "characters"
        _update_series_characters_dir(series, chars_dir)
        assert (chars_dir / "ivy_url.txt").read_text() == "https://x/ivy.png"

    def test_lazy_no_chars_no_dir(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_characters_dir
        from videoclaw.drama.models import DramaSeries
        series = DramaSeries(title="t", series_id="abc")
        chars_dir = tmp_path / "characters"
        _update_series_characters_dir(series, chars_dir)
        assert not chars_dir.exists()


class TestUpdateSeriesScenesDir:
    def test_symlinks_each_scene_reference(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_scenes_dir
        from videoclaw.drama.models import DramaSeries, ConsistencyManifest
        pool_src = tmp_path / "pool.png"
        pool_src.write_bytes(b"x")
        room_src = tmp_path / "server.png"
        room_src.write_bytes(b"y")
        series = DramaSeries(title="t", series_id="abc")
        series.consistency_manifest = ConsistencyManifest(
            scene_references={"Pool deck": str(pool_src), "Server room": str(room_src)},
        )
        scenes_dir = tmp_path / "out" / "scenes"
        _update_series_scenes_dir(series, scenes_dir)
        assert (scenes_dir / "pool_deck.png").is_symlink()
        assert (scenes_dir / "server_room.png").is_symlink()

    def test_lazy_no_refs_no_dir(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_scenes_dir
        from videoclaw.drama.models import DramaSeries
        series = DramaSeries(title="t", series_id="abc")
        scenes_dir = tmp_path / "scenes"
        _update_series_scenes_dir(series, scenes_dir)
        assert not scenes_dir.exists()

    def test_skips_missing_source_files(self, tmp_path):
        from videoclaw.drama.checkpoint import _update_series_scenes_dir
        from videoclaw.drama.models import DramaSeries, ConsistencyManifest
        series = DramaSeries(title="t", series_id="abc")
        series.consistency_manifest = ConsistencyManifest(
            scene_references={"Ghost": "/nonexistent/ghost.png"},
        )
        scenes_dir = tmp_path / "scenes"
        _update_series_scenes_dir(series, scenes_dir)
        assert not scenes_dir.exists()


# ---------------------------------------------------------------------------
# _series_root_for — single source of series_slug derivation (Task 9a per A8)
# ---------------------------------------------------------------------------


class TestSeriesRootFor:
    def test_uses_slugified_title(self, tmp_path):
        from videoclaw.drama.checkpoint import _series_root_for
        from videoclaw.drama.models import DramaSeries
        series = DramaSeries(
            title="Satan in a Suit",
            series_id="abc1234567890",
        )
        assert _series_root_for(series, tmp_path) == tmp_path / "satan_in_a_suit"

    def test_falls_back_to_series_id_prefix_when_no_title(self, tmp_path):
        from videoclaw.drama.checkpoint import _series_root_for
        from videoclaw.drama.models import DramaSeries
        series = DramaSeries(title="", series_id="abcdef1234567890")
        assert _series_root_for(series, tmp_path) == tmp_path / "abcdef12"

    def test_matches_review_dir_for_episode_series_part(self, tmp_path):
        # Critical drift guard: this helper must produce the same series-slug
        # path that review_dir_for_episode uses (which is the canonical
        # series-root location). If they diverge, _SERIES.md links will 404.
        from videoclaw.drama.checkpoint import _series_root_for, review_dir_for_episode
        from videoclaw.drama.models import DramaSeries, Episode
        series = DramaSeries(title="My Drama", series_id="x")
        ep = Episode(number=1, title="Pilot")
        ep_dir = review_dir_for_episode(series, ep, tmp_path)
        # ep_dir.parent must equal _series_root_for(series, tmp_path)
        assert ep_dir.parent == _series_root_for(series, tmp_path)
