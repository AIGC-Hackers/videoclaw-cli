---
name: videoclaw-workflow
description: >
  Use this skill whenever the user wants to "make a drama with videoclaw",
  "produce a short video drama", "用 videoclaw 做短剧", "build a TikTok
  drama", "run the videoclaw pipeline", or invokes any `claw drama …`
  command. Always-active entrypoint into the videoclaw drama lifecycle —
  covers `drama new` / `drama import` (setup), `plan` / `script`,
  `design-characters` / `design-scenes` / `design-cover` /
  `assign-voices`, `run`, `audit` / `audit-regen`, `export`. Loads
  related skills (`/videoclaw-drama-setup`, `/videoclaw-models`,
  `/videoclaw-checkpoint`, `/videoclaw-troubleshoot`) when sub-phases
  apply.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.0
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup"
---

# VideoClaw Drama Production Workflow

> **STOP — Do NOT generate prompts or videos yet.** If no series exists,
> start with `/videoclaw-drama-setup` to create one via `claw drama new`
> or `claw drama import`. Run `claw drama list` to check first. Skipping
> setup leads to orphaned assets and broken checkpoint references.

This skill is the always-active entrypoint for producing a TikTok-format
Western live-action AI drama with **videoclaw** — input a script,
output a 50–90s episode through the
**plan → design → generate → audit → export** lifecycle.

> **Placeholder body** — full lifecycle phases (Phase 0 Understand →
> Phase 7 Export & Observe), command tables, cross-skill activation
> rules, and troubleshooting jumps land in T2 of M002. Until then this
> file exists to satisfy the schema validator and let `claw setup`
> bundle a complete skills set.
