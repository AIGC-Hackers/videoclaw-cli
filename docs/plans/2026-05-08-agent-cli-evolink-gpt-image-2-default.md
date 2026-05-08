# Spec: Evolink GPT Image 2 as Default Image Asset Generator

## Objective

Make VideoClaw prefer Evolink `gpt-image-2` for all image asset generation,
especially character turnaround sheets, scene/location references, props, cover
frames, and direct `claw image` calls.

The implementation should support BytePlus Seedream 5.0 Lite as an optional
image provider, but it must no longer be the default for drama assets. If the
user does not specify an image provider/model, VideoClaw should attempt
Evolink `gpt-image-2` first. If a user-selected non-Evolink image provider
fails and Evolink credentials are available, the fallback path should try
`gpt-image-2` before failing the design stage.

Assumption to confirm: the user request says "byteplus seedance5.0-lite" for
image generation. The current code and BytePlus image naming use
`seedream-5.0-lite`; `seedance` is the video model family. This spec treats the
requested BytePlus image fallback as `seedream-5.0-lite`.

## Official Source

Primary source:

- https://evolink.ai/api-reference/gpt-image-2/gpt-image-2-API-Reference.md

Relevant documented contract captured on 2026-05-08:

- Create image task: `POST https://api.evolink.ai/v1/images/generations`.
- Authentication: `Authorization: Bearer YOUR_API_KEY`.
- Required request fields: `model`, `prompt`.
- Model enum and default: `gpt-image-2`.
- Prompt max length: 32,000 Unicode code points.
- Input image URLs for image-to-image/editing: `image_urls`, 1 to 16 images,
  each image up to 50 MB, formats `.jpeg`, `.jpg`, `.png`, `.webp`.
- `size` supports ratio strings such as `1:1`, `3:4`, `9:16`, `16:9`,
  explicit pixel strings such as `1024x1024`, and `auto`.
- `resolution` supports `1K`, `2K`, `4K`; default is `1K`.
- `quality` supports `low`, `medium`, `high`; default is `medium`.
- `n` supports 1 to 10; default is 1.
- API is asynchronous. Initial response returns a task id; results are fetched
  from `GET /v1/tasks/{task_id}`.
- Completed task details include `results`, an array of result image URLs.
- Generated image links are valid for 24 hours and must be saved promptly.

## Desired Defaults

New config defaults:

```python
default_image_provider: str = "evolink"
default_image_model: str = "gpt-image-2"
default_image_resolution: str = "1K"
default_image_quality: str = "medium"
```

Default size behavior:

- Use the lowest documented resolution tier, `1K`, whenever an aspect-ratio
  `size` is used.
- Preserve asset-specific aspect ratios:
  - Character turnaround sheets: `3:4` unless a caller specifies otherwise.
  - Scene/location references: `16:9` or the existing scene-specific aspect
    ratio where already encoded.
  - Props: `1:1` unless a caller specifies otherwise.
  - `claw image`: default `size` remains a user-facing option, but the
    `resolution` default is `1K`.
- Do not default to `2K`, `4K`, or BytePlus high-resolution presets.
- Do not use explicit pixel dimensions by default. If explicit pixels are
  introduced later, they must respect Evolink's documented minimum pixel
  budget and multiple-of-16 constraints.

Quality behavior:

- Keep `quality="medium"` by default because that is the official API default.
- Allow `quality="low"` as an explicit cost-saving option, but do not silently
  degrade quality unless the user configures it.

## Provider Priority

For drama asset generation:

1. If the user explicitly specifies provider/model, try that first.
2. If the explicit provider/model is not Evolink `gpt-image-2` and it fails
   with a provider/runtime error, try Evolink `gpt-image-2` next when
   `VIDEOCLAW_EVOLINK_API_KEY` is configured.
3. If the user did not specify provider/model, try Evolink `gpt-image-2` first.
4. BytePlus `seedream-5.0-lite` remains supported as an optional fallback or
   explicit provider, but it must not outrank `gpt-image-2`.
5. If `gpt-image-2` itself was explicitly selected and fails, surface the
   Evolink error rather than hiding it behind another provider.

For direct `claw image`:

1. Default provider/model should be Evolink `gpt-image-2`.
2. `--provider byteplus --model seedream-5.0-lite` should remain available.
3. `--provider gemini` can remain for backward compatibility, but agent-facing
   skills and docs should recommend Evolink `gpt-image-2`.

## Public Interface

Environment variables:

```bash
VIDEOCLAW_DEFAULT_IMAGE_PROVIDER=evolink
VIDEOCLAW_DEFAULT_IMAGE_MODEL=gpt-image-2
VIDEOCLAW_DEFAULT_IMAGE_RESOLUTION=1K
VIDEOCLAW_DEFAULT_IMAGE_QUALITY=medium
```

CLI additions:

```bash
claw image "prompt" \
  --provider evolink \
  --model gpt-image-2 \
  --size 3:4 \
  --resolution 1K \
  --quality medium

claw drama design-characters <series_id> \
  --image-provider evolink \
  --image-model gpt-image-2

claw drama design-scenes <series_id> \
  --image-provider evolink \
  --image-model gpt-image-2

claw drama design-cover <series_id> \
  --image-provider evolink \
  --image-model gpt-image-2
```

Implementation can stage the drama CLI flags after the provider resolver is in
place. The config defaults are required in the first implementation slice.

## Project Structure

Likely source files:

- `src/videoclaw/config.py`
  - Add image default config fields.
- `src/videoclaw/generation/evolink_image.py`
  - Change default model to `gpt-image-2`.
  - Send `resolution` and `quality` according to the gpt-image-2 schema.
  - Continue async polling through `/tasks/{task_id}`.
- `src/videoclaw/generation/byteplus_image.py`
  - Keep BytePlus `seedream-5.0-lite` available as explicit/optional provider.
  - Confirm model alias names include `seedream-5.0-lite`.
- `src/videoclaw/drama/character_designer.py`
  - Replace BytePlus-first default with resolver/default provider logic.
- `src/videoclaw/drama/scene_designer.py`
  - Same resolver/default provider logic for scene and prop images.
- `src/videoclaw/cli/stage.py`
  - Default `claw image` to Evolink `gpt-image-2`.
  - Add `--model`, `--resolution`, and `--quality`.
- `src/videoclaw/cli/drama/_design.py`
  - Add provider/model options if implementation scope includes CLI override
    in the first slice.
- `skills/videoclaw-models/SKILL.md`
  - Teach agents that image assets default to Evolink `gpt-image-2`.
- `skills/videoclaw-workflow/SKILL.md`
  - Update drama design guidance to prefer `gpt-image-2` for character,
    scene, prop, and cover assets.
- `skills/videoclaw-troubleshoot/SKILL.md`
  - Add troubleshooting for Evolink image auth/quota/model-access failures.
- `AGENTS.md`, `README.md`, and setup docs
  - Document new image defaults and required `VIDEOCLAW_EVOLINK_API_KEY`.

Optional supporting file:

- `src/videoclaw/generation/image_provider.py`
  - A small resolver/factory can be introduced only if it removes duplicated
    provider-selection logic between character and scene designers.
  - Keep it narrow: no generic plugin framework.

## Code Style

Prefer explicit provider candidates over hidden global fallback behavior:

```python
def default_image_candidates(explicit: ImageChoice | None) -> list[ImageChoice]:
    if explicit is None:
        return [
            ImageChoice(provider="evolink", model="gpt-image-2"),
            ImageChoice(provider="byteplus", model="seedream-5.0-lite"),
        ]
    if explicit.provider == "evolink" and explicit.model == "gpt-image-2":
        return [explicit]
    return [explicit, ImageChoice(provider="evolink", model="gpt-image-2")]
```

This keeps fallback order testable and avoids spreading implicit `try/except`
provider selection through the drama designers.

## Testing Strategy

Unit tests should run without real API calls.

Required tests:

- Config defaults:
  - `default_image_provider == "evolink"`.
  - `default_image_model == "gpt-image-2"`.
  - `default_image_resolution == "1K"`.
- Evolink request payload:
  - Default body includes `model: gpt-image-2`, `resolution: 1K`,
    `quality: medium`, `n: 1`.
  - `image_urls` is passed through when provided.
  - The generator polls `/tasks/{task_id}` when the initial response has no
    direct image URL.
  - Completed `results` URLs are downloaded and stored locally.
- Provider resolver:
  - No explicit provider returns `evolink:gpt-image-2` before BytePlus.
  - Explicit BytePlus returns BytePlus first and Evolink second.
  - Explicit Evolink `gpt-image-2` returns only Evolink.
- Character designer:
  - With no injected generator and an Evolink key, it instantiates Evolink
    `gpt-image-2`, not BytePlus.
  - If explicit/injected BytePlus generation fails, fallback attempts Evolink
    `gpt-image-2` when configured.
- Scene designer:
  - Same default and fallback behavior as character designer.
- CLI:
  - `claw image --help` shows provider/model/resolution/quality options.
  - Default provider in the JSON result is `evolink` when no provider is set.
- Skills/docs:
  - Skills validation still passes: `uv run python packaging/skills-validate.py skills/`.

Suggested command set:

```bash
uv run pytest \
  tests/test_evolink_gpt_image2.py \
  tests/test_image_provider_resolution.py \
  tests/test_english_character_designer.py \
  tests/test_scene_designer.py \
  -q

uv run python packaging/skills-validate.py skills/
./agent-cli-release-gate.sh ci
```

Optional real smoke, gated by credentials:

```bash
VIDEOCLAW_EVOLINK_API_KEY=... \
uv run claw image "simple product photo of a white ceramic cup" \
  --provider evolink \
  --model gpt-image-2 \
  --size 1:1 \
  --resolution 1K \
  --quality medium \
  --output /tmp/videoclaw-gpt-image-2-smoke.png
```

## Boundaries

Always:

- Use Evolink official docs as the source for request fields and defaults.
- Save generated URLs immediately because Evolink links are documented as
  valid for 24 hours.
- Keep image defaults separate from video defaults. Do not change
  `default_video_model` in this work.
- Keep BytePlus support optional and explicit.
- Preserve injected-generator tests and mocks used by existing designer tests.

Ask first:

- Removing Gemini image generation support.
- Changing video model defaults or Seedance video adapter behavior.
- Introducing new runtime dependencies.
- Making real API calls in default tests or CI.
- Changing public drama command names.

Never:

- Put API keys in tests, docs, or fixtures.
- Make billable image/video API calls in default test runs.
- Catch and discard all provider errors without preserving the original
  provider/model/error in logs or JSON output.
- Fall back from explicit `gpt-image-2` failures to another provider without
  user opt-in.

## Implementation Slices

1. Config and generator payload
   - Add image default config fields.
   - Update Evolink generator defaults to `gpt-image-2`, `resolution=1K`,
     `quality=medium`.
   - Add unit tests for request body and polling.

2. Provider resolver
   - Add the smallest shared resolver/factory needed by character and scene
     designers.
   - Test default order and fallback behavior.

3. Drama assets
   - Wire character, scene, prop, and cover asset generation through the
     resolver.
   - Preserve existing retry behavior while logging provider/model attempted.

4. CLI surface
   - Add `--model`, `--resolution`, and `--quality` to `claw image`.
   - Add drama design override flags only if needed for user-facing selection.

5. Agent skills and docs
   - Update `videoclaw-models`, `videoclaw-workflow`, and troubleshooting
     skills so coding agents choose gpt-image-2 by default.
   - Update README/AGENTS/setup docs.

6. Verification
   - Run focused tests.
   - Run `./agent-cli-release-gate.sh ci`.
   - Optional real Evolink smoke only with explicit credentials and approval.

## Success Criteria

- Default image asset generation uses Evolink `gpt-image-2`.
- BytePlus `seedream-5.0-lite` remains supported as an optional provider, not
  the default.
- Unspecified character/scene/prop/cover asset generation attempts
  `gpt-image-2` first.
- If a non-Evolink explicit provider fails, fallback attempts `gpt-image-2`
  when available.
- Default generated image resolution is the lowest documented tier, `1K`.
- Existing tests remain green, and new tests cover payloads and provider order.
- Agent skills tell coding agents to choose `gpt-image-2` for image assets.

## Open Questions

- Confirm whether "byteplus seedance5.0-lite" should be implemented as the
  existing BytePlus image model alias `seedream-5.0-lite`.
- Should `quality` default remain Evolink's documented `medium`, or should
  VideoClaw set `low` for the lowest-cost asset pipeline?
- Should explicit non-Evolink provider failures always fallback to
  `gpt-image-2`, or only for retryable provider/runtime failures?
- Should `claw drama design-cover` receive provider/model flags in the first
  implementation slice, or should cover generation follow config defaults
  only for now?
