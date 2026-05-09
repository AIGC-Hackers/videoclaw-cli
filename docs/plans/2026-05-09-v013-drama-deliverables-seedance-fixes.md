# v0.1.3 Drama Deliverables and Seedance Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the current drama lifecycle preserve source/derived scripts, expose readable storyboard deliverables, generate complete reference assets, and align Seedance 2.0 audio/reference inputs with the intended all-in-one clip generation path.

**Architecture:** Keep fixes inside the existing CLI + drama pipeline. Use `DramaPlanner` for source/LLM ingestion metadata, `checkpoint.py` for human-facing deliverables, `SceneDesigner`/prompt reference routing for intermediate assets, and the Seedance adapter/executor boundary for API payload correctness.

**Tech Stack:** Python 3.12, Typer CLI, dataclass drama models, pytest, local filesystem deliverables under `VIDEOCLAW_DELIVERABLES_DIR`.

### Task 1: Source and LLM Input Deliverables

**Files:**
- Modify: `src/videoclaw/drama/planner.py`
- Modify: `src/videoclaw/drama/checkpoint.py`
- Modify: `src/videoclaw/cli/drama/_setup.py`
- Test: `tests/test_drama_script_ingestion.py`
- Test: `tests/test_checkpoint.py`

**Steps:**
1. Write/verify tests proving imported source text is persisted in series metadata.
2. Write/verify tests proving `build_series_view()` writes `source/input_series.txt`, `source/input_series.html`, and `source/llm_input.html`.
3. Ensure `claw drama import` builds deliverables immediately after decomposition and returns review paths in JSON mode.
4. Run `uv run pytest tests/test_drama_script_ingestion.py tests/test_checkpoint.py -q`.
5. Commit as `fix(drama): archive imported scripts in deliverables`.

### Task 2: Required Scene and Prop Reference Assets

**Files:**
- Modify: `src/videoclaw/drama/scene_designer.py`
- Modify: `src/videoclaw/drama/runner.py`
- Modify: `src/videoclaw/core/executor.py`
- Test: `tests/test_scene_designer.py`
- Test: `tests/test_reference_image_injection.py`
- Test: `tests/test_prompt_segments.py`

**Steps:**
1. Add failing tests for explicit `shot_scale`-driven scene references and single-use dramatic prop references.
2. Make `SceneDesigner` extract stable location keys from scene fields, not only the first visual-prompt phrase.
3. Keep prop extraction conservative but include `detail` shots and strongly marked objects even when they appear once.
4. Verify reference maps flow into video nodes and prompt segment slot allocation.
5. Run `uv run pytest tests/test_scene_designer.py tests/test_reference_image_injection.py tests/test_prompt_segments.py -q`.
6. Commit as `fix(drama): generate required scene and prop references`.

### Task 3: Human-Readable HTML Storyboards

**Files:**
- Modify: `src/videoclaw/drama/checkpoint.py`
- Test: `tests/test_checkpoint.py`

**Steps:**
1. Add a failing test that `build_review_dir()` writes `storyboard.html` beside `storyboard.md`.
2. Render semantic HTML with a summary, scene table, dialogue/narration transcript, and links to local shot/video/audio assets where present.
3. Keep `storyboard.md` for compatibility; make HTML the richer review surface.
4. Run `uv run pytest tests/test_checkpoint.py -q`.
5. Commit as `fix(drama): add html storyboard deliverables`.

### Task 4: Seedance 2.0 Reference Input Validation

**Files:**
- Modify: `src/videoclaw/core/executor.py`
- Modify: `src/videoclaw/models/adapters/seedance.py`
- Test: `tests/test_reference_image_injection.py`
- Test: `tests/test_seedance_adapter.py`

**Steps:**
1. Add failing tests for Seedance reference audio rules: audio refs only attach when at least one image/video ref exists, URLs must be HTTP(S), and generated audio defaults to enabled.
2. Strengthen executor payload construction so prompt text, image references, optional reference videos, and optional reference audios match Seedance 2.0 role constraints.
3. Keep Universal Reference image count capped at nine and preserve structured prompt segment behavior.
4. Run `uv run pytest tests/test_reference_image_injection.py tests/test_seedance_adapter.py -q`.
5. Commit as `fix(seedance): validate reference media inputs`.

### Task 5: Default Seedance Audio Flow

**Files:**
- Modify: `src/videoclaw/drama/runner.py`
- Modify: `src/videoclaw/core/executor.py`
- Test: `tests/test_reference_image_injection.py`
- Test: `tests/test_drama_runner.py`

**Steps:**
1. Add failing tests proving default `seedance-2.0` video generation requests `generate_audio=True` and final composition does not overlay TTS dialogue audio onto Seedance clips by default.
2. Preserve TTS voice generation as reference/consistency assets for character voice profiles and non-Seedance models.
3. Make compose skip dialogue/narration voice tracks when the episode video model uses Seedance co-generated audio, while still allowing music/subtitle/fallback behavior where explicitly enabled.
4. Run `uv run pytest tests/test_reference_image_injection.py tests/test_drama_runner.py -q`.
5. Commit as `fix(drama): avoid double audio overlay for seedance`.

### Task 6: Release Verification

**Files:**
- Modify only version/release notes if required; `pyproject.toml` is already at `0.1.3`.

**Steps:**
1. Run focused tests from Tasks 1-5.
2. Run `uv run pytest tests/test_setup_skills.py tests/test_doctor_exit_codes.py -q`.
3. Run `./agent-cli-release-gate.sh package`.
4. Inspect `git status --short` and `git log --oneline`.
5. Push commits/tags and create the CLI release only after local verification passes.
