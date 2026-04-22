---
version: 1
models:
  research: claude-opus-4-7
  planning: claude-opus-4-7
  execution: claude-opus-4-7
  completion: claude-opus-4-7
skill_discovery: suggest
auto_supervisor:
  soft_timeout_minutes: 20
  idle_timeout_minutes: 10
  hard_timeout_minutes: 30
unique_milestone_ids: true
git:
  isolation: worktree
verification_commands: []
verification_auto_fix: false
auto_report: true
---
