<div align="center">
  <h1>VideoClaw</h1>
  <p><strong>The Agent OS for AI Video Generation.</strong></p>
  <p>
    Turn your favorite coding agent into an expert at producing
    TikTok-format AI dramas — from script to published episode.
  </p>
  <p>
    <a href="#get-started">Get Started</a> &bull;
    <a href="#skills">Skills</a> &bull;
    <a href="#cli-commands">Commands</a> &bull;
    <a href="#faq">FAQ</a> &bull;
    <a href="#how-it-works">How it works</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/license-Modified%20MIT-blue" alt="License" />
    <img src="https://img.shields.io/badge/python-3.12+-green" alt="Python" />
    <img src="https://img.shields.io/badge/tests-700%2B%20passing-brightgreen" alt="Tests" />
    <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Docker-lightgrey" alt="Platform" />
  </p>
</div>

---

**Works seamlessly with:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code) &nbsp;•&nbsp; [OpenClaw](https://github.com/AIGC-Hackers/openclaw) &nbsp;•&nbsp; [Codex](https://github.com/openai/codex) &nbsp;•&nbsp; [Cursor](https://cursor.sh) &nbsp;•&nbsp; [Gemini CLI](https://github.com/google-gemini/gemini-cli) &nbsp;•&nbsp; *and any other coding agent.*

VideoClaw gives your coding agent the **CLI commands and skills** to plan, design, generate, audit, and export AI dramas — so you don't have to learn every adapter and prompt convention yourself.

## Get Started

**Prerequisites:** Python ≥ 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/), an Evolink LLM key, and (for real video) an ARK / Seedance key.

### 1. Install the CLI + skills

```bash
uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup
```

`claw setup` detects which coding agents are present and copies the
`videoclaw-*` skills into each. After v0.1.0 lands on PyPI you'll be
able to use the shorter form `uvx videoclaw setup`.

<details>
<summary>Other install paths</summary>

- **From source (Python ≥ 3.12)** — `git clone … && uv sync && uv run claw --help`
- **One-line installer (post-release)** — `curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh`
- **Docker** — `docker build -t videoclaw-cli -f packaging/Dockerfile . && docker run --rm videoclaw-cli version`
- **Wheel from GitHub Releases (post-v0.1.0)** — `pip install https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl`

Full channel matrix: [`packaging/DISTRIBUTION-PLAN.md`](packaging/DISTRIBUTION-PLAN.md).

</details>

### 2. Open your coding agent

Launch [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenClaw](https://github.com/AIGC-Hackers/openclaw), [Codex](https://github.com/openai/codex), or any coding agent of your choice. The skills installed by `claw setup` activate automatically when you mention drama production.

> Per-agent quickstart blocks (Claude Code / OpenClaw / Codex / Cursor) — to be expanded in M002 task T11. For now: any agent with a Bash tool can call `claw …` directly.

### 3. Make your first drama

Ask your coding agent something like:

> *"Use videoclaw to import `examples/script.md` as a drama, design the characters and scenes, and run the first 3 shots."*

The `videoclaw-workflow` skill activates and walks the agent through `drama import → plan → design-characters → design-scenes → assign-voices → run --max-shots 3`.

Or run the CLI directly without an agent — every command supports `--json`:

```bash
claw --json doctor                                      # health check
claw drama new "<synopsis>" --title "<title>" --lang zh # LLM-authored
claw drama import script.docx --title "<title>"         # locked-script mode
claw drama run <series_id> --max-shots 3                # generate first 3 shots
```

## Skills

| Skill | What your coding agent learns |
|---|---|
| [`videoclaw-workflow`](skills/videoclaw-workflow/SKILL.md) | Drama lifecycle entrypoint (always-active): `new/import → plan → design-* → assign-voices → run → audit → export`. |
| [`videoclaw-drama-setup`](skills/videoclaw-drama-setup/SKILL.md) | Choosing between `drama new` (LLM writes) vs `drama import` (locked) vs `drama script` (edit). |
| [`videoclaw-models`](skills/videoclaw-models/SKILL.md) | Selecting video adapters (Seedance / Kling / MiniMax / Zhipu / OpenAI / mock); HTTPS-only refs; stylized-faces rule. |
| [`videoclaw-checkpoint`](skills/videoclaw-checkpoint/SKILL.md) | Resume after stage failures; regenerate single shots; flat `checkpoint-*` commands. |
| [`videoclaw-troubleshoot`](skills/videoclaw-troubleshoot/SKILL.md) | `claw doctor` triage; exit-code contract (0/1/2/3/4); common errors. |

`claw setup` installs these into each detected coding agent's skill directory; `claw setup --uninstall` removes them.

## CLI Commands

| Command | What it does |
|---|---|
| `claw setup` | Install CLI + skills into detected coding agents (idempotent). |
| `claw version` | Print the version string. |
| `claw --json doctor` | Health check (envelope + exit code). |
| `claw --json info` | Registered models / drama series count. |
| `claw drama new "<synopsis>"` | Create a new series from a synopsis (LLM authors script). |
| `claw drama import <script>` | Import a locked external script. |
| `claw drama plan <id>` | Plan episode shots via LLM. |
| `claw drama design-{characters,scenes,cover} <id>` | Generate visual assets. |
| `claw drama assign-voices <id>` | Map characters to TTS voices. |
| `claw drama run <id> [--max-shots N] [--dry-run]` | Generate video shots. |
| `claw drama audit <id>` / `audit-regen <id>` | Vision QA + auto-fix. |
| `claw drama export <id>` | Export deliverables under `docs/deliverables/<drama>/`. |
| `claw drama checkpoint-{list,show,resume,redo,assets}` | Resume / inspect runs. |

<details>
<summary>See all commands</summary>

```bash
# Top-level
claw setup [--dry-run] [--agent <name>] [--uninstall]
claw version
claw doctor [--json]
claw info [--json]
claw generate <prompt>            # single-shot full pipeline
claw stage-* …                    # 7 staged-pipeline commands

# Sub-apps
claw model    list / info <name>
claw project  list / show / delete
claw template list
claw flow     run / validate <file.yaml>
claw drama    (see drama subcommands above)
claw config   show / check
claw agent    list
claw cost     summary / show <run-id>
```

Full reference: `claw <command> --help` or [`AGENTS.md`](AGENTS.md).

</details>

Every `--json` output uses the envelope `{ok, version, command, data, error}`. Exit codes follow the agent-cli contract: **0** ok / **1** runtime / **2** usage / **3** auth / **4** blocked.

## FAQ

**Is this an alternative to Claude Code, OpenClaw, Codex, or Gemini CLI?**<br>
No. **VideoClaw is a tool *for* coding agents, not a coding agent itself.** It provides the CLI commands and skills that make your coding agent better at building, evaluating, and shipping AI dramas.

**Do I need a coding agent to use videoclaw?**<br>
No — every command runs standalone in your terminal (`claw drama new …`). The skills are an *opt-in* enhancement that lets a coding agent drive the pipeline without you typing each step.

**How does this differ from calling Seedance / Kling / MiniMax directly?**<br>
The video adapters do single shots. VideoClaw orchestrates the full lifecycle — script parsing, character / scene assets, prompt engineering, generation, vision QA, checkpoint resume, multi-episode export — across the model of your choice.

**Can I plug in a new video model?**<br>
Yes. Implement the `VideoModelAdapter` protocol (4 async methods), register in `pyproject.toml` under `[project.entry-points."videoclaw.adapters"]`, reinstall. See `/videoclaw-models` skill for the full template.

**Is MCP supported?**<br>
Optional, secondary path. `mcp-shim/` exposes 4 read-only discovery tools for clients that prefer MCP. The CLI + skills path is the universal contract; MCP is an informational alternative. The deployment manifest at `packaging/agent-cli.yaml` is similarly informational — *primary discovery is via skills*.

**Where do generated assets go?**<br>
`{VIDEOCLAW_PROJECTS_DIR:-./projects}/dramas/<series_id>/` for raw assets and checkpoints; `{VIDEOCLAW_DELIVERABLES_DIR:-./docs/deliverables}/<drama>/` for final exports.

---

## How it works

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

Seven-layer architecture:

| Layer | Purpose |
|---|---|
| Interface | CLI (`claw`) + REST API (optional) |
| Gateway | FastAPI server, WebSocket progress |
| Agent Runtime | AgentTeam, Director, Reviewer, Cameraman, Producer |
| Orchestration | DAG Planner, Executor, Event Bus, State Manager |
| Generation | Script, Storyboard, Video, TTS, Music, Compose |
| Model Adapters | Protocol-based adapters (Seedance, Kling, OpenAI, etc.) |
| Distribution | Publishers (YouTube, TikTok, Bilibili) |

### Supported Models

| Category | Models | Mode |
|---|---|---|
| Video | Seedance 2.0, Kling, Sora (OpenAI), MiniMax, ZhipuAI, CogVideoX | Cloud + Local |
| LLM | Claude, GPT, Qwen, DeepSeek, Ollama (via LiteLLM) | Cloud + Local |
| TTS | Edge-TTS, Fish-Speech, ElevenLabs, ChatTTS | Cloud + Local |
| Music | Suno, Udio, MusicGen | Cloud + Local |

### Why VideoClaw

You've tried Sora, Runway, Kling, CogVideo... Each is impressive alone.
But making a *real* video still means writing prompts for each shot
manually, waiting between tools, having no idea what it costs until
the bill arrives, starting from scratch when one shot fails, and
manually stitching subtitles, music, voiceover. **VideoClaw fixes
all of this.**

### Drama Production Pipeline

Complete production pipeline for TikTok-format Western AI short dramas — from script import to published episode:

```bash
claw drama import script.docx --title "Satan in a Suit" --language en
claw drama design-characters <series_id>     # turnaround sheets
claw drama preview-prompts <series_id>       # preview before spending credits
claw drama pipeline <series_id> --episode 1  # design → run → audit → fix → export
```

**Key capabilities:** Seedance 2.0 video generation (9:16 / 720p) · character consistency via Universal Reference turnaround sheets · vision QA with Claude · self-correcting audit-regen loop · multi-episode series with cross-episode continuity.

### ClawFlow — YAML Pipelines

Define entire video pipelines in version-controllable YAML; `claw flow run my-pipeline.yaml` executes the DAG with parallel-where-possible scheduling. See [`examples/`](examples/) for templates.

## REST API

```bash
uvicorn videoclaw.server.app:create_app --factory
```

Endpoints: `GET /health` · `POST /api/projects/` · `POST /api/generate/` · `POST /api/generate/flow` · `WS /ws/{project_id}` · etc.

## Configuration

Run `bash packaging/setup.sh` (interactive wizard) — writes
`$XDG_CONFIG_HOME/videoclaw/.env` (or `~/.config/videoclaw/.env`) with
`chmod 600`. Or set env vars directly:

| Variable | Required | Description |
|---|---|---|
| `VIDEOCLAW_EVOLINK_API_KEY` | Yes | Evolink LLM gateway (Claude / GPT / Kimi / DeepSeek). |
| `VIDEOCLAW_ARK_API_KEY` | For Seedance | Seedance 2.0 video API. |
| `VIDEOCLAW_DEFAULT_LLM` | No | Default LLM (default `kimi-k2`). |
| `VIDEOCLAW_DEFAULT_VIDEO_MODEL` | No | Default video model (default `seedance-2.0`; use `mock` for dry-run). |
| `VIDEOCLAW_PROJECTS_DIR` | No | Project storage path (default `./projects`). |
| `VIDEOCLAW_BUDGET_DEFAULT_USD` | No | Budget cap (default `10.0`). |
| `VIDEOCLAW_KLING_*` / `VIDEOCLAW_MINIMAX_API_KEY` / `VIDEOCLAW_BYTEPLUS_*` | Optional | Alternative video adapters. |
| `VIDEOCLAW_ANTHROPIC_API_KEY` / `VIDEOCLAW_MOONSHOT_API_KEY` / `VIDEOCLAW_GOOGLE_API_KEY` | Optional | Direct LLM keys (Evolink fallback). |

`claw --json doctor` reports per-key health; `videoclaw-setup/v1` envelope from `setup.sh` summarizes the same in one line.

## Development

```bash
git clone https://github.com/AIGC-Hackers/videoclaw-cli.git videoclaw
cd videoclaw
uv sync --all-extras
make test                                    # internal unit/integration
uv run pytest mcp-shim/tests/ -v             # MCP shim
uv run pytest tests-external/ -v             # external agent-callable e2e
make lint                                    # ruff + mypy strict
python packaging/skills-validate.py skills/  # skills schema
```

External matrix details: [`tests-external/README.md`](tests-external/README.md).

## Project Structure

```
videoclaw/
├── src/videoclaw/        # CLI (Typer + Rich), core, agents, models, drama, generation, server
├── skills/               # videoclaw-* skills (Markdown; consumed by `claw setup`)
├── packaging/            # Wheel/PyInstaller/Docker build + setup.sh + manifest + validators
├── mcp-shim/             # Optional MCP transport (secondary)
├── tests/ tests-external/
├── examples/             # ClawFlow YAML samples
└── docs/plans/           # Spec-driven planning docs (M002 toolkit milestone)
```

## Roadmap

- [x] **Phase 1** — Core engine, DAG executor, model adapters, CLI, cost tracking.
- [x] **Phase 2** — FastAPI server, WebSocket, storage, publishers, test suite.
- [x] **Phase 3** — ClawFlow YAML engine, integration tests, Docker.
- [x] **Phase 4** — Director LLM integration, GitHub Actions CI, flow templates.
- [x] **Phase 5** — AI Short Drama orchestration, Seedance 2.0, vision QA, audit-regen loop.
- [x] **Phase 6** — Agent framework (Director, Reviewer, Cameraman, Producer), AgentTeam, entry-point discovery.
- [ ] **Phase 7** — Multi-agent collaboration, MCP server, skills + tool integration (M002 in progress).
- [ ] **Phase 8** — Plugin marketplace (ClawHub) + universal video orchestration platform.

## License

Modified MIT — see [LICENSE](LICENSE) for details.
