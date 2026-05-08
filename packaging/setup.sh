#!/usr/bin/env sh
#
# packaging/setup.sh — "Continue with CLI setup" wizard for videoclaw.
#
# Detects an existing config dir (or creates ~/.config/videoclaw/),
# prompts for the four canonical API-key / config values, writes
# `.env` with chmod 600, runs `claw --json doctor`, and prints a
# `videoclaw-setup/v1` JSON envelope on stdout for orchestrator parsing.
#
# Usage::
#
#   bash packaging/setup.sh             # interactive
#   bash packaging/setup.sh --quiet     # use existing values, skip prompts
#                                       # (useful for CI smoke or re-runs)
#   bash packaging/setup.sh --print-config-path
#                                       # print resolved config path and exit
#
# Re-running is idempotent — empty answers keep the existing value.

set -eu

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

err()  { printf 'setup: %s\n' "$*" >&2; }
info() { printf '%s\n' "$*" >&2; }
prompt() {
    # $1 = label, $2 = default (may be empty), $3 = secret? (1 = mask echo)
    label=$1
    default=$2
    secret=${3:-0}
    if [ "$secret" = "1" ] && [ -n "$default" ]; then
        printf '%s [<keep existing>]: ' "$label" >&2
    elif [ -n "$default" ]; then
        printf '%s [%s]: ' "$label" "$default" >&2
    else
        printf '%s: ' "$label" >&2
    fi
    if [ "$secret" = "1" ]; then
        # Disable echo via stty when reading from a tty.
        if [ -t 0 ]; then
            old_stty=$(stty -g 2>/dev/null || true)
            stty -echo 2>/dev/null || true
            IFS= read -r value
            stty "$old_stty" 2>/dev/null || true
            printf '\n' >&2
        else
            IFS= read -r value
        fi
    else
        IFS= read -r value
    fi
    if [ -z "$value" ]; then
        value=$default
    fi
    printf '%s' "$value"
}

emit_envelope() {
    # $1 = ok ("true" / "false"), $2 = config_path, $3 = version, $4 = doctor_passed, $5 = error_msg or "null"
    ok=$1; cfg=$2; ver=$3; passed=$4; errmsg=$5
    if [ "$errmsg" = "null" ]; then err_field='null'; else err_field="\"$(printf %s "$errmsg" | sed 's/"/\\"/g')\""; fi
    printf '{"schema":"videoclaw-setup/v1","ok":%s,"config_path":"%s","version":"%s","doctor_passed":%s,"error":%s,"next_steps":["claw drama new \\"<synopsis>\\" --title <title> --lang zh"]}\n' \
        "$ok" "$cfg" "$ver" "$passed" "$err_field"
}

# ---------------------------------------------------------------------------
# Resolve config path
# ---------------------------------------------------------------------------

resolve_config_dir() {
    # Priority: $XDG_CONFIG_HOME/videoclaw/ → ~/.config/videoclaw/ → repo cwd.
    if [ -n "${XDG_CONFIG_HOME:-}" ]; then
        printf '%s/videoclaw' "$XDG_CONFIG_HOME"
    else
        printf '%s/.config/videoclaw' "$HOME"
    fi
}

CONFIG_DIR=$(resolve_config_dir)
CONFIG_PATH="$CONFIG_DIR/.env"

# Repo-local fallback when the user runs setup from inside a videoclaw
# checkout — videoclaw's pydantic-settings reads `.env` from cwd.
if [ -f "$PWD/pyproject.toml" ] && grep -q '^name = "videoclaw"' "$PWD/pyproject.toml" 2>/dev/null; then
    if [ ! -f "$CONFIG_PATH" ] && [ -f "$PWD/.env" ]; then
        # Existing project-local .env wins on a fresh setup.
        CONFIG_PATH="$PWD/.env"
        CONFIG_DIR=$PWD
    fi
fi

# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

QUIET=0
for arg in "$@"; do
    case "$arg" in
        --print-config-path) printf '%s\n' "$CONFIG_PATH"; exit 0 ;;
        --quiet|-q)          QUIET=1 ;;
        --help|-h)           sed -n '3,/^$/p' "$0"; exit 0 ;;
        *) err "unknown flag: $arg"; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Read existing values (if any) so prompts can show them as defaults.
# ---------------------------------------------------------------------------

read_var() {
    # Read VAR=… line from $CONFIG_PATH; strip surrounding quotes.
    if [ -f "$CONFIG_PATH" ]; then
        line=$(grep "^$1=" "$CONFIG_PATH" 2>/dev/null | tail -n 1 || true)
        if [ -n "$line" ]; then
            printf '%s' "${line#*=}" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
        fi
    fi
}

EXISTING_EVOLINK=$(read_var VIDEOCLAW_EVOLINK_API_KEY)
EXISTING_ARK=$(read_var VIDEOCLAW_ARK_API_KEY)
EXISTING_VIDEO_MODEL=$(read_var VIDEOCLAW_DEFAULT_VIDEO_MODEL)
EXISTING_PROJECTS_DIR=$(read_var VIDEOCLAW_PROJECTS_DIR)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

if [ "$QUIET" = "0" ]; then
    cat >&2 <<'BANNER'

  videoclaw — Continue with CLI setup
  -----------------------------------
  Press Enter to keep existing values. API keys are masked while typing.

BANNER
fi

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

if [ "$QUIET" = "1" ]; then
    EVOLINK=$EXISTING_EVOLINK
    ARK=$EXISTING_ARK
    VIDEO_MODEL=${EXISTING_VIDEO_MODEL:-seedance-2.0}
    PROJECTS_DIR=${EXISTING_PROJECTS_DIR:-./projects}
else
    info "Config path: $CONFIG_PATH"
    info ""
    EVOLINK=$(prompt "VIDEOCLAW_EVOLINK_API_KEY (LLM gateway)" "$EXISTING_EVOLINK" 1)
    ARK=$(prompt "VIDEOCLAW_ARK_API_KEY (Seedance video)" "$EXISTING_ARK" 1)
    VIDEO_MODEL=$(prompt "VIDEOCLAW_DEFAULT_VIDEO_MODEL" "${EXISTING_VIDEO_MODEL:-seedance-2.0}" 0)
    PROJECTS_DIR=$(prompt "VIDEOCLAW_PROJECTS_DIR" "${EXISTING_PROJECTS_DIR:-./projects}" 0)
fi

if [ -z "$EVOLINK" ]; then
    emit_envelope false "$CONFIG_PATH" "" false "VIDEOCLAW_EVOLINK_API_KEY is required"
    err "VIDEOCLAW_EVOLINK_API_KEY is required (cannot proceed without LLM gateway)"
    exit 3
fi

# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

mkdir -p "$CONFIG_DIR"
tmp=$(mktemp "${CONFIG_PATH}.XXXXXX")
{
    printf '# videoclaw config — written by packaging/setup.sh\n'
    printf 'VIDEOCLAW_EVOLINK_API_KEY=%s\n' "$EVOLINK"
    if [ -n "$ARK" ]; then
        printf 'VIDEOCLAW_ARK_API_KEY=%s\n' "$ARK"
    fi
    printf 'VIDEOCLAW_DEFAULT_VIDEO_MODEL=%s\n' "$VIDEO_MODEL"
    printf 'VIDEOCLAW_PROJECTS_DIR=%s\n' "$PROJECTS_DIR"
} > "$tmp"
mv "$tmp" "$CONFIG_PATH"
chmod 600 "$CONFIG_PATH"

# ---------------------------------------------------------------------------
# Run doctor
# ---------------------------------------------------------------------------

if ! command -v claw >/dev/null 2>&1; then
    emit_envelope true "$CONFIG_PATH" "unknown" false "claw not on PATH — install first (see packaging/DISTRIBUTION-PLAN.md §2)"
    err "config written, but claw is not on PATH — skipping doctor."
    err "install via: uv tool install videoclaw   OR   curl ... | sh"
    exit 0
fi

doctor_passed=false
if claw --json doctor >/dev/null 2>&1; then
    doctor_passed=true
fi
version=$(claw version 2>/dev/null | awk '/v[0-9]+/{for(i=1;i<=NF;i++)if($i~/^v[0-9]/){print $i;exit}}' || printf 'unknown')

emit_envelope true "$CONFIG_PATH" "$version" "$doctor_passed" "null"

if [ "$doctor_passed" = "true" ]; then
    info ""
    info "✓ setup complete. Try: claw drama new \"<your synopsis>\" --title \"<title>\" --lang zh"
else
    info ""
    info "⚠ config written but \`claw --json doctor\` reported issues."
    info "  Run \`claw --verbose doctor\` for details."
fi
