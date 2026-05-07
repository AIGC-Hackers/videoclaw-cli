# Release Notes

All notable changes to videoclaw are documented in this file. Format
follows the google/agents-cli style — `## [<version>] - YYYY-MM-DD`
with grouped bullets.

## [0.1.2] - 2026-05-07

Stabilizes the packaged Codex / coding-agent drama workflow with Sonnet
4.6 as the default LLM and stronger retries around real external model
calls.

### Behavior

- `VIDEOCLAW_DEFAULT_LLM` now defaults to `claude-sonnet-4-6`.
- `claw drama plan` and `claw drama script` request larger, lower-temperature
  JSON completions to reduce truncation and schema drift.
- Planner JSON calls retry once when the model returns markdown, invalid JSON,
  or JSON missing required arrays.
- Scene and prop reference image generation retries transient external image
  gateway failures before surfacing an error.

### Tests

- Added regression coverage for the Sonnet 4.6 config default.
- Added planner tests for malformed JSON recovery, missing-schema recovery,
  and JSON call options.
- Added scene-designer coverage for transient image generation retry.

## [0.1.1] - 2026-05-07

Hybrid `claw setup` — delegates to the [`vercel-labs/skills`](https://github.com/vercel-labs/skills)
ecosystem CLI when Node.js is available, falls back to the built-in
Python installer when not. Unlocks 51+ coding agents (Gemini CLI,
Antigravity, Windsurf, Cline, Continue, Trae, Kiro CLI, ...) without
us shipping per-agent path tables.

### Features

- **`claw setup` now tries `npx skills@1.5.5` first.** When `npx` is
  on `PATH` and the bundled `_skills/` directory is resolvable, it
  invokes `npx -y skills@1.5.5 add <local-skills-path> -g --all -y`
  so every agent the `skills` CLI knows about (51+) receives the
  bundle in one pass. No GitHub round-trip, no network dependency —
  the local skills root (the same one bundled in the wheel) is what
  gets installed.
- **`--no-npx` flag** — forces the M002 python-fallback installer
  (Claude Code / Codex / OpenClaw only). Useful for offline hosts,
  CI environments without Node, or testing the fallback path.
- **`--copy` flag** — passes `--copy` to `npx skills add`, which
  copies files instead of symlinking. Use on filesystems without
  symlink support (e.g., some Windows / WSL setups).
- **Envelope `data.installer` field** — every `claw setup --json`
  result now includes `installer: "npx-skills"` or
  `"python-fallback"` so orchestrators can dispatch on which path
  ran. Schema name unchanged (`videoclaw-setup-skills/v1`); this
  is an additive field.

### Behavior

- When neither npx nor any python-fallback agent is detected,
  `next_steps` now suggests installing Node.js to unlock the wider
  agent set, in addition to the existing per-agent install hints.
- `--agent <id>` continues to target one python-fallback agent and
  now implies `--no-npx` (since the npx path installs to all
  detected agents at once).

### Documentation

- README "Works seamlessly with" line expanded to call out
  Antigravity / Gemini CLI / Windsurf / Continue alongside the
  M002 set, with a link to the `vercel-labs/skills` registry for
  the long tail.
- `AGENTS.md` "Per-agent quickstart" section gains Gemini CLI and
  Antigravity blocks; the deferred-Gemini block is removed. New
  top-of-section note documents the npx-vs-fallback resolution
  order.

### Tests

- `tests/test_setup_skills.py` grows from 11 → 16 tests. New cases
  cover `_try_npx_skills` falling back when `npx` is absent, the
  exact subprocess command shape, the `--copy` flag, the `--no-npx`
  flag bypassing delegation, and the `installer` envelope field.
  All existing tests continue to pass on the python-fallback path.

### Compatibility

- No breaking changes. M002 fallback path (Claude Code / Codex /
  OpenClaw) preserved byte-for-byte; default behavior on hosts
  without Node is unchanged.
- Default behavior on Node-equipped hosts now installs to *more*
  agents (whichever the `skills` CLI detects) — pass `--no-npx`
  to opt back into the M002 narrow target list.

## [0.1.0] - 2026-05-06 (pending)

First public release. Packages videoclaw as a distributable
agent-callable CLI: install once, drive from any coding agent
(Claude Code, OpenClaw, Codex, Cursor, Gemini CLI, others).

### Features

- **`claw setup`** — new top-level command. Detects which coding
  agents are installed locally and copies the `videoclaw-*` skills
  into each agent's skills directory in one idempotent step. Per-agent
  naming: flat (`videoclaw-workflow/`) for Claude Code & Codex;
  versioned (`videoclaw-workflow-0.1.0/`) for OpenClaw. Supports
  `--dry-run`, `--agent <id>`, `--uninstall`. Custom envelope
  schema `videoclaw-setup-skills/v1` for orchestrator dispatch.
- **5 markdown skills** (`videoclaw-workflow`, `videoclaw-drama-setup`,
  `videoclaw-models`, `videoclaw-checkpoint`, `videoclaw-troubleshoot`)
  bundled into the wheel + PyInstaller binary as `videoclaw/_skills/`.
  Each skill carries trigger-phrase frontmatter so coding agents
  activate the right phase automatically.
- **`packaging/skills-validate.py`** — schema validator for the
  skills directory. Checks frontmatter completeness, name/dirname
  alignment, version consistency with `pyproject.toml`.
- **Distribution channels**: wheel (`uv build --wheel`), PyInstaller
  single-binary (`packaging/claw.spec`, excludes `torch` /
  `diffusers` / `fastapi` / `uvicorn`), multi-stage Docker image
  (`packaging/Dockerfile`, non-root user). One-command verification
  via `bash packaging/dist-verify.sh`.
- **Public installer** `install.sh` — auto-detects OS / arch
  (macOS arm64, Linux x86_64), prefers `uv tool install`, falls back
  to PyInstaller binary download, SHA256 verification, refuses root.
  Emits `videoclaw-install/v1` envelope. Suggests `claw setup` as
  the next step.
- **First-run wizard** `packaging/setup.sh` — XDG-aware (`$XDG_CONFIG_HOME/videoclaw/.env`
  → `~/.config/videoclaw/.env` → repo cwd), `chmod 600` on the file,
  emits `videoclaw-setup/v1` envelope, idempotent re-run.
- **Agent-CLI deployment manifest** `packaging/agent-cli.yaml`
  (schema `agent-cli/v1`) — informational; primary discovery is via
  skills. Documents commands, exit-code contract (0/1/2/3/4),
  health_check, MCP block, distribution channels.
- **Tag-driven release CI** `.github/workflows/release.yml` — builds
  wheel + sdist + PyInstaller binaries on the macOS arm64 / Linux
  x86_64 matrix, computes SHA256SUMS, generates `update-manifest.json`
  (schema `agent-cli-update/v1`), uploads to GitHub Releases.
  `workflow_dispatch` is structurally dry-run (no release created)
  with explicit `dry_run` input for clarity.
- **MCP shim** `mcp-shim/` — optional secondary integration path
  exposing 4 read-only tools (`list_drama_series`, `get_drama_series`,
  `list_video_models`, `get_videoclaw_version`) over stdio JSON-RPC
  for MCP-preferring clients. Mutating ops still go through the CLI.

### Behavior

- `claw doctor` now emits **exit code 3** (auth needed) when
  `VIDEOCLAW_EVOLINK_API_KEY` is missing, **exit 1** for other
  failures, **exit 0** when all checks pass. Coding agents can branch
  on `$? == 3` to auto-trigger `bash packaging/setup.sh` without
  parsing stderr.
- README restructured to `google/agents-cli` template: Hero +
  Get Started + Skills table + CLI Commands table + FAQ.
- AGENTS.md updated with per-agent quickstart blocks
  (Claude Code, OpenClaw, Codex, Cursor) and the new exit-code
  branching pattern.

### Internal

- Wheel bundles `skills/` as `videoclaw/_skills/` via hatch
  `force-include`, so `claw setup` resolves the skills via
  `importlib.resources.files()` at runtime — works for editable,
  wheel, and PyInstaller installs alike.
- `tests/test_setup_skills.py` (11 tests) and
  `tests/test_doctor_exit_codes.py` (7 tests) cover the new
  surface; both run in <1 second with `tmp_path` filesystem
  isolation, never touching the developer's real `~/.claude/skills/`.
- Spec-driven planning docs live under
  `docs/plans/2026-05-06-agent-cli-*.md` — distribution spec, feature
  audit (F1-F13), task breakdown (T1-T17), reachable from `git log`.

### Source repositories

- Source: https://github.com/AIGC-Hackers/videoclaw-cli
- Issues: https://github.com/AIGC-Hackers/videoclaw-cli/issues
- Skills: [`skills/`](skills/) (mirror of bundled `_skills/`)

### Compatibility

- Python ≥ 3.12 (3.12 / 3.13)
- macOS arm64, Linux x86_64 (single-binary install)
- Any platform with Python 3.12+ for the wheel install
- Coding agents tested: Claude Code, Codex, OpenClaw (skills
  auto-install); Cursor (manual); Gemini CLI / Cline (CLI-only)
