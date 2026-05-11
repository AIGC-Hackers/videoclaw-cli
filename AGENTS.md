# videoclaw — Agents quickstart

`videoclaw` ships with a CLI (`claw`) and a set of markdown skills.
Coding agents drive the CLI through their built-in shell tool; the
skills (`videoclaw-workflow`, `videoclaw-drama-setup`,
`videoclaw-models`, `videoclaw-checkpoint`, `videoclaw-troubleshoot`)
teach the agent *when* and *how* to call which command.

**Three integration paths**, in order of friction:

1. **CLI + skills (recommended)** — `claw setup` detects which coding
   agents are installed and copies skills into each. The agent loads
   skills automatically on next start and triggers them by user
   intent (e.g. "use videoclaw to make a drama").
2. **CLI-only** — any code agent with a Bash tool calls `claw …`
   directly. Predictable `--json` envelope; standard exit codes
   `0/1/2/3/4`.
3. **MCP shim (optional, secondary)** — `videoclaw-mcp-server` over
   stdio for clients that prefer structured tool discovery. 4
   read-only tools; mutating ops still go through `claw`.

The CLI + skills path is the universal contract. The deployment
manifest at `packaging/agent-cli.yaml` is **informational** —
primary discovery is via skills.

## Two-command bootstrap

```bash
# 1. Install claw + skills:
curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh
claw setup

# 2. Configure API keys:
bash packaging/setup.sh        # interactive wizard, writes ~/.config/videoclaw/.env
```

Until videoclaw is on PyPI, install from a wheel URL:

```bash
uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.4/videoclaw-0.1.4-py3-none-any.whl videoclaw setup
```

Or from local source (works today):

```bash
uv pip install -e .
uv run claw setup
```

## Deployment agent release gate

For repository automation, the stable root command is:

```bash
./agent-cli-release-gate.sh package
```

Use it before publishing artifacts for external coding agents. It prepares
packaging dependencies, runs tests and validators, builds distribution
artifacts, installs the rebuilt wheel into a fresh venv, and verifies the
packaged `claw` CLI can run both `setup --dry-run --no-npx` and the
`npx-skills` setup path.

First-time host setup:

```bash
./agent-cli-release-gate.sh setup --with-npx --with-bin
```

Normal source-change gate:

```bash
./agent-cli-release-gate.sh ci
```

Version and release flow:

```bash
./agent-cli-release-gate.sh version
./agent-cli-release-gate.sh release --with-npx
./agent-cli-release-gate.sh release --with-npx --with-real-llm --with-real-video
```

Source changes do not require an immediate public release. Any artifact that
will be handed to external coding agents does require a rebuild and fresh
wheel-install verification before publishing. The order is: edit source, run
`ci`, bump version if public behavior or bundled assets changed, then run
`package` or `release --with-npx`, optionally run real-video E2E, then
commit/tag/push.

See `AGENT_CLI_PACKAGING.md` for setup details and
`docs/plans/2026-05-08-agent-cli-release-gate.md` for the spec.

## Per-agent quickstart

> **How `claw setup` resolves agents:** when `npx` is on `PATH`, it
> delegates to [`vercel-labs/skills`](https://github.com/vercel-labs/skills)
> (51+ supported agents incl. Gemini CLI, Antigravity, Windsurf, Cline,
> Continue, Trae, Kiro CLI). When `npx` is missing, it falls back to a
> built-in Python installer covering Claude Code, Codex, OpenClaw. The
> 4 detailed blocks below describe the python-fallback layout; the npx
> path uses each agent's own per-tool conventions automatically.

### Claude Code

```bash
# 1. Install (one-time)
uvx --from <wheel-url> videoclaw setup
# → installs videoclaw-* skills into ~/.claude/skills/

# 2. Verify
claw --json doctor
# Exit 0 = ok; exit 3 = run `bash packaging/setup.sh` to configure keys

# 3. Drive from Claude Code
# In a Claude Code conversation, say:
#   "Use videoclaw to import examples/script.md as a drama and run the first 3 shots"
# The videoclaw-workflow skill activates and runs:
#   claw drama import …  →  claw drama plan …  →  claw drama design-* …
#   →  claw drama run … --max-shots 3  →  claw drama audit …
```

### OpenClaw

```bash
# 1. Install (one-time)
uvx --from <wheel-url> videoclaw setup
# → installs videoclaw-* skills as videoclaw-workflow-0.1.4/, etc.
#   into ~/.openclaw-autoclaw/skills/ (versioned naming convention)

# 2. Verify
claw --json doctor

# 3. Drive from OpenClaw
# OpenClaw loads skills by name + version; reference them as:
#   /videoclaw-workflow
# in your orchestration prompts.
```

### Codex

```bash
# 1. Install (one-time)
uvx --from <wheel-url> videoclaw setup
# → installs videoclaw-* skills into ~/.codex/skills/

# 2. Verify
claw --json doctor

# 3. Drive from Codex
# Codex picks up skills automatically. The videoclaw-workflow skill
# activates on intents matching its description ("make a drama",
# "build a TikTok video drama"). All Bash invocations of `claw …`
# work directly without the skill too.
```

### Cursor (manual install)

Cursor doesn't have a `~/.cursor/skills/` convention; `claw setup`
skips it. To use videoclaw skills with Cursor, either:

```bash
# Option A — copy the skills body into Cursor Rules (project-wide):
cat $(uv run python -c "from importlib.resources import files; print(files('videoclaw') / '_skills' / 'videoclaw-workflow' / 'SKILL.md')") \
    >> .cursorrules

# Option B — drive the CLI directly via Cursor's terminal; the
# skills aren't auto-loaded, but `claw drama …` works as-is.
```

Treat Cursor as a **CLI-only** agent until skills support lands
upstream.

### Gemini CLI

```bash
# 1. Install (one-time) — auto-installed via npx skills
uvx --from <wheel-url> videoclaw setup
# → installs videoclaw-* skills into ~/.gemini/skills/ (npx skills path)

# 2. Verify
claw --json doctor
ls ~/.gemini/skills/videoclaw-workflow/SKILL.md

# 3. Drive from Gemini CLI
# Skills auto-activate on description-trigger phrases; or call the CLI
# directly via Gemini CLI's shell tool.
```

### Antigravity

```bash
# 1. Install (one-time) — auto-installed via npx skills
uvx --from <wheel-url> videoclaw setup
# → installs videoclaw-* skills into ~/.antigravity/skills/

# 2. Verify
claw --json doctor

# 3. Drive from Antigravity
# Same description-trigger model as Claude Code / Codex; the
# videoclaw-workflow skill activates on drama production intents.
```

### Other 45+ agents (Cline, Continue, Trae, Kiro CLI, Windsurf, ...)

When `npx` is available, `claw setup` delegates to
[`vercel-labs/skills`](https://github.com/vercel-labs/skills), which
ships per-agent path tables for 51+ coding agents. Run `claw setup`
and any installed agent listed in the `skills` registry will receive
the videoclaw skill bundle automatically.

Any agent with a Bash tool can also call `claw` directly — see the
"How code agents use videoclaw" section below.

For the default `seedance-2.0` drama model, VideoClaw treats the model's
native dialogue/SFX/subtitle output as authoritative. The DAG skips
downstream TTS, BGM, and subtitle-overlay nodes so compose only assembles
the generated clips instead of re-mixing audio over them.

## How code agents use videoclaw

### CLI + Bash tool (universal)

```bash
claw image "character turnaround sheet" \
  --provider evolink --model gpt-image-2 \
  --resolution 1K --quality medium
claw drama new "<synopsis>" --title "<title>" --lang zh
claw drama plan <series_id>
claw drama design-characters <series_id>
claw drama design-scenes <series_id>
claw drama run <series_id> --max-shots 3
claw drama audit <series_id>
claw drama export <series_id>
```

Image assets default to Evolink `gpt-image-2` at `resolution=1K` and
`quality=medium`. Agents should use that for character turnaround sheets,
scene/location references, props, cover frames, and direct `claw image`
calls unless the user explicitly chooses another provider. BytePlus
`seedream-5.0-lite` remains available as an explicit image fallback:

```bash
claw image "scene reference" --provider byteplus --model seedream-5.0-lite
```

Every command supports `--json` for predictable parsing. Exit codes:

| Code | Meaning | Agent action |
|---|---|---|
| 0 | OK | continue |
| 1 | Runtime error | retry once, then escalate |
| 2 | Usage error | re-read `claw <cmd> --help` |
| 3 | Auth needed | run `bash packaging/setup.sh` |
| 4 | Blocked | read envelope `error` field |

`claw doctor` returns 3 specifically when `VIDEOCLAW_EVOLINK_API_KEY`
is missing. That key powers both the LLM gateway and default Evolink
`gpt-image-2` image assets, so coding agents can branch on `$? == 3`
to auto-trigger configuration.

### MCP shim (optional, secondary)

For clients that prefer MCP:

```bash
uv pip install -e mcp-shim/

# Register with Claude Code (~/.claude/settings.json):
# {
#   "mcpServers": {
#     "videoclaw": {"command": "videoclaw-mcp-server"}
#   }
# }

# 4 read-only tools exposed via tools/list:
#   list_drama_series / get_drama_series / list_video_models / get_videoclaw_version
```

Mutating ops (`drama run`, `drama design-*`, etc.) still go through
the CLI via the agent's Bash tool — the shim deliberately doesn't
claim the `claw drama` namespace.

### From custom orchestrators (Python over stdio)

```python
import json, asyncio
from asyncio.subprocess import PIPE


async def call_tool(name: str, arguments: dict) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "videoclaw-mcp-server", stdin=PIPE, stdout=PIPE, stderr=PIPE
    )
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "myorch", "version": "0.1"}}}
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}
    for msg in (init, notif, call):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()
    _ = await proc.stdout.readline()
    raw = await proc.stdout.readline()
    proc.terminate()
    return json.loads(raw.decode())


result = asyncio.run(call_tool("list_drama_series", {}))
```

### As a containerized batch tool

```bash
docker build -t videoclaw-cli -f packaging/Dockerfile .
docker run --rm \
  -v $HOME/.config/videoclaw:/home/claw/.config/videoclaw \
  videoclaw-cli --json drama list
```

### As a no-Python binary

```bash
uv pip install pyinstaller
bash packaging/dist-verify.sh   # builds wheel + binary + docker
./dist/claw version
./dist/claw --json drama list
```

## External tests

```bash
uv run pytest tests-external/ -v          # 9-stage e2e (T1-T9)
uv run pytest mcp-shim/tests/ -v          # MCP single-point + protocol
uv run pytest tests/test_setup_skills.py tests/test_doctor_exit_codes.py -v
                                           # claw setup + doctor exit codes
```

T1-T4 + T7 in `tests-external/` always run; T5/T6/T8/T9 (LLM and
real video) are gated by `E2E_REAL_LLM=1` / `E2E_REAL_VIDEO=1` env
vars. T9 (Seedance first-3-shots) requires real `VIDEOCLAW_ARK_API_KEY`.

## Manifest discovery

```bash
python packaging/manifest-validate.py packaging/agent-cli.yaml
# VALID: packaging/agent-cli.yaml conforms to agent-cli/v1
```

`agent-cli.yaml` is **informational** — orchestrators that already
read manifests can auto-wire videoclaw, but the primary path is now
skills + CLI. The manifest declares: 5 commands, MCP tool list,
exit_codes (0-4), distribution channels, health_check.

```bash
python packaging/skills-validate.py skills/
# VALID: 5 skill(s) under skills conform (version 0.1.4)
```

## Write-scope (M002 + M003)

`feat/agent-cli-toolkit` is reviewable as a mostly-additive diff.
The src/ files touched are:

- `src/videoclaw/cli/setup.py` — implements `claw setup`. M002 added
  the python-fallback installer (~150 LOC). M003 adds `_try_npx_skills`
  delegation + `--copy` / `--no-npx` flags + `installer` envelope
  field (~120 LOC additive; M002 helpers untouched).
- `src/videoclaw/cli/doctor.py` — small change (~10 lines): adds
  Evolink key check + `typer.Exit(code=3)` when required keys
  missing, per the agent-cli exit-code contract.

Plus one import line in `src/videoclaw/cli/__init__.py` to register
the `claw setup` command. Everything else lands under `skills/`,
`packaging/`, `mcp-shim/`, `install.sh`, `docs/`, `.github/`,
`README.md`, `AGENTS.md`, `RELEASE_NOTES.md`.
