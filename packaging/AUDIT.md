# Videoclaw — Audit (playbook Step 1)

Four-bucket inventory of the existing surface, taken without modifying any
code under `src/videoclaw/**`. Citation form is `path:line` against the
working tree.

## Entry point

- `pyproject.toml:51-52` — `claw = "videoclaw.cli:app"` registers the binary.
- `src/videoclaw/cli/_app.py` — primary Typer app + global flags
  (`--json/-j`, `--verbose/-v`).

## Command tree

Top-level commands registered in `src/videoclaw/cli/__init__.py:10-24`:

- `claw generate PROMPT` — single-shot video generation.
- `claw doctor` — environment diagnostics.
- `claw info` — system snapshot.
- `claw version` — version string (non-eager subcommand).
- `claw stage-*` — seven staged-pipeline commands.

Sub-app namespaces mounted in `src/videoclaw/cli/_app.py:55-61`:

| Namespace | Source | Purpose |
|---|---|---|
| `model` | `cli/model.py` | List / inspect video models. |
| `project` | `cli/project.py` | Project lifecycle. |
| `template` | `cli/template.py` | Template management. |
| `flow` | `cli/flow.py` | Flow orchestration. |
| `drama` | `cli/drama/` (8 modules) | Drama production pipeline. |
| `config` | `cli/config_cmd.py` | Config inspection. |
| `agent` | `cli/agent_cmd.py` | Agent registry. |
| `cost` | `cli/cost_cmd.py` (self-registers) | Cost reporting. |

The `mcp-server` and `acp` command names are **unclaimed** in
`_app.py:55-61` — agent-cli surface lands cleanly via the sibling
`mcp-shim/` tree without a name collision.

## Configuration surface

- `src/videoclaw/config.py:30-35` — `pydantic-settings` with
  `env_prefix="VIDEOCLAW_"` and `env_file=".env"`.
- `src/videoclaw/config.py:38-40` — cwd-relative dir defaults
  (`./projects`, `./models_cache`, `./docs/deliverables`); no
  `platformdirs` / XDG awareness today.
- API keys read both with and without the `VIDEOCLAW_` prefix
  (`VIDEOCLAW_EVOLINK_API_KEY` / `EVOLINK_API_KEY` etc.).

Per playbook Step 3, full XDG migration to `~/.config/videoclaw/`
+ `CLAW_*` aliasing is **deferred to a future milestone**
(`packaging/xdg-migration.md`, P2 in the blueprint) — current
defaults stay cwd-relative for backward compatibility.

## Test surface

- `Makefile:13-14` — `uv run pytest tests/ -v` runs the full suite.
- `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`.
- Tests under `tests/` cover drama runner, executor, TTS,
  voice_caster, subtitle, frame_analyzer, cover_frame, registry,
  flow, audit.

## Distribution channels (today)

| Channel | Today | Target (this milestone) |
|---|---|---|
| Wheel | `hatchling` whitelist `pyproject.toml:73-74`; **no** `source-exclude` (tests, docs/deliverables, projects, models_cache leak). | `pyproject.overlay.toml` adds `source-exclude` patterns; build via `uv build --build-constraint`. |
| PyInstaller | None (`pyinstaller` absent from dev deps). | `claw.spec` covers one-file + one-dir branches; `torch` / `diffusers` excluded. |
| Docker | Existing `Dockerfile:1-29` is single-stage FastAPI image (`uvicorn :8000` for the optional `server` extra). | New `packaging/Dockerfile` is multi-stage CLI image, **parallel** to the existing FastAPI image. |
| GitHub Releases | None. | Out of this milestone — pattern lives in the toolkit. |

## Ship-vs-skip matrix

| Concern | Ship now (this milestone) | Skip (deferred) |
|---|---|---|
| Wheel with `source-exclude` | ✅ | — |
| PyInstaller binary | ✅ | — |
| Docker CLI image | ✅ | — |
| MCP shim (read-only tools) | ✅ | — |
| `.agent-cli.yaml` manifest | ✅ | — |
| `claw mcp-server` subcommand | ❌ | Lives in `mcp-shim/` (sibling) — don't claim the namespace yet. |
| `claw acp` subcommand | ❌ | P2; `mcp-shim/acp_server.py` deferred. |
| Envelope upgrade to `agent-cli/v1` | ❌ (design note only) | Wrapper-script approach, M002+. |
| XDG / `CLAW_*` aliasing | ❌ | P2 — surface change. |
