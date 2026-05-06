"""``claw setup`` -- install videoclaw skills into detected coding agents.

Two installer paths are tried in order:

1. **npx-skills** (M003) --- when ``npx`` is on PATH, delegate to
   ``vercel-labs/skills`` (51+ supported agents incl. Gemini CLI,
   Antigravity, Windsurf, Cline, Trae, Kiro CLI, ...).  We pass the
   locally bundled ``_skills/`` directory so no network round-trip
   or GitHub repo dependency is required.
2. **python-fallback** (M002) --- the original installer covering
   Claude Code / Codex / OpenClaw with explicit per-agent path tables.
   Used when ``npx`` is missing or ``--no-npx`` is passed.

Per-agent naming in the fallback path: Claude Code / Codex use flat
``videoclaw-workflow/`` directories; OpenClaw expects versioned
``videoclaw-workflow-0.1.0/``.

Skills source resolution order:

1. PyInstaller frozen binary --- ``sys._MEIPASS/videoclaw/_skills/``
2. Wheel / pip install --- ``importlib.resources.files("videoclaw") / "_skills"``
3. Editable install / repo --- ``<repo_root>/skills/``

Output is the ``videoclaw-setup-skills/v1`` envelope (custom schema,
distinct from the default ``{ok, version, command, data, error}`` so
orchestrators can dispatch on it).  The ``data.installer`` field is
either ``"npx-skills"`` or ``"python-fallback"``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

import videoclaw
from videoclaw.cli._app import app
from videoclaw.cli._output import get_console, get_output

SKILL_PREFIX = "videoclaw-"
SKILLS_NPM_VERSION = "skills@1.5.5"


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


def _npx_list_videoclaw(env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Return ``npx skills list -g --json`` filtered to ``videoclaw-*`` skills.

    Returns ``[]`` on any failure (caller treats as empty pre/post state).
    """
    try:
        result = subprocess.run(
            ["npx", "-y", SKILLS_NPM_VERSION, "list", "-g", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [
        s
        for s in data
        if isinstance(s, dict) and str(s.get("name", "")).startswith(SKILL_PREFIX)
    ]


def _try_npx_skills(
    *,
    action: Literal["install", "uninstall", "dry_run"],
    copy_mode: bool,
    skills_root: Path | None,
) -> dict[str, Any] | None:
    """Delegate to ``vercel-labs/skills`` CLI. Returns ``None`` to fall back.

    On success returns a dict shaped like the python-fallback result
    (``agents_detected`` / ``skills_installed`` / ``skills_skipped`` /
    ``skills_removed`` / ``error``).  ``installer`` is set by the caller.
    """
    if shutil.which("npx") is None:
        return None
    if action != "uninstall" and skills_root is None:
        return None

    before = _npx_list_videoclaw()

    if action == "uninstall":
        # `skills remove` takes skill NAMES as positional args (not a glob).
        # Snapshot the currently-installed videoclaw-* skill names from `before`,
        # falling back to the bundled skills directory if the live list is empty
        # (e.g. user is uninstalling a partial state we can't see).
        names = sorted({s["name"] for s in before})
        if not names and skills_root is not None:
            names = sorted(
                d.name for d in skills_root.iterdir()
                if d.is_dir() and d.name.startswith(SKILL_PREFIX)
            )
        if not names:
            # Nothing to remove — return success with empty records.
            return {
                "ok": True,
                "error": None,
                "agents_detected": [],
                "skills_installed": [],
                "skills_skipped": [],
                "skills_removed": [],
            }
        cmd = ["npx", "-y", SKILLS_NPM_VERSION, "remove", *names, "-g", "-y"]
    else:
        cmd = [
            "npx",
            "-y",
            SKILLS_NPM_VERSION,
            "add",
            str(skills_root),
            "-g",
            "--all",
            "-y",
        ]
        if copy_mode:
            cmd.append("--copy")
        if action == "dry_run":
            cmd.append("--list")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"npx {SKILLS_NPM_VERSION} timed out after 300s",
            "agents_detected": [],
            "skills_installed": [],
            "skills_skipped": [],
            "skills_removed": [],
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "error": f"npx skills failed (exit {result.returncode}): {result.stderr.strip()[:500]}",
            "agents_detected": [],
            "skills_installed": [],
            "skills_skipped": [],
            "skills_removed": [],
        }

    after = _npx_list_videoclaw()
    return _build_npx_records(action, before, after)


def _build_npx_records(
    action: Literal["install", "uninstall", "dry_run"],
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build envelope-compatible records by diffing before/after npx state."""
    before_paths = {s["path"]: s for s in before}
    after_paths = {s["path"]: s for s in after}

    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    agents: set[str] = set()

    if action == "uninstall":
        for path, s in before_paths.items():
            if path not in after_paths:
                removed.append(
                    {
                        "agent": ",".join(s.get("agents", [])) or "unknown",
                        "skill": s["name"],
                        "path": path,
                        "action": "removed",
                    }
                )
            for a in s.get("agents", []):
                agents.add(a)
    else:
        new_action = "would-create" if action == "dry_run" else "created"
        for path, s in after_paths.items():
            for a in s.get("agents", []):
                agents.add(a)
            rec = {
                "agent": ",".join(s.get("agents", [])) or "unknown",
                "skill": s["name"],
                "path": path,
                "version": videoclaw.__version__,
            }
            if path in before_paths:
                rec["action"] = "skip-current"
                skipped.append(rec)
            else:
                rec["action"] = new_action
                installed.append(rec)
        # For dry-run, `add --list` doesn't write anything, so after==before
        # and we synthesize "would-create" records from the listing output.
        if action == "dry_run" and not installed and not skipped:
            # No skills detected by post-list scan (dry_run doesn't write).
            # Treat all "before" entries as already-installed (skip-current)
            # and report 0 new — accurate even if uninformative.
            pass

    return {
        "ok": True,
        "error": None,
        "agents_detected": sorted(agents),
        "skills_installed": installed,
        "skills_skipped": skipped,
        "skills_removed": removed,
    }


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
            help="Install to one specific agent only (python-fallback path: "
            "claude_code / codex / openclaw). Forces --no-npx.",
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
    copy_mode: Annotated[
        bool,
        typer.Option(
            "--copy",
            help="(npx-skills only) Copy files instead of symlinking. "
            "For filesystems without symlink support.",
        ),
    ] = False,
    no_npx: Annotated[
        bool,
        typer.Option(
            "--no-npx",
            help="Skip npx-skills delegation; use the built-in python "
            "installer (Claude Code / Codex / OpenClaw only).",
        ),
    ] = False,
) -> None:
    """Install videoclaw skills into detected coding agents."""
    out = get_output()
    out._command = "setup"
    console = get_console()

    version = videoclaw.__version__
    installer: Literal["npx-skills", "python-fallback"] = "python-fallback"
    error: str | None = None
    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    agents_detected: list[str] = []

    # --agent narrows to one specific python-fallback target, so it implies --no-npx.
    use_npx = not no_npx and agent is None
    skills_root = _resolve_skills_root()

    npx_result: dict[str, Any] | None = None
    if use_npx:
        action: Literal["install", "uninstall", "dry_run"] = (
            "uninstall" if uninstall else ("dry_run" if dry_run else "install")
        )
        npx_result = _try_npx_skills(
            action=action, copy_mode=copy_mode, skills_root=skills_root
        )

    if npx_result is not None:
        installer = "npx-skills"
        if not npx_result.get("ok", True):
            error = str(npx_result.get("error") or "npx-skills delegation failed")
        installed = list(npx_result.get("skills_installed", []))
        skipped = list(npx_result.get("skills_skipped", []))
        removed = list(npx_result.get("skills_removed", []))
        agents_detected = list(npx_result.get("agents_detected", []))
    else:
        # python-fallback path (M002).
        targets = _agent_targets(Path.home())
        if agent:
            targets = [t for t in targets if t.id == agent]
            if not targets:
                msg = (
                    f"unknown agent: {agent!r} "
                    "(known: claude_code, codex, openclaw)"
                )
                if out.json_mode:
                    _emit_envelope({"installer": installer}, ok=False, error=msg)
                else:
                    console.print(f"[red]error[/red]: {msg}")
                raise typer.Exit(code=2)
        detected = _detect(targets)
        agents_detected = [t.id for t in detected]
        if uninstall:
            for t in detected:
                removed.extend(_uninstall_one(t))
        else:
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
    elif not agents_detected and installer == "python-fallback":
        next_steps = [
            "install one of: Claude Code (~/.claude/), Codex (~/.codex/), "
            "OpenClaw (~/.openclaw-autoclaw/)",
            "or install Node.js so 'claw setup' can use 'npx skills' "
            "(51+ supported agents incl. Gemini CLI, Antigravity, Windsurf)",
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
        "installer": installer,
        "agents_detected": agents_detected,
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

    label = "via npx skills" if installer == "npx-skills" else "python fallback"
    console.print(f"[bold cyan]videoclaw[/bold cyan] setup v{version} [dim]({label})[/dim]")
    if error:
        console.print(f"[red]error[/red]: {error}")
        raise typer.Exit(code=1)
    if not agents_detected:
        console.print("[yellow]No supported coding agents detected on this host.[/yellow]")
        for step in next_steps:
            console.print(f"  → {step}")
        return
    console.print(f"Detected: {', '.join(agents_detected)}")
    if uninstall:
        console.print(f"Removed {len(removed)} skill(s) from {len(agents_detected)} agent(s).")
        return
    if dry_run:
        console.print(
            f"[yellow]Dry-run[/yellow] — would install {len(installed)} skill(s):"
        )
    else:
        console.print(
            f"Installed {len(installed)} skill(s) across {len(agents_detected)} agent(s):"
        )
    for rec in installed:
        console.print(f"  • {rec['agent']}: {rec['path']}")
    if skipped:
        console.print(f"Skipped {len(skipped)} (already current).")
    for step in next_steps:
        console.print(f"\n[dim]{step}[/dim]")
