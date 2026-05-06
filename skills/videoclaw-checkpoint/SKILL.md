---
name: videoclaw-checkpoint
description: >
  Use when a `claw drama` stage failed, the user wants to "resume a
  drama run", "regenerate a single shot", "list checkpoints", "redo
  audit", "断点恢复", "重生镜头", or invokes any of `claw drama
  checkpoint-list` / `checkpoint-show` / `checkpoint-resume` /
  `checkpoint-redo` / `checkpoint-assets`. The checkpoint subcommands
  are FLAT (e.g. `drama checkpoint-resume`), not nested under a
  `checkpoint` sub-app. Also load whenever a non-zero exit appears
  mid-pipeline.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.0
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.0/videoclaw-0.1.0-py3-none-any.whl videoclaw setup"
---

# Checkpoint Recovery

> **STOP — never `rm -rf` the dramas directory.** Every stage of
> `drama run` writes a checkpoint snapshot to
> `{projects_dir}/dramas/{series_id}/checkpoints/`. Resuming from a
> snapshot is essentially free; rebuilding from scratch costs minutes
> to hours and re-burns API credits.

When a stage fails or you need to re-run a single shot, the
checkpoint subcommands let you resume from the last successful
boundary.

> **Placeholder body** — five-subcommand reference table, snapshot
> file layout, semantic-filename rule for `build_review_dir`, and
> recovery decision flow land in T5 of M002.
