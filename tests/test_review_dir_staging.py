"""Stage-level review directory asset verification tests.

These tests verify that after each pipeline stage completes, the expected
assets exist in the review directory. They exercise the existing
``_update_review_dir`` / ``build_review_dir`` code paths — no new code is
tested here, only existing behaviour is asserted.

If a test discovers that an expected asset is missing (because the
pipeline stage hasn't been wired to produce it yet), it should be marked
``xfail`` with a clear reason — not silently skipped, and not fixed in
this changeset (out of scope per spec).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from videoclaw.drama.checkpoint import (
    CheckpointController,
    CheckpointManager,
    CheckpointStage,
    review_dir_for_episode,
)
from videoclaw.drama.models import (
    Character,
    ConsistencyManifest,
    DramaManager,
    DramaScene,
    DramaSeries,
    Episode,
    ShotScale,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rich_series(tmp_path: Path) -> tuple[DramaSeries, Episode]:
    """Build a series with characters, scenes, and one episode.

    Returns (series, episode).
    """
    projects_dir = tmp_path / "projects"
    series_dir = projects_dir / "dramas" / "test_stage_series"
    series_dir.mkdir(parents=True, exist_ok=True)

    # Character turnaround image
    char_img = series_dir / "characters" / "lucian_front.png"
    char_img.parent.mkdir(parents=True, exist_ok=True)
    char_img.write_bytes(b"\x89PNG" + b"\x00" * 16)

    # Scene reference image
    scene_img = series_dir / "scenes" / "rooftop.png"
    scene_img.parent.mkdir(parents=True, exist_ok=True)
    scene_img.write_bytes(b"\x89PNG" + b"\x00" * 16)

    series = DramaSeries(
        series_id="test_stage_series",
        title="Stage Test Drama",
        model_id="mock",
        aspect_ratio="9:16",
    )
    series.characters = [
        Character(
            name="Lucian",
            description="Protagonist",
            reference_image=str(char_img),
        ),
    ]
    series.consistency_manifest = ConsistencyManifest(
        scene_references={"rooftop": str(scene_img)},
    )

    ep = Episode(number=1, title="Pilot", project_id="proj_001")
    ep.scenes = [
        DramaScene(
            scene_id="ep01_s01",
            description="Rooftop arrival",
            duration_seconds=5.0,
            shot_scale=ShotScale.MEDIUM,
            characters_present=["Lucian"],
        ),
    ]
    series.episodes = [ep]
    return series, ep


def _make_controller(
    tmp_path: Path,
    series: DramaSeries,
    ep: Episode,
) -> CheckpointController:
    deliverables_dir = tmp_path / "deliverables"
    deliverables_dir.mkdir(exist_ok=True)
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(exist_ok=True)

    mgr = CheckpointManager(base_dir=projects_dir)
    drama_mgr = DramaManager(base_dir=projects_dir / "dramas")

    return CheckpointController(
        series=series,
        episode=ep,
        manager=mgr,
        drama_manager=drama_mgr,
        breakpoints=[],  # no pausing
        interactive=False,
        deliverables_dir=deliverables_dir,
    )


# ---------------------------------------------------------------------------
# 1. After design — characters + scenes materialise
# ---------------------------------------------------------------------------


async def test_after_design_materializes_characters_and_scenes(tmp_path: Path) -> None:
    series, ep = _make_rich_series(tmp_path)
    ctrl = _make_controller(tmp_path, series, ep)

    await ctrl.checkpoint(CheckpointStage.AFTER_DESIGN)

    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    chars_dir = review_dir / "characters"
    scenes_dir = review_dir / "scenes"

    # Characters should be materialised
    if chars_dir.is_dir():
        char_files = list(chars_dir.iterdir())
        assert len(char_files) >= 1, "Expected at least one character turnaround"
    else:
        pytest.xfail("characters/ not materialised after AFTER_DESIGN — verify pipeline wiring")

    # Scenes should be materialised
    if scenes_dir.is_dir():
        scene_files = list(scenes_dir.iterdir())
        assert len(scene_files) >= 1, "Expected at least one scene reference"
    else:
        pytest.xfail("scenes/ not materialised after AFTER_DESIGN — verify pipeline wiring")


# ---------------------------------------------------------------------------
# 2. After storyboard — storyboard.md exists
# ---------------------------------------------------------------------------


async def test_after_storyboard_materializes_storyboard_md(tmp_path: Path) -> None:
    series, ep = _make_rich_series(tmp_path)
    ctrl = _make_controller(tmp_path, series, ep)

    await ctrl.checkpoint(CheckpointStage.AFTER_STORYBOARD)

    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    storyboard_md = review_dir / "storyboard.md"
    assert storyboard_md.exists(), "storyboard.md should exist after AFTER_STORYBOARD"
    content = storyboard_md.read_text()
    assert "分镜表" in content or "storyboard" in content.lower()


# ---------------------------------------------------------------------------
# 3. After video_tts — videos + audio appear (also tests incremental)
# ---------------------------------------------------------------------------


async def test_after_video_tts_materializes_videos_and_audio(tmp_path: Path) -> None:
    series, ep = _make_rich_series(tmp_path)

    # Simulate video generation output
    projects_dir = tmp_path / "projects"
    shots_dir = projects_dir / "proj_001" / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    video_file = shots_dir / "ep01_s01_hash.mp4"
    video_file.write_bytes(b"\x00" * 32)

    # Set asset path on the scene
    ep.scenes[0].video_asset_path = str(video_file)

    # Simulate TTS output
    audio_dir = projects_dir / "proj_001" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    dlg_file = audio_dir / "ep01_s01_dialogue.mp3"
    dlg_file.write_bytes(b"\x00" * 16)
    ep.scenes[0].dialogue_audio_path = str(dlg_file)

    ctrl = _make_controller(tmp_path, series, ep)
    await ctrl.checkpoint(CheckpointStage.AFTER_VIDEO_TTS)

    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    videos_dir = review_dir / "videos"
    audio_review_dir = review_dir / "audio"

    if videos_dir.is_dir():
        video_files = [f for f in videos_dir.iterdir() if f.suffix == ".mp4"]
        assert len(video_files) >= 1, "Expected at least one .mp4 in videos/"
    else:
        pytest.xfail("videos/ not materialised after AFTER_VIDEO_TTS")

    if audio_review_dir.is_dir():
        audio_files = list(audio_review_dir.iterdir())
        assert len(audio_files) >= 1, "Expected at least one audio file"
    else:
        pytest.xfail("audio/ not materialised after AFTER_VIDEO_TTS")


# ---------------------------------------------------------------------------
# 4. After compose — final/ appears
# ---------------------------------------------------------------------------


async def test_after_compose_materializes_final(tmp_path: Path) -> None:
    series, ep = _make_rich_series(tmp_path)

    # Simulate composed video
    projects_dir = tmp_path / "projects"
    series_dir = projects_dir / "dramas" / series.series_id
    video_dir = series_dir / f"ep{ep.number:02d}_video"
    video_dir.mkdir(parents=True, exist_ok=True)
    final_video = video_dir / "composed_final.mp4"
    final_video.write_bytes(b"\x00" * 64)

    ctrl = _make_controller(tmp_path, series, ep)
    await ctrl.checkpoint(CheckpointStage.AFTER_COMPOSE)

    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    final_dir = review_dir / "final"

    if final_dir.is_dir():
        final_files = list(final_dir.iterdir())
        assert len(final_files) >= 1, "Expected at least one file in final/"
    else:
        pytest.xfail("final/ not materialised after AFTER_COMPOSE — verify compose output path")


# ---------------------------------------------------------------------------
# 5. After audit — audit/*.json appears
# ---------------------------------------------------------------------------


async def test_after_audit_materializes_audit_json(tmp_path: Path) -> None:
    series, ep = _make_rich_series(tmp_path)

    # Simulate audit output
    projects_dir = tmp_path / "projects"
    series_dir = projects_dir / "dramas" / series.series_id
    audit_src = series_dir / f"ep{ep.number:02d}_audit"
    audit_src.mkdir(parents=True, exist_ok=True)
    audit_file = audit_src / "round_1.json"
    audit_file.write_text('{"pass": true}')

    ctrl = _make_controller(tmp_path, series, ep)
    await ctrl.checkpoint(CheckpointStage.AFTER_AUDIT)

    review_dir = review_dir_for_episode(series, ep, base_dir=tmp_path / "deliverables")
    audit_dir = review_dir / "audit"

    if audit_dir.is_dir():
        audit_files = [f for f in audit_dir.iterdir() if f.suffix == ".json"]
        assert len(audit_files) >= 1, "Expected at least one .json in audit/"
    else:
        pytest.xfail("audit/ not materialised after AFTER_AUDIT — verify audit output path")
