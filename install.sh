#!/usr/bin/env sh
#
# install.sh — public installer for the videoclaw `claw` CLI.
#
# Curl-able::
#
#   curl -fsSL https://raw.githubusercontent.com/AIGC-Hackers/videoclaw-cli/main/install.sh | sh
#
# Behavior:
# 1. Detects OS / arch via uname.
# 2. Picks Channel A (`uv tool install`) when `uv` is on PATH; falls back to
#    Channel B (PyInstaller binary download from GitHub Releases) when not.
# 3. Verifies the downloaded binary against SHA256SUMS from the release.
# 4. Drops the binary at $INSTALL_DIR (default: $HOME/.local/bin/claw)
#    with chmod +x. Refuses to install as root.
# 5. Prints a `videoclaw-install/v1` JSON envelope as the LAST stdout line.
# 6. Suggests `claw setup` (or the local setup.sh) as the next step.
#
# Overrides via env::
#
#   GH_OWNER=AIGC-Hackers GH_REPO=videoclaw-cli   # source release
#   VERSION=0.1.4                                 # which release tag
#   INSTALL_DIR=$HOME/.local/bin                  # where to drop the binary
#   CHANNEL=auto|uv|binary                        # force channel selection

set -eu

GH_OWNER=${GH_OWNER:-AIGC-Hackers}
GH_REPO=${GH_REPO:-videoclaw-cli}
VERSION=${VERSION:-0.1.4}
INSTALL_DIR=${INSTALL_DIR:-${HOME}/.local/bin}
CHANNEL=${CHANNEL:-auto}

err()  { printf 'install: %s\n' "$*" >&2; }
info() { printf '%s\n' "$*" >&2; }

emit_envelope() {
    # $1 = ok, $2 = channel, $3 = installed_to, $4 = version, $5 = error_msg or "null"
    if [ "$5" = "null" ]; then errfield='null'; else errfield="\"$(printf %s "$5" | sed 's/"/\\"/g')\""; fi
    printf '{"schema":"videoclaw-install/v1","ok":%s,"channel":"%s","installed_to":"%s","version":"%s","error":%s,"next_steps":["claw setup","claw --json doctor"]}\n' \
        "$1" "$2" "$3" "$4" "$errfield"
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

if [ "$(id -u 2>/dev/null || printf 0)" = "0" ]; then
    emit_envelope false unknown "" "$VERSION" "refusing to install as root — re-run as non-root user"
    err "refusing to install as root. Re-run as your normal user;"
    err "the binary lands in \$HOME/.local/bin/ (override with INSTALL_DIR)."
    exit 4
fi

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    arm64|aarch64)  ARCH_NORM=arm64 ;;
    x86_64|amd64)   ARCH_NORM=x86_64 ;;
    *) emit_envelope false unknown "" "$VERSION" "unsupported arch: $ARCH"
       err "unsupported architecture: $ARCH"; exit 4 ;;
esac
case "$OS" in
    darwin|linux) : ;;
    *) emit_envelope false unknown "" "$VERSION" "unsupported os: $OS"
       err "unsupported OS: $OS"; exit 4 ;;
esac

mkdir -p "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------

if [ "$CHANNEL" = "auto" ]; then
    if command -v uv >/dev/null 2>&1; then
        CHANNEL=uv
    else
        CHANNEL=binary
    fi
fi

# ---------------------------------------------------------------------------
# Channel A: uv tool install
# ---------------------------------------------------------------------------

install_via_uv() {
    info "==> installing via \`uv tool install videoclaw\`"
    # uv tool install fetches from PyPI; we point at the wheel asset on
    # GitHub Releases when PyPI doesn't have the version yet.
    pypi_name=videoclaw
    if uv tool install "$pypi_name" 2>/dev/null; then
        :
    else
        info "PyPI install failed; falling back to wheel from GitHub Releases"
        wheel_url="https://github.com/$GH_OWNER/$GH_REPO/releases/download/v$VERSION/videoclaw-$VERSION-py3-none-any.whl"
        uv tool install "$wheel_url"
    fi

    # uv tool install puts entry-point scripts into ~/.local/bin already;
    # if the user passed a different INSTALL_DIR, copy / symlink there.
    found=$(command -v claw 2>/dev/null || true)
    if [ -z "$found" ]; then
        emit_envelope false uv "" "$VERSION" "uv tool install completed but \`claw\` is not on PATH"
        err "uv tool install completed but \`claw\` is not on PATH."
        err "Add \$HOME/.local/bin to PATH or set INSTALL_DIR."
        exit 1
    fi
    if [ "$(dirname "$found")" != "$INSTALL_DIR" ]; then
        ln -sf "$found" "$INSTALL_DIR/claw"
    fi
    INSTALLED_TO="$INSTALL_DIR/claw"
}

# ---------------------------------------------------------------------------
# Channel B: PyInstaller binary
# ---------------------------------------------------------------------------

install_via_binary() {
    info "==> installing PyInstaller binary for $OS/$ARCH_NORM"
    artifact="claw-$VERSION-$OS-$ARCH_NORM"
    base_url="https://github.com/$GH_OWNER/$GH_REPO/releases/download/v$VERSION"
    bin_url="$base_url/$artifact"
    sums_url="$base_url/SHA256SUMS"

    tmpdir=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf '$tmpdir'" EXIT INT HUP TERM

    info "    downloading $bin_url"
    if ! curl -fsSL "$bin_url" -o "$tmpdir/claw"; then
        emit_envelope false binary "" "$VERSION" "failed to fetch $bin_url — release may not be published yet"
        err "failed to fetch $bin_url"
        err "if v$VERSION is not yet released, retry once the GitHub Release is up,"
        err "or install from source: git clone … && uv pip install -e ."
        exit 1
    fi

    if curl -fsSL "$sums_url" -o "$tmpdir/SHA256SUMS" 2>/dev/null; then
        info "    verifying SHA256"
        cd "$tmpdir"
        if command -v sha256sum >/dev/null 2>&1; then
            grep " $artifact\$" SHA256SUMS | sha256sum -c - >/dev/null
        else
            expected=$(grep " $artifact\$" SHA256SUMS | awk '{print $1}')
            actual=$(shasum -a 256 claw | awk '{print $1}')
            [ "$expected" = "$actual" ] || {
                emit_envelope false binary "" "$VERSION" "SHA256 mismatch — refusing to install (got $actual)"
                err "SHA256 mismatch — refusing to install"; exit 1; }
        fi
        cd - >/dev/null
    else
        info "    SHA256SUMS unavailable — skipping verify (release may predate the manifest format)"
    fi

    chmod +x "$tmpdir/claw"
    mv "$tmpdir/claw" "$INSTALL_DIR/claw"
    INSTALLED_TO="$INSTALL_DIR/claw"
    trap - EXIT INT HUP TERM
    rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$CHANNEL" in
    uv)     install_via_uv ;;
    binary) install_via_binary ;;
    *) emit_envelope false unknown "" "$VERSION" "unknown CHANNEL: $CHANNEL"
       err "unknown CHANNEL: $CHANNEL (allowed: auto / uv / binary)"; exit 2 ;;
esac

# ---------------------------------------------------------------------------
# Smoke + report
# ---------------------------------------------------------------------------

if ! "$INSTALLED_TO" version >/dev/null 2>&1; then
    emit_envelope false "$CHANNEL" "$INSTALLED_TO" "$VERSION" "smoke test \`claw version\` failed"
    err "post-install smoke (\`claw version\`) failed at $INSTALLED_TO"
    exit 1
fi

info ""
info "✓ claw installed at $INSTALLED_TO"
info ""
info "  Next steps (in order):"
info "    1. Install skills into your coding agent(s):"
info "         claw setup"
info "       (auto-detects Claude Code / Codex / OpenClaw and"
info "        copies the videoclaw-* skills into each)"
info ""
info "    2. Configure API keys:"
info "         bash $INSTALL_DIR/../share/videoclaw/setup.sh"
info "         (or from source: bash packaging/setup.sh)"
info ""
info "    3. Verify:"
info "         claw --json doctor"
info ""

emit_envelope true "$CHANNEL" "$INSTALLED_TO" "$VERSION" "null"
