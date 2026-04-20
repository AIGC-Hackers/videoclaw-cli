"""Tests for shot-breakpoint propagation fixes (R1/R2/R3).

R1: ShotBreakpointError inherits BaseException, not Exception
R2: regenerate_scene subscribes to TASK_COMPLETED for review dir
R3: _subscribe_shot_review returns unsubscribe callable; callers clean up
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videoclaw.core.events import TASK_COMPLETED, EventBus
from videoclaw.drama.models import DramaScene, DramaSeries, Episode
from videoclaw.drama.runner import DramaRunner, ShotBreakpointError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_series() -> DramaSeries:
    """Minimal DramaSeries with one episode and two scenes."""
    series = DramaSeries(
        series_id="test_bp_series",
        title="Breakpoint Test",
        model_id="mock",
        aspect_ratio="9:16",
    )
    ep = Episode(number=1, title="Pilot")
    ep.scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="Scene one",
            duration_seconds=5.0,
        ),
        DramaScene(
            scene_id="ep01_s02",
            description="Scene two",
            duration_seconds=5.0,
        ),
    ]
    series.episodes = [ep]
    return series


# ---------------------------------------------------------------------------
# R1: ShotBreakpointError inheritance
# ---------------------------------------------------------------------------


def test_shot_breakpoint_error_inherits_base_exception() -> None:
    """ShotBreakpointError must be a BaseException, NOT an Exception."""
    assert issubclass(ShotBreakpointError, BaseException)
    assert not issubclass(ShotBreakpointError, Exception)


async def test_abort_propagates_through_event_bus() -> None:
    """BaseException-derived error escapes EventBus._safe_call + emit."""
    bus = EventBus()

    async def _raise_abort(_et: str, _data: dict[str, Any]) -> None:
        raise ShotBreakpointError("s01")

    bus.subscribe("test.event", _raise_abort)

    with pytest.raises(ShotBreakpointError):
        await bus.emit("test.event", {"node_id": "video_s01"})


async def test_abort_propagates_through_executor_run_node() -> None:
    """ShotBreakpointError escapes DAGExecutor._execute_node (not retried)."""
    from videoclaw.core.executor import DAGExecutor
    from videoclaw.core.planner import DAG, TaskNode, TaskType
    from videoclaw.core.state import ProjectState, Shot, ShotStatus

    dag = DAG()
    dag.add_node(TaskNode(
        node_id="video_s01",
        task_type=TaskType.VIDEO_GEN,
        params={"shot_id": "s01", "prompt": "test", "duration": 5},
    ))

    state = ProjectState(
        prompt="test",
        storyboard=[
            Shot(shot_id="s01", description="test", prompt="test",
                 duration_seconds=5, model_id="mock", status=ShotStatus.PENDING),
        ],
    )

    bus = EventBus()

    async def _raise_on_complete(_et: str, _data: dict[str, Any]) -> None:
        raise ShotBreakpointError("s01")

    bus.subscribe(TASK_COMPLETED, _raise_on_complete)

    executor = DAGExecutor(
        dag=dag,
        state=state,
        bus=bus,
        max_concurrency=1,
    )

    with pytest.raises(ShotBreakpointError):
        await executor.run()


async def test_run_episode_catches_shot_breakpoint_and_marks_failed() -> None:
    """run_episode catches ShotBreakpointError → episode FAILED + re-raises."""
    from videoclaw.drama.models import EpisodeStatus

    series = _make_series()
    ep = series.episodes[0]
    bus = EventBus()

    runner = DramaRunner(auto_refresh_urls=False)

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_episode_dag") as mock_build,
        patch("videoclaw.drama.runner.event_bus", bus),
        patch("videoclaw.drama.runner.DAGExecutor") as mock_exec_cls,
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_test"
        mock_state.status = MagicMock(value="completed")
        mock_state.cost_total = 0.0

        mock_dag = MagicMock()
        mock_build.return_value = (mock_dag, mock_state)
        mock_sm.save_async = AsyncMock()

        mock_exec = MagicMock()
        mock_exec.run = AsyncMock(side_effect=ShotBreakpointError("ep01_s01"))
        mock_exec.bus = bus
        mock_exec_cls.return_value = mock_exec

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        with pytest.raises(ShotBreakpointError) as exc_info:
            await runner.run_episode(series, ep, shot_breakpoint=True)

        assert exc_info.value.scene_id == "ep01_s01"
        assert ep.status == EpisodeStatus.FAILED
        assert "edit-shot" in str(exc_info.value)
        assert "checkpoint-resume" in str(exc_info.value)


# ---------------------------------------------------------------------------
# R3: subscribe / unsubscribe lifecycle
# ---------------------------------------------------------------------------


async def test_subscribe_unsubscribe_round_trip() -> None:
    """unsubscribe callable removes the handler from the bus."""
    bus = EventBus()
    call_count = 0

    async def _handler(_et: str, _data: dict[str, Any]) -> None:
        nonlocal call_count
        call_count += 1

    bus.subscribe(TASK_COMPLETED, _handler)
    await bus.emit(TASK_COMPLETED, {"node_id": "x"})
    assert call_count == 1

    bus.unsubscribe(TASK_COMPLETED, _handler)
    await bus.emit(TASK_COMPLETED, {"node_id": "y"})
    assert call_count == 1  # not called again


async def test_run_episode_cleans_up_subscription_on_success(tmp_path: Path) -> None:
    """After successful run_episode, no stale handlers remain on the bus."""
    bus = EventBus()
    series = _make_series()
    ep = series.episodes[0]

    runner = DramaRunner(auto_refresh_urls=False)

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_episode_dag") as mock_build,
        patch("videoclaw.drama.runner.event_bus", bus),
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_test"
        mock_state.status = MagicMock(value="completed")
        mock_state.cost_total = 0.0
        mock_state.assets = {}

        mock_dag = MagicMock()
        mock_dag.is_complete = True
        mock_dag.has_failures = False
        mock_dag.get_ready_nodes.return_value = []
        mock_dag.nodes = {}

        mock_build.return_value = (mock_dag, mock_state)
        mock_sm.save_async = AsyncMock()

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        # Record handlers before
        before_count = len(bus._handlers.get(TASK_COMPLETED, []))

        await runner.run_episode(series, ep)

        after_count = len(bus._handlers.get(TASK_COMPLETED, []))
        assert after_count == before_count


async def test_run_episode_cleans_up_subscription_on_failure(tmp_path: Path) -> None:
    """Even when pipeline raises, subscription is cleaned up (try/finally)."""
    bus = EventBus()
    series = _make_series()
    ep = series.episodes[0]

    runner = DramaRunner(auto_refresh_urls=False)

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_episode_dag") as mock_build,
        patch("videoclaw.drama.runner.event_bus", bus),
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_test"

        mock_dag = MagicMock()
        mock_build.return_value = (mock_dag, mock_state)
        mock_sm.save_async = AsyncMock()

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        # Make executor.run raise
        with patch("videoclaw.drama.runner.DAGExecutor") as mock_exec_cls:
            mock_exec_inst = MagicMock()
            mock_exec_inst.run = AsyncMock(side_effect=RuntimeError("boom"))
            mock_exec_inst.bus = bus
            mock_exec_cls.return_value = mock_exec_inst

            before_count = len(bus._handlers.get(TASK_COMPLETED, []))

            with pytest.raises(RuntimeError, match="boom"):
                await runner.run_episode(series, ep)

            after_count = len(bus._handlers.get(TASK_COMPLETED, []))
            assert after_count == before_count


async def test_run_series_no_handler_leak() -> None:
    """Running 2 episodes leaves no stale handlers on the bus."""
    bus = EventBus()
    series = _make_series()
    # Add a second episode
    ep2 = Episode(number=2, title="Episode Two")
    ep2.scenes = [
        DramaScene(scene_id="ep02_s01", description="Scene", duration_seconds=5.0),
    ]
    series.episodes.append(ep2)

    runner = DramaRunner(auto_refresh_urls=False)

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_episode_dag") as mock_build,
        patch("videoclaw.drama.runner.event_bus", bus),
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_test"
        mock_state.status = MagicMock(value="completed")
        mock_state.cost_total = 0.0
        mock_state.assets = {}

        mock_dag = MagicMock()
        mock_dag.is_complete = True
        mock_dag.has_failures = False
        mock_dag.get_ready_nodes.return_value = []
        mock_dag.nodes = {}

        mock_build.return_value = (mock_dag, mock_state)
        mock_sm.save_async = AsyncMock()

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        before_count = len(bus._handlers.get(TASK_COMPLETED, []))

        await runner.run_series(series)

        after_count = len(bus._handlers.get(TASK_COMPLETED, []))
        assert after_count == before_count


# ---------------------------------------------------------------------------
# R2: regenerate_scene triggers incremental review
# ---------------------------------------------------------------------------


async def test_regenerate_scene_updates_review_dir(tmp_path: Path) -> None:
    """regenerate_scene subscribes to TASK_COMPLETED → review dir updated."""
    series = _make_series()
    ep = series.episodes[0]
    ep.project_id = "proj_regen"

    runner = DramaRunner(auto_refresh_urls=False)

    from videoclaw.drama.checkpoint import CheckpointManager

    link_calls: list[tuple[str, str]] = []

    def _mock_link(
        _series: Any, _episode: Any, scene: Any, kind: str, src: Path,
        *, base_dir: Path,
    ) -> Path:
        link_calls.append((scene.scene_id, kind))
        return base_dir / "review" / f"{scene.scene_id}.mp4"

    fake_asset = tmp_path / "video_out.mp4"
    fake_asset.write_text("fake")

    real_bus = EventBus()

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_scene_regen_dag") as mock_regen_dag,
        patch("videoclaw.drama.runner.event_bus", real_bus),
        patch("videoclaw.drama.runner.DAGExecutor") as mock_exec_cls,
        patch("videoclaw.drama.runner.build_episode_dag") as mock_build,
        patch.object(
            CheckpointManager, "link_shot_asset", side_effect=_mock_link,
        ),
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_regen"
        mock_state.status = MagicMock(value="completed")
        mock_state.storyboard = []

        mock_sm.load_async = AsyncMock(return_value=mock_state)
        mock_sm.save_async = AsyncMock()

        mock_dag = MagicMock()
        mock_regen_dag.return_value = mock_dag
        mock_build.return_value = (mock_dag, mock_state)

        # Configure executor to emit TASK_COMPLETED via the real bus
        async def _fake_run() -> MagicMock:
            await real_bus.emit(TASK_COMPLETED, {
                "node_id": "video_ep01_s01",
                "task_type": "video_gen",
                "result": {"asset_path": str(fake_asset)},
            })
            return mock_state

        mock_exec = MagicMock()
        mock_exec.run = AsyncMock(side_effect=_fake_run)
        mock_exec.bus = real_bus
        mock_exec_cls.return_value = mock_exec

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        await runner.regenerate_scene(series, ep, "ep01_s01")

        assert any(sid == "ep01_s01" and k == "video" for sid, k in link_calls)


async def test_regenerate_scene_cleans_up_subscription() -> None:
    """After regenerate_scene, no stale handlers remain on the bus."""
    bus = EventBus()
    series = _make_series()
    ep = series.episodes[0]
    ep.project_id = "proj_regen2"

    runner = DramaRunner(auto_refresh_urls=False)

    with (
        patch.object(runner, "state_mgr") as mock_sm,
        patch("videoclaw.drama.runner.build_scene_regen_dag") as mock_regen_dag,
        patch("videoclaw.drama.runner.event_bus", bus),
        patch("videoclaw.drama.runner.DAGExecutor") as mock_exec_cls,
    ):
        mock_state = MagicMock()
        mock_state.project_id = "proj_regen2"
        mock_state.status = MagicMock(value="completed")
        mock_state.storyboard = []

        mock_sm.load_async = AsyncMock(return_value=mock_state)
        mock_sm.save_async = AsyncMock()

        mock_dag = MagicMock()
        mock_regen_dag.return_value = mock_dag

        mock_exec = MagicMock()
        mock_exec.run = AsyncMock(return_value=mock_state)
        mock_exec.bus = bus
        mock_exec_cls.return_value = mock_exec

        runner.drama_mgr = MagicMock()
        runner.drama_mgr.save_async = AsyncMock()

        before_count = len(bus._handlers.get(TASK_COMPLETED, []))

        await runner.regenerate_scene(series, ep, "ep01_s01")

        after_count = len(bus._handlers.get(TASK_COMPLETED, []))
        assert after_count == before_count
