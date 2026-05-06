"""Tests for ``claw setup`` -- the skills installer.

Covers detection, install/uninstall, idempotency, dry-run, and the
``videoclaw-setup-skills/v1`` envelope.  Filesystem isolation via
``tmp_path`` so the tests never touch the developer's real
``~/.claude/skills/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import videoclaw
from videoclaw.cli import setup as _skills_setup


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    """Build a fake $HOME with all three supported agent dirs present."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".codex" / "skills").mkdir(parents=True)
    (tmp_path / ".openclaw-autoclaw" / "skills").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def fake_skills_root(tmp_path: Path) -> Path:
    """Build a fake skills/ root with two videoclaw-* skill dirs."""
    root = tmp_path / "_skills_src"
    for name in ("videoclaw-workflow", "videoclaw-models"):
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\nmetadata:\n  version: {videoclaw.__version__}\n---\nbody\n"
        )
    return root


def test_agent_targets_detection_partial(tmp_path: Path) -> None:
    """Only agents whose root dir exists are detected."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    targets = _skills_setup._agent_targets(tmp_path)
    detected = _skills_setup._detect(targets)
    ids = {t.id for t in detected}
    assert ids == {"claude_code", "codex"}


def test_agent_targets_naming() -> None:
    """OpenClaw uses versioned naming; Claude / Codex use flat."""
    targets = _skills_setup._agent_targets(Path("/tmp/fake"))
    by_id = {t.id: t for t in targets}
    assert (
        by_id["claude_code"].install_dirname("videoclaw-workflow", "0.1.0")
        == "videoclaw-workflow"
    )
    assert (
        by_id["codex"].install_dirname("videoclaw-workflow", "0.1.0")
        == "videoclaw-workflow"
    )
    assert (
        by_id["openclaw"].install_dirname("videoclaw-workflow", "0.1.0")
        == "videoclaw-workflow-0.1.0"
    )


def test_install_one_creates(fake_home: Path, fake_skills_root: Path) -> None:
    targets = _skills_setup._agent_targets(fake_home)
    skill = fake_skills_root / "videoclaw-workflow"
    target = next(t for t in targets if t.id == "claude_code")

    rec = _skills_setup._install_one(skill, target, version="0.1.0", dry_run=False)

    assert rec["action"] == "created"
    assert (fake_home / ".claude" / "skills" / "videoclaw-workflow" / "SKILL.md").is_file()


def test_install_one_idempotent_skip_current(fake_home: Path, fake_skills_root: Path) -> None:
    """Re-running install when the same content is already there returns skip-current."""
    targets = _skills_setup._agent_targets(fake_home)
    skill = fake_skills_root / "videoclaw-workflow"
    target = next(t for t in targets if t.id == "claude_code")

    _skills_setup._install_one(skill, target, version="0.1.0", dry_run=False)
    rec2 = _skills_setup._install_one(skill, target, version="0.1.0", dry_run=False)

    assert rec2["action"] == "skip-current"


def test_install_one_dry_run_no_write(fake_home: Path, fake_skills_root: Path) -> None:
    targets = _skills_setup._agent_targets(fake_home)
    skill = fake_skills_root / "videoclaw-workflow"
    target = next(t for t in targets if t.id == "claude_code")

    rec = _skills_setup._install_one(skill, target, version="0.1.0", dry_run=True)

    assert rec["action"] == "would-create"
    assert not (fake_home / ".claude" / "skills" / "videoclaw-workflow").exists()


def test_install_one_versioned_naming_openclaw(fake_home: Path, fake_skills_root: Path) -> None:
    targets = _skills_setup._agent_targets(fake_home)
    skill = fake_skills_root / "videoclaw-workflow"
    openclaw = next(t for t in targets if t.id == "openclaw")

    rec = _skills_setup._install_one(skill, openclaw, version="0.1.0", dry_run=False)

    assert rec["action"] == "created"
    assert (
        fake_home / ".openclaw-autoclaw" / "skills" / "videoclaw-workflow-0.1.0" / "SKILL.md"
    ).is_file()
    assert not (fake_home / ".openclaw-autoclaw" / "skills" / "videoclaw-workflow").exists()


def test_uninstall_one_removes_only_videoclaw_dirs(fake_home: Path) -> None:
    """uninstall should remove `videoclaw-*` and leave foreign skills alone."""
    skills_dir = fake_home / ".claude" / "skills"
    (skills_dir / "videoclaw-workflow").mkdir()
    (skills_dir / "videoclaw-workflow" / "SKILL.md").write_text("body\n")
    (skills_dir / "videoclaw-models").mkdir()
    (skills_dir / "videoclaw-models" / "SKILL.md").write_text("body\n")
    (skills_dir / "some-other-skill").mkdir()
    (skills_dir / "some-other-skill" / "SKILL.md").write_text("body\n")

    targets = _skills_setup._agent_targets(fake_home)
    target = next(t for t in targets if t.id == "claude_code")

    records = _skills_setup._uninstall_one(target)

    assert len(records) == 2
    assert all(r["action"] == "removed" for r in records)
    assert not (skills_dir / "videoclaw-workflow").exists()
    assert not (skills_dir / "videoclaw-models").exists()
    assert (skills_dir / "some-other-skill").exists()


def test_resolve_skills_root_finds_repo_local() -> None:
    """In the dev / editable-install layout, we should find <repo>/skills/."""
    root = _skills_setup._resolve_skills_root()
    assert root is not None
    assert (root / "videoclaw-workflow" / "SKILL.md").is_file()


def test_setup_command_dry_run_envelope(
    fake_home: Path,
    fake_skills_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`claw setup --dry-run --json` returns a videoclaw-setup-skills/v1 envelope."""
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(_skills_setup.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(_skills_setup, "_resolve_skills_root", lambda: fake_skills_root)

    from videoclaw.cli._output import get_output

    out = get_output()
    out.json_mode = True
    try:
        _skills_setup.setup(agent=None, dry_run=True, uninstall=False)
    finally:
        out.json_mode = False
    captured = capsys.readouterr()
    envelope = json.loads(captured.out.strip().splitlines()[-1])

    assert envelope["schema"] == "videoclaw-setup-skills/v1"
    assert envelope["ok"] is True
    assert envelope["command"] == "setup"
    assert "agents_detected" in envelope["data"]
    assert set(envelope["data"]["agents_detected"]) == {"claude_code", "codex", "openclaw"}
    # Dry-run should not have written anything
    assert not (fake_home / ".claude" / "skills" / "videoclaw-workflow").exists()
    # 3 agents × 2 skills = 6 would-create records
    assert len(envelope["data"]["skills_installed"]) == 6
    assert all(r["action"] == "would-create" for r in envelope["data"]["skills_installed"])


def test_setup_command_install_then_idempotent(
    fake_home: Path,
    fake_skills_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run install twice; second run should report all skills as skipped-current."""
    monkeypatch.setattr(_skills_setup.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(_skills_setup, "_resolve_skills_root", lambda: fake_skills_root)

    from videoclaw.cli._output import get_output

    out = get_output()
    out.json_mode = True
    try:
        # First run -- creates everything
        _skills_setup.setup(agent=None, dry_run=False, uninstall=False)
        first = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert len(first["data"]["skills_installed"]) == 6
        assert len(first["data"]["skills_skipped"]) == 0

        # Second run -- everything should be skip-current
        _skills_setup.setup(agent=None, dry_run=False, uninstall=False)
        second = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert len(second["data"]["skills_installed"]) == 0
        assert len(second["data"]["skills_skipped"]) == 6
        assert all(r["action"] == "skip-current" for r in second["data"]["skills_skipped"])
    finally:
        out.json_mode = False


def test_setup_unknown_agent_exits_2(
    fake_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_skills_setup.Path, "home", classmethod(lambda cls: fake_home))
    import typer

    with pytest.raises(typer.Exit) as exc_info:
        _skills_setup.setup(agent="bogus_agent", dry_run=True, uninstall=False)
    assert exc_info.value.exit_code == 2
