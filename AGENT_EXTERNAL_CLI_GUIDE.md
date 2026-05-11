# VideoClaw External CLI Agent Guide

This guide is written for a coding agent installing VideoClaw into a fresh
machine and then driving the external `claw` CLI end to end. Prefer `--json`
for all checks and parse the envelope instead of scraping rich terminal output.

## Contract

VideoClaw is an external CLI plus skill bundle.

- CLI entrypoint: `claw`
- Current release: `v0.1.4`
- Install artifact: GitHub Release wheel or platform binary
- Primary agent integration: `claw setup` installs `videoclaw-*` skills
- Universal fallback: any coding agent with a shell tool can call `claw ...`
- JSON envelope: `{"ok": bool, "version": str, "command": str, "data": ..., "error": ...}`
- Exit codes: `0` ok, `1` runtime, `2` usage, `3` auth needed, `4` blocked

Use the CLI for mutating work. The optional MCP shim is read-only discovery and
does not replace `claw drama ...`.

## Fresh Host Prerequisites

Install these before the CLI:

```bash
python3 --version          # must be 3.12+
ffmpeg -version            # required for compose/render/export flows
curl --version
jq --version              # recommended for parsing --json envelopes
```

Recommended for the lowest-friction agent-skill install path:

```bash
uv --version               # recommended package runner
npx --version              # enables 40+ agents through vercel-labs/skills
```

If missing on macOS:

```bash
brew install uv node ffmpeg jq
```

If `uv` is unavailable, the public installer can fall back to the GitHub
Release binary. If `npx` is unavailable, `claw setup --no-npx` still installs
skills for Claude Code, Codex, and OpenClaw.

## Install VideoClaw

Preferred release-wheel path:

```bash
uv tool install \
  https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.4/videoclaw-0.1.4-py3-none-any.whl
```

Alternative one-line public installer:

```bash
curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh
```

Verify the binary:

```bash
claw version
claw --json info
```

Expected version line:

```text
VideoClaw v0.1.4
```

## Install Skills Into Coding Agents

Default path, using `npx skills` when available:

```bash
claw --json setup --dry-run
claw setup
```

Fallback path for Claude Code, Codex, and OpenClaw:

```bash
claw --json setup --dry-run --no-npx
claw setup --no-npx
```

Agent-specific fallback targets:

```bash
claw setup --agent codex
claw setup --agent claude_code
claw setup --agent openclaw
```

The dry-run is successful when `.ok == true` and `.data.installer` is either
`npx-skills` or `python-fallback`. In the npx path, an empty
`skills_installed` list can still be correct when the installed skills are
already current.

## Configure API Keys

Minimum real drama configuration:

```bash
export VIDEOCLAW_EVOLINK_API_KEY="<required: LLM + default gpt-image-2 images>"
export VIDEOCLAW_ARK_API_KEY="<required for default seedance-2.0 real video>"
export VIDEOCLAW_DEFAULT_LLM="claude-sonnet-4-6"
export VIDEOCLAW_DEFAULT_VIDEO_MODEL="seedance-2.0"
export VIDEOCLAW_DEFAULT_IMAGE_PROVIDER="evolink"
export VIDEOCLAW_DEFAULT_IMAGE_MODEL="gpt-image-2"
export VIDEOCLAW_DEFAULT_IMAGE_RESOLUTION="1K"
export VIDEOCLAW_DEFAULT_IMAGE_QUALITY="medium"
export VIDEOCLAW_PROJECTS_DIR="$HOME/videoclaw-projects"
export VIDEOCLAW_DELIVERABLES_DIR="$HOME/videoclaw-deliverables"
export VIDEOCLAW_BUDGET_DEFAULT_USD="25"
```

Persist the same values for future shells:

```bash
mkdir -p "$HOME/.config/videoclaw"
umask 077
PROJECTS_DIR="${VIDEOCLAW_PROJECTS_DIR:-$HOME/videoclaw-projects}"
DELIVERABLES_DIR="${VIDEOCLAW_DELIVERABLES_DIR:-$HOME/videoclaw-deliverables}"
cat > "$HOME/.config/videoclaw/.env" <<EOF
VIDEOCLAW_EVOLINK_API_KEY=<required>
VIDEOCLAW_ARK_API_KEY=<required-for-seedance-video>
VIDEOCLAW_DEFAULT_LLM=claude-sonnet-4-6
VIDEOCLAW_DEFAULT_VIDEO_MODEL=seedance-2.0
VIDEOCLAW_DEFAULT_IMAGE_PROVIDER=evolink
VIDEOCLAW_DEFAULT_IMAGE_MODEL=gpt-image-2
VIDEOCLAW_DEFAULT_IMAGE_RESOLUTION=1K
VIDEOCLAW_DEFAULT_IMAGE_QUALITY=medium
VIDEOCLAW_PROJECTS_DIR=$PROJECTS_DIR
VIDEOCLAW_DELIVERABLES_DIR=$DELIVERABLES_DIR
VIDEOCLAW_BUDGET_DEFAULT_USD=25
EOF
chmod 600 "$HOME/.config/videoclaw/.env"
set -a
. "$HOME/.config/videoclaw/.env"
set +a
```

Runtime config is loaded from environment variables first, then a local `.env`
in the current working directory, then `$XDG_CONFIG_HOME/videoclaw/.env` or
`$HOME/.config/videoclaw/.env`.

Replace placeholder values from the host secret manager before running
`config check`. The `set -a` block exports the file into the current shell, so
the same instructions also work with older installed wheels that only read
environment variables and a local `.env`.

When working from a source checkout, the interactive wizard is also available:

```bash
bash packaging/setup.sh
```

Operational rule: never paste real secrets into issue comments, commit logs, or
agent final answers. Agents should read keys from the host environment or a
secret manager and write only masked status.

## Deployment Smoke Tests

Run these before using billable APIs:

```bash
claw version
claw --json setup --dry-run
claw --json setup --dry-run --no-npx
claw --json config check
claw --json model list
```

Readiness criteria:

- `claw version` returns `VideoClaw v0.1.4`.
- `config check` returns `.ok == true` and `.data.all_ok == true`.
- `model list` marks `seedance-2.0` healthy when `VIDEOCLAW_ARK_API_KEY` is set.
- `setup --dry-run` returns `installer: "npx-skills"` when `npx` works.
- `setup --dry-run --no-npx` returns `installer: "python-fallback"`.

`claw --json doctor` is useful for broader host diagnostics. It may return
exit `1` when optional OpenAI or Anthropic keys are absent. For production
drama readiness, prefer `claw --json config check`; it verifies projects dir,
FFmpeg, a video key, an LLM key, and an image key.

## Source Checkout Deployment Tests

Use this only when the source repository is available:

```bash
./agent-cli-release-gate.sh setup --with-npx --with-bin
./agent-cli-release-gate.sh ci
./agent-cli-release-gate.sh package --with-npx --with-bin
```

The package gate must rebuild the wheel, install that wheel into a fresh venv,
and verify both setup paths. For a billable proof:

```bash
./agent-cli-release-gate.sh package --with-real-llm --with-real-video
```

That runs the external first-3-shots proof and should produce at least three
`.mp4` files.

## Agent-Callable CLI Workflow

Always use `--json` for commands where the agent needs to parse output.

### Concept-driven drama

```bash
SERIES_JSON=$(claw --json drama new \
  "A contract couple accidentally falls in love while fighting a family takeover." \
  --title "Contract Heart" \
  --lang zh \
  --episodes 1 \
  --duration 70 \
  --model seedance-2.0 \
  --plan)

SERIES_ID=$(printf '%s' "$SERIES_JSON" | jq -r '.data.series_id')
```

Then:

```bash
claw --json drama script "$SERIES_ID" --episode 1
claw --json drama design-characters "$SERIES_ID"
claw --json drama design-scenes "$SERIES_ID"
claw --json drama preview-prompts "$SERIES_ID"
claw --json drama run "$SERIES_ID" --episode 1 --max-shots 3 --no-review
claw --json drama audit "$SERIES_ID" --episode 1
claw --json drama export "$SERIES_ID" --episode 1 --copy
```

### Locked script import

Use this when the user provides a finished `.pdf`, `.docx`, or `.txt` script.
Text-based PDFs are supported; scanned PDFs must be OCR-converted first.

```bash
SERIES_JSON=$(claw --json drama import "/absolute/path/to/script.pdf" \
  --title "Imported Drama" \
  --lang zh \
  --model seedance-2.0)

SERIES_ID=$(printf '%s' "$SERIES_JSON" | jq -r '.data.series_id')
```

Then run the same design/run/audit/export sequence.

### One-command prepared pipeline

After `drama import` or `drama plan` plus `drama script` has created planned
episodes:

```bash
claw --json drama pipeline "$SERIES_ID" \
  --episode 1 \
  --concurrency 4 \
  --audit-rounds 3
```

For a bounded deployment smoke:

```bash
claw --json drama run "$SERIES_ID" --episode 1 --max-shots 3 --no-review
claw --json drama export "$SERIES_ID" --episode 1 --copy
```

## Asset and Model Rules

Default image assets use Evolink `gpt-image-2`:

```bash
claw image "vertical character turnaround sheet, cinematic drama" \
  --provider evolink \
  --model gpt-image-2 \
  --size 3:4 \
  --resolution 1K \
  --quality medium \
  --output character.png
```

BytePlus `seedream-5.0-lite` is optional and lower priority. Use it only when
the user explicitly asks for BytePlus or Evolink image access is unavailable.

Default video uses `seedance-2.0`. Treat Seedance 2.0 native dialogue,
subtitles, SFX, and ambient audio as authoritative. Do not add a separate TTS,
BGM, or subtitle-overlay stage after Seedance clips unless the user explicitly
asks for a non-Seedance model or a manual remix.

## Outputs

Raw project state:

```text
$VIDEOCLAW_PROJECTS_DIR/dramas/<series_id>/
```

Human/auditor deliverables:

```text
$VIDEOCLAW_DELIVERABLES_DIR/<drama-title>/
```

Important deliverables:

- `_SERIES.md` for series summary
- `review/storyboard.html` for browser review
- `review/storyboard.md` for markdown review
- `final/final.mp4` for the canonical final video

Open HTML review pages when requested:

```bash
claw drama export "$SERIES_ID" --episode 1 --open
```

## Failure Handling

If any `claw drama ...` stage exits non-zero:

1. Save the command, exit code, JSON envelope, and relevant output paths.
2. Run `claw --json drama checkpoint-list "$SERIES_ID"`.
3. Resume from the newest safe checkpoint:

```bash
claw --json drama checkpoint-resume <checkpoint_id>
```

4. For a single bad shot:

```bash
claw --json drama regen-shot "$SERIES_ID" --episode 1 --shot <N>
```

5. Re-export:

```bash
claw --json drama export "$SERIES_ID" --episode 1 --copy
```

Common auth branches:

- Exit `3` or missing `VIDEOCLAW_EVOLINK_API_KEY`: configure Evolink and rerun.
- `seedance-2.0` unhealthy: configure `VIDEOCLAW_ARK_API_KEY`.
- `npx skills` DNS/registry failure: rerun `claw setup --no-npx` or fix Node/npm network.
- Seedance rejects reference images: run `claw drama refresh-urls "$SERIES_ID"`.

## Minimal Prompt for Another Coding Agent

Use this prompt to hand VideoClaw to another agent:

```text
You can use VideoClaw through the external `claw` CLI. First run:
  claw version
  claw --json config check
  claw --json setup --dry-run
If config check fails, configure VIDEOCLAW_EVOLINK_API_KEY and
VIDEOCLAW_ARK_API_KEY in ~/.config/videoclaw/.env or the host environment.
Use `claw --json` for parseable output. Create or import a drama, parse
`.data.series_id`, then run design-characters, design-scenes, preview-prompts,
run --max-shots 3 --no-review, audit, and export --copy. Default image assets
are Evolink gpt-image-2. Default video is seedance-2.0 with native audio; do
not add downstream TTS or subtitle overlays for Seedance clips.
```
