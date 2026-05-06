---
name: videoclaw-troubleshoot
description: >
  Use when `claw doctor` reports failures, any `claw …` command exits
  non-zero, the user reports an error, "claw 报错", "为什么生成失败",
  or one of these specific symptoms: Seedance privacy-information
  rejection on realistic faces, base64 data-URI rejected by Seedance
  proxy, EdgeTTS voice_id mismatch, Evolink rate limiting, missing API
  key. Also use to interpret videoclaw's exit-code contract
  (0 ok / 1 runtime / 2 usage / 3 auth / 4 blocked).
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.0
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup"
---

# Troubleshooting & Doctor

> **STOP — run `claw --json doctor` first.** Most error reports
> resolve to a missing or stale API key; doctor's JSON envelope
> tells you which one in one line. Do NOT start debugging adapter
> behavior or rebuilding checkpoints before doctor is green.

Videoclaw's exit codes are a contract every coding agent can branch
on without parsing stderr:

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Runtime error (transient or unknown) |
| 2 | Usage error (bad CLI arguments) |
| 3 | Auth needed (missing / invalid API key) |
| 4 | Blocked (refusing to run — e.g. installer as root, unsupported OS) |

> **Placeholder body** — doctor output reading, exit-code dispatch
> table, common error catalog (Privacy Information filter, base64
> URI, rate limits, voice fallback), and recovery hints land in T6
> of M002.
