# VideoClaw Agent-CLI Packaging Guide

This is the low-friction path for deployment agents and maintainers who need
to ship VideoClaw as an external `claw` CLI that any coding agent can use.

## One-Command Path

```bash
./agent-cli-release-gate.sh package
```

That single command runs the recommended non-billable packaging flow:

1. Prepare local packaging dependencies.
2. Run the source-change gate.
3. Build distribution artifacts through `packaging/dist-verify.sh`.
4. Install the rebuilt wheel into a fresh venv.
5. Verify the packaged `claw` CLI.
6. Verify both setup paths:
   - `claw --json setup --dry-run --no-npx` -> `python-fallback`
   - `claw --json setup --dry-run` -> `npx-skills`

Use this before tagging or publishing a release artifact for external coding
agents.

## First-Time Setup

Run this once on a new machine:

```bash
./agent-cli-release-gate.sh setup --with-npx --with-bin
```

The setup mode performs the concrete dependency steps used by packaging:

```bash
command -v uv
uv python install 3.12
uv sync --extra dev
command -v npx
npx --version
uv pip install pyinstaller
```

Optional Docker image verification:

```bash
./agent-cli-release-gate.sh setup --with-npx --with-bin --with-docker
```

This additionally checks:

```bash
command -v docker
docker version
```

If `uv` is not installed yet, install it first. Common options:

```bash
# macOS with Homebrew
brew install uv

# Cross-platform installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Node.js / `npx` if the `--with-npx` check fails. On macOS:

```bash
brew install node
```

Real LLM/video E2E requires API keys. Configure them with:

```bash
bash packaging/setup.sh
```

## Daily Source-Change Gate

For normal source, tests, docs, skills, or packaging edits:

```bash
./agent-cli-release-gate.sh ci
```

This does not hit network-only agent registries and does not run billable
video generation. It still builds the wheel, installs it into a fresh venv,
and verifies the packaged CLI fallback setup path.

## Version-Bump Gate

When the public version changes or release metadata changes:

```bash
./agent-cli-release-gate.sh version
```

This runs `packaging/dist-verify.sh` with PyInstaller enabled and Docker
disabled by default. Docker is opt-in because many agent hosts do not have a
running Docker daemon:

```bash
./agent-cli-release-gate.sh version --with-docker
```

## Release Candidate Gate

Before publishing an artifact that coding agents will install:

```bash
./agent-cli-release-gate.sh release --with-npx
```

This verifies the packaged wheel plus the `npx skills` ecosystem path used for
Gemini CLI, Antigravity, Windsurf, Continue, Cline, Kiro CLI, and other
coding agents.

## Real First-3-Shots Proof

When API keys, budget, and time are available:

```bash
./agent-cli-release-gate.sh package --with-real-llm --with-real-video
```

This runs the gated external drama E2E stages and expects at least three
generated `.mp4` files.

## Repackaging Rule

Not every source edit requires a public release. But every artifact handed to
external coding agents must be rebuilt and verified from that rebuilt artifact.

Use this rule:

- Source-only development: `./agent-cli-release-gate.sh ci`
- Public behavior, skills, setup, packaging, or default-model change:
  `./agent-cli-release-gate.sh package`
- Published release candidate: `./agent-cli-release-gate.sh package`, then
  tag/push or trigger the release workflow.

## Useful Flags

```bash
./agent-cli-release-gate.sh package --print-plan
./agent-cli-release-gate.sh package --skip-setup
./agent-cli-release-gate.sh package --no-bin
./agent-cli-release-gate.sh package --with-docker
./agent-cli-release-gate.sh package --no-npx
```

Use `--print-plan` when an agent needs to explain what will run before doing
work.
