---
name: videoclaw-checkpoint
description: >
  Use when a `claw drama` stage failed, the user wants to "resume a
  drama run", "regenerate a single shot", "list checkpoints", "redo
  audit", "断点恢复", "重生镜头", or invokes any of `claw drama
  checkpoint-list` / `checkpoint-show` / `checkpoint-resume` /
  `checkpoint-redo` / `checkpoint-assets` / `regen-shot` /
  `edit-shot`. The checkpoint subcommands are FLAT (e.g. `drama
  checkpoint-resume`), NOT nested under a `checkpoint` sub-app.
  Also load whenever a non-zero exit appears mid-pipeline.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.4
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.4/videoclaw-0.1.4-py3-none-any.whl videoclaw setup"
---

# Checkpoint Recovery

> **STOP — never `rm -rf` the dramas directory.** Every stage of
> `drama run` writes a checkpoint snapshot to
> `{VIDEOCLAW_PROJECTS_DIR}/dramas/<series_id>/checkpoints/`.
> Resuming from a snapshot is essentially free; rebuilding from
> scratch costs minutes to hours and re-burns API credits. If the
> user asks to "start over", first ask whether resume can satisfy
> the goal.

## Five flat subcommands

```bash
claw drama checkpoint-list <series_id>                    # all snapshots
claw drama checkpoint-show <checkpoint_id>                # full detail (stage, assets, cost)
claw drama checkpoint-resume <checkpoint_id>              # continue pipeline from this point
claw drama checkpoint-redo <checkpoint_id>                # re-execute the stage that produced this snapshot
claw drama checkpoint-assets <checkpoint_id>              # list assets at this snapshot (optionally open)
```

Naming is **flat** — `checkpoint-list` is one command, not
`checkpoint list`. Coding agents that auto-construct nested
sub-commands from `--help` output will get this wrong; the table
above is authoritative.

## When each command applies

| Symptom | Command | What happens |
|---|---|---|
| `drama run` exited mid-episode (network / quota / signal) | `checkpoint-resume <last_id>` | Pipeline continues from the next stage; already-generated assets reused |
| Audit reported shots 3, 7, 9 failed; want to re-audit only | `audit-regen` (in `/videoclaw-workflow`) handles loop, but to manually re-do the audit stage: `checkpoint-redo <audit_id>` | Re-runs audit on existing shots; doesn't re-generate video |
| Want to see what's at a snapshot | `claw --json drama checkpoint-show <id>` | Returns full snapshot dict |
| Want to inspect generated mp4 / images | `checkpoint-assets <id>` | Lists semantic-named assets; `--open` opens dir in file manager |
| Lost the `series_id` | `claw --json drama list` | Find it by title |
| Want to regen single shot only | `claw drama regen-shot <series_id> --episode N --shot M` | Bypasses checkpoint flow; regenerates one shot in place |
| Want to edit a shot's prompt then regen | `claw drama edit-shot <series_id> --episode N --shot M` | Opens prompt in `$EDITOR`, regenerates on save |

## Snapshot file layout

Snapshots live as JSON files (no database). Path:

```
{VIDEOCLAW_PROJECTS_DIR}/dramas/<series_id>/checkpoints/ep<NN>_<stage>_<id>.json
```

`<stage>` is one of: `plan`, `script`, `design_characters`,
`design_scenes`, `assign_voices`, `run`, `audit`. `<id>` is a
**semantic** logical id — never a UUID or hash, per the videoclaw
constitution.

Snapshot fields (see `src/videoclaw/drama/checkpoint.py`):

- `checkpoint_id / stage / series_id / episode_number / created_at`
- `series_state / project_state / dag_state` (deep copies; safe to replay)
- `assets`: logical name → relative path map
- `stage_result / cost_usd / pipeline_config / remaining_stages`
- `metadata` (free-form)

## Resume semantics

`checkpoint-resume <id>` reads the snapshot, restores
`series_state` / `project_state`, and continues with the **first
stage in `remaining_stages`** — i.e. the stage *after* the snapshot's
`stage` field.

Concrete example:

```
ep01_plan_<id>            ← snapshot after plan
ep01_design_characters_<id>
ep01_design_scenes_<id>
ep01_run_<id>             ← run failed; this snapshot is partial-state
```

If `run` failed, `checkpoint-resume <ep01_run_id>` re-enters the
`run` stage and processes the shots flagged unfinished in
`dag_state`. If you want to **redo** the run from scratch, use
`checkpoint-redo <ep01_design_scenes_id>` — it re-executes
`design_scenes` and onward.

## Review directory (semantic filenames only)

Each successful run rebuilds a review directory at:

```
{VIDEOCLAW_DELIVERABLES_DIR}/<drama-name>/review/
```

Built via `build_review_dir()` (in `drama/checkpoint.py`) which
symlinks assets with **semantic filenames**:

```
review/
├── ep01-shot01-cafe-morning.mp4
├── ep01-shot02-confrontation-night.mp4
├── characters/
│   ├── alice-turnaround.png
│   └── bob-turnaround.png
└── audit-report.md
```

Never UUID or hash leak in this layout. If you see UUIDs, the
review dir was built incorrectly — re-run via:

```bash
claw drama series-view <series_id>      # series-level rebuild (idempotent)
claw drama export <series_id> --episode N    # episode-level export
```

## Common recovery flows

### Network blip mid-run

```bash
claw --json drama checkpoint-list abc123 | jq '.data.checkpoints | last'
claw drama checkpoint-resume <last_id>
```

### Cost cap exceeded — increase budget and resume

```bash
export VIDEOCLAW_BUDGET_DEFAULT_USD=25
claw drama checkpoint-resume <last_id>
```

### Audit failed shots — auto-regen loop (preferred)

```bash
claw drama audit-regen abc123 --episode 1
```

### Single-shot manual fix

```bash
# Edit prompt, regen
claw drama edit-shot abc123 --episode 1 --shot 7

# Or skip editor, just regen with current prompt
claw drama regen-shot abc123 --episode 1 --shot 7
```

### Lost track of series

```bash
claw --json drama list | jq '.data.series'
# pick the right one, then
claw --json drama show <series_id>
claw drama checkpoint-list <series_id>
```
