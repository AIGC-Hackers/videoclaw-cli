---
name: videoclaw-workflow
description: >
  Use this skill whenever the user wants to "make a drama with videoclaw",
  "produce a short video drama", "用 videoclaw 做短剧", "build a TikTok
  drama", "run the videoclaw pipeline", or invokes any `claw drama …`
  command. Always-active entrypoint into the videoclaw drama lifecycle —
  covers `drama new` / `drama import` (setup), `plan` / `script`,
  `design-characters` / `design-scenes` / `design-cover` /
  `assign-voices` / `refresh-urls`, `preview-prompts`, `run`, `audit` /
  `audit-regen`, `export`. Loads related skills
  (`/videoclaw-drama-setup`, `/videoclaw-models`,
  `/videoclaw-checkpoint`, `/videoclaw-troubleshoot`) when sub-phases
  apply.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.3
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.3/videoclaw-0.1.3-py3-none-any.whl videoclaw setup"
---

# VideoClaw Drama Production Workflow

> **STOP — Do NOT generate prompts or videos yet.** If no series exists,
> start with `/videoclaw-drama-setup` to create one via `claw drama new`
> or `claw drama import`. Run `claw --json drama list` to check first.
> Skipping setup leads to orphaned assets, broken checkpoint references,
> and silent re-billing.

This skill is the always-active entrypoint for producing a TikTok-format
Western live-action AI drama with **videoclaw** — input a script,
output a 50–90s episode through the
**setup → plan → design → preview → generate → audit → export**
lifecycle.

> Requires: videoclaw ≥ 0.1.0 with Evolink key configured for LLM and
> default `gpt-image-2` image assets. Run
> `claw --json doctor` first; if it returns exit 3, load
> `/videoclaw-troubleshoot` to fix the auth path.

## Phase 0 — Understand

Before scaffolding anything, get the user's intent in writing. Ask
these and **wait for answers** — do not assume:

1. **Synopsis or finished script?** — concept-driven (LLM authors) vs
   imported finalized script (locked, decomposition only).
2. **Language?** — `zh` (default for `drama new`) or `en` (default for
   `drama import`).
3. **Episodes × duration?** — default 5 episodes × 70s. TikTok cap is
   90s; below 50s is too short for narrative arc.
4. **Genre / style?** — `drama` / `cinematic` are the defaults; other
   genres (`thriller`, `romance`, `comedy`) acceptable.
5. **Video model preference?** — default `seedance-2.0`. If the user
   has cost / region constraints, load `/videoclaw-models`.
6. **Image asset provider?** — default Evolink `gpt-image-2`
   (`1K`, `medium`). BytePlus `seedream-5.0-lite` is an optional
   explicit fallback, not the default.
7. **Any constraints on faces?** — Seedance Privacy Information filter
   rejects realistic women's faces; turnarounds must be stylized.

Once answered, persist intent in a working note (e.g. project memo)
before scaffolding. Do not skip. Wrong assumptions here cost hours.

## Phase 1 — Setup (load `/videoclaw-drama-setup` for details)

Pick one of three entry modes:

| User has | Command | Mode |
|---|---|---|
| A synopsis only | `claw drama new "<synopsis>" --title "<t>" --lang zh --episodes 5` | LLM authors script (creative) |
| A finalized .pdf / .docx / .txt script | `claw drama import script.pdf --title "<t>" --lang en` | Locked, decomposition only |
| Existing series, want to re-plan | `claw drama script <series_id> --episode N` | Re-author specific episode |

After setup, capture the `series_id` from the JSON envelope — every
later command takes it as an argument.

## Phase 2 — Plan

```bash
claw drama plan <series_id>                  # episodes outline + scene list (LLM)
claw drama script <series_id> --episode 1    # full scene-by-scene script for ep 1
```

Outputs land under `{VIDEOCLAW_PROJECTS_DIR}/dramas/<series_id>/`. Open
the generated script and verify scene blocks have `location` /
`time_of_day` / `characters_present` / `emotion` / `scene_group`
populated.

## Phase 3 — Design assets

Order matters — characters before scenes (scenes reference characters):

```bash
claw drama design-characters <series_id>     # Universal Reference turnaround sheets
claw drama design-scenes <series_id>         # location reference images
claw drama design-cover <series_id> --episode 1  # TikTok thumbnail
claw drama assign-voices <series_id>         # only for non-native-audio video models
```

For the default `seedance-2.0` model, skip `assign-voices` unless the
user explicitly opts into external TTS. Seedance 2.0 co-generates
dialogue, subtitles, SFX, and ambient audio inside each clip; adding
TTS, BGM, or subtitle overlays later degrades short-drama quality.

Default image asset generation uses Evolink `gpt-image-2` at
`resolution=1K` and `quality=medium` for character turnaround sheets,
scene/location references, props, and cover frames. For direct image
checks, use:

```bash
claw image "location reference, cinematic motel exterior" \
  --provider evolink --model gpt-image-2 --size 16:9 \
  --resolution 1K --quality medium
```

Only use BytePlus as an explicit fallback when requested or when
Evolink image access is unavailable:

```bash
claw image "character turnaround sheet" \
  --provider byteplus --model seedream-5.0-lite --size 3:4
```

If reference image URLs become stale (Seedance refuses base64; uses
HTTPS only), refresh:

```bash
claw drama refresh-urls <series_id>
```

Load `/videoclaw-models` for the **HTTPS-only** rule and the
**stylized faces** Privacy Information rule before designing
characters.

## Phase 4 — Pre-flight

```bash
claw drama preview-prompts <series_id> --episode 1
```

Reads the script + assets and prints the enhanced Seedance 2.0 prompts
for **every shot** — review before spending API credits. If a prompt
looks wrong, return to Phase 2 (`drama script`) or Phase 3
(`design-characters`) before running. **Never skip preview on a fresh
series.**

## Phase 5 — Generate

Always test with the first 3 shots before the full run:

```bash
# Test run
claw drama run <series_id> --episode 1 --max-shots 3

# Full episode after the test passes
claw drama run <series_id> --episode 1
```

Useful flags:

- `--max-shots N` — limit to first N (test budget control)
- `--shot-breakpoint` — pause after each shot for manual review
- `--dry-run` — wire-only validation, no model calls
- `--start N` / `--end M` — generate episode range

Each stage of `run` writes a checkpoint snapshot. If `run` fails
mid-way, **don't** start over — load `/videoclaw-checkpoint` and
resume from the last good checkpoint.

## Phase 6 — Audit

```bash
claw drama audit <series_id> --episode 1            # Vision QA via Claude
claw drama audit-regen <series_id> --episode 1      # audit → regen failing shots → re-audit loop
```

Audit checks character consistency, dialogue alignment, scene
continuity, and prompt-vs-output match. Failed shots are listed in
the checkpoint; `audit-regen` loops automatically up to
`VIDEOCLAW_MAX_RETRIES` (default 3).

For single-shot fixes (audit failed on shot 7 of 12):

```bash
claw drama regen-shot <series_id> --episode 1 --shot 7
claw drama edit-shot <series_id> --episode 1 --shot 7    # opens prompt in $EDITOR
```

## Phase 7 — Export

```bash
claw drama export <series_id> --episode 1
```

Writes deliverables under `{VIDEOCLAW_DELIVERABLES_DIR}/<drama-name>/`:
final mp4, scene-by-scene review directory (semantic filenames, no
UUIDs), audit report, character sheet. Ready to publish to TikTok.

For multi-episode series:

```bash
claw drama series-view <series_id>           # rebuild series-level review (idempotent)
```

## Quick decision matrix

| Symptom | Action | Skill |
|---|---|---|
| `claw doctor` returns 3 | API key missing / expired | `/videoclaw-troubleshoot` |
| Need to pick a non-default video model | Load model selection | `/videoclaw-models` |
| Generate failed mid-episode | Resume from checkpoint | `/videoclaw-checkpoint` |
| Audit flagged shots 3, 7, 9 | `drama audit-regen` (auto) or `regen-shot` (manual) | this skill, Phase 6 |
| Reference image URLs expired | `claw drama refresh-urls` | this skill, Phase 3 |
| Privacy filter rejecting faces | Switch turnaround to stylized illustration | `/videoclaw-models` |

## Universal rules (the videoclaw constitution)

- **Zero hardcoded drama data**. Drama-specific info flows through CLI
  flags / config / assets — never edit `src/videoclaw/**` to embed
  series-specific values.
- **Semantic filenames in review directories** — no UUID / hash leak
  in `docs/deliverables/<drama>/review/`.
- **Subtitle is rendered by Seedance inside the video**, not by FFmpeg
  external overlay. Don't fight this.
- **Seedance 2.0 native audio is authoritative**. Do not add downstream
  TTS, BGM, or subtitle overlay nodes for default Seedance drama runs.
- **Reference images are HTTPS URLs only** (Seedance proxy rejects
  base64 data URIs).
- **Faces in turnaround sheets are stylized / illustrated**, not
  realistic — the Privacy Information filter rejects realistic women.
- **TikTok format is locked** at 9:16 / 720p / 50-90s / Seedance 2.0
  (4-15s per clip).

## Reference

Long-form internals (DAG, checkpoint layout, cost accounting):
[`references/pipeline-internals.md`](references/pipeline-internals.md).
