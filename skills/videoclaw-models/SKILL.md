---
name: videoclaw-models
description: >
  Use when the user asks "which video model should I use", "choose an
  adapter", "select Seedance / Kling / MiniMax / Zhipu / OpenAI Sora /
  mock", "切视频模型", or invokes `claw model list` / `claw model info`.
  Also load before `claw drama run` so the agent picks the adapter that
  matches the user's quality / cost / region constraints. Covers the
  seven adapters, the Seedance HTTPS-URL constraint, and the "stylized
  faces only" Privacy Information rule.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.0
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup"
---

# Video Adapter Selection

> **STOP — check `claw model list` first.** The set of registered
> adapters depends on which API keys are configured; selecting an
> adapter without a key produces an exit code 3 (auth needed) at
> generate time, not at selection time.

Videoclaw ships adapters for **seedance** (default), **seedance_byteplus**,
**kling**, **minimax**, **zhipu**, **openai**, and **mock** (testing
only). Pick by quality / cost / region / availability.

> **Placeholder body** — seven-row capability matrix, selection
> decision tree, and the Seedance reference-image / face-style
> constraints land in T4 of M002.
