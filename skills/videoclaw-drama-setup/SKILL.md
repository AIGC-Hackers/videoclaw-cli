---
name: videoclaw-drama-setup
description: >
  Use when the user wants to "create a new drama series", "import a
  script", "新建剧集", "写脚本", "edit episode script", or invokes
  `claw drama new` / `claw drama import` / `claw drama script`. Covers
  the three series-entry modes (concept-driven LLM authoring vs
  imported locked script vs interactive episode editing), `--lang
  zh|en`, `--title`, `--episodes N`, `--duration`, `--style`,
  `--genre`, `--model`, and the criteria for picking each entry mode.
  Do NOT use this skill for scene/character design (use
  `/videoclaw-workflow` Phase 3) or for video generation (Phase 5).
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.3
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.3/videoclaw-0.1.3-py3-none-any.whl videoclaw setup"
---

# Drama Series Setup

> **STOP — pick an entry mode before running anything.** `drama new`
> (LLM authors from a synopsis) and `drama import` (decompose a
> locked finalized script) are *not* interchangeable. Importing a
> finished script and then running `drama new` produces a duplicate
> series and double-bills the LLM.

## Decision: which entry mode?

| User has | Command | Use when |
|---|---|---|
| **Synopsis / concept only** | `claw drama new "<synopsis>" …` | Creative project; LLM should write the script |
| **Finished .docx / .txt script** | `claw drama import <file> …` | Adaptation; script is locked, decomposition only |
| **Existing series, re-plan an episode** | `claw drama script <series_id> --episode N` | Already created; want fresh scene breakdown for one episode |

The two creation modes write different state — once a series exists
in `{VIDEOCLAW_PROJECTS_DIR}/dramas/<series_id>/series.json`, switching
modes requires `claw project delete <id>` first or you get a duplicate.

## Mode 1 — `drama new` (concept-driven, LLM authors)

```bash
claw drama new "Two strangers meet on a midnight subway and trade life stories" \
    --title "Last Train Confessions" \
    --lang zh \
    --episodes 5 \
    --duration 70 \
    --style cinematic \
    --genre drama \
    --model seedance-2.0
```

Flags (all optional except `synopsis`):

| Flag | Default | Notes |
|---|---|---|
| `--title / -t` | (auto) | Required if you want stable series naming |
| `--genre / -g` | `drama` | Free-form; common: `drama` / `thriller` / `romance` / `comedy` |
| `--episodes / -n` | `5` | Series length |
| `--duration / -d` | `70.0` | Seconds per episode (50-90 valid for TikTok) |
| `--style / -s` | `cinematic` | Visual style hint passed to Seedance |
| `--lang / -l` | `zh` | `zh` or `en` |
| `--aspect-ratio / -a` | `9:16` | Locked at 9:16 for TikTok |
| `--model / -m` | `seedance-2.0` | See `/videoclaw-models` |

The LLM writes a script under
`{projects_dir}/dramas/<series_id>/series.json`. Verify before
proceeding to Phase 2:

```bash
claw drama show <series_id> --json
```

## Mode 2 — `drama import` (locked, decomposition only)

```bash
claw drama import script.docx \
    --title "Satan in a Suit" \
    --lang en \
    --style cinematic
```

The script is treated as **read-only**. Videoclaw decomposes scenes
into Seedance 2.0-compatible shots (4-15s each) but **does not** edit
plot, dialogue, or characterization. This is the right mode for:

- Adaptations of existing IP
- Client-finalized scripts where creative changes need approval
- Re-runs against a script you've already iterated externally

Default `--lang` is `en` for `import` (vs `zh` for `new`) — set
explicitly to be safe.

Supported formats: `.docx` (preferred, formatting preserved) and
`.txt` (plain). PDF / Markdown not supported in 0.1.0.

## Mode 3 — `drama script` (re-plan one episode)

```bash
claw drama script <series_id> --episode 2
```

Re-runs the LLM scene-breakdown step for **one** episode of an
already-created series. Useful when:

- Episode 1 turned out well but episode 2's pacing is off
- You changed character cast and want fresh dialogue
- A new constraint emerged (e.g. character can't appear in scene N)

The script overwrites the existing episode plan but preserves
already-generated assets (you'll need to regen affected shots
afterward via `regen-shot`; see `/videoclaw-workflow` Phase 5).

## Output paths

After successful setup:

```
{VIDEOCLAW_PROJECTS_DIR}/dramas/<series_id>/
├── series.json              # Series-level state (title, episodes, characters)
├── episodes/
│   └── ep01.json            # Episode-level state (script + scenes)
└── checkpoints/             # First snapshot lands here after plan
```

The `<series_id>` is printed by the JSON envelope:

```bash
claw drama new "..." --json | jq -r '.data.series_id'
```

Capture it — every subsequent command needs it.

## Common pitfalls

- **Wrong language flag** — `drama new` defaults to `zh`, `drama
  import` to `en`. Mismatched script + flag produces garbled scenes.
- **Title with spaces** — quote it: `--title "Last Train"`. Without
  quotes the parser sees two args.
- **Mixing modes** — running `drama new` after `drama import` on the
  same script duplicates the series. Use `drama show` /
  `drama list` to verify before re-running.
- **Episode count vs duration** — 5 episodes × 70s = 350s of video.
  At Seedance default cost (~$0.20/clip × ~25 clips per episode) =
  ~$25. Set `VIDEOCLAW_BUDGET_DEFAULT_USD` accordingly.
