# Pipeline internals (reference, loaded on demand)

Long-form reference for the videoclaw drama pipeline — placeholder.
T2 of M002 fills in:

- DAG construction (`build_episode_dag`) and stage ordering
- Checkpoint persistence layout under
  `{projects_dir}/dramas/{series_id}/checkpoints/`
- `build_review_dir` symlink semantics for `docs/deliverables/<drama>/review/`
- Quality-gate thresholds and the audit-regen loop
- Cost accounting (`videoclaw.cost`) and budget guards
