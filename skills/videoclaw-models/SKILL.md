---
name: videoclaw-models
description: >
  Use when the user asks "which video model should I use", "choose an
  adapter", "select Seedance / Kling / MiniMax / Zhipu / OpenAI Sora /
  mock", "切视频模型", or invokes `claw model list` / `claw model pull`.
  Also load before `claw drama run` so the agent picks the adapter that
  matches the user's quality / cost / region constraints. Covers the
  registered adapters, Evolink gpt-image-2 image defaults, BytePlus
  seedream-5.0-lite image fallback, the Seedance HTTPS-URL constraint,
  and the "stylized faces only" Privacy Information rule.
metadata:
  author: VideoClaw Contributors
  license: Modified-MIT
  version: 0.1.4
  requires:
    bins:
      - claw
    install: "uvx --from https://github.com/AIGC-Hackers/videoclaw-cli/releases/download/v0.1.4/videoclaw-0.1.4-py3-none-any.whl videoclaw setup"
---

# Video And Image Adapter Selection

> **STOP — check `claw model list` first.** The set of healthy
> adapters depends on which API keys are configured. Selecting an
> adapter without its key produces exit code 3 (auth needed) at
> generation time, after the LLM has already written the prompts —
> wasted spend.

```bash
claw model list           # show registered adapters + health
claw --json model list    # machine-readable
claw model pull <model>   # download / prepare a local model (offline)
```

## Registered adapters

| Model ID | Capabilities | Mode | When to use |
|---|---|---|---|
| `seedance-2.0` | text→video, image→video | cloud | **Default**. 4-15s clips, audio + dialogue co-generation, 9:16 vertical, Universal Reference. TikTok-grade. |
| `seedance-1.5-pro` | text→video, image→video | cloud | Older Seedance generation; cheaper, lower quality. Fallback if 2.0 quota exhausted. |
| `seedance-bp` (BytePlus) | text→video, image→video | cloud | BytePlus-routed Seedance for users in BytePlus enterprise tier. |
| `kling-1.6` | text→video, image→video | cloud | Strong stylization, distinct visual flavor; longer 10s clips. |
| `minimax-hailuo-2.3` | text→video, image→video | cloud | Hailuo 2.3 — strong motion realism, weaker character consistency. |
| `cogvideox-flash` (Zhipu) | text→video, image→video | cloud | Zhipu's CogVideoX; fastest cloud option, lower fidelity. |
| `sora` (OpenAI) | text→video, image→video | cloud | Sora via OpenAI; high quality, region-restricted, expensive. |
| `mock` | text→video, image→video | local | **Testing only**. Returns deterministic fake videos for CI / dry-runs. Free. |

The id passed to `--model` matches the **Model ID** column. Health
column (OK / FAIL) reflects whether the API key for that adapter is
configured and reachable; FAIL doesn't mean unusable, only
unconfigured.

## Selection decision tree

1. **Just developing / testing the pipeline?** → `--model mock`. Free,
   deterministic, no quota burn.
2. **Want TikTok-grade default?** → `--model seedance-2.0` (default).
   Audio-co-gen and Universal Reference solve character consistency
   and lip-sync in one pass.
3. **Need stronger stylization (anime, painterly)?** → `--model
   kling-1.6`.
4. **Need Sora-quality realism, in supported region, with budget?** →
   `--model sora`.
5. **Cost-bounded, ok with slightly lower fidelity?** → `--model
   seedance-1.5-pro` or `--model cogvideox-flash`.
6. **Region restriction (China-only / no Seedance)?** → `--model
   minimax-hailuo-2.3` or `--model cogvideox-flash` (both China-domestic).

Pass the chosen id to **either**:

- `claw drama new … --model <id>` (set per-series default at creation)
- `claw drama import … --model <id>` (set per-series default for imported scripts)
- `VIDEOCLAW_DEFAULT_VIDEO_MODEL=<id>` (env, applies to all new
  runs)

## Required environment variables

Map of adapter → key (see `claw --json doctor` for status):

| Adapter | Env vars |
|---|---|
| `seedance-2.0` / `seedance-1.5-pro` | `VIDEOCLAW_ARK_API_KEY` (Seedance via vectorspace.cn proxy) |
| `seedance-bp` | `VIDEOCLAW_BYTEPLUS_*` |
| `kling-1.6` | `VIDEOCLAW_KLING_ACCESS_KEY` + `VIDEOCLAW_KLING_SECRET_KEY` |
| `minimax-hailuo-2.3` | `VIDEOCLAW_MINIMAX_API_KEY` |
| `cogvideox-flash` | `VIDEOCLAW_ZHIPU_API_KEY` (or via Evolink) |
| `sora` | `VIDEOCLAW_OPENAI_API_KEY` (or `OPENAI_API_KEY`) |
| `mock` | (none) |

LLM keys (for script writing, audit) live in
`VIDEOCLAW_EVOLINK_API_KEY` and route to Claude / GPT / Kimi /
DeepSeek through one gateway.

## Image asset defaults

Image assets default to Evolink `gpt-image-2` with `resolution=1K`
and `quality=medium`. Use this for character turnaround sheets,
scene/location references, props, cover frames, and direct one-off
images:

```bash
claw image "character turnaround sheet" \
  --provider evolink --model gpt-image-2 --size 3:4 \
  --resolution 1K --quality medium
```

BytePlus remains an optional fallback for image generation. When the
user explicitly asks for BytePlus image assets, prefer
`--provider byteplus --model seedream-5.0-lite`. Do not confuse
`seedream-5.0-lite` (image) with `seedance-*` (video).

## Hard constraints (read these before designing assets)

### 1. HTTPS URLs only for reference images

The Seedance 2.0 proxy at vectorspace.cn **rejects base64 data
URIs**. Reference images (turnaround sheets, scene refs) **must** be
public HTTPS URLs. `claw drama design-characters` writes the assets
to a CDN-backed bucket; if URLs go stale (often after 24h), refresh:

```bash
claw drama refresh-urls <series_id>
```

If you build a custom adapter, the protocol contract enforces:

```python
async def generate(self, prompt: str, refs: list[str], ...) -> Path:
    # refs items MUST be https:// URLs, not base64 data URIs
```

### 2. Stylized / illustrated faces only

Seedance's Privacy Information filter rejects **realistic women's
faces** in turnaround sheets. The character design phase
(`drama design-characters`) defaults to a stylized illustrated
turnaround prompt — do not override this with a "photorealistic"
modifier or you'll get a generation refusal.

If you need realism for non-character beauty shots (landscapes,
products, abstract imagery), you're fine. The constraint only
applies to character reference sheets.

### 3. Subtitle is in-video, not external

Seedance 2.0 renders subtitles **inside the video** during
generation. Do not pipe through FFmpeg subtitle overlay. The
generation prompt template includes the subtitle text; if you change
it after generation, you regenerate, not overlay.

### 4. Clip length 4-15s

Seedance 2.0 hard-caps clips at 15 seconds. The DAG planner enforces
this when slicing scene blocks into shots. If a scene block exceeds
15s, the planner splits it. Don't fight this in custom adapters —
match the cap.

## Adding a new adapter

1. Implement `videoclaw.models.protocol.VideoModelAdapter` (4 async
   methods) — see `src/videoclaw/models/adapters/mock.py` as the
   minimal reference.
2. Register in `pyproject.toml`:
   ```toml
   [project.entry-points."videoclaw.adapters"]
   my_model = "videoclaw.models.adapters.my_model:MyAdapter"
   ```
3. `uv pip install -e .` — `ModelRegistry.discover()` picks it up on
   next start.
4. Write a unit test in `tests/test_my_model_adapter.py`.

The protocol is **structural** (no ABC inheritance needed). Anything
that implements the four methods works.
