# videoclaw — Agents quickstart

This branch (`feat/agent-cli-toolkit`) packages **videoclaw** as an
**agent-callable CLI**. Two integration paths:

1. **CLI-first (universal, recommended)** — `claw` on PATH + `--json`
   envelope. Any code agent (Claude Code, Cursor, Cline, Codex,
   openclaw, custom orchestrators) calls it via its built-in shell
   tool. No protocol setup, no per-agent registration.
2. **MCP (optional)** — `videoclaw-mcp-server` over stdio for agents
   that prefer structured tool discovery. Same source of truth, just
   a thinner read-only surface.

The CLI is the universal contract; MCP is a convenience.

## Two-command bootstrap

Everything below assumes one of these paths got `claw` on PATH:

```bash
# Path A — Python-aware host (uv tool install, post-v0.1.0 release):
curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh

# Path B — local source checkout right now:
uv pip install -e .
```

Then configure API keys::

```bash
bash packaging/setup.sh        # interactive wizard, writes ~/.config/videoclaw/.env
```

That's it. The wizard prints a `videoclaw-setup/v1` JSON envelope on
stdout so an orchestrator can confirm success programmatically.

The full distribution / install / setup / test / release plan lives at
**`packaging/DISTRIBUTION-PLAN.md`**.

## What ships on this branch

| Path | What it is | Who consumes it |
|---|---|---|
| `install.sh` | Public one-line installer (uv-tool / PyInstaller binary fallback, SHA256 verify, JSON envelope on stdout). | Any host bootstrapping `claw`. |
| `packaging/setup.sh` | "Continue with CLI setup" interactive wizard (writes `.env`, runs `claw doctor`, prints `videoclaw-setup/v1` JSON). | Any host post-install. |
| `packaging/DISTRIBUTION-PLAN.md` | The 8-section plan (channels / contract / setup / test / release / friction checklist). | Reviewers + ops. |
| `mcp-shim/` | FastMCP stdio server exposing 4 read-only tools. Optional. | MCP-preferring clients (Claude Code, IDEs). |
| `packaging/AUDIT.md` | Four-bucket audit of the existing CLI surface + ship-vs-skip matrix. | Reviewers. |
| `packaging/Dockerfile` | Multi-stage CLI image, parallel to the FastAPI image at the repo root. | Container hosts. |
| `packaging/claw.spec` + `packaging/_entry.py` | PyInstaller spec for a no-Python-required binary. | Hosts without Python. |
| `packaging/pyproject.overlay.toml` | Hatchling source-exclude for future sdist publishing. | Reference only — wheel is already clean. |
| `packaging/dist-verify.sh` | Builds wheel + binary + image; smoke-tests `claw version`. | CI / local dev. |
| `packaging/agent-cli.yaml` | `agent-cli/v1` deployment manifest. | Orchestrators auto-discovering videoclaw. |
| `packaging/manifest-validate.py` | Schema validator for the manifest above. | CI / local dev. |
| `packaging/envelope_shim.md` | Design note for the future `agent-cli/v1` envelope wrapper. | Future milestone. |

The work is split into the toolkit's P0 / P1 / P2 buckets:

- **P0 (delivered)** — MCP shim with read-only tools. Unblocks agent interop today.
- **P1 (delivered)** — Distribution recipe (wheel + PyInstaller + Docker) and the manifest.
- **P2 (deferred)** — `claw mcp-server` / `claw acp` subcommands, XDG migration with `CLAW_*` env aliasing, eager `--version` flag, the envelope wrapper. All require `src/videoclaw/` edits and are out of scope for this branch.

## How code agents use videoclaw

### From Claude Code (or any MCP-compatible client)

```bash
# 1. Install the shim (editable from this repo).
uv pip install -e mcp-shim/

# 2. Register the server with your MCP client. Example for Claude Code's
#    ~/.claude/settings.json:
#    {
#      "mcpServers": {
#        "videoclaw": {
#          "command": "videoclaw-mcp-server",
#          "args": []
#        }
#      }
#    }

# 3. The agent now sees four tools via tools/list:
#    - list_drama_series
#    - get_drama_series(series_id)
#    - list_video_models
#    - get_videoclaw_version
```

### From openclaw / custom orchestrators

```python
import json, asyncio
from asyncio.subprocess import PIPE


async def call_tool(name: str, arguments: dict) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "videoclaw-mcp-server", stdin=PIPE, stdout=PIPE, stderr=PIPE
    )
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "openclaw", "version": "0.1"}}}
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}
    for msg in (init, notif, call):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()
    _ = await proc.stdout.readline()  # initialize response
    raw = await proc.stdout.readline()  # tools/call response
    proc.terminate()
    return json.loads(raw.decode())


# orchestrator code:
result = asyncio.run(call_tool("list_drama_series", {}))
print(result["result"]["content"])
```

The orchestrator never has to know videoclaw's internal Python API —
`videoclaw-mcp-server` is the boundary.

### As a containerized batch tool

```bash
# Build the CLI image (separate from the existing FastAPI image at /Dockerfile).
docker build -t videoclaw-cli -f packaging/Dockerfile .

# Drive videoclaw from another container.
docker run --rm \
  -v $HOME/.config/videoclaw:/home/claw/.config/videoclaw \
  videoclaw-cli drama list --json
```

### As a no-Python binary

```bash
uv pip install pyinstaller
bash packaging/dist-verify.sh   # builds wheel + binary

./dist/claw version
./dist/claw drama list --json
```

## External tests

Two layers, both under `mcp-shim/tests/`:

- **Single-point** (`test_tools_unit.py`, 5 tests) — each tool exercised
  individually via fastmcp's in-process `Client(mcp)`. Verifies the tool is
  registered, returns the expected shape, is read-only, and surfaces missing
  inputs as errors instead of crashing.
- **Integration** (`test_mcp_protocol.py`, 2 tests) — spawn
  `videoclaw-mcp-server` as a real subprocess, send the standard MCP opening
  sequence (`initialize` → `notifications/initialized` → request) over stdio,
  parse the response. Mirrors what Claude Code / openclaw actually do.

Run both layers:

```bash
uv pip install -e "mcp-shim/[test]"
uv run pytest mcp-shim/tests/ -v
# 7 passed
```

The integration tests use **Pattern 2b** from the toolkit's S05
known-limitations notes — `asyncio.create_subprocess_exec + readline +
terminate` — to avoid the stdin-EOF deadlock that hits fastmcp 2.12.5 with
`subprocess.run(input=..., capture_output=True)`.

## Manifest discovery

```bash
python packaging/manifest-validate.py packaging/agent-cli.yaml
# VALID: packaging/agent-cli.yaml conforms to agent-cli/v1
```

The manifest declares:
- `name: videoclaw` / `binary: claw` / `version: 0.1.0`.
- 5 commands (`version`, `--json doctor`, `--json info`, `drama`, `model list`).
- `mcp:` block listing the 4 read-only tools and the install hint.
- `health_check`: `{binary} --json doctor` expecting exit 0 + `.ok == true`.
- `distribution`: wheel / pyinstaller / docker artifact patterns.

Orchestrators that read `agent-cli/v1` manifests can auto-wire videoclaw
without scraping `--help`.

## What stays untouched

Per the videoclaw-packaging blueprint's **write-scope lock**:

- `src/videoclaw/**` — zero edits.
- `tests/**` (the existing pytest suite) — zero edits.
- `pyproject.toml` (in-tree) — zero edits.
- `Dockerfile` (the existing FastAPI image) — zero edits.

All new artifacts live under `packaging/`, `mcp-shim/`, or this top-level
`AGENTS.md`. The branch is reviewable as one purely additive diff.
