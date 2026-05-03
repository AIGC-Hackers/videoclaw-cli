# videoclaw — Distribution Plan (CLI-first, MCP-optional)

This plan turns videoclaw into a CLI that **any** code agent — Claude
Code, Cursor, Cline, Codex, openclaw, custom orchestrators — can call
through its Bash / shell tool, without requiring MCP. MCP via
`mcp-shim/` stays available as an alternative for agents that prefer
structured tool discovery, but it is no longer the primary integration
boundary.

## 1. Why CLI-first

Every code agent supports shell invocation; MCP support is a strict
subset. Treating the CLI as the universal contract:

- removes the per-agent registration step (`mcp.servers.videoclaw`),
- removes the `videoclaw-mcp-server` editable-install requirement,
- lets agents introspect with `claw --help` and parse `claw --json …`
  without speaking JSON-RPC,
- works inside short-lived sandboxes where stdio MCP servers are awkward.

The MCP shim stays for agents that want first-class tool listings, but
the headline path is `Bash("claw …")`.

## 2. Distribution channels (ranked by friction)

| Channel | Command | Needs | When to recommend |
|---|---|---|---|
| **A. `uv tool install`** | `uv tool install videoclaw` | Python ≥3.12 + uv | Python-aware hosts (most dev laptops, CI). |
| **B. PyInstaller binary via `install.sh`** | `curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh \| sh` | `curl`, `sh` | Servers / sandboxes without Python. |
| **C. Docker image** | `docker run --rm ghcr.io/aigc-hackers/videoclaw-cli:0.1.0 …` | Docker | Containerized agents, multi-tenant hosts. |
| **D. Wheel from GitHub Releases** | `pip install <release-url>/videoclaw-0.1.0-py3-none-any.whl` | Python ≥3.12 | Air-gapped or pinned environments. |

All four channels resolve to the same `claw` binary on PATH and the
same `--json` envelope contract.

## 3. The CLI invocation contract

This is what every consuming agent should rely on. It is the only
contract; once an agent is confident in this surface, MCP becomes
unnecessary.

### 3.1 Stable command surface (read-only or status)

```
claw version                                    # version string
claw --json doctor                              # health check, exit 0 if OK
claw --json info                                # registered models / drama series count
claw drama list --json                          # series listing
claw drama show <series_id> --json              # series metadata
claw model list --json                          # registered video adapters
```

### 3.2 Mutating command surface (drama pipeline)

```
claw drama new "<synopsis>" --title "<t>" --lang zh
claw drama plan <series_id>
claw drama script <series_id> --episode 1
claw drama design-scenes <series_id>
claw drama design-characters <series_id>
claw drama assign-voices <series_id>
claw drama run <series_id> --max-shots 3 [--dry-run]
claw drama export <series_id>
```

### 3.3 JSON envelope (every `--json` response)

Today's envelope is `{ok, version, command, data, error}`. The blueprint
prescribes evolving toward `agent-cli/v1`
(`{schema:"agent-cli/v1", ok, data, error:{code,message,hint}}`) via a
boundary wrapper — this is `packaging/envelope_shim.md`'s territory and
is not part of this milestone.

### 3.4 Exit codes

`0` ok · `1` runtime error · `2` usage error · `3` auth needed ·
`4` blocked. Agents should branch on these without parsing stderr.

### 3.5 Capability self-description

The deployment manifest at `packaging/agent-cli.yaml` (schema
`agent-cli/v1`) is the machine-readable capability descriptor.
`packaging/manifest-validate.py` is the schema check. Agents that
cache discovery results read this once at install time.

## 4. "Continue with CLI setup" — first-run wizard

Once `claw` is on PATH, any host (human or agent) runs
`bash packaging/setup.sh` (also installable via `curl ... | sh`,
see §5 below) which:

1. Detects the existing config dir (`$XDG_CONFIG_HOME/videoclaw/` or
   `~/.config/videoclaw/`, falling back to a project-local `.env` in
   `$PWD` when in a videoclaw repo).
2. Prompts for the four canonical keys:
   - `VIDEOCLAW_EVOLINK_API_KEY` (LLM gateway, required)
   - `VIDEOCLAW_ARK_API_KEY` (Seedance video, required for real video)
   - `VIDEOCLAW_DEFAULT_VIDEO_MODEL` (default `seedance-2.0`)
   - `VIDEOCLAW_PROJECTS_DIR` (default `./projects`)
3. Writes the file with `chmod 600`.
4. Runs `claw --json doctor` and reports the result.
5. Prints a `setup/v1` JSON envelope on stdout so an orchestrator can
   parse the outcome::

    ```json
    {
      "schema": "videoclaw-setup/v1",
      "ok": true,
      "config_path": "/Users/.../.config/videoclaw/.env",
      "version": "0.1.0",
      "doctor_passed": true,
      "next_steps": ["claw drama new \"<synopsis>\" --title <t>"]
    }
    ```

The wizard is idempotent — re-running it updates only the keys the user
re-enters, leaves the rest alone.

## 5. Public install one-liner

Repository root carries `install.sh`:

```bash
curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh
```

The script:

1. Detects OS / arch (`uname -s | -m`).
2. Picks Channel A (uv tool) when `uv` is on PATH; otherwise Channel B
   (PyInstaller binary). Channels C / D are documented but not
   auto-installed (Docker / wheel are deliberate user choices).
3. Verifies the downloaded artifact via `SHA256SUMS` from the GitHub
   Release — refuses to install on mismatch.
4. Drops the binary at `${INSTALL_DIR:-$HOME/.local/bin}/claw` with
   `chmod +x`. Refuses to install as root (`id -u != 0`).
5. Outputs a `videoclaw-install/v1` JSON envelope as the last stdout
   line for orchestrator parsing.
6. After a successful install, suggests `claw setup` (wizard from §4)
   as the next step.

## 6. Test plan

| Layer | Tool | What it covers |
|---|---|---|
| Unit | `mcp-shim/tests/test_tools_unit.py` | each MCP tool individually (in-process). |
| Protocol | `mcp-shim/tests/test_mcp_protocol.py` | initialize → tools/list / tools/call over real stdio subprocess. |
| External T1-T4 | `tests-external/test_e2e_first_3_shots.py` | drama new + MCP discovery / metadata round-trip. |
| External T5-T7 | `tests-external/test_e2e_first_3_shots.py` | LLM-driven plan / script / design-scenes / design-characters → intermediate assets on disk. |
| External T8 | `tests-external/test_e2e_first_3_shots.py` | dry-run executor — proves the run wiring without billing. |
| External T9 | `tests-external/test_e2e_first_3_shots.py` | real Seedance video for the first 3 shots — the complete-asset gate. |
| Smoke after install | `claw version`, `claw --json doctor` | post-install sanity, no API calls. |
| Manifest | `python packaging/manifest-validate.py packaging/agent-cli.yaml` | `agent-cli/v1` schema conformance. |
| Build | `bash packaging/dist-verify.sh` | wheel + binary + image, single exit code. |

Smoke is what `install.sh` runs at the tail to confirm the install
landed correctly.

## 7. Release process (for v0.1.0)

When this branch is ready to ship:

1. Tag `v0.1.0` on `feat/agent-cli-toolkit` (or after merge to main).
2. CI (a `.github/workflows/release.yml` matching the toolkit template)
   builds:
   - wheel via `uv build --wheel`
   - PyInstaller binary via `packaging/claw.spec` on macOS arm64 +
     Linux x86_64 matrix
   - Docker image via `packaging/Dockerfile`
3. CI computes `SHA256SUMS` over every artifact and assembles
   `update-manifest.json` (schema `agent-cli-update/v1`, see the
   toolkit's `templates/update-manifest.json.tmpl` for the canonical
   fields).
4. CI uploads artifacts + `SHA256SUMS` + `update-manifest.json` to a
   GitHub Release.
5. `install.sh` reads the manifest from the Release URL and picks the
   matching (platform, arch) binary.

The release.yml workflow is **not yet present** on this branch — it is
the only piece between today and a one-line install. Adding it is a
small, isolated PR that does not require src/videoclaw/ edits.

## 8. Friction-elimination checklist

Status as of today:

- [x] Stable `claw` entry point (`pyproject.toml:51-52`).
- [x] `--json` envelope on every command (`src/videoclaw/cli/_output.py`).
- [x] Exit codes 0/1/2/3/4 (documented in `agent-cli.yaml`).
- [x] Wheel builds clean (no leakage of tests / projects / models_cache /
      .gsd / mcp-shim / packaging).
- [x] `agent-cli.yaml` manifest + validator.
- [x] `mcp-shim/` for MCP-preferring agents.
- [x] `tests-external/` proves Claude-Code-callable end-to-end.
- [ ] **`packaging/setup.sh` first-run wizard** — this milestone.
- [ ] **`install.sh` at repo root** — this milestone.
- [ ] **`.github/workflows/release.yml`** — next milestone.
- [ ] **GitHub Releases v0.1.0** with binary + checksums + manifest —
      depends on release.yml.
- [ ] XDG config dir (`~/.config/videoclaw/`) by default — P2 in the
      blueprint, deferred (would need src/videoclaw/ edits).
- [ ] Eager `--version/-V` flag — P2, deferred.
- [ ] `agent-cli/v1` envelope schema (with nested error) — P2, deferred.

When every box above is ticked, a fresh agent in any environment goes
from zero to a working drama pipeline in two commands::

    curl -fsSL .../install.sh | sh
    claw setup       # or: bash $(claw --packaging-root)/setup.sh
