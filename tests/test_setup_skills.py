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
        _skills_setup.setup(
            agent=None, dry_run=True, uninstall=False, copy_mode=False, no_npx=True
        )
    finally:
        out.json_mode = False
    captured = capsys.readouterr()
    envelope = json.loads(captured.out.strip().splitlines()[-1])

    assert envelope["schema"] == "videoclaw-setup-skills/v1"
    assert envelope["ok"] is True
    assert envelope["command"] == "setup"
    assert envelope["data"]["installer"] == "python-fallback"
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
        _skills_setup.setup(
            agent=None, dry_run=False, uninstall=False, copy_mode=False, no_npx=True
        )
        first = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert len(first["data"]["skills_installed"]) == 6
        assert len(first["data"]["skills_skipped"]) == 0

        # Second run -- everything should be skip-current
        _skills_setup.setup(
            agent=None, dry_run=False, uninstall=False, copy_mode=False, no_npx=True
        )
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
        _skills_setup.setup(
            agent="bogus_agent", dry_run=True, uninstall=False, copy_mode=False, no_npx=True
        )
    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# D2 — npx-skills delegation tests (M003)
# ---------------------------------------------------------------------------


def test_try_npx_skills_returns_none_when_npx_absent(
    monkeypatch: pytest.MonkeyPatch, fake_skills_root: Path
) -> None:
    """No `npx` on PATH → fall back (None) so caller picks python-fallback."""
    monkeypatch.setattr(_skills_setup.shutil, "which", lambda _: None)
    result = _skills_setup._try_npx_skills(
        action="install", copy_mode=False, skills_root=fake_skills_root
    )
    assert result is None


def test_try_npx_skills_invokes_correct_command(
    monkeypatch: pytest.MonkeyPatch, fake_skills_root: Path
) -> None:
    """The exact command line passed to subprocess.run is correct."""
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> object:
        captured.append(cmd)

        class _R:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return _R()

    monkeypatch.setattr(_skills_setup.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(_skills_setup.subprocess, "run", fake_run)
    _skills_setup._try_npx_skills(
        action="install", copy_mode=False, skills_root=fake_skills_root
    )

    add_cmd = next(c for c in captured if "add" in c)
    assert add_cmd[:3] == ["npx", "-y", _skills_setup.SKILLS_NPM_VERSION]
    assert "add" in add_cmd
    assert str(fake_skills_root) in add_cmd
    assert "-g" in add_cmd
    assert "--all" in add_cmd
    assert "-y" in add_cmd
    assert "--copy" not in add_cmd  # copy_mode=False


def test_try_npx_skills_copy_mode_appends_flag(
    monkeypatch: pytest.MonkeyPatch, fake_skills_root: Path
) -> None:
    """copy_mode=True appends --copy to the install command."""
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> object:
        captured.append(cmd)

        class _R:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return _R()

    monkeypatch.setattr(_skills_setup.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(_skills_setup.subprocess, "run", fake_run)
    _skills_setup._try_npx_skills(
        action="install", copy_mode=True, skills_root=fake_skills_root
    )

    add_cmd = next(c for c in captured if "add" in c)
    assert "--copy" in add_cmd


def test_setup_uses_fallback_when_no_npx_flag(
    fake_home: Path,
    fake_skills_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`setup(no_npx=True)` skips npx delegation even when npx is available."""
    npx_calls: list[str] = []
    monkeypatch.setattr(_skills_setup.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(
        _skills_setup,
        "_try_npx_skills",
        lambda **_kw: npx_calls.append("called") or None,  # type: ignore[func-returns-value]
    )
    monkeypatch.setattr(_skills_setup.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(_skills_setup, "_resolve_skills_root", lambda: fake_skills_root)

    from videoclaw.cli._output import get_output

    out = get_output()
    out.json_mode = True
    try:
        _skills_setup.setup(
            agent=None, dry_run=True, uninstall=False, copy_mode=False, no_npx=True
        )
    finally:
        out.json_mode = False

    envelope = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert envelope["data"]["installer"] == "python-fallback"
    assert npx_calls == [], "npx delegation must not be invoked when --no-npx is set"


def test_setup_envelope_installer_npx_when_delegation_succeeds(
    fake_home: Path,
    fake_skills_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When _try_npx_skills returns a dict, envelope.data.installer == 'npx-skills'."""
    monkeypatch.setattr(_skills_setup.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(_skills_setup, "_resolve_skills_root", lambda: fake_skills_root)
    monkeypatch.setattr(
        _skills_setup,
        "_try_npx_skills",
        lambda **_kw: {
            "ok": True,
            "error": None,
            "agents_detected": ["Claude Code", "Gemini CLI", "Antigravity"],
            "skills_installed": [
                {
                    "agent": "Claude Code,Gemini CLI,Antigravity",
                    "skill": "videoclaw-workflow",
                    "path": "/fake/path",
                    "version": videoclaw.__version__,
                    "action": "would-create",
                }
            ],
            "skills_skipped": [],
            "skills_removed": [],
        },
    )

    from videoclaw.cli._output import get_output

    out = get_output()
    out.json_mode = True
    try:
        _skills_setup.setup(
            agent=None, dry_run=True, uninstall=False, copy_mode=False, no_npx=False
        )
    finally:
        out.json_mode = False

    envelope = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert envelope["ok"] is True
    assert envelope["data"]["installer"] == "npx-skills"
    assert "Gemini CLI" in envelope["data"]["agents_detected"]
    assert "Antigravity" in envelope["data"]["agents_detected"]
