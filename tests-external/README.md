# tests-external — agent-callable E2E

External tests that drive videoclaw the way Claude Code or another code
agent would: a mix of MCP (read-only discovery / metadata) and `claw`
CLI (mutating ops). Lives outside `tests/` so the existing pytest suite
stays fast and offline-safe.

## Stage matrix

Verified locally on this branch — **passing** column reflects what was
observed on a real run against the `loving-talk` PDF.

| Stage | What it does | Cost | Runtime | Default | Passing |
|---|---|---|---|---|---|
| T1 | Verify converted markdown exists. | free | <1 s | ✅ runs | ✅ |
| T2 | `claw drama new "<synopsis>" --no-plan` persists series. | free | ~2 s | ✅ runs | ✅ |
| T3 | MCP `list_drama_series` includes new id. | free | ~3 s | ✅ runs | ✅ |
| T4 | MCP `get_drama_series` returns metadata. | free | ~3 s | ✅ runs | ✅ |
| T5 | `claw drama plan` — produces characters + episode synopsis. | ~$0.05 | ~30 s | gated `E2E_REAL_LLM=1` | ✅ |
| T6 | `claw drama script` + `drama design-scenes` — shot decomposition + scene/prop ref images. | ~$0.20 | ~2 min | gated `E2E_REAL_LLM=1` | ✅ |
| T7 | `claw drama design-characters` — turnaround sheets wired into `series.characters[].reference_images`. | ~$1 | ~2 min | gated `E2E_REAL_LLM=1` | not yet run |
| T8 | `claw drama run --dry-run --max-shots 3`. | free | ~3 s | ✅ runs | ✅ |
| T9 | Real Seedance video for first 3 shots. | ~$3 | ~10 min | gated `E2E_REAL_VIDEO=1` | needs T7 first |

**T7 prerequisite for T9** — without `design-characters` populating
`reference_images`, the pre-production gate (item 2 of 7, see
`src/videoclaw/drama/pre_production_gate.py:62-70`) fails-quiet and Seedance
returns 0 cost / 13-min hang. The first attempt at T9 burned ~$3 of wall time
discovering this; T9 now pre-checks `reference_images` and skips with a
clear message if they're missing.

## What the run produces (verified)

After T2-T6 against the loving-talk PDF, ``$projects_dir/dramas/<id>/`` contains:

```
series.json                                        # 2 characters, 1 episode, 7 shots
characters/陆北辰_turnaround.png                   # design-scenes by-product
characters/苏念念_turnaround.png
scenes/scene_upscale_chinese_restaurant_entrance.png
scenes/scene_restaurant_corner_booth.png
scenes/scene_restaurant_booth.png
scenes/scene_restaurant_booth_closeup.png
scenes/scene_closeup_of_chinese_female_late_20s.png
scenes/scene_closeup_of_two_hands_shaking_across_restaurant_tab.png
scenes/scene_closeup_of_female_hands_holding_smartphone.png
scenes/scene_extreme_closeup.png
props/prop_phone.png
props/prop_necklace.png
ep01_prompts/confirmed_prompts.json                # locked Seedance prompts
```

Each shot in ``series.json::episodes[0].scenes[]`` carries 28 fields
including ``visual_prompt``, ``shot_scale``, ``camera_movement``,
``duration_seconds``, ``dialogue``, ``speaking_character``, ``emotion``,
``characters_present``, ``time_of_day`` — i.e. every input Seedance needs
plus every input a code agent reads to know what's about to happen.

## Setup

```bash
# Install MCP shim with test extras (pytest + pytest-asyncio).
uv pip install -e "mcp-shim/[test]" pypdf

# (One-time) convert the source PDF to markdown.
uv run python -c "
from pypdf import PdfReader; from pathlib import Path
r = PdfReader('/Users/moose/Downloads/《恋爱好啊，得谈！》项目介绍（一卡）.pdf')
md = '# 恋爱好啊，得谈！ — 项目介绍\n\n' + '\n\n'.join((p.extract_text() or '').strip() for p in r.pages)
Path('tests-external/data/loving-talk-script.md').write_text(md, encoding='utf-8')
"
```

## Run

```bash
# Free tiers only (T1, T2, T3, T4, T8) — proves the discovery + drama-new +
# MCP-readback + dry-run flow works without hitting any billable API.
uv run pytest tests-external/test_e2e_first_3_shots.py -v
# 5 passed, 4 skipped in ~5s

# Add the LLM stages (T5 plan, T6 script+design-scenes, T7 design-characters).
# Total: ~$1.25, ~5 minutes, produces all intermediate assets above.
E2E_REAL_LLM=1 uv run pytest tests-external/test_e2e_first_3_shots.py -v

# Full real run — also produces 3 actual Seedance video files.
# Requires VIDEOCLAW_EVOLINK_API_KEY + VIDEOCLAW_ARK_API_KEY in .env.
# Total: ~$4.25, ~17 minutes.
E2E_REAL_LLM=1 E2E_REAL_VIDEO=1 \
  uv run pytest tests-external/test_e2e_first_3_shots.py -v
```

## What this proves

If T1..T4 + T7 pass, an external code agent can:

1. Discover videoclaw's read-only surface over MCP (`tools/list`,
   `list_drama_series`, `get_drama_series`).
2. Drive videoclaw's mutating ops via `claw drama …` (Bash invocation).
3. Round-trip a freshly-imported series: CLI created it → MCP sees it →
   MCP returns its metadata.
4. Reach the dry-run executor — proves the plan/run wiring is reachable
   even before LLM/video keys are configured.

If T5 + T8 also pass, the agent has produced actual intermediate
(storyboard) and final (3 video files) assets end-to-end.

## Data hygiene

`tests-external/data/` holds drama scripts which are user content, not
toolkit artifacts. The `.gitignore` keeps the directory out of the repo
(only `.gitkeep` is tracked). Set the env var `VIDEOCLAW_PROJECTS_DIR`
or run from a temp cwd if you don't want generated `dramas/<id>/` to
land in the default `./projects/` dir.

## Why the shim doesn't expose `drama plan` / `drama run`

The MCP shim is intentionally **read-only**. Mutating ops stay on the
CLI per the videoclaw-packaging blueprint's Section 4 decision: the
shim wraps videoclaw at the boundary, never claims the `claw drama`
namespace, and never edits `src/videoclaw/`. A future milestone (P2)
may add mutating tools — for now an external agent that needs to drive
generation calls `claw drama …` via Bash.

This split is the pragmatic answer to "can Claude Code fully drive
videoclaw": **yes**, by composing MCP discovery with Bash CLI calls —
the same shape every other code agent already uses for non-trivial CLI
tools.
