# Videoclaw — brief overview for blueprint reference

This is NOT the project being built. It is the project that will LATER consume the toolkit. S09 produces a blueprint; actual videoclaw refactoring happens in a future milestone.

## Current shape (one screen)

- **Purpose**: AI short-drama orchestration system for TikTok (script → assets → storyboard → Seedance video → audit → delivery).
- **Stack**: Python 3.12+, Typer CLI (`claw`), Pydantic v2, litellm (LLM gateway via Evolink), pytest with `asyncio_mode=auto`.
- **Layout**: single package `src/videoclaw/` with subpackages `cli/`, `drama/`, `agents/`, `models/adapters/`, `core/`, `generation/`, `storage/`, `publishers/`, `server/` (FastAPI, optional).
- **Entry point**: `claw = videoclaw.cli:app` (Typer).
- **Build**: `pyproject.toml` uses standard PEP 517 backend (hatchling/setuptools, not `uv_build` yet).
- **Extension points today**: `videoclaw.agents` and `videoclaw.adapters` entry_points discovered at runtime.
- **No MCP server mode.** No ACP server mode. No `--json` machine-readable output gating on all commands (some commands have it). No PyInstaller binary.

## What the blueprint (S09) must cover — gap analysis

For each of the 7 playbook steps (defined in S02), show:

1. **Current state of videoclaw** (file paths + current behavior).
2. **Target state** (what the playbook prescribes).
3. **Concrete migration actions** (files to add, not files to edit — the user constraint is no-source-change).
4. **Verification** (how to confirm the step is done).

Key gaps videoclaw must close to become an agent CLI per this toolkit:

- MCP server mode (so other agents can call it).
- ACP server mode (so IDEs can launch it as an agent).
- Unified `--json` flag on every command with schema version.
- Config-path standardization (`~/.config/videoclaw/`).
- Wheel slimming (strip tests/examples from dist).
- PyInstaller single-binary build (optional).
- Dockerfile for reproducible deploy.

Keep this list terse. S09 will expand it with file-level specificity.

## What videoclaw already does well (and should keep)

- Typer CLI with sub-apps (`claw drama`, `claw model`, etc.).
- Pydantic-based config with env override (`VIDEOCLAW_*`).
- Entry_points-driven adapter/agent registry.
- Async pytest baseline.
- Rich-formatted output.

The blueprint should preserve these and add what's missing — not rewrite.
