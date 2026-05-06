# Plan — Hybrid `claw setup` via `npx skills` (Path C, M003)

> Phase 3 plan for executing M003: extend `claw setup` to delegate
> to **vercel-labs/skills** (the `npx skills` ecosystem CLI) when
> Node is available, falling back to the existing M002 Python
> installer when not. This unlocks 51+ coding agents (Claude Code,
> Codex, Cursor, **Gemini CLI**, **Antigravity**, OpenClaw,
> Windsurf, Continue, Goose, ...) without us maintaining per-agent
> path tables.
>
> Spec gate already cleared: user approved Path C ("hybrid,
> recommended") on 2026-05-06. Karpathy / surgical-changes
> principle applies — preserve existing T8 / cli/setup.py
> structure, only add the npx delegation layer.

## Why this plan exists

After shipping M002, research into google/agents-cli's wheel
revealed they delegate skills installation to `npx skills@1.4.8`
(vercel-labs/skills) rather than maintaining per-agent path tables
themselves. The npm package's keywords list confirms 51+ agents
including the user's stated targets `gemini-cli`, `antigravity`,
`claude-code`, `codex`, `cursor`, `openclaw`.

Adopting that layer brings us to parity with google/agents-cli's
"Works seamlessly with" promise without us shipping a long-tail
of per-agent code.

## Verifiable success criteria

After this plan is executed:

1. **`claw setup --json` on a Node-equipped host**: envelope
   `installer: "npx-skills"`, exit 0, reports list of agents
   detected by the `skills` tool.
2. **`claw setup --json` on a no-Node host**: envelope
   `installer: "python-fallback"`, exit 0, identical to current
   T8 behavior (Claude Code / Codex / OpenClaw).
3. **End-to-end smoke**: real `~/.gemini/skills/videoclaw-workflow/`
   and `~/.antigravity/skills/videoclaw-workflow/` exist after
   running on this host (Node-equipped).
4. **No regression**: 18 existing tests
   (`test_setup_skills.py` + `test_doctor_exit_codes.py`) all pass.
5. **Lint clean**: 0 new ruff errors on M002+M003 files.
6. **Skills schema unchanged**: `python packaging/skills-validate.py
   skills/` still exits 0; the existing `videoclaw-*/SKILL.md`
   layout already matches what `npx skills` expects.

## Tasks

### D1 — Add `_try_npx_skills()` delegation path in `cli/setup.py`

**Acceptance**:
- New helper `_try_npx_skills(action, dry_run, agent, copy_mode) -> dict | None`
  in `src/videoclaw/cli/setup.py`. Returns a result dict on success,
  or `None` if `npx` is not on PATH (so caller falls back).
- The `setup()` entrypoint tries `_try_npx_skills` **first**; on
  `None`, falls through to the existing `_install_one()` /
  `_uninstall_one()` per-agent path (preserving M002 behavior).
- The delegation invokes:
  ```
  npx -y skills@1.5.5 add AIGC-Hackers/videoclaw-cli -y --all -g [--copy]
  ```
  for install (or `remove videoclaw-cli` for uninstall, or `list
  --json` filtered for current state in `--dry-run`).
- Envelope schema gains an `installer` field: either
  `"npx-skills"` or `"python-fallback"`. The schema name stays
  `videoclaw-setup-skills/v1` (additive change, no version bump).
- New flag `--copy` (default false) — passes `--copy` to
  `npx skills add` so it copies instead of symlinking; for users
  on filesystems without symlink support.
- New flag `--no-npx` (default false) — forces python-fallback
  even when npx is available; for testing the fallback path
  and for users who don't want Node involvement.

**Verify**:
```bash
# Node-equipped host
uv run claw --json setup --dry-run | jq '.data.installer'
# expected: "npx-skills"

# Force fallback
uv run claw --json setup --dry-run --no-npx | jq '.data.installer'
# expected: "python-fallback"
```

**Files**:
- `src/videoclaw/cli/setup.py` — additive (~50 LOC), keep
  existing `_install_one` / `_uninstall_one` / `_resolve_skills_root`
  helpers untouched.

**Dependencies**: none.

---

### D2 — Tests for `_try_npx_skills` + dispatch logic

**Acceptance**:
- New tests in `tests/test_setup_skills.py` (no rename to
  `test_setup_npx.py`; same test module):
  - `test_try_npx_skills_returns_none_when_npx_absent` — patches
    `shutil.which("npx")` to return None, verifies fallback.
  - `test_try_npx_skills_invokes_correct_command` — patches
    `subprocess.run` to capture args, verifies the exact command
    line `npx -y skills@1.5.5 add AIGC-Hackers/videoclaw-cli -y
    --all -g`.
  - `test_setup_uses_npx_when_available_and_no_npx_false` —
    higher-level test that `setup()` chooses npx when
    `_try_npx_skills` returns a dict.
  - `test_setup_uses_fallback_when_no_npx_flag` — `setup(no_npx=True)`
    skips npx, runs the existing python install path.
  - `test_envelope_includes_installer_field` — verifies the
    envelope's `data.installer` is set correctly in both paths.
- All 11 existing tests still pass unchanged.

**Verify**:
```bash
uv run pytest tests/test_setup_skills.py -v
# expected: ≥ 16 passed (11 existing + 5 new)
```

**Files**:
- `tests/test_setup_skills.py` — additive (~80 LOC).

**Dependencies**: D1.

---

### D3 — Local end-to-end verification on this host

**Acceptance**:
- A live `npx skills add ./skills -g --all -y` (against the local
  `skills/` directory) succeeds and writes
  `videoclaw-workflow/SKILL.md` (or equivalent) into at least 4 of
  the agent skill paths present on this host:
  `~/.claude/skills/`, `~/.codex/skills/`,
  `~/.openclaw-autoclaw/skills/`, `~/.gemini/skills/`,
  `~/.antigravity/skills/` (whichever the `skills` tool detects).
- A subsequent `claw setup --json` (with no `--no-npx`) round-trips
  through the new code path and emits a valid
  `videoclaw-setup-skills/v1` envelope with `installer:
  "npx-skills"`.
- A `claw setup --uninstall --json` cleans up successfully.

**Verify**: Manual smoke documented in the verification report
update at the end of the plan. Outputs captured for the report
file.

**Files**: None (verification only). May add a short
`docs/plans/2026-05-07-agent-cli-via-skills-cli-verification.md`
appendix with captured output.

**Dependencies**: D1, D2.

---

### D4 — README "Works with" section expansion

**Acceptance**:
- The `**Works seamlessly with:**` line in README.md HEAD region
  is updated to match google/agents-cli more closely. Specifically
  call out: Gemini CLI, Claude Code, Codex, Cursor, **Antigravity**,
  OpenClaw, Windsurf, Continue, *and 40+ more via `npx skills`*.
- A short note in the Get Started section explains that the wider
  agent support comes via the `npx skills` ecosystem and links to
  https://github.com/vercel-labs/skills.
- Per-agent `<details>` blocks under "Open your coding agent"
  collapse / simplify (since the npx layer handles them all).
  Keep Claude Code + OpenClaw + Codex + Cursor blocks; replace
  the Gemini/Antigravity placeholder with a one-line "auto-installed
  by `claw setup` via `npx skills`".

**Verify**:
```bash
grep -E "Antigravity|Gemini CLI|Windsurf" README.md | wc -l
# expected: ≥ 3
grep -i "vercel-labs/skills" README.md
# expected: 1+ match (link present)
```

**Files**:
- `README.md` — surgical edits, no structural change.

**Dependencies**: none (can run in parallel with D1/D2/D3).

---

### D5 — AGENTS.md per-agent simplification

**Acceptance**:
- The `## Per-agent quickstart` section in AGENTS.md is restructured:
  - Top-line note: "When `npx` is available, `claw setup`
    delegates to the `skills` ecosystem CLI (51+ agents). When not,
    it falls back to a built-in Python installer covering Claude
    Code, Codex, OpenClaw."
  - Keep the 4 detailed blocks (Claude Code / OpenClaw / Codex /
    Cursor) — they're useful as concrete examples.
  - Replace the "Gemini CLI / other agents (deferred)" block with
    a "Gemini CLI" block + a "Antigravity" block reflecting their
    new auto-install via npx, plus a final "Other 45+ agents" line
    pointing at the `skills` agent registry.
- The `## Write-scope (M002)` section is renamed `## Write-scope
  (M002 + M003)` and notes the M003 change as an additive edit to
  `cli/setup.py` only — no new src/ files in M003.

**Verify**:
```bash
grep -E "Antigravity|Gemini CLI" AGENTS.md | wc -l
# expected: ≥ 2 (one heading each)
```

**Files**:
- `AGENTS.md` — surgical edits.

**Dependencies**: none.

---

### D6 — RELEASE_NOTES.md `0.1.1 (pending)` entry

**Acceptance**:
- New section `## [0.1.1] - 2026-05-07 (pending)` at the top of
  `RELEASE_NOTES.md` (above the existing `## [0.1.0]` block).
- Bullets cover:
  - Hybrid `claw setup` — `npx skills` first, Python fallback.
  - 51+ coding agent support via vercel-labs/skills delegation.
  - New flags `--copy` and `--no-npx`.
  - `installer` field added to `videoclaw-setup-skills/v1` envelope.
  - No breaking changes; M002 behavior preserved as fallback path.

**Verify**:
```bash
head -20 RELEASE_NOTES.md | grep -E "^## \[0\.1\.1\]"
# expected: 1 match
```

**Files**:
- `RELEASE_NOTES.md` — prepend new version block.

**Dependencies**: D1 (so the user-facing flag names are stable).

---

### D7 — Verification report append

**Acceptance**:
- Append a new section `## M003 verification (2026-05-07)` to
  `docs/plans/2026-05-06-agent-cli-verification-report.md` (or
  create a sibling `2026-05-07-...-verification.md`).
- Capture: lint pass, test count diff (18 → 23+), npx delegation
  smoke, fallback smoke, real-host npx skills add output.

**Files**:
- `docs/plans/2026-05-06-agent-cli-verification-report.md`
  (append) **OR** `docs/plans/2026-05-07-agent-cli-via-skills-cli-verification.md`
  (new) — implementer's choice based on length.

**Dependencies**: D1, D2, D3, D4, D5, D6 — runs last.

## Dependency graph

```
D4 (README)        ─┐
D5 (AGENTS.md)     ─┼─ all parallel, no D1 dep
D1 (setup.py npx) ─┘
   ⏵ D2 (tests)
   ⏵ D6 (RELEASE_NOTES — needs final flag names)
   ⏵ D3 (smoke + verification)
        ⏵ D7 (verification report)  — runs last after everything
```

## Boundaries (Karpathy + spec)

**Always**:
- Keep existing `_install_one` / `_uninstall_one` /
  `_resolve_skills_root` / `AgentTarget` code untouched. The
  fallback path **must** continue to work exactly as M002.
- Run `uv run pytest tests/test_setup_skills.py -v` after every
  D1 / D2 change.
- `make lint` (M002+M003 files only) must report 0 errors.

**Ask first**:
- Bumping the pinned `skills@1.5.5` version (e.g. to
  `latest`) — could break our envelope layer if vercel-labs
  changes output format.
- Adding any new flag beyond `--copy` and `--no-npx`.
- Adding new src/ files (D1 only edits `cli/setup.py`).

**Never**:
- Replace the existing fallback installer with a stub. Hybrid
  means **both paths work**; the python path is the
  offline / no-Node escape hatch.
- Pin to `skills@latest` (floating) — supply chain risk; we pin to
  `skills@1.5.5` and bump deliberately.
- Change the envelope schema name from `videoclaw-setup-skills/v1`
  (additive `installer` field is fine; rename is not).
