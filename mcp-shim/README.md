# videoclaw-mcp-shim

MCP server exposing videoclaw's read-only surface to other agents over stdio.

## Why this is a sibling project

Per the packaging blueprint (`packaging/AUDIT.md`), the shim wraps videoclaw at
the boundary — it imports videoclaw as a library and never edits
`src/videoclaw/**`. Shipping it as a separate distributable lets users pin
`fastmcp` independently and lets the videoclaw wheel stay shim-free.

## Install (editable, from repo root)

```bash
uv pip install -e mcp-shim/
```

This installs both `videoclaw-mcp-server` (the entry point) and the local
videoclaw package (editable, via `[tool.uv.sources]`).

## Run

```bash
videoclaw-mcp-server                 # stdio server, blocks until EOF
python -m mcp_server                 # equivalent
```

Other agents (Claude Code, Codex, IDEs supporting MCP) discover tools via the
`tools/list` JSON-RPC method on the stdio transport.

## Tool surface (read-only)

| Tool | Wraps |
|---|---|
| `list_drama_series` | `DramaManager().list_series()` |
| `get_drama_series` | `DramaManager().load(series_id)` |
| `list_video_models` | `ModelRegistry.list_models()` |
| `get_videoclaw_version` | `videoclaw.__version__` |

Mutating tools (drama generation, scene design, video synthesis) are
intentionally out of scope for this shim — they remain CLI-driven via `claw
drama …` per the blueprint's "Write-scope lock" decision.
