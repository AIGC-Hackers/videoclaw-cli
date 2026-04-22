# Milestone M001 — agent-cli-toolkit

## One-line goal

Deliver a **prescriptive toolkit** (playbook + interface contract + runnable templates + verified minimal example + deployment recipe + videoclaw blueprint) that any CLI developer can follow to transform their existing CLI into an **agent-CLI** — deployable on any machine, callable by other agents — **without modifying the CLI's internal source code**.

## Why this exists

Kimi-CLI (MoonshotAI/kimi-cli, v1.37.0) is an exemplar agent-CLI: it exposes a clean interactive TUI, an ACP server for IDE integration, an MCP client for tool composition, and ships as both a wheel and a PyInstaller single binary. A full teardown of its structure already exists at `../docs/references/kimi-cli-teardown/01-structure.md` (copied into `input/kimi-cli-structure-evidence.md`).

Developers who want to level up their own CLIs to the same standard currently have to reverse-engineer kimi's design themselves. This milestone extracts the transferable patterns into a **copy-paste toolkit**.

## Primary audience

A Python CLI maintainer with an existing 2,000–20,000 LOC CLI (typer/click/argparse based) who wants to:

1. Expose the CLI so other agents can discover and call it (MCP + ACP).
2. Ship a single-binary install for machines without Python.
3. Standardize config, logging, and `--json` machine output.
4. Enable plugin/extension discovery at runtime.
5. Keep doing all the above **without rewriting their business logic**.

## Scope — 10 slices

Exactly these slices, in this order. Do **not** add speculative slices. Do **not** merge slices.

### S01 — Scaffolding

**Out**: `agent-cli-toolkit/README.md`, `agent-cli-toolkit/PROJECT.md`, top-level layout decisions.

**Definition of done**: README answers "what is this, who is it for, how do I use it in 60 seconds". PROJECT.md lists all planned deliverables with status markers.

### S02 — Migration Playbook (the prescriptive core)

**Out**: `docs/agent-cli-migration-playbook.md`.

**Content**: exactly 7 numbered steps. Each step has this structure:

- **Goal** (one sentence, what this step achieves)
- **Before state** (assumed starting condition, with a file sketch)
- **After state** (file sketch showing what's added)
- **Actions** (numbered bash/edit operations, copy-pasteable)
- **Evidence from kimi-cli** (citations like `path:line`)
- **Verification** (a command + expected output that proves the step is done)

The 7 steps, in this fixed order:

1. Audit current CLI shape (produce inventory: entry point, command tree, config surface, tests).
2. Introduce standard `--json` machine-readable output on all commands.
3. Standardize config path (`~/.config/<tool>/`) and env-var namespace.
4. Add MCP server mode (`<tool> mcp-server` → exposes tools over MCP).
5. Add ACP server mode (`<tool> acp` → agent-client-protocol over stdio).
6. Build distribution (wheel with pruned sources + PyInstaller single binary + Dockerfile).
7. Emit a deployment manifest (`.agent-cli.yaml`) so other agents can auto-discover the CLI.

**Non-negotiables**: Each step's Actions section must be runnable as-is against the minimal example built in S05. Playbook is validated end-to-end in S06.

### S03 — Interface Contract

**Out**: `docs/agent-cli-interface-contract.md`.

**Content**: the uniform surface every agent-CLI must expose for consistent agent interop.

Sections:

1. **Command name convention** (short binary + long alias, per kimi's `kimi`/`kimi-cli`).
2. **Required global flags**: `--json`, `--verbose`, `--version`, `--config`, `--mcp-config-file`.
3. **Required subcommands**: `<tool> version`, `<tool> doctor`, `<tool> mcp-server`, `<tool> acp`.
4. **JSON envelope schema**: every `--json` response uses the same top-level envelope `{"schema":"agent-cli/v1","ok":bool,"data":...,"error":{...}}`.
5. **Config path contract**: `~/.config/<tool>/config.yaml`, `~/.config/<tool>/credentials.json`, `~/.cache/<tool>/`, `~/.local/share/<tool>/`.
6. **Exit codes**: `0` ok, `1` runtime error, `2` usage error, `3` auth needed, `4` blocked.
7. **MCP tool discovery schema**: what `tools/list` must return.
8. **ACP handshake**: what version/capabilities every agent-CLI must report.
9. **Deployment manifest schema** (`.agent-cli.yaml`): for orchestrators to auto-discover.

### S04 — Templates (`templates/`)

**Out**:

- `templates/pyproject.toml.tmpl` — uv_build backend, source-exclude, dual entry points.
- `templates/__main__.py` — process entry with arg routing to Typer.
- `templates/cli_app.py` — Typer app skeleton with global flags + `--json` envelope helper.
- `templates/command_skeleton.py` — one fully-worked subcommand with docstring, error handling, JSON output.
- `templates/tool_skeleton.py` — MCP tool declaration.
- `templates/mcp_server.py` — FastMCP-based `mcp-server` subcommand.
- `templates/acp_server.py` — ACP-based `acp` subcommand.
- `templates/config.py` — pydantic-settings config with env override.
- `templates/plugin_entrypoint.py` — entry_points-based plugin discovery.
- `templates/Dockerfile.tmpl` — multi-stage build.
- `templates/pyinstaller.spec.tmpl` — single-binary spec.
- `templates/.agent-cli.yaml.tmpl` — deployment manifest.
- `templates/README.md` — how to use the templates.

Every template has `${PLACEHOLDER}` tokens for: `PROJECT_NAME`, `BIN_NAME`, `PKG_NAME`, `VERSION`, `AUTHOR`, `DESCRIPTION`. A `templates/apply.py` script does substitution.

### S05 — Minimal Example CLI (`examples/hello-agent-cli/`)

**Out**: a complete 100-300 LOC Python CLI named `hello-agent` that uses every template from S04. It has:

- Two domain commands (`hello-agent greet NAME`, `hello-agent fortune`).
- `--json` on both commands.
- `hello-agent mcp-server` exposing `greet` as an MCP tool.
- `hello-agent acp` stub that reports capability.
- Wheel-buildable via `uv build`.
- Tests (pytest) for both commands + MCP tools/list.

**Definition of done**: `cd examples/hello-agent-cli && uv pip install -e . && hello-agent --json greet Ada` returns a well-formed envelope.

### S06 — End-to-End Verification

**Out**: `examples/hello-agent-cli/VERIFIED.md`.

**Content**: run every step of the S02 playbook against `hello-agent-cli/`. Record expected-vs-actual for each step. Any mismatch → go back and fix S02/S04/S05.

Also produce a short `docs/how-the-toolkit-was-validated.md` pointing to VERIFIED.md as the authoritative evidence.

### S07 — Packaging

**Out**: in `examples/hello-agent-cli/`:

- Built wheel in `examples/hello-agent-cli/dist/*.whl`.
- Built PyInstaller binary (at least for the current platform).
- Working Dockerfile (buildable; does not need to be pushed).

Plus `docs/packaging-cookbook.md` documenting the three distribution paths (wheel / binary / Docker) with pros/cons and when to pick each.

### S08 — Deployment Recipe

**Out**: `docs/deploy-to-machine.md`.

**Content**: three deployment targets — developer laptop (pip install), remote Linux box (wheel from PyPI or binary scp), Docker host (pull + run). For each, show:

- How an OTHER agent would install & call this CLI (so the CLI becomes a composable building block in a larger agent system).
- Systemd unit skeleton (optional) if running `mcp-server` as a long-lived service.
- Health check command.

### S09 — Videoclaw Blueprint

**Out**: `docs/videoclaw-packaging-plan.md`.

**Content**: apply the 7-step playbook to videoclaw WITHOUT modifying `src/videoclaw/**`. For each step, show:

- Current videoclaw state (cite file paths).
- What file to ADD under `videoclaw/packaging/` or `videoclaw/mcp-shim/` (not edit).
- Verification command.

End with a priority-ordered checklist (P0/P1/P2) so videoclaw maintainers can pick up step 1 and proceed.

### S10 — Final Delivery

**Out**: updated `agent-cli-toolkit/README.md` + `QUICKSTART.md` + `INDEX.md`.

- README: pitch (2 paragraphs), quickstart (60 seconds), layout, contribution.
- QUICKSTART: a CLI maintainer with a 2000-LOC typer CLI follows this and gets an agent-CLI in 1 hour.
- INDEX: every deliverable with 1-line summary + link.

Also write a Chinese executive summary at `README.zh.md` (≤ 1 page).

## Success criteria (milestone-level)

1. All 10 slices have their "Out" artifacts present and non-stub.
2. `examples/hello-agent-cli/` builds a wheel AND a PyInstaller binary.
3. `hello-agent mcp-server` responds to `tools/list` (verified in VERIFIED.md).
4. `VERIFIED.md` shows 7/7 playbook steps passed.
5. No file under `src/videoclaw/**` or `tests/**` is touched.

## Constraints recap (echo from AGENTS.md)

- Write only under `agent-cli-toolkit/**`.
- Read-only reference: `~/Moose/kimi-cli/**`.
- Cite kimi sources with `path:line`.
- Prescriptive > descriptive. Prefer working code over prose.
