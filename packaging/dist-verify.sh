#!/usr/bin/env bash
#
# dist-verify.sh — build wheel + PyInstaller binary + Docker image and
# verify each artifact runs `claw --version`. Single exit code: 0 if every
# enabled stage passes, non-zero on first failure.
#
# Stages can be skipped via env (useful when a host lacks docker or
# pyinstaller):
#
#   STAGE_WHEEL=0  bash packaging/dist-verify.sh    # skip wheel
#   STAGE_BIN=0    bash packaging/dist-verify.sh    # skip PyInstaller
#   STAGE_DOCKER=0 bash packaging/dist-verify.sh    # skip docker
#
# All stages are enabled by default.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGE_WHEEL="${STAGE_WHEEL:-1}"
STAGE_BIN="${STAGE_BIN:-1}"
STAGE_DOCKER="${STAGE_DOCKER:-1}"

dist_dir="$REPO_ROOT/dist"
mkdir -p "$dist_dir"

step() { printf '\n=== %s ===\n' "$1"; }

# ---------- wheel ----------
if [ "$STAGE_WHEEL" = "1" ]; then
    step "wheel — uv build (overlay-applied)"
    uv build --wheel --out-dir "$dist_dir" \
        --config-file packaging/pyproject.overlay.toml
    whl=$(ls -1t "$dist_dir"/*.whl 2>/dev/null | head -n 1)
    [ -n "$whl" ] || { echo "FAIL: no wheel produced"; exit 1; }
    echo "wheel: $whl"

    step "wheel — install + smoke"
    venv="$(mktemp -d)/venv"
    python3 -m venv "$venv"
    "$venv/bin/pip" install --quiet "$whl"
    "$venv/bin/claw" --version
fi

# ---------- PyInstaller binary ----------
if [ "$STAGE_BIN" = "1" ]; then
    if ! command -v pyinstaller >/dev/null 2>&1 \
        && ! uv run --quiet -- python -c "import PyInstaller" 2>/dev/null; then
        echo "SKIP: pyinstaller not installed (uv pip install pyinstaller)"
    else
        step "PyInstaller — one-file build via packaging/claw.spec"
        uv run pyinstaller packaging/claw.spec --clean --noconfirm \
            --workpath "$dist_dir/build" --distpath "$dist_dir"
        bin="$dist_dir/claw"
        [ -x "$bin" ] || { echo "FAIL: dist/claw missing or not executable"; exit 1; }
        "$bin" --version
    fi
fi

# ---------- Docker ----------
if [ "$STAGE_DOCKER" = "1" ]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "SKIP: docker daemon unavailable"
    else
        step "Docker — multi-stage build"
        docker build -t videoclaw-cli -f packaging/Dockerfile .
        docker run --rm videoclaw-cli --version
    fi
fi

step "ALL ENABLED STAGES PASSED"
