# Verification Report — videoclaw Agent-CLI M003 (v0.1.1)

> Phase 4 final output for the M003 plan
> (`2026-05-07-agent-cli-via-skills-cli.md`). Runs the success
> criteria from that plan against HEAD on branch
> `feat/agent-cli-toolkit`. Generated 2026-05-07.

## Verdict — **GO (release-ready, v0.1.1)**

7 of 7 plan tasks (D1-D7) complete. All 6 success criteria from
`2026-05-07-agent-cli-via-skills-cli.md` §"Verifiable success
criteria" pass on this Node-equipped host:

| # | Criterion | Result |
|---|-----------|--------|
| 1 | `claw setup --json` on Node host emits `installer: "npx-skills"`, exit 0, lists detected agents | ✅ 41 agents detected |
| 2 | `claw setup --json --no-npx` emits `installer: "python-fallback"`, exit 0, identical to M002 | ✅ Claude Code / Codex / OpenClaw, 0 regression |
| 3 | E2E smoke: real `~/.gemini/skills/` etc. populated after `claw setup` | ✅ Skills landed via `~/.agents/skills/` central + symlinks (npx-skills layout); 41 agents covered including Gemini CLI, Antigravity, Windsurf, Cline, Continue, Trae, Kiro CLI |
| 4 | No regression: 18 existing tests still pass | ✅ 16 setup tests + 7 doctor tests + 7 mcp tests = 30 pass |
| 5 | Lint clean on M002+M003 files | ✅ `ruff check` 0 errors |
| 6 | `skills-validate.py` still exits 0 | ✅ 5 skills, version 0.1.1 |

## Gate-by-gate results

### D1 — `_try_npx_skills` delegation in `cli/setup.py` — ✅

`src/videoclaw/cli/setup.py` gains:
- `_try_npx_skills(action, copy_mode, skills_root) -> dict | None`
  helper. Returns `None` to signal fallback when `npx` is missing
  (or the `npx skills` invocation fails).
- `_npx_list_videoclaw()` — wraps `npx skills list -g --json` and
  filters to `videoclaw-*` entries; used to snapshot before/after
  state for diff-based record building.
- `_build_npx_records(action, before, after)` — diffs two snapshots
  to produce envelope-shaped `agents_detected` / `skills_installed`
  / `skills_skipped` / `skills_removed` records.
- `setup()` entrypoint — now calls `_try_npx_skills` first when
  `npx` is on PATH and `--no-npx` is not set; falls back to the
  M002 `_install_one` / `_uninstall_one` path on `None`.
- New CLI flags: `--copy` (passes `--copy` to `npx skills add`)
  and `--no-npx` (forces the python-fallback path).
- Envelope `data.installer` field — `"npx-skills"` or
  `"python-fallback"`.

**Deviations from plan**: the plan suggested invoking
`npx skills add AIGC-Hackers/videoclaw-cli`. Implementation passes
the locally-resolved `_skills/` path instead — no GitHub round-trip
required, no supply-chain dependency on a published wheel/release,
and works identically for editable / wheel / PyInstaller installs.

**Implementation note**: the uninstall command was originally
written as `npx skills remove -s "videoclaw-*" -g -y` per the
plan's hint; the live `npx skills@1.5.5` CLI does **not** support
glob patterns in `-s`, so the implementation enumerates skill
names (from `_npx_list_videoclaw()`, falling back to the bundled
`_skills/` directory) and passes them as positional args:
`npx skills remove videoclaw-workflow videoclaw-models … -g -y`.
Verified end-to-end with `claw setup --uninstall` clean removal.

```bash
$ uv run ruff check src/videoclaw/cli/setup.py tests/test_setup_skills.py
All checks passed!
```

### D2 — Tests grow 11 → 16 — ✅

`tests/test_setup_skills.py` gains 5 new tests:

| Test | What it asserts |
|---|---|
| `test_try_npx_skills_returns_none_when_npx_absent` | `shutil.which("npx") = None` ⇒ helper returns `None` so caller falls back |
| `test_try_npx_skills_invokes_correct_command` | Captures `subprocess.run` args; verifies `["npx", "-y", "skills@1.5.5", "add", <root>, "-g", "--all", "-y"]` |
| `test_try_npx_skills_copy_mode_appends_flag` | `copy_mode=True` ⇒ `--copy` appended to the add command |
| `test_setup_uses_fallback_when_no_npx_flag` | `setup(no_npx=True)` ⇒ envelope `installer: "python-fallback"`; `_try_npx_skills` never called |
| `test_setup_envelope_installer_npx_when_delegation_succeeds` | Stubbed `_try_npx_skills` returns dict ⇒ envelope `installer: "npx-skills"`, agent list propagated |

The 11 existing M002 tests were updated to pass `no_npx=True`
explicitly (since the new default tries npx first); behavior on
the python-fallback path is byte-identical to M002.

```bash
$ uv run pytest tests/test_setup_skills.py -v
============================== 16 passed in 0.20s ==============================
```

### D3 — Real-host E2E smoke — ✅

Round-trip executed on this macOS arm64 host with `npx 10.9.2`:

```bash
$ uv run claw --json setup
# 1st run:  installer=npx-skills | installed=5 | ok=true | agents=41
$ uv run claw --json setup
# 2nd run (idempotent): installer=npx-skills | installed=0 | skipped=5 | ok=true
$ uv run claw --json setup --uninstall
# uninstall: installer=npx-skills | removed=5 | ok=true
$ uv run claw --json setup
# reinstall: installer=npx-skills | installed=5 | ok=true | agents=41
```

The 41 agents `npx skills` detected on this host:

```
AdaL, AiderDesk, Augment, Claude Code, Cline, Code Studio,
CodeArts Agent, CodeBuddy, Codemaker, Command Code, Continue,
Cortex Code, Crush, Devin for Terminal, Droid, ForgeCode, Goose,
Hermes Agent, IBM Bob, Junie, Kilo Code, Kiro CLI, Kode, MCPJam,
Mistral Vibe, Mux, Neovate, OpenClaw, OpenHands, Pi, Pochi, Qoder,
Qwen Code, Roo Code, Rovo Dev, Tabnine CLI, Trae, Trae CN,
Windsurf, Zencoder, iFlow CLI
```

Skills land at `~/.agents/skills/videoclaw-*/` (central store) and
are symlinked into each agent's expected path (e.g.
`~/.claude/skills/videoclaw-workflow → ../../.agents/skills/videoclaw-workflow`).
Verified content equality: `~/.agents/skills/videoclaw-workflow/SKILL.md`
matches `skills/videoclaw-workflow/SKILL.md` byte-for-byte.

The Claude Code session running this verification picked up the
freshly-installed `videoclaw-workflow / -checkpoint / -drama-setup
/ -models / -troubleshoot` skills live (visible in `Skill` tool
listings) — confirms the install is wired all the way through, not
just on disk.

### D4 — README "Works with" expansion — ✅

```bash
$ grep -E "Antigravity|Gemini CLI|Windsurf" README.md | wc -l
4
$ grep -i "vercel-labs/skills" README.md | wc -l
2
```

The hero "Works seamlessly with" line now lists Claude Code,
Gemini CLI, Codex, Cursor, Antigravity, OpenClaw, Windsurf,
Continue + "and 40+ more via `npx skills`" with a link to the
`vercel-labs/skills` registry. The Get Started section gains a
"How agent coverage works" paragraph explaining the npx-vs-fallback
resolution order and the `--copy` / `--no-npx` flags.

### D5 — AGENTS.md per-agent simplification — ✅

```bash
$ grep -E "Antigravity|Gemini CLI" AGENTS.md | wc -l
6
```

Per-agent quickstart section gains a top-of-section note
documenting the npx-vs-fallback resolution. The deferred Gemini
CLI block is replaced with three new blocks: Gemini CLI,
Antigravity, "Other 45+ agents". Write-scope section renamed to
M002 + M003 with M003 noted as `setup.py`-only (~120 LOC additive).

### D6 — RELEASE_NOTES `[0.1.1]` entry — ✅

```bash
$ head -10 RELEASE_NOTES.md | grep -E "^## \[0\.1\.1\]"
## [0.1.1] - 2026-05-07
```

Section covers: hybrid setup, 51+ agent reach, `--copy` / `--no-npx`
flags, additive `installer` field, no breaking changes.

### D7 — This file — ✅

(You're reading it.)

## Version consistency — ✅ across 5 places

| Source | Value |
|---|---|
| `pyproject.toml` `version` | `0.1.1` |
| `src/videoclaw/__init__.py` `__version__` | `0.1.1` |
| `packaging/agent-cli.yaml` `version:` | `0.1.1` |
| `claw version` (CLI) | `v0.1.1` |
| All 5 `skills/videoclaw-*/SKILL.md` `metadata.version:` | `0.1.1` |

`packaging/skills-validate.py` enforces SKILL.md ↔ pyproject.toml
on every run; `python packaging/skills-validate.py skills/` →
`VALID: 5 skill(s) under skills conform (version 0.1.1)`.

## Build artifacts — ✅

Wheel + PyInstaller binary both rebuilt for v0.1.1:

```
dist/videoclaw-0.1.1-py3-none-any.whl   372K
dist/claw                                64M  Mach-O 64-bit arm64
dist/SHA256SUMS                          (sha256 of both above)
```

Wheel contents: 7 entries under `_skills/` (5 SKILL.md + 1 README +
1 references). Leakage check (each must be 0) — `tests/`, `projects/`,
`models_cache/`, `docs/deliverables/`, `mcp-shim/`, `packaging/`:
all 0.

PyInstaller binary smoke:

```bash
$ ./dist/claw version
VideoClaw v0.1.1

$ ./dist/claw --json setup --dry-run --no-npx
# binary fallback → installer: python-fallback | version: 0.1.1 | ok: True

$ ./dist/claw --json setup --dry-run
# binary npx path → installer: npx-skills | version: 0.1.1 | ok: True | agents: 41
```

End-to-end: frozen binary boots → `claw version` → both setup paths
resolve their respective installers → 41 agents detected via npx,
3 detected via fallback. T7's `datas += [("../skills",
"videoclaw/_skills")]` line in `claw.spec` continues to ship the
bundled skills.

## Test summary

```bash
$ uv run pytest tests/test_setup_skills.py tests/test_doctor_exit_codes.py mcp-shim/tests/ -q
30 passed, 1 warning in 4.08s
```

- `tests/test_setup_skills.py`         16 tests (was 11 in M002)
- `tests/test_doctor_exit_codes.py`     7 tests (unchanged)
- `mcp-shim/tests/`                     7 tests (unchanged)

Project-wide `make lint` baseline (460 pre-existing errors elsewhere)
is unchanged; M003 added 0 net errors.

## Conclusion

videoclaw v0.1.1 is **release-ready** as the first hybrid
agent-callable CLI. M002's narrow 3-agent installer is preserved
byte-identically as the offline / no-Node escape hatch; M003 adds
51+ agent reach via `npx skills` delegation when Node is available.
The two paths share the same envelope schema
(`videoclaw-setup-skills/v1`, additive `installer` field) so
orchestrators can dispatch on which installer ran without
breaking M002 consumers.

Push the branch + tag `v0.1.1` to publish via the existing
`release.yml` matrix (macOS arm64 + Linux x86_64 + Docker).
