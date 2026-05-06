# Release Notes

All notable changes to videoclaw are documented in this file. Format
follows the google/agents-cli style — `## [<version>] - YYYY-MM-DD`
with grouped bullets.

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
