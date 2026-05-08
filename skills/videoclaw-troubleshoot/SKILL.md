---
name: videoclaw-troubleshoot
description: >
  Use when `claw doctor` reports failures, any `claw …` command exits
  non-zero, the user reports an error, "claw 报错", "为什么生成失败",
  or one of these specific symptoms: Seedance privacy-information
  rejection on realistic faces, base64 data-URI rejected by Seedance
  proxy, EdgeTTS voice_id mismatch, Evolink gpt-image-2 auth/quota or
  model-access failure, Evolink rate limiting, missing API key, doctor
  returns 3, install.sh reports unsupported OS. Also use to interpret
  videoclaw's exit-code contract
  (0 ok / 1 runtime / 2 usage / 3 auth / 4 blocked).
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.3
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.3/videoclaw-0.1.3-py3-none-any.whl videoclaw setup"
---

# Troubleshooting & Doctor

> **STOP — run `claw --json doctor` first.** Most error reports
> resolve to a missing or stale API key; doctor's JSON envelope
> tells you which one in one line. Do NOT start debugging adapter
> behavior or rebuilding checkpoints before doctor is green.

## The exit-code contract

Videoclaw's exit codes are a contract every coding agent can branch
on without parsing stderr or stdout text:

| Code | Meaning | Typical cause | First action |
|---|---|---|---|
| **0** | OK | (success) | continue |
| **1** | Runtime error | transient API / network / unknown | retry; check `--verbose` log |
| **2** | Usage error | bad CLI args / unknown flag | check `claw <cmd> --help` |
| **3** | Auth needed | missing or invalid API key | run `bash packaging/setup.sh` to (re)configure |
| **4** | Blocked | refusing to run (root install, unsupported OS, policy) | read the JSON envelope's `error` field |

Currently exit 4 is used by `install.sh` (root refusal, unsupported
OS/arch). The CLI itself emits 0/1/2/3.

Agent dispatch pattern (any coding agent's Bash tool):

```bash
claw --json doctor
case $? in
    0) echo "all good" ;;
    1) echo "runtime — retry once, then escalate" ;;
    2) echo "usage — check --help" ;;
    3) echo "auth — run setup wizard" ;;
    4) echo "blocked — read envelope.error" ;;
esac
```

## Doctor — what it checks

```bash
claw --json doctor
```

The envelope's `data` field includes per-key health for:

- `VIDEOCLAW_EVOLINK_API_KEY` — LLM gateway and default
  `gpt-image-2` image assets (required)
- `VIDEOCLAW_ARK_API_KEY` — Seedance video (required for real video)
- `VIDEOCLAW_KLING_*` / `VIDEOCLAW_MINIMAX_API_KEY` /
  `VIDEOCLAW_BYTEPLUS_*` / `VIDEOCLAW_ZHIPU_API_KEY` /
  `VIDEOCLAW_OPENAI_API_KEY` — optional adapters
- Default model resolution
- Storage directory writability (`VIDEOCLAW_PROJECTS_DIR`,
  `VIDEOCLAW_MODELS_DIR`, `VIDEOCLAW_DELIVERABLES_DIR`)

A green doctor = exit 0, `data.healthy = true`. A red doctor on
**required** keys = exit 3.

## Common errors & fixes

### `Privacy Information filter` — Seedance rejects realistic faces

**Symptom**: `drama design-characters` succeeds but `drama run`
returns 1 with stderr mentioning "privacy information" or "policy
violation".

**Cause**: Seedance's content filter rejects **realistic women's
faces** in turnaround sheets (and shots that reference them).

**Fix**: Re-design characters with explicit **stylized / illustrated**
guidance. The default prompt in `drama design-characters` already
biases this way; if you overrode it with `--style photorealistic`,
back out:

```bash
# Re-design with default stylized prompt
claw drama design-characters <series_id>
# Then refresh URLs that downstream shots depend on
claw drama refresh-urls <series_id>
```

### `400: Invalid image format` — base64 data URI rejected

**Symptom**: Custom adapter or hand-edited prompt embeds an image as
`data:image/png;base64,…`; Seedance proxy returns 400.

**Cause**: Seedance proxy at vectorspace.cn **only accepts public
HTTPS URLs** for reference images.

**Fix**: Upload the image to a public bucket (or the assets
directory videoclaw uses) and pass the HTTPS URL:

```bash
claw drama refresh-urls <series_id>
```

If you wrote the offending base64 in a custom adapter, change the
adapter to upload first.

### `claw doctor` returns 3 — auth needed

**Symptom**:

```bash
$ claw --json doctor
{"ok": false, ..., "error": "VIDEOCLAW_EVOLINK_API_KEY missing"}
$ echo $?
3
```

**Fix**:

```bash
bash packaging/setup.sh        # interactive wizard
# or:
export VIDEOCLAW_EVOLINK_API_KEY=sk-...
export VIDEOCLAW_ARK_API_KEY=...
claw --json doctor             # should now exit 0
```

### `429 Too Many Requests` — Evolink rate limit

**Symptom**: `drama plan`, `drama script`, `drama design-*`, or
`claw image` returns 1 with stderr mentioning rate limit on the
Evolink gateway.

**Fix**: Wait ~60s and retry. If persistent for LLM planning:

```bash
# Override default model to something less rate-limited
export VIDEOCLAW_DEFAULT_LLM=claude-sonnet-4-6  # stronger structured output
claw drama plan <series_id>
```

If the rate limit is specifically for image assets, keep Evolink
`gpt-image-2` as the preferred default and use BytePlus
`seedream-5.0-lite` only as an explicit fallback:

```bash
claw image "scene reference" --provider byteplus --model seedream-5.0-lite
```

### Evolink `gpt-image-2` auth / quota / model-access failure

**Symptom**: `claw image` or `drama design-characters` /
`design-scenes` / `design-cover` fails with 401, 403, quota exceeded,
or a message that `gpt-image-2` is unavailable.

**Cause**: Image assets default to Evolink `gpt-image-2`
(`resolution=1K`, `quality=medium`) and require a valid
`VIDEOCLAW_EVOLINK_API_KEY` with image-generation access.

**Fix**:

```bash
claw --json doctor
export VIDEOCLAW_EVOLINK_API_KEY=sk-...
claw image "smoke test" --provider evolink --model gpt-image-2 \
  --resolution 1K --quality medium
```

If the key is valid but the account lacks `gpt-image-2` access, ask
the provider to enable it or temporarily use explicit BytePlus image
fallback: `--provider byteplus --model seedream-5.0-lite`.

### EdgeTTS voice fallback warning

**Symptom**: `drama assign-voices` succeeds but log says "voice_id
'<custom_id>' not found, falling back to language default".

**Cause**: EdgeTTS doesn't recognize MiniMax-style voice IDs;
videoclaw auto-falls back to the language's default voice.

**Fix**: Two options:
1. Accept the fallback (acceptable for most narrative dramas).
2. Map custom voice_ids in `assign-voices` interactively (the
   command prompts when fallback occurs in interactive mode).

### `unsupported os: <name>` — install.sh exits 4

**Symptom**: `bash install.sh` immediately exits 4 with envelope
saying unsupported OS or arch.

**Supported**: macOS arm64 (`darwin/arm64`), Linux x86_64
(`linux/x86_64`).

**Fix**: For other platforms, install from source:

```bash
git clone https://github.com/AIGC-Hackers/videoclaw-cli.git
cd videoclaw-cli
uv sync
uv run claw version
```

### `claw setup` — no agents detected

**Symptom**:

```bash
$ claw setup --json
{"ok": true, "agents_detected": [], ...}
```

**Cause**: None of `~/.claude/skills/`, `~/.codex/skills/`,
`~/.openclaw-autoclaw/skills/` exist on this host.

**Fix**: Install at least one supported coding agent first, or copy
the skills manually:

```bash
# Manual install for any agent that reads markdown rules:
mkdir -p ~/.<agent>/skills
cp -r $(uv run python -c "from importlib.resources import files; print(files('videoclaw') / '_skills')")/videoclaw-* ~/.<agent>/skills/
```

## Reading `--verbose` output

```bash
claw --verbose drama run <series_id> --episode 1 --max-shots 1
```

Look for:

- `[ERROR]` lines — actual failures
- `[WARN]` lines — degraded but proceeding (e.g. voice fallback)
- `[INFO]` lines preceding errors — usually the offending stage
- HTTP 4xx / 5xx — adapter or LLM gateway issue
- `cost_usd=0.00` on a non-mock run — adapter probably mocked itself
  silently; check `claw model list` health column

## When all else fails

1. Capture the full failing command + envelope: `claw --json
   --verbose <cmd> 2>&1 | tee debug.log`
2. Run `claw --json doctor` and capture
3. Run `claw --json info` and capture (registered adapters /
   versions)
4. Open issue at https://github.com/AIGC-Hackers/videoclaw-cli/issues
   with the three captures
