---
name: videoclaw-drama-setup
description: >
  Use when the user wants to "create a new drama series", "import a
  script", "新建剧集", "写脚本", "edit episode script", or invokes
  `claw drama new` / `claw drama import` / `claw drama script`. Covers
  the three series-entry modes (concept-driven LLM authoring vs
  imported locked script vs interactive editing), `--lang zh|en`,
  `--title`, `--episode N`, and the criteria for picking each entry
  mode. Do NOT use this skill for scene/character design (use
  `/videoclaw-workflow` Phase 3) or for video generation (Phase 5).
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.0
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup"
---

# Drama Series Setup

> **STOP — pick an entry mode first.** `drama new` (LLM writes from
> a synopsis) and `drama import` (locked external script) are *not*
> interchangeable. Importing a finished script and then running
> `drama new` will produce a duplicate series.

Three entry modes, one decision: how is the script authored?

> **Placeholder body** — full mode-comparison table, flag reference,
> and worked examples land in T3 of M002.
