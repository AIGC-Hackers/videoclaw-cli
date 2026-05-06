# Pipeline internals (reference, loaded on demand)

Long-form reference for the videoclaw drama pipeline. Coding agents
load this only when they need to reason about layout, costs, or
checkpoint internals — most tasks resolve from `SKILL.md` alone.

## DAG construction

`drama run` calls `videoclaw.drama.runner.DramaRunner.run_episode()`
which invokes `build_episode_dag()`. The DAG nodes are scene shots
(each Seedance 2.0 call is one node). Edges encode:

- character-reference dependencies (turnaround sheet → shots that
  feature the character)
- scene-reference dependencies (location reference → shots in that
  location)
- audio-mix dependencies (per-shot dialogue → final compose)

`DAGExecutor.run()` schedules independent nodes in parallel
(bounded by `VIDEOCLAW_MAX_RETRIES` and the per-node budget).

## Checkpoint layout

```
{VIDEOCLAW_PROJECTS_DIR}/dramas/{series_id}/
├── checkpoints/
│   ├── ep01_plan_<id>.json
│   ├── ep01_design_characters_<id>.json
│   ├── ep01_design_scenes_<id>.json
│   ├── ep01_run_<id>.json
│   └── ep01_audit_<id>.json
├── assets/
│   ├── characters/
│   ├── scenes/
│   └── shots/ep01/
└── series.json
```

Each `<id>` is the snapshot's logical ID (semantic, not UUID).
Snapshot fields (see `src/videoclaw/drama/checkpoint.py` →
`CheckpointSnapshot`):

- `checkpoint_id / stage / series_id / episode_number / created_at`
- `series_state / project_state / dag_state` (deep copies for safe replay)
- `assets`: logical name → relative path (semantic filenames only)
- `stage_result / cost_usd / pipeline_config / remaining_stages`

Resume:

```bash
claw drama checkpoint-resume <checkpoint_id>
```

The runner picks up at the stage *after* the snapshot's `stage`
field, replaying `remaining_stages` against the captured
`series_state`.

## Cost accounting

Per-node cost is tracked by `videoclaw.cost.CostTracker` and
exposed via `claw cost summary <series_id>`. Budget guard:
`VIDEOCLAW_BUDGET_DEFAULT_USD` (default $10). When exceeded the run
fails with exit 1 and the partial checkpoint persists for resume.

## Quality gate

`audit-regen` uses Claude Vision to score each shot on:

- **Character consistency** — same face / clothing across shots
- **Dialogue alignment** — lip-sync vs spoken text
- **Scene continuity** — location / lighting / time-of-day stable
- **Prompt-vs-output** — generated frame matches enhanced prompt

Failing shots auto-regenerate up to `VIDEOCLAW_MAX_RETRIES` (default
3) attempts; persistent failures land in the audit report and need
manual intervention via `regen-shot` / `edit-shot`.
