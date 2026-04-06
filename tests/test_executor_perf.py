"""Tests for DAGExecutor performance features: checkpoint batching (P0#3) and async I/O (P0#2)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videoclaw.core.executor import DAGExecutor
from videoclaw.core.planner import DAG, TaskNode, TaskType
from videoclaw.core.state import ProjectState, Shot, StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _single_node_dag() -> tuple[DAG, ProjectState]:
    """Minimal DAG with one VIDEO_GEN node."""
    ps = ProjectState(prompt="perf test")
    ps.storyboard = [Shot(shot_id="s1", prompt="test", duration_seconds=3.0)]
    dag = DAG()
    dag.add_node(TaskNode(node_id="s1", task_type=TaskType.VIDEO_GEN))
    return dag, ps


def _n_node_dag(n: int) -> tuple[DAG, ProjectState]:
    """DAG with n sequential VIDEO_GEN nodes."""
    ps = ProjectState(prompt="perf test")
    ps.storyboard = [
        Shot(shot_id=f"s{i}", prompt=f"shot {i}", duration_seconds=3.0)
        for i in range(n)
    ]
    dag = DAG()
    prev = None
    for i in range(n):
        node = TaskNode(node_id=f"s{i}", task_type=TaskType.VIDEO_GEN)
        dag.add_node(node)
        if prev is not None:
            dag.add_edge(prev, f"s{i}")
        prev = f"s{i}"
    return dag, ps


# ---------------------------------------------------------------------------
# Checkpoint batching (P0#3)
# ---------------------------------------------------------------------------


class TestCheckpointBatching:
    """_checkpoint() should write every _CHECKPOINT_INTERVAL nodes, not every node."""

    @pytest.mark.asyncio
    async def test_non_forced_checkpoints_batch(self, tmp_path: Path):
        """Intermediate checkpoints must batch at CHECKPOINT_INTERVAL."""
        sm = StateManager(projects_dir=tmp_path)
        dag, ps = _single_node_dag()
        sm.save(ps)

        save_calls: list[str] = []

        async def _mock_save_async(state: ProjectState) -> Path:
            save_calls.append("save")
            return tmp_path / state.project_id / "state.json"

        executor = DAGExecutor(dag=dag, state=ps, state_manager=sm)
        executor.state_manager.save_async = _mock_save_async  # type: ignore[method-assign]

        interval = DAGExecutor._CHECKPOINT_INTERVAL
        # Trigger (interval - 1) non-forced checkpoints — should produce 0 writes
        for _ in range(interval - 1):
            await executor._checkpoint(force=False)

        assert len(save_calls) == 0, "No write expected before interval is reached"

        # One more triggers the batch write
        await executor._checkpoint(force=False)
        assert len(save_calls) == 1, "Write must fire exactly at interval boundary"

    @pytest.mark.asyncio
    async def test_forced_checkpoint_always_writes(self, tmp_path: Path):
        """force=True must always write regardless of interval counter."""
        sm = StateManager(projects_dir=tmp_path)
        dag, ps = _single_node_dag()
        sm.save(ps)

        save_calls: list[str] = []

        async def _mock_save_async(state: ProjectState) -> Path:
            save_calls.append("save")
            return tmp_path / state.project_id / "state.json"

        executor = DAGExecutor(dag=dag, state=ps, state_manager=sm)
        executor.state_manager.save_async = _mock_save_async  # type: ignore[method-assign]

        await executor._checkpoint(force=True)
        await executor._checkpoint(force=True)
        assert len(save_calls) == 2

    @pytest.mark.asyncio
    async def test_forced_checkpoint_resets_counter(self, tmp_path: Path):
        """After a forced write, the interval counter resets so the next N non-forced don't write."""
        sm = StateManager(projects_dir=tmp_path)
        dag, ps = _single_node_dag()
        sm.save(ps)

        save_calls: list[str] = []

        async def _mock_save_async(state: ProjectState) -> Path:
            save_calls.append("save")
            return tmp_path / state.project_id / "state.json"

        executor = DAGExecutor(dag=dag, state=ps, state_manager=sm)
        executor.state_manager.save_async = _mock_save_async  # type: ignore[method-assign]

        await executor._checkpoint(force=True)  # 1 write, resets counter
        base_calls = len(save_calls)

        interval = DAGExecutor._CHECKPOINT_INTERVAL
        for _ in range(interval - 1):
            await executor._checkpoint(force=False)

        assert len(save_calls) == base_calls, "Counter was reset — no extra write expected yet"

    @pytest.mark.asyncio
    async def test_checkpoint_interval_is_five(self):
        """Interval must be exactly 5 (as documented in HANDOFF)."""
        assert DAGExecutor._CHECKPOINT_INTERVAL == 5


# ---------------------------------------------------------------------------
# Async checkpoint wires through save_async (P0#2)
# ---------------------------------------------------------------------------


class TestAsyncCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_calls_save_async(self, tmp_path: Path):
        """_checkpoint() must call save_async, not the blocking save()."""
        sm = StateManager(projects_dir=tmp_path)
        dag, ps = _single_node_dag()
        sm.save(ps)

        save_async_calls: list[str] = []
        save_sync_calls: list[str] = []

        async def _mock_save_async(state: ProjectState) -> Path:
            save_async_calls.append("async")
            return tmp_path / state.project_id / "state.json"

        def _mock_save(state: ProjectState) -> Path:
            save_sync_calls.append("sync")
            return tmp_path / state.project_id / "state.json"

        executor = DAGExecutor(dag=dag, state=ps, state_manager=sm)
        executor.state_manager.save_async = _mock_save_async  # type: ignore[method-assign]
        executor.state_manager.save = _mock_save  # type: ignore[method-assign]

        await executor._checkpoint(force=True)

        assert len(save_async_calls) == 1
        assert len(save_sync_calls) == 0, "Blocking save() must not be called from _checkpoint"
