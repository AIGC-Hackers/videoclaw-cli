# videoclaw — packaging

Recipe for shipping `claw` as an agent-callable CLI: wheel, PyInstaller
binary, Docker image, and an `.agent-cli.yaml` manifest that orchestrators
read to auto-discover the surface.

The top-level `agent-cli-release-gate.sh` is the deployment-agent entrypoint
for the full release contract. It calls the packaging tools here, then verifies
the rebuilt wheel through a fresh installed `claw` CLI.

## Files in this directory

| File | Purpose |
|---|---|
| `AUDIT.md` | Four-bucket inventory of the existing CLI surface + ship-vs-skip matrix. |
| `pyproject.overlay.toml` | Hatchling `source-exclude` block applied at `uv build` time via `--config-file`. |
| `claw.spec` | PyInstaller spec — one-file (default) and one-dir (`PYINSTALLER_ONEDIR=1`). |
| `_entry.py` | Entry shim for PyInstaller / `python -m`; imports `videoclaw.cli:app`. |
| `Dockerfile` | Multi-stage CLI image; parallel to the FastAPI image at repo root. |
| `dist-verify.sh` | Builds wheel + binary + image and smoke-tests `claw version`. |
| `agent-cli.yaml` | Deployment manifest (schema `agent-cli/v1`). |
| `manifest-validate.py` | Schema validator for the manifest above. |
| `envelope_shim.md` | Design note — boundary-wrapper plan for the `agent-cli/v1` envelope. |

The MCP server lives in the sibling `mcp-shim/` tree; see `mcp-shim/README.md`.

## Quickstart

```bash
# Full agent-callable CLI gate from the repo root.
./agent-cli-release-gate.sh ci
./agent-cli-release-gate.sh version
./agent-cli-release-gate.sh release --with-npx

# Build all three distribution artifacts and smoke-test each.
bash packaging/dist-verify.sh

# Skip stages when their tooling is missing on the host:
STAGE_DOCKER=0 STAGE_BIN=0 bash packaging/dist-verify.sh   # wheel only

# Validate the manifest.
python packaging/manifest-validate.py packaging/agent-cli.yaml

# Build the MCP shim (sibling project).
uv pip install -e mcp-shim/
videoclaw-mcp-server                      # blocks on stdio for tools/list
```

## Deferred (future milestones)

The blueprint splits work into P0 / P1 / P2 (see
`agent-cli-toolkit/docs/videoclaw-packaging-plan.md` in the toolkit, kept
out of the published repo). P0 + P1 are delivered here; P2 is deferred:

- `claw mcp-server` and `claw acp` subcommands — staying out of the namespace
  for now to avoid a breaking surface change.
- Full XDG / `~/.config/videoclaw` migration with `CLAW_*` env-prefix
  aliasing.
- `--version/-V` eager root flag (today's `claw version` subcommand stays).
- `agent-cli/v1` envelope wrapper (design note only — wrapper script comes
  later).

## Shape recap

```
videoclaw/                       (repo root)
├── src/videoclaw/               (source — untouched in this milestone)
├── packaging/                   (recipe — this directory)
│   ├── AUDIT.md
│   ├── pyproject.overlay.toml
│   ├── claw.spec
│   ├── _entry.py
│   ├── Dockerfile
│   ├── dist-verify.sh
│   ├── agent-cli.yaml
│   ├── manifest-validate.py
│   ├── envelope_shim.md
│   └── README.md                (this file)
├── mcp-shim/                    (sibling — MCP shim)
│   ├── pyproject.toml
│   ├── mcp_server.py
│   └── README.md
├── pyproject.toml               (in-tree — unchanged)
└── Dockerfile                   (in-tree — unchanged; FastAPI image)
```
