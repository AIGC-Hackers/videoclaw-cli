#!/usr/bin/env bash
#
# Agent CLI release gate for VideoClaw.
#
# This script is intentionally rooted at the repository top level so a
# deployment agent can run one stable command after source changes or version
# bumps and prove the distributable CLI contract, not just the source checkout.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./agent-cli-release-gate.sh [ci|changed|version|release] [options]

Modes:
  ci       Deterministic, network-free gate for pull requests and source edits.
  changed  Local source-change gate; same artifact contract as ci.
  version  Version-bump gate; runs packaging/dist-verify.sh plus packaged CLI checks.
  release  Release-candidate gate; version gate plus optional registry and E2E flags.

Options:
  --mode MODE          Set mode explicitly.
  --print-plan         Print the commands that would run without executing them.
  --with-npx           Verify the npx skills registry path with packaged claw.
  --no-npx             Disable the npx skills registry path.
  --with-real-llm      Run the billable LLM external drama preparation stages.
  --with-real-video    Run the billable first-3-shots real video E2E stage.
  --with-bin           Enable PyInstaller stage when dist-verify.sh runs.
  --no-bin             Disable PyInstaller stage when dist-verify.sh runs.
  --with-docker        Enable Docker stage when dist-verify.sh runs.
  --no-docker          Disable Docker stage when dist-verify.sh runs.
  -h, --help           Show this help.

Environment:
  AGENT_CLI_WITH_NPX=1       Same as --with-npx.
  AGENT_CLI_REAL_LLM=1       Same as --with-real-llm.
  AGENT_CLI_REAL_VIDEO=1     Same as --with-real-video.
  AGENT_CLI_DIST_BIN=0|1     Override PyInstaller stage for version/release modes.
  AGENT_CLI_DIST_DOCKER=0|1  Override Docker stage for version/release modes.
  AGENT_CLI_PYTHON=/path     Python >=3.12 used for wheel-install venvs.
  KEEP_AGENT_CLI_GATE_VENV=1 Keep the temporary wheel-install venv for inspection.

Contract:
  The gate builds a wheel, installs it into a fresh venv, and verifies the
  packaged claw CLI can run version and setup dry-runs. Optional real E2E
  stages prove that coding agents can drive external VideoClaw CLI commands
  all the way to short-drama video artifacts when API keys are configured.
EOF
}

MODE="changed"
PRINT_PLAN=0
WITH_NPX="${AGENT_CLI_WITH_NPX:-0}"
REAL_LLM="${AGENT_CLI_REAL_LLM:-0}"
REAL_VIDEO="${AGENT_CLI_REAL_VIDEO:-0}"
DIST_BIN_OVERRIDE="${AGENT_CLI_DIST_BIN:-}"
DIST_DOCKER_OVERRIDE="${AGENT_CLI_DIST_DOCKER:-}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        ci|changed|version|release)
            MODE="$1"
            ;;
        full)
            MODE="release"
            ;;
        --mode)
            shift
            [ "$#" -gt 0 ] || { echo "ERROR: --mode requires a value" >&2; exit 2; }
            MODE="$1"
            ;;
        --print-plan)
            PRINT_PLAN=1
            ;;
        --with-npx)
            WITH_NPX=1
            ;;
        --no-npx)
            WITH_NPX=0
            ;;
        --with-real-llm)
            REAL_LLM=1
            ;;
        --with-real-video)
            REAL_VIDEO=1
            ;;
        --with-bin)
            DIST_BIN_OVERRIDE=1
            ;;
        --no-bin)
            DIST_BIN_OVERRIDE=0
            ;;
        --with-docker)
            DIST_DOCKER_OVERRIDE=1
            ;;
        --no-docker)
            DIST_DOCKER_OVERRIDE=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

case "$MODE" in
    ci|changed)
        RUN_DIST_VERIFY=0
        DEFAULT_DIST_BIN=0
        DEFAULT_DIST_DOCKER=0
        ;;
    version|release)
        RUN_DIST_VERIFY=1
        DEFAULT_DIST_BIN=1
        DEFAULT_DIST_DOCKER=0
        ;;
    *)
        echo "ERROR: unsupported mode: $MODE" >&2
        usage >&2
        exit 2
        ;;
esac

DIST_BIN="${DIST_BIN_OVERRIDE:-$DEFAULT_DIST_BIN}"
DIST_DOCKER="${DIST_DOCKER_OVERRIDE:-$DEFAULT_DIST_DOCKER}"
PROJECT_VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)"
[ -n "$PROJECT_VERSION" ] || { echo "ERROR: could not read project version" >&2; exit 1; }
WHEEL="dist/videoclaw-${PROJECT_VERSION}-py3-none-any.whl"
PYTHON_BIN="${AGENT_CLI_PYTHON:-}"
TMP_WORK=""
VENV=""
VENV_BIN=""

cleanup() {
    if [ -n "${TMP_WORK:-}" ] && [ "${KEEP_AGENT_CLI_GATE_VENV:-0}" != "1" ]; then
        rm -rf "$TMP_WORK"
    fi
}
trap cleanup EXIT

step() {
    printf '\n== %s ==\n' "$1"
}

note() {
    printf '# %s\n' "$1"
}

run_shell() {
    printf '+ %s\n' "$1"
    if [ "$PRINT_PLAN" = "1" ]; then
        return 0
    fi
    bash -lc "$1"
}

resolve_python() {
    if [ -z "$PYTHON_BIN" ] && command -v uv >/dev/null 2>&1; then
        PYTHON_BIN="$(uv python find 3.12 2>/dev/null || true)"
    fi
    if [ -z "$PYTHON_BIN" ]; then
        PYTHON_BIN="$(command -v python3 || true)"
    fi
    [ -n "$PYTHON_BIN" ] || {
        echo "ERROR: Python >=3.12 is required for wheel install checks" >&2
        exit 1
    }

    if [ "$PRINT_PLAN" = "1" ]; then
        return 0
    fi

    "$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(
        f"Python >=3.12 is required, got "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
PY
}

ensure_wheel_exists() {
    if [ "$PRINT_PLAN" = "1" ]; then
        return 0
    fi
    [ -f "$WHEEL" ] || {
        echo "ERROR: expected wheel is missing: $WHEEL" >&2
        exit 1
    }
}

prepare_wheel_venv() {
    step "Install wheel into isolated venv"
    resolve_python
    note "packaged claw CLI from built wheel: $WHEEL"
    note "wheel-install python: $PYTHON_BIN"
    ensure_wheel_exists

    if [ "$PRINT_PLAN" = "1" ]; then
        VENV="<temp>/venv"
        VENV_BIN="$VENV/bin"
        run_shell "$PYTHON_BIN -m venv <temp>/venv"
        run_shell "<temp>/venv/bin/pip install --quiet $WHEEL"
        return 0
    fi

    TMP_PARENT="${TMPDIR:-/tmp}"
    TMP_WORK="$(mktemp -d "$TMP_PARENT/videoclaw-agent-cli-gate.XXXXXX")"
    VENV="$TMP_WORK/venv"
    VENV_BIN="$VENV/bin"
    run_shell "$PYTHON_BIN -m venv $VENV"
    run_shell "$VENV_BIN/pip install --quiet $WHEEL"
}

assert_setup_installer() {
    local json_path="$1"
    local expected="$2"
    local label="$3"

    note "$label setup JSON installer == $expected"
    if [ "$PRINT_PLAN" = "1" ]; then
        return 0
    fi

    "$VENV_BIN/python" - "$json_path" "$expected" <<'PY'
import json
import sys

path, expected = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    payload = json.load(fh)

if payload.get("ok") is not True:
    raise SystemExit(f"setup envelope ok is not true: {payload!r}")

actual = (payload.get("data") or {}).get("installer")
if actual != expected:
    raise SystemExit(f"expected installer {expected!r}, got {actual!r}")
PY
}

run_source_gates() {
    step "Source contract gates"
    run_shell "bash -n agent-cli-release-gate.sh"
    run_shell "uv run pytest tests/ -q"
    run_shell "uv run ruff check tests/test_agent_cli_release_gate.py packaging/manifest-validate.py packaging/skills-validate.py"
    run_shell "uv run python packaging/skills-validate.py skills/"
    run_shell "uv run python packaging/manifest-validate.py packaging/agent-cli.yaml"
}

build_artifacts() {
    step "Distribution build"
    if [ "$RUN_DIST_VERIFY" = "1" ]; then
        run_shell "STAGE_BIN=$DIST_BIN STAGE_DOCKER=$DIST_DOCKER bash packaging/dist-verify.sh"
    else
        run_shell "uv build --wheel --out-dir dist"
    fi
}

run_packaged_cli_checks() {
    step "Packaged CLI checks"
    run_shell "$VENV_BIN/claw version"
    run_shell "$VENV_BIN/claw --json setup --dry-run --no-npx > ${TMP_WORK:-<temp>}/setup-fallback.json"
    assert_setup_installer "${TMP_WORK:-<temp>}/setup-fallback.json" "python-fallback" "python fallback"

    if [ "$WITH_NPX" = "1" ]; then
        run_shell "$VENV_BIN/claw --json setup --dry-run > ${TMP_WORK:-<temp>}/setup-npx.json"
        assert_setup_installer "${TMP_WORK:-<temp>}/setup-npx.json" "npx-skills" "npx"
    else
        note "npx skills registry setup check skipped; pass --with-npx to verify it"
    fi
}

run_optional_external_e2e() {
    step "Optional external drama E2E"

    if [ "$REAL_LLM" = "1" ]; then
        run_shell "PATH=$VENV_BIN:\$PATH E2E_REAL_LLM=1 uv run pytest tests-external/test_e2e_first_3_shots.py::test_T2_drama_new_persists_series tests-external/test_e2e_first_3_shots.py::test_T5_drama_plan_produces_characters_and_episode_synopsis tests-external/test_e2e_first_3_shots.py::test_T6_script_then_design_scenes_produces_shots tests-external/test_e2e_first_3_shots.py::test_T7_design_characters_populates_reference_images -v"
    else
        note "real LLM drama preparation skipped; pass --with-real-llm when keys and budget are available"
    fi

    if [ "$REAL_VIDEO" = "1" ]; then
        run_shell "PATH=$VENV_BIN:\$PATH E2E_REAL_VIDEO=1 uv run pytest tests-external/test_e2e_first_3_shots.py::test_T9_drama_run_first_3_shots_produces_videos -v"
    else
        note "real first-3-shots video generation skipped; pass --with-real-video when keys and budget are available"
    fi
}

step "Agent CLI release gate"
note "mode=$MODE version=$PROJECT_VERSION with_npx=$WITH_NPX real_llm=$REAL_LLM real_video=$REAL_VIDEO"

run_source_gates
build_artifacts
prepare_wheel_venv
run_packaged_cli_checks
run_optional_external_e2e

step "Agent CLI release gate passed"
