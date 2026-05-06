"""``claw setup`` -- install videoclaw skills into detected coding agents.

Mirrors the google/agents-cli model: detect which coding agents are
installed locally, copy the ``videoclaw-*`` skills (bundled at
``videoclaw/_skills/`` in the wheel / PyInstaller binary) into each
agent's skill directory.  Per-agent naming differs --- Claude Code /
Codex use flat ``videoclaw-workflow/`` directories; OpenClaw expects
versioned ``videoclaw-workflow-0.1.0/``.

Skills source resolution order:

1. PyInstaller frozen binary --- ``sys._MEIPASS/videoclaw/_skills/``
2. Wheel / pip install --- ``importlib.resources.files("videoclaw") / "_skills"``
3. Editable install / repo --- ``<repo_root>/skills/``

Output is the ``videoclaw-setup-skills/v1`` envelope (custom schema,
distinct from the default ``{ok, version, command, data, error}`` so
orchestrators can dispatch on it).
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

import videoclaw
from videoclaw.cli._app import app
from videoclaw.cli._output import get_console, get_output

SKILL_PREFIX = "videoclaw-"


@dataclass(frozen=True)
class AgentTarget:
    """One coding-agent skill installation target."""

    id: str
    label: str
    skills_dir: Path
    naming: Literal["flat", "versioned"]

    def install_dirname(self, skill_name: str, version: str) -> str:
        return f"{skill_name}-{version}" if self.naming == "versioned" else skill_name


def _agent_targets(home: Path) -> list[AgentTarget]:
    return [
        AgentTarget("claude_code", "Claude Code", home / ".claude" / "skills", "flat"),
        AgentTarget("codex", "Codex", home / ".codex" / "skills", "flat"),
        AgentTarget(
            "openclaw",
            "OpenClaw",
            home / ".openclaw-autoclaw" / "skills",
            "versioned",
        ),
    ]


def _detect(targets: list[AgentTarget]) -> list[AgentTarget]:
    """Keep targets whose agent root (e.g. ``~/.claude``) exists."""
    return [t for t in targets if t.skills_dir.parent.is_dir()]


def _resolve_skills_root() -> Path | None:
    """Locate the bundled skills directory. ``None`` if not found."""
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "videoclaw" / "_skills"
        if candidate.is_dir():
            return candidate

    try:
        from importlib.resources import files

        resource = files("videoclaw").joinpath("_skills")
        path = Path(str(resource))
        if path.is_dir():
            return path
    except (ImportError, ModuleNotFoundError, FileNotFoundError):
        pass

    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent.parent / "skills",
        Path.cwd() / "skills",
    ]
    for c in candidates:
        if c.is_dir() and (c / "videoclaw-workflow").is_dir():
            return c
    return None


def _list_skill_dirs(root: Path) -> list[Path]:
    return sorted(
        d for d in root.iterdir() if d.is_dir() and d.name.startswith(SKILL_PREFIX)
    )


def _install_one(
    skill_dir: Path, target: AgentTarget, version: str, dry_run: bool
) -> dict[str, Any]:
    """Install one skill into one target. Returns an action record."""
    dest_name = target.install_dirname(skill_dir.name, version)
    dest = target.skills_dir / dest_name
    record: dict[str, Any] = {
        "agent": target.id,
        "skill": skill_dir.name,
        "path": str(dest),
        "version": version,
    }
    if dest.is_dir():
        src_md = skill_dir / "SKILL.md"
        dst_md = dest / "SKILL.md"
        if dst_md.is_file() and dst_md.read_bytes() == src_md.read_bytes():
            record["action"] = "skip-current"
            return record
        record["action"] = "skip-conflict"
        return record
    if dry_run:
        record["action"] = "would-create"
        return record
    target.skills_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, dest)
    record["action"] = "created"
    return record


def _uninstall_one(target: AgentTarget) -> list[dict[str, Any]]:
    """Remove every ``videoclaw-*`` directory from ``target.skills_dir``."""
    if not target.skills_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for d in sorted(target.skills_dir.iterdir()):
        if d.is_dir() and d.name.startswith(SKILL_PREFIX):
            shutil.rmtree(d)
            records.append(
                {
                    "agent": target.id,
                    "skill": d.name,
                    "path": str(d),
                    "action": "removed",
                }
            )
    return records


def _emit_envelope(data: dict[str, Any], ok: bool, error: str | None) -> None:
    """Write the ``videoclaw-setup-skills/v1`` envelope to stdout."""
    envelope = {
        "schema": "videoclaw-setup-skills/v1",
        "ok": ok,
        "version": videoclaw.__version__,
        "command": "setup",
        "data": data,
        "error": error,
    }
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()


@app.command()
def setup(
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            "-a",
            help="Install to one specific agent only (claude_code / codex / openclaw).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview targets but write nothing."),
    ] = False,
    uninstall: Annotated[
        bool,
        typer.Option("--uninstall", help="Remove all videoclaw-* skills from detected agents."),
    ] = False,
) -> None:
    """Install videoclaw skills into detected coding agents."""
    out = get_output()
    out._command = "setup"
    console = get_console()

    home = Path.home()
    targets = _agent_targets(home)
    if agent:
        targets = [t for t in targets if t.id == agent]
        if not targets:
            msg = (
                f"unknown agent: {agent!r} "
                "(known: claude_code, codex, openclaw)"
            )
            if out.json_mode:
                _emit_envelope({}, ok=False, error=msg)
            else:
                console.print(f"[red]error[/red]: {msg}")
            raise typer.Exit(code=2)

    detected = _detect(targets)
    version = videoclaw.__version__

    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    error: str | None = None

    if uninstall:
        for t in detected:
            removed.extend(_uninstall_one(t))
    else:
        skills_root = _resolve_skills_root()
        if skills_root is None:
            error = (
                "bundled skills/ not found "
                "(looked in _MEIPASS, importlib.resources, repo-local)"
            )
        else:
            skill_dirs = _list_skill_dirs(skills_root)
            for t in detected:
                for s in skill_dirs:
                    rec = _install_one(s, t, version, dry_run)
                    if rec["action"] in {"created", "would-create"}:
                        installed.append(rec)
                    else:
                        skipped.append(rec)

    next_steps: list[str]
    if error:
        next_steps = []
    elif not detected:
        next_steps = [
            "install one of: Claude Code (~/.claude/), Codex (~/.codex/), "
            "OpenClaw (~/.openclaw-autoclaw/)"
        ]
    elif uninstall:
        next_steps = []
    elif dry_run:
        next_steps = [f"re-run without --dry-run to install {len(installed)} skill(s)"]
    else:
        next_steps = [
            "restart your coding agent, then say 'use videoclaw to make a drama'"
        ]

    data: dict[str, Any] = {
        "agents_detected": [t.id for t in detected],
        "skills_installed": installed,
        "skills_skipped": skipped,
        "skills_removed": removed,
        "next_steps": next_steps,
    }

    if out.json_mode:
        _emit_envelope(data, ok=error is None, error=error)
        if error is not None:
            raise typer.Exit(code=1)
        return

    console.print(f"[bold cyan]videoclaw[/bold cyan] setup v{version}")
    if error:
        console.print(f"[red]error[/red]: {error}")
        raise typer.Exit(code=1)
    if not detected:
        console.print("[yellow]No supported coding agents detected on this host.[/yellow]")
        for step in next_steps:
            console.print(f"  → {step}")
        return
    console.print(
        f"Detected: {', '.join(t.label for t in detected)}"
    )
    if uninstall:
        console.print(f"Removed {len(removed)} skill(s) from {len(detected)} agent(s).")
        return
    if dry_run:
        console.print(
            f"[yellow]Dry-run[/yellow] — would install {len(installed)} skill(s):"
        )
    else:
        console.print(
            f"Installed {len(installed)} skill(s) across {len(detected)} agent(s):"
        )
    for rec in installed:
        console.print(f"  • {rec['agent']}: {rec['path']}")
    if skipped:
        console.print(f"Skipped {len(skipped)} (already current).")
    for step in next_steps:
        console.print(f"\n[dim]{step}[/dim]")
