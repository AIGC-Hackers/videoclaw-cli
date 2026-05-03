<div align="center">
  <h1>VideoClaw</h1>
  <p><strong>The Agent OS for AI Video Generation</strong></p>
  <p>
    Orchestrate multiple AI models. Automate entire video pipelines.<br/>
    From script to publish — one command, one flow, zero babysitting.
  </p>
  <p>
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#features">Features</a> &bull;
    <a href="#clawflow">ClawFlow</a> &bull;
    <a href="#architecture">Architecture</a> &bull;
    <a href="#supported-models">Models</a> &bull;
    <a href="#contributing">Contributing</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/license-Modified%20MIT-blue" alt="License" />
    <img src="https://img.shields.io/badge/python-3.12+-green" alt="Python" />
    <img src="https://img.shields.io/badge/tests-700%2B%20passing-brightgreen" alt="Tests" />
    <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Docker-lightgrey" alt="Platform" />
  </p>
</div>

---

## Install

Pick the path that matches your environment. All four resolve to the same
`claw` binary on `PATH`.

### A. One-line installer (recommended, no Python required)

> Available once `v0.1.0` is tagged and the GitHub Release is published.
> CI is set up; see [`.github/workflows/release.yml`](.github/workflows/release.yml).

```bash
curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh
```

The script auto-detects your OS / arch (darwin/arm64 + linux/x86_64
supported), prefers `uv tool install videoclaw` when `uv` is on `PATH`,
otherwise downloads the matching PyInstaller binary from GitHub Releases,
verifies the SHA256 against the release manifest, and drops the binary at
`$HOME/.local/bin/claw`. Refuses to install as root. Last stdout line is a
machine-readable `videoclaw-install/v1` JSON envelope for orchestrator
parsing.

### B. From source (Python ≥ 3.12, works today)

```bash
git clone https://github.com/AIGC-Hackers/videoclaw-cli.git videoclaw
cd videoclaw
uv sync            # installs deps + creates .venv
uv run claw --help # done. No activation needed.
```

> Or activate the venv: `source .venv/bin/activate && claw --help`.

### C. Docker (CLI image)

```bash
docker build -t videoclaw-cli -f packaging/Dockerfile .
docker run --rm \
  -v $HOME/.config/videoclaw:/home/claw/.config/videoclaw \
  videoclaw-cli version
```

The CLI image at `packaging/Dockerfile` ships parallel to the existing
FastAPI image at the repo root (`/Dockerfile` + `docker-compose.yml`,
`uvicorn :8000` for the optional `server` extra) — they don't replace
each other.

### D. Wheel from GitHub Releases (post-v0.1.0)

```bash
pip install https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl
```

Useful for air-gapped or pinned environments. The release also ships an
`update-manifest.json` (schema `agent-cli-update/v1`) listing every
artifact's `sha256` + `size` + `download_url` for automated update flows.

### Continue with CLI setup

After installing via any channel above, run the interactive wizard to
configure API keys:

```bash
bash packaging/setup.sh    # interactive
bash packaging/setup.sh --quiet    # CI / re-run mode (keeps existing values)
```

The wizard:

1. Detects an existing config (`$XDG_CONFIG_HOME/videoclaw/.env` →
   `~/.config/videoclaw/.env` → repo-local `.env` when run from a
   videoclaw checkout).
2. Prompts for `VIDEOCLAW_EVOLINK_API_KEY`, `VIDEOCLAW_ARK_API_KEY`,
   `VIDEOCLAW_DEFAULT_VIDEO_MODEL`, `VIDEOCLAW_PROJECTS_DIR`. Empty
   answers keep existing values (idempotent re-runs).
3. Writes the file with `chmod 600` and runs `claw --json doctor`.
4. Last stdout line is a machine-readable `videoclaw-setup/v1` JSON
   envelope so an orchestrator can parse the outcome.

Sample envelope:

```json
{"schema":"videoclaw-setup/v1","ok":true,"config_path":"/Users/.../.config/videoclaw/.env","version":"0.1.0","doctor_passed":true,"error":null,"next_steps":["claw drama new \"<synopsis>\" --title <title> --lang zh"]}
```

---

> **VideoClaw doesn't generate videos. It orchestrates the models that do.**
>
> Think Kubernetes for containers, but for AI video generation.

## Why VideoClaw?

You've tried Sora, Runway, Kling, CogVideo... Each is impressive alone.
But making a *real* video still means:

- Writing prompts for each shot manually
- Waiting, downloading, re-uploading between tools
- No idea what it costs until the bill arrives
- Starting from scratch when one shot fails
- Manually stitching, adding subtitles, music, voiceover

**VideoClaw fixes all of this.**

## Quick Start

```bash
# Install from source (one of the four channels above; this is the
# zero-friction path until v0.1.0 is published).
git clone https://github.com/AIGC-Hackers/videoclaw-cli.git videoclaw
cd videoclaw
uv sync                          # Install dependencies + create .venv

# Configure API keys (Evolink LLM gateway, Seedance video, model defaults).
bash packaging/setup.sh          # interactive wizard

# Sanity check.
uv run claw version              # → "VideoClaw v0.1.0"
uv run claw --json doctor        # → {"ok": true, ...}

# Generate a video from a single prompt.
uv run claw generate "A 30-second product intro for a smart watch, cinematic style"

# Or run individual stages independently.
uv run claw video "A cat riding a skateboard" -d 5 -o cat.mp4
uv run claw image "Character portrait" --provider gemini -o portrait.png
uv run claw tts "Hello world" --lang en -o hello.mp3
uv run claw storyboard "Product unboxing" -d 30 -o shots.json

# Agent-friendly: JSON output for programmatic use.
uv run claw -j video "sunset over ocean" -o sunset.mp4
# → {"ok": true, "command": "video", "data": {"path": "...", "cost_usd": 0.05}, "error": null}

# Or run a YAML pipeline.
uv run claw flow run examples/product-promo.yaml
```

### For code agents (Claude Code, Cursor, Cline, Codex, openclaw, …)

Two integration paths — the CLI is universal; MCP is optional convenience.

**Path 1 — CLI via Bash tool (universal)**: every code agent has a shell
tool. After `claw` is on `PATH`, the agent calls it directly:

```bash
claw drama new "<synopsis>" --title "<title>" --lang zh
claw drama plan <series_id>
claw drama design-scenes <series_id>
claw drama run <series_id> --max-shots 3
```

Every command supports `--json` so the agent gets a predictable envelope
to parse. Exit codes follow the standard contract: `0` ok / `1` runtime /
`2` usage / `3` auth / `4` blocked.

**Path 2 — MCP shim (read-only discovery, optional)**: for clients that
prefer structured tool listings:

```bash
uv pip install -e mcp-shim/

# Register with Claude Code (~/.claude/settings.json):
# {
#   "mcpServers": {
#     "videoclaw": {"command": "videoclaw-mcp-server"}
#   }
# }
```

Exposes 4 read-only tools (`list_drama_series`, `get_drama_series`,
`list_video_models`, `get_videoclaw_version`). Mutating ops still go
through `claw drama …` via the agent's Bash tool — the shim
intentionally doesn't claim the `claw drama` namespace.

See [`AGENTS.md`](AGENTS.md) for the full integration shape and
[`packaging/DISTRIBUTION-PLAN.md`](packaging/DISTRIBUTION-PLAN.md) for
the channel matrix, contract, and release process.

## Features

### ClawFlow — YAML Pipelines

Define your entire video pipeline in a version-controllable YAML file:

```yaml
name: product-promo
variables:
  product: "VideoClaw"

steps:
  - id: script
    type: script_gen
    params:
      prompt: "Write a promo for {{product}}"

  - id: storyboard
    type: storyboard
    depends_on: [script]

  - id: hero_shot
    type: video_gen
    depends_on: [storyboard]
    params:
      prompt: "{{product}} logo reveal, cinematic"
      model_id: sora

  - id: narration
    type: tts
    depends_on: [script]

  - id: compose
    type: compose
    depends_on: [hero_shot, narration]

  - id: render
    type: render
    depends_on: [compose]
```

Features: variable interpolation (`{{var}}`), dependency validation, cycle detection, parallel execution of independent steps.

```bash
claw flow validate my-pipeline.yaml   # Check without running
claw flow run my-pipeline.yaml        # Execute the pipeline
```

### AI Short Drama Production

VideoClaw includes a complete production pipeline for TikTok-format Western AI short dramas — from script import to published episode:

```bash
# Import a script and set up the series
claw drama import script.docx --title "Satan in a Suit" --language en

# Design character turnaround sheets for visual consistency
claw drama design-characters <series_id>

# Preview Seedance 2.0 prompts before spending API credits
claw drama preview-prompts <series_id>

# Run the full pipeline: design → generate → audit → fix → export
claw drama pipeline <series_id> --episode 1

# Or run individual stages
claw drama run <series_id> --max-shots 5    # Test with first 5 shots
claw drama audit <series_id>                # Vision QA with Claude
claw drama audit-regen <series_id>          # Auto-fix failing shots
claw drama export <series_id>               # Export deliverables
```

**Key capabilities:**
- **Seedance 2.0** video generation (9:16 vertical, 720p)
- **Character consistency** via Universal Reference turnaround sheets
- **Vision QA** with Claude for automated shot quality review
- **Self-correcting audit-regen loop** — bad shots are auto-detected and regenerated
- **Multi-episode** series with cross-episode continuity

### Multi-Model Orchestration

One pipeline, multiple models. VideoClaw picks the best model for each shot based on your strategy — quality, speed, or cost.

```
Same 30s video:
  All Sora:              $2.50  ~3 min
  VideoClaw hybrid:      $0.47  ~2 min   <- auto-routes simple shots locally
  VideoClaw all-local:   $0.00  ~6 min
```

### Director Agent (LLM-Powered)

The Director takes your prompt and uses an LLM to produce a structured production plan: scene breakdown, visual descriptions, camera movements, voiceover script, and music style. Supports prompt refinement based on reviewer feedback.

### Video Agents

Protocol-based AI agents that think, act, review, and collaborate. Four built-in agents:

| Agent | Role | Wraps |
|-------|------|-------|
| **DirectorAgent** | Production planning, prompt refinement | `Director`, `DramaPlanner` |
| **CameramanAgent** | Visual prompt enhancement, shot generation | `PromptEnhancer`, `VideoGenerator` |
| **ReviewerAgent** | Vision QA, quality validation | `VisionAuditor`, `QualityValidator` |
| **ProducerAgent** | Pipeline orchestration, budget tracking | `DramaRunner`, `CostTracker` |

Agents plug into the DAG Executor via `AgentTeam.install_handlers()` — zero changes to the core pipeline. Third-party agents are auto-discovered via entry points.

### Built-in Cost Tracking

Real-time per-node cost display. Budget guards. Optimization hints. Know exactly what every video costs.

### Smart DAG Executor

Dependency-aware parallel execution. Shots generate concurrently. If one fails, others keep running. Resume from any checkpoint.

### Apple Silicon Ready

Designed for local inference on Mac. MPS backend support for PyTorch-based models.

## Architecture

```
  You --> AgentTeam --> DirectorAgent --> Planner --> DAG Executor
              |              |                            |
              |              v                   +--------+--------+
              |        CameramanAgent           v        v        v
              |              |              [Seedance] [Kling]  [Mock]
              |              v                  |        |        |
              |        ReviewerAgent           +--------+--------+
              |              |                          v
              v              v                   Compose → Render
         ProducerAgent --> Quality Gate                  |
                                                         v
                                                   Output / Publish
```

Seven-layer design:

| Layer | Purpose |
|-------|---------|
| Interface | CLI (`claw`) + REST API (optional) |
| Gateway | FastAPI server, WebSocket progress |
| Agent Runtime | AgentTeam, Director, Reviewer, Cameraman, Producer |
| Orchestration | DAG Planner, Executor, Event Bus, State Manager |
| Generation | Script, Storyboard, Video, TTS, Music, Compose |
| Model Adapters | Protocol-based adapters (Seedance, Kling, OpenAI, etc.) |
| Distribution | Publishers (YouTube, TikTok, Bilibili) |

## Supported Models

| Category | Models | Mode |
|----------|--------|------|
| Video | Seedance 2.0, Kling, Sora (OpenAI), MiniMax, ZhipuAI, CogVideoX | Cloud + Local |
| LLM | Claude, GPT, Qwen, DeepSeek, Ollama (via LiteLLM) | Cloud + Local |
| TTS | Edge-TTS, Fish-Speech, ElevenLabs, ChatTTS | Cloud + Local |
| Music | Suno, Udio, MusicGen | Cloud + Local |

> Adding a new model? Implement the `VideoModelAdapter` protocol (4 async methods). No ABC inheritance needed.

## CLI Commands

> All commands support `--json / -j` for structured JSON output (agent-friendly).

```bash
# Full pipeline
claw generate <prompt>              # Script → shots → compose → render
claw generate <prompt> --dry-run    # Preview DAG without executing

# Single-stage commands (run each step independently)
claw video <prompt>                 # Generate a single video clip
claw image <prompt>                 # Generate a single image
claw tts <text>                     # Text-to-speech (supports stdin pipe)
claw storyboard <prompt>            # Decompose prompt into shot list
claw compose <v1.mp4> <v2.mp4> ...  # Compose multiple clips together
claw render <input.mp4>             # Encode/render final video
claw subtitle <scenes.json>         # Generate SRT/ASS subtitles

# ClawFlow YAML pipelines
claw flow run <file.yaml>           # Execute a pipeline
claw flow validate <file.yaml>      # Validate without running

# AI short drama series (full production pipeline)
claw drama new <synopsis>           # Create series from concept
claw drama import <script.docx>     # Import complete script (locked mode)
claw drama plan <id>                # Plan episodes via LLM
claw drama script <id>              # Generate episode scripts
claw drama design-characters <id>   # Generate turnaround sheets
claw drama design-scenes <id>       # Generate scene reference images
claw drama assign-voices <id>       # Assign voice profiles
claw drama preview-prompts <id>     # Preview Seedance 2.0 prompts
claw drama run <id>                 # Execute generation pipeline
claw drama audit <id>               # Vision QA with Claude
claw drama audit-regen <id>         # Auto-fix failing shots
claw drama pipeline <id>            # Full pipeline (design → run → audit)
claw drama regen-shot <id> <shot>   # Regenerate single shot
claw drama export <id>              # Export deliverables
claw drama list                     # List all series
claw drama show <id>                # Show series details

# Management
claw config show                    # View all config (API keys masked)
claw config check                   # Validate config completeness
claw doctor                         # System health check
claw model list                     # List model adapters
claw project list                   # List all projects
claw project show <id>              # Show project details
claw project delete <id>            # Delete project and assets
```

## REST API

```bash
# Start the server
uvicorn videoclaw.server.app:create_app --factory

# Endpoints
GET  /health                  # Health check
POST /api/projects/           # Create project
GET  /api/projects/           # List projects
GET  /api/projects/{id}       # Get project details
DELETE /api/projects/{id}     # Delete project
POST /api/generate/           # Start generation pipeline
POST /api/generate/flow       # Run a ClawFlow pipeline
GET  /api/generate/{id}/status# Check generation status
WS   /ws/{project_id}        # Real-time progress updates
```

## Docker

```bash
docker compose up
# API available at http://localhost:8000
```

## Project Structure

```
videoclaw/
├── src/videoclaw/
│   ├── cli/                # CLI package (Typer + Rich)
│   │   ├── _app.py         # App definition, validators, helpers
│   │   ├── _output.py      # JSON output mode (OutputContext)
│   │   ├── stage.py        # Single-stage commands (video/image/tts/...)
│   │   ├── generate.py     # Full pipeline command
│   │   ├── drama.py        # Drama series commands
│   │   ├── config_cmd.py   # Config management
│   │   └── ...             # doctor, model, project, template, flow
│   ├── config.py           # Configuration (Pydantic Settings)
│   ├── core/               # Director, DAG engine, state, events
│   ├── agents/             # Video Agent framework (Director, Reviewer, Cameraman, Producer)
│   ├── models/             # Model adapters, registry, LLM wrapper
│   ├── generation/         # Script, storyboard, video, audio, compose
│   ├── drama/              # AI short drama orchestration
│   ├── cost/               # Cost tracking + budget guards
│   ├── flow/               # ClawFlow YAML parser + runner
│   ├── server/             # FastAPI REST API (optional, headless)
│   ├── storage/            # Local filesystem storage
│   ├── publishers/         # YouTube, Bilibili publishers
│   └── utils/              # FFmpeg helpers
├── examples/               # Example ClawFlow YAML pipelines
├── tests/                  # Unit + integration tests
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Configuration

The simplest path is `bash packaging/setup.sh` (see "Continue with CLI
setup" above) — it writes the four canonical keys to your config
`.env` with `chmod 600`. To configure manually:

```bash
# Either export them, or write a `.env` (project-local or
# ~/.config/videoclaw/.env — the wizard prefers the latter on fresh hosts).
export VIDEOCLAW_EVOLINK_API_KEY=sk-...   # required (LLM gateway)
export VIDEOCLAW_ARK_API_KEY=...          # required for real video gen
```

| Variable | Required | Description |
|----------|----------|-------------|
| `VIDEOCLAW_EVOLINK_API_KEY` | Yes | Evolink LLM gateway — routes Claude / GPT / Kimi / DeepSeek through one key. |
| `VIDEOCLAW_ARK_API_KEY` | For Seedance | Seedance 2.0 video API. |
| `VIDEOCLAW_DEFAULT_LLM` | No | Default LLM (default: `kimi-k2`). |
| `VIDEOCLAW_DEFAULT_VIDEO_MODEL` | No | Default video model (default: `seedance-2.0`; use `mock` for dry-run / CI). |
| `VIDEOCLAW_PROJECTS_DIR` | No | Project storage path (default: `./projects`). |
| `VIDEOCLAW_BUDGET_DEFAULT_USD` | No | Default budget cap (default: `10.0`). |
| `VIDEOCLAW_KLING_*` / `VIDEOCLAW_MINIMAX_API_KEY` / `VIDEOCLAW_BYTEPLUS_*` / `VIDEOCLAW_WAVESPEED_API_KEY` | Optional | Alternative video adapters (Kling / MiniMax / Seedance via BytePlus / WaveSpeed). |
| `VIDEOCLAW_ANTHROPIC_API_KEY` / `VIDEOCLAW_MOONSHOT_API_KEY` / `VIDEOCLAW_GOOGLE_API_KEY` | Optional | Direct LLM keys (used as fallback when Evolink doesn't route the requested model). |

`claw --json doctor` reads these and reports per-key health; the
`videoclaw-setup/v1` envelope from `setup.sh` summarizes the same in one
line.

## Development

```bash
git clone https://github.com/AIGC-Hackers/videoclaw-cli.git videoclaw
cd videoclaw
uv sync --all-extras          # Install all deps including dev/server
# or: make dev

uv run pytest tests/ -v                       # Internal unit/integration tests
uv run pytest mcp-shim/tests/ -v              # MCP shim — single-point + protocol
uv run pytest tests-external/ -v              # External agent-callable e2e (free tiers)
uv run ruff check src/ tests/                 # Lint
# or: make test / make lint
```

For the full external matrix (LLM-driven plan / design + real video gen
for the first 3 shots), see [`tests-external/README.md`](tests-external/README.md).

## Roadmap

- [x] **Phase 1**: Core engine, DAG executor, model adapters, CLI, cost tracking
- [x] **Phase 2**: FastAPI server, WebSocket, storage, publishers, test suite
- [x] **Phase 3**: ClawFlow YAML engine, integration tests, Docker
- [x] **Phase 4**: Director LLM integration, GitHub Actions CI, flow templates
- [x] **Phase 5**: AI Short Drama orchestration, Seedance 2.0, Vision QA, audit-regen loop
- [x] **Phase 6**: Agent framework (Director, Reviewer, Cameraman, Producer), AgentTeam, entry-point discovery
- [ ] **Phase 7**: Multi-agent collaboration, MCP server, skill/tool integration
- [ ] **Phase 8**: Plugin marketplace (ClawHub) + universal video orchestration platform

## License

Modified MIT — see [LICENSE](LICENSE) for details.
