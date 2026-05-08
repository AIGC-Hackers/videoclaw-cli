# Spec — Agent-CLI Release Gate for Distributable VideoClaw

## Objective

Make the repository itself give deployment agents one stable root-level
command for proving the final product: an external `claw` CLI that any coding
agent can call through its shell tool and that can return usable VideoClaw
results.

The deliverable is `./agent-cli-release-gate.sh`. It does not replace
`packaging/dist-verify.sh`; it wraps the broader release contract around it:
source verification, schema validation, artifact build, fresh wheel install,
packaged CLI setup checks, and optional billable drama video E2E.

## User Intent

The release path is optimized for these deployment-agent workflows:

- After each source change, run a deterministic gate that proves tests,
  schemas, packaging, and the wheel-installed CLI still work.
- After each version bump, run the distribution gate before tagging or
  publishing release artifacts.
- Before a release candidate is advertised to coding agents, optionally verify
  the `npx skills` registry path and real first-3-shots video generation.

## Commands

```bash
# Pull request / normal source edit.
./agent-cli-release-gate.sh ci

# Local source-change check.
./agent-cli-release-gate.sh changed

# Version bump / release candidate without Docker.
./agent-cli-release-gate.sh version

# Full release candidate, including the npx skills registry path.
./agent-cli-release-gate.sh release --with-npx

# Billable proof that the packaged external CLI can produce the first 3 videos.
./agent-cli-release-gate.sh release --with-npx --with-real-llm --with-real-video

# Let an agent see the exact plan without doing work.
./agent-cli-release-gate.sh release --print-plan --with-npx
```

## Gate Stages

1. **Source contract gates**
   - `bash -n agent-cli-release-gate.sh`
   - `uv run pytest tests/ -q`
   - `uv run ruff check tests/test_agent_cli_release_gate.py packaging/manifest-validate.py packaging/skills-validate.py`
   - `uv run python packaging/skills-validate.py skills/`
   - `uv run python packaging/manifest-validate.py packaging/agent-cli.yaml`

2. **Distribution build**
   - `ci` / `changed`: `uv build --wheel --out-dir dist`
   - `version` / `release`: `STAGE_BIN=1 STAGE_DOCKER=0 bash packaging/dist-verify.sh`
   - Docker is opt-in with `--with-docker` because many agent hosts lack a
     running Docker daemon.

3. **Fresh packaged install**
   - Create a temporary venv.
   - Use `AGENT_CLI_PYTHON` when set, otherwise `uv python find 3.12`, so
     macOS hosts whose `python3` is still 3.9 do not install with the wrong
     interpreter.
   - Install `dist/videoclaw-<version>-py3-none-any.whl`.
   - Run the installed `claw`, not `uv run claw` from the source tree.

4. **Packaged CLI contract**
   - `claw version`
   - `claw --json setup --dry-run --no-npx`
   - Assert `data.installer == "python-fallback"`.
   - If `--with-npx` is enabled: `claw --json setup --dry-run` and assert
     `data.installer == "npx-skills"`.

5. **Optional external drama proof**
   - `--with-real-llm` runs T2/T5/T6/T7 preparation stages.
   - `--with-real-video` runs T9 and expects at least three non-empty `.mp4`
     artifacts.
   - These are gated because they require real API keys, budget, and time.

## Repackaging Policy

Not every source edit needs an immediate public version release. But every
artifact that will be handed to an external coding agent must be rebuilt and
verified from the rebuilt artifact.

Recommended order:

1. Edit source, skills, packaging, docs, or tests.
2. Run `./agent-cli-release-gate.sh ci`.
3. If the change affects public behavior, bundled skills, packaging metadata,
   model defaults, or install/setup behavior, bump the release version before
   publishing.
4. Run `./agent-cli-release-gate.sh version`.
5. Run `./agent-cli-release-gate.sh release --with-npx` on a Node-equipped host.
6. For real-video confidence, add `--with-real-llm --with-real-video`.
7. Commit the source and packaging changes.
8. Tag/push or trigger the existing release workflow to publish artifacts.

## Acceptance Criteria

- A deployment agent can call one root command and get a single pass/fail
  signal for agent-callable CLI readiness.
- The gate proves the installed wheel CLI, not just the editable source CLI.
- The Python fallback setup path is always verified.
- The `npx skills` multi-agent setup path is explicitly verifiable.
- Billable first-3-shots generation remains opt-in and documented.
- The script is tested by `tests/test_agent_cli_release_gate.py`.
