"""CLI tests for the series-view + export commands (Tasks 14 and 15)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from videoclaw import config as cfg
from videoclaw.cli._app import drama_app
from videoclaw.drama.models import (
    Character,
    DramaManager,
    DramaScene,
    DramaSeries,
    Episode,
)

# Side-effect import registers `series-view` / `export` on drama_app.
import videoclaw.cli.drama  # noqa: F401


@pytest.fixture
def configured_paths(tmp_path, monkeypatch):
    """Point the config singleton at tmp dirs for the duration of the test.

    A1/A9: mutating the already-built singleton is insufficient — future
    ``get_config()`` calls hit the lru_cache. Clear it so the CLI, which
    re-calls ``get_config()`` inside the command body, sees tmp paths.
    """
    projects = tmp_path / "projects"
    deliv = tmp_path / "deliv"
    projects.mkdir()
    monkeypatch.setenv("VIDEOCLAW_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("VIDEOCLAW_DELIVERABLES_DIR", str(deliv))
    cfg.get_config.cache_clear()
    yield projects, deliv
    cfg.get_config.cache_clear()


def _make_series(projects: Path, chars_src: Path, *, with_scene: bool = False) -> DramaSeries:
    series = DramaSeries(title="t", series_id="abc1234")
    series.characters = [
        Character(name="Ivy", reference_image=str(chars_src / "ivy.png"))
    ]
    ep = Episode(number=1, title="ep1")
    if with_scene:
        ep.scenes = [DramaScene(description="Ivy enters", characters_present=["Ivy"])]
    series.episodes = [ep]
    DramaManager(base_dir=projects).save(series)
    return series


class TestSeriesViewCli:
    def test_series_view_creates_root(self, tmp_path, configured_paths):
        projects, deliv = configured_paths
        chars_src = tmp_path / "src"
        chars_src.mkdir()
        (chars_src / "ivy.png").write_bytes(b"x")
        _make_series(projects, chars_src)

        result = CliRunner().invoke(drama_app, ["series-view", "abc1234"])
        assert result.exit_code == 0, result.output
        assert (deliv / "t" / "_SERIES.md").exists()
        assert (deliv / "t" / "characters" / "ivy_turnaround.png").is_symlink()


class TestDramaExportBuildsSeriesView:
    def test_export_creates_series_md_at_root(self, tmp_path, configured_paths):
        projects, deliv = configured_paths
        chars_src = tmp_path / "src"
        chars_src.mkdir()
        (chars_src / "ivy.png").write_bytes(b"x")
        _make_series(projects, chars_src, with_scene=True)

        result = CliRunner().invoke(drama_app, ["export", "abc1234", "-e", "1"])
        assert result.exit_code == 0, result.output
        assert (deliv / "t" / "_SERIES.md").exists()
        assert (deliv / "t" / "characters" / "ivy_turnaround.png").is_symlink()
        # Per-ep filtered chain goes through the series root
        assert (
            deliv / "t" / "ep01_ep1" / "characters" / "ivy_turnaround.png"
        ).is_symlink()
