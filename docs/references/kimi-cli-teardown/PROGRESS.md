# Kimi-CLI Teardown — Progress Tracker

**Goal**: Extract transferable CLI-agent construction methodology from `~/Moose/kimi-cli` (MoonshotAI/kimi-cli). Ignore Kimi-specific business logic; capture **how the CLI is built**, not **what it does**.

**Deliverables root**: `docs/references/kimi-cli-teardown/` + `docs/references/cli-construction-methodology.md` + `docs/references/videoclaw-packaging-plan.md` + 2 memory files.

**Source root**: `~/Moose/kimi-cli/` (read-only; do not modify).

## Stages

Each stage: read source → write one numbered file → tick the box → move on. If a stage is already done (file exists with real content > 50 lines), skip it. If a stage's file exists but is a stub, fill it in.

- [x] **S1** — `01-structure.md` — Macro layout: tree (2 levels deep) of `src/`, `tests/`, `packages/`, `sdks/`, `web/`; entry points in `pyproject.toml`; runtime deps summary; Python/Node split (if any); Makefile target inventory.
- [ ] **S2** — `02-cli-routing.md` — CLI framework used (argparse/click/typer/prompt-toolkit/other). How commands are declared. Subcommand routing. Global flags. REPL vs one-shot. Help rendering. Cite exact files+lines.
- [ ] **S3** — `03-agent-loop.md` — The core agent loop: message construction, model call, tool-use handling, termination. Sequence (prose or ASCII) from user input → model → tool → result → model. Cite files+lines.
- [ ] **S4** — `04-config.md` — Config system: env vars, config files, precedence, secrets handling, auth/login flow. Cite files.
- [ ] **S5** — `05-tools.md` — Tool system: how built-in tools are declared, registered, and discovered at runtime. Tool schema shape. Permission/approval model if any.
- [ ] **S6** — `06-extensions.md` — Extension/plugin story: entry_points, MCP, hooks, slash commands, subagents. What's pluggable and how.
- [ ] **S7** — `07-packaging.md` — Packaging: `pyproject.toml` anatomy, build backend, wheel contents, binary distribution (`kimi.spec` PyInstaller?), release scripts, versioning.
- [ ] **S8** — `08-testing.md` — Test layout: `tests/` vs `tests_ai/` vs `tests_e2e/`, pytest config, fixtures, CI hooks.
- [ ] **S9** — `../cli-construction-methodology.md` — Synthesis: a reusable playbook. Not a kimi-specific description — a **checklist any CLI-agent project should follow**, with kimi examples as illustrations. Section per concern (structure / routing / agent loop / config / tools / extensions / packaging / testing). Each section ends with a **"apply-to-your-project" checklist**.
- [ ] **S10** — `../videoclaw-packaging-plan.md` — Concrete diff between videoclaw (current state) and the methodology. Gap list, prioritized (blocker / important / nice-to-have), with file paths where videoclaw should change. No implementation — just the plan.
- [ ] **S11** — Memory: write `~/.claude/projects/-Users-moose-Moose-videoclaw/memory/reference_kimi_cli_methodology.md` (pointer to methodology doc) + `reference_cli_build_patterns.md` (distilled 1-pager of the top patterns worth remembering across projects). Add both to `MEMORY.md`.
- [ ] **S12** — Emit `<promise>METHODOLOGY COMPLETE</promise>` after verifying every file in S1–S11 exists and is non-stub (>50 lines each except memory files which can be shorter).

## Working rules (read every iteration)

1. **One stage per iteration.** Find the first unchecked box, do it, tick it, stop. Over-doing wastes the loop.
2. **Cite source**. Every claim about kimi-cli must have `path/to/file.py:NN` backing it.
3. **Methodology over features.** If a detail is kimi-specific (their model, their API), skip it unless it illustrates a generalizable pattern.
4. **Surgical.** Don't edit kimi-cli. Don't reformat videoclaw. Only write to `docs/references/kimi-cli-teardown/`, `docs/references/cli-construction-methodology.md`, `docs/references/videoclaw-packaging-plan.md`, and memory files.
5. **Verify before promise.** S12 runs a check — if any stage file is <50 lines or missing, go back to that stage instead of promising.
