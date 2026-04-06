"""Tests for project state management."""

import json
from pathlib import Path

import pytest

from videoclaw.core.state import ProjectState, Shot, ShotStatus, StateManager


def test_project_state_roundtrip():
    ps = ProjectState(prompt="test video")
    ps.storyboard = [
        Shot(description="shot 1", prompt="a cat"),
        Shot(description="shot 2", prompt="a dog", status=ShotStatus.COMPLETED),
    ]
    data = ps.to_dict()
    restored = ProjectState.from_dict(data)
    assert restored.project_id == ps.project_id
    assert restored.prompt == "test video"
    assert len(restored.storyboard) == 2
    assert restored.storyboard[1].status == ShotStatus.COMPLETED


def test_state_manager_crud(tmp_path: Path):
    mgr = StateManager(projects_dir=tmp_path)

    ps = mgr.create_project("hello world")
    assert (tmp_path / ps.project_id / "state.json").exists()

    loaded = mgr.load(ps.project_id)
    assert loaded.prompt == "hello world"

    ps.storyboard = [Shot(shot_id="s1", description="test")]
    mgr.save(ps)
    mgr.update_shot(ps.project_id, "s1", status=ShotStatus.COMPLETED)
    updated = mgr.load(ps.project_id)
    assert updated.storyboard[0].status == ShotStatus.COMPLETED

    assert ps.project_id in mgr.list_projects()


# ---------------------------------------------------------------------------
# Compact JSON serialization (P1#6)
# ---------------------------------------------------------------------------


def test_save_produces_compact_json(tmp_path: Path):
    """StateManager.save() must write compact JSON (no indentation)."""
    mgr = StateManager(projects_dir=tmp_path)
    ps = mgr.create_project("compact test")
    path = mgr.save(ps)
    raw = path.read_text(encoding="utf-8")
    # Compact JSON has no trailing newline or spaces after colons/commas
    assert "\n" not in raw
    # Can round-trip fine
    data = json.loads(raw)
    assert data["prompt"] == "compact test"


# ---------------------------------------------------------------------------
# Async save (P0#2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_async_roundtrip(tmp_path: Path):
    """save_async() must produce the same on-disk result as save()."""
    mgr = StateManager(projects_dir=tmp_path)
    ps = mgr.create_project("async test")
    path = await mgr.save_async(ps)
    assert path.exists()
    loaded = mgr.load(ps.project_id)
    assert loaded.prompt == "async test"


@pytest.mark.asyncio
async def test_save_async_compact_json(tmp_path: Path):
    """save_async() must write compact (non-indented) JSON."""
    mgr = StateManager(projects_dir=tmp_path)
    ps = mgr.create_project("async compact")
    path = await mgr.save_async(ps)
    raw = path.read_text(encoding="utf-8")
    assert "\n" not in raw
