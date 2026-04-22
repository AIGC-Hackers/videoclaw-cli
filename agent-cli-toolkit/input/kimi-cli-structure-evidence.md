# S1 — Macro Structure

Source: `~/Moose/kimi-cli` @ v1.37.0. Every claim cites `path:line` in kimi-cli.

## 1. Top-level shape — a uv monorepo with embedded web UI

Kimi-cli is **not** a single package. It is a `uv` workspace with four members plus two Vite frontends that get baked into the wheel.

```
kimi-cli/
├── pyproject.toml          # root package `kimi-cli` + workspace declaration
├── Makefile                # orchestrates all members + frontends
├── kimi.spec               # PyInstaller one-file/one-dir binary spec
├── flake.nix, flake.lock   # Nix dev env (ignore; Nix is optional)
├── src/kimi_cli/           # root package source (21 subpackages)
├── packages/
│   ├── kosong/             # agent runtime (model loop, tool calls, streaming)
│   ├── kaos/               # pykaos — low-level kernel helpers
│   └── kimi-code/          # separately distributable "code" flavor
├── sdks/
│   └── kimi-sdk/           # public Python SDK for embedding the agent
├── web/                    # Vite+React UI served by FastAPI
├── vis/                    # Vite+React debug-visualizer UI
├── tests/                  # unit + integration (pytest)
├── tests_e2e/              # end-to-end (pytest, spawns real subprocess)
├── tests_ai/               # AI-driven tests (run by the kimi agent itself)
├── examples/               # doc / example payloads
├── klips/                  # video clips (demo assets)
├── scripts/                # build glue (build_web.py, build_vis.py)
└── docs/                   # user docs site (mkdocs-style)
```

Verification: `ls ~/Moose/kimi-cli/`; `find ~/Moose/kimi-cli -maxdepth 2 -type d`.

## 2. Workspace declaration — the uv-native way

`pyproject.toml:60-71`:

```toml
[tool.uv.workspace]
members = [
    "packages/kosong",
    "packages/kaos",
    "packages/kimi-code",
    "sdks/kimi-sdk",
]

[tool.uv.sources]
kosong = { workspace = true }
pykaos = { workspace = true }
kimi-cli = { workspace = true }
```

**Methodology note**: the workspace pattern lets a monorepo ship multiple wheels from one repo without sym-link hacks or editable-install gymnastics. `uv sync --all-packages` (`Makefile:18`) installs every member in editable mode into the same `.venv`. Contrast with a single-package repo (videoclaw): if you later split `drama`, `agents`, `models` into independent publishables, uv workspace is the low-friction path.

## 3. Entry points — two names, one `main`

`pyproject.toml:73-75`:

```toml
[project.scripts]
kimi = "kimi_cli.__main__:main"
kimi-cli = "kimi_cli.__main__:main"
```

Dual name (`kimi` and `kimi-cli`) = short primary + unambiguous alias. `__main__:main` means `python -m kimi_cli` also works — a useful property for debuggers and CI sandboxes that don't put `~/.local/bin` on PATH.

## 4. Build backend — `uv_build`, not hatch/setuptools/poetry

`pyproject.toml:52-58`:

```toml
[build-system]
requires = ["uv_build>=0.8.5,<0.10.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = ["kimi_cli"]
source-exclude = ["examples/**/*", "tests/**/*", "src/kimi_cli/deps/**/*"]
```

`uv_build` is uv's native PEP 517 backend. Two things to steal:
1. **Explicit `module-name`** — avoids ambiguity when `src/` has multiple top-level packages.
2. **`source-exclude`** — prunes examples, tests, and vendored deps from the sdist/wheel. Videoclaw's wheel today likely ships tests; this is the clean way to fix it without `MANIFEST.in`.

## 5. Python version & type strictness

`pyproject.toml`:

- `requires-python = ">=3.12"` (line 6)
- `pyright.pythonVersion = "3.14"` (line 97), `strict = ["src/kimi_cli/**/*.py"]` (line 104)
- `ty.environment.python-version = "3.14"` (line 107) — a second type checker (`ty`) run non-blockingly (`Makefile:72`)

**Methodology**: dual-checker strategy (strict pyright for gate, ty as leading-indicator) catches regressions that one tool misses, without making ty's churn block PRs.

## 6. `src/kimi_cli/` — 21 subpackages, each a single concern

From `find src/kimi_cli -maxdepth 1 -type d`:

| Subpackage | Concern (one line) |
|------------|---------------------|
| `__main__.py` | process entry, arg parsing dispatch |
| `cli/` | Typer command tree |
| `acp/` | Agent Client Protocol adapter (IDE integration) |
| `agents/` | per-agent personas/prompts |
| `approval_runtime/` | permission/confirmation engine for tool calls |
| `auth/` | login, keyring-backed credentials |
| `background/` | long-running task manager |
| `deps/` | vendored runtime deps (excluded from wheel, see §4) |
| `hooks/` | lifecycle hooks (on_start, on_stop, etc.) |
| `notifications/` | desktop notifications (pyobjc on macOS) |
| `plugin/` | plugin loader |
| `prompts/` | prompt templates |
| `skill/` + `skills/` | skill framework + packaged skills |
| `soul/` | agent identity / system-prompt scaffolding |
| `subagents/` | spawning nested agents |
| `telemetry/` | metrics/tracing |
| `tools/` | tool definitions exposed to the model |
| `ui/` | terminal UI (prompt-toolkit + rich) |
| `utils/` | misc helpers |
| `vis/` | debug visualizer (FastAPI backend for `vis/` frontend) |
| `web/` | web UI backend (FastAPI factory at `web.app:create_app`) |
| `wire/` | transport/serialization layer |

**Methodology note**: each directory is a **concern**, not a **layer**. The repo does not segregate "models vs views vs services" — it segregates "CLI vs ACP vs web" on the boundary side, and "tools vs skills vs hooks vs subagents" on the agent side. Videoclaw's `src/videoclaw/` already follows this (`cli/`, `drama/`, `agents/`, `models/`, `generation/`) — keep that and formalize it.

## 7. Runtime dependency budget

`pyproject.toml:7-39`. Grouped by role:

| Role | Packages |
|------|----------|
| CLI framework | `typer==0.21.1`, `prompt-toolkit==3.0.52`, `rich==14.2.0` |
| Agent runtime | `kosong[contrib]==0.50.0` (local workspace), `pykaos==0.9.0` |
| Async I/O | `aiohttp==3.13.3`, `aiofiles>=24.0,<26.0`, `httpx[socks]==0.28.1`, `websockets>=14.0` |
| Web/server | `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `scalar-fastapi>=1.5.0` |
| Agent protocol | `agent-client-protocol==0.8.0`, `fastmcp==2.12.5` |
| Data/validation | `pydantic==2.12.5`, `pyyaml==6.0.3`, `tomlkit==0.14.0`, `streamingjson==0.0.5` |
| Content | `trafilatura==2.0.0`, `lxml==6.0.2`, `ripgrepy==2.2.0`, `pillow==12.1.0`, `jinja2==3.1.6` |
| Reliability | `tenacity==9.1.2`, `loguru>=0.6.0,<0.8` |
| OS integration | `keyring>=25.7.0`, `setproctitle>=1.3.0`, `pyobjc-framework-cocoa` (darwin only) |

**Methodology**: pins are **exact** for hot-path deps (typer, rich, pydantic, httpx) and **ranged** for low-churn ones (aiofiles, loguru, fastapi). This balances reproducibility against transitive-constraint pain. Compare to videoclaw's `pyproject.toml` (more ranges) — kimi's exact pinning is what you want once a CLI has real users.

## 8. Dev/build dependency groups

`pyproject.toml:41-50`:

```toml
[dependency-groups]
dev = [
    "pyinstaller==6.18.0",
    "inline-snapshot[black]>=0.31.1",
    "pyright>=1.1.407",
    "ty>=0.0.9",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "ruff>=0.14.10",
]
```

Note `pyinstaller` lives in `dev`, not runtime — binary build is a dev concern. `inline-snapshot` is a snapshot-testing library (covered in S8).

## 9. Python / Node split

- **Python**: all CLI / agent / server / protocol logic.
- **Node (npm)**: `web/` (user-facing web UI) and `vis/` (debug visualizer). Both are Vite projects.
- **Bridge**: `scripts/build_web.py` and `scripts/build_vis.py` (invoked by `Makefile:131-135`) call `npm run build`, then copy the `dist/` output into the Python package so the wheel ships the UI. `build-kimi-cli` depends on `build-web build-vis` (`Makefile:116`), so `uv build` ships a wheel with UI bundled.

**Methodology note**: treat the frontend as a **build-time dependency of the wheel**, not a sibling package users install separately. This avoids version-skew between backend and frontend.

## 10. Makefile target inventory

Target count: ~30 phony targets. Grouped:

| Group | Targets |
|-------|---------|
| setup | `help`, `install-prek`, `prepare`, `prepare-build` |
| dev servers | `web-back`, `web-front`, `vis-back`, `vis-front` |
| format | `format`, `format-{kimi-cli,kosong,pykaos,kimi-sdk,web}` |
| lint+type | `check`, `check-{kimi-cli,kosong,pykaos,kimi-sdk,web}` |
| test | `test`, `test-{kimi-cli,kosong,pykaos,kimi-sdk}`, `ai-test` |
| build | `build`, `build-{kimi-cli,kosong,pykaos,kimi-sdk,web,vis,bin,bin-onedir}` |
| docs | `gen-changelog`, `gen-docs` (both invoke `uv run kimi --yolo --prompt /skill:…` — the CLI generates its own docs) |

`Makefile:160` pulls in `src/kimi_cli/deps/Makefile` — a sub-Makefile that handles downloading vendored runtime deps (`download-deps` referenced at `Makefile:16`). Split-Makefile keeps the top clean.

**Methodology note worth stealing**:
1. **Uniform per-package target pattern** (`{verb}-{package}`). Scaling to N workspace members is copy-paste, not recursion hacks.
2. **Self-generated docs/changelog** (`gen-docs`, `gen-changelog`). The agent produces its own release notes by reading git history via `/skill:gen-changelog`. Dogfooding as release process.
3. **`.DEFAULT_GOAL := prepare`** (`Makefile:1`) — `make` bare sets up the dev env. Zero-config onboarding.

## 11. What this stage intentionally does NOT cover

- How Typer commands are declared → **S2**
- The agent loop itself → **S3**
- Config/secret storage → **S4**
- Tool registration → **S5**
- Plugin/MCP/skill extension points → **S6**
- PyInstaller spec contents → **S7**
- Snapshot/AI/e2e test tiers → **S8**

## 12. Apply-to-videoclaw checklist (previewing S10)

- [ ] Consider uv workspace if `drama/`, `agents/`, `models/` need independent release cadence.
- [ ] Switch build backend to `uv_build`, set `tool.uv.build-backend.source-exclude` to prune `tests/`, `docs/`, `examples/`.
- [ ] Pin hot-path deps exactly (typer, pydantic, httpx, litellm).
- [ ] Add `ty` alongside `mypy` as a non-blocking second opinion.
- [ ] `.DEFAULT_GOAL := install` or similar — bare `make` should bootstrap the dev env.
- [ ] If videoclaw ever ships a UI, build it into the wheel via a `scripts/build_*.py` bridge.
