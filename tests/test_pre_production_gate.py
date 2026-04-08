"""Tests for the pre-production gate — 7-item checklist before generation."""

from __future__ import annotations

import pytest

from videoclaw.drama.models import (
    Character,
    ConsistencyManifest,
    DramaScene,
    DramaSeries,
    Episode,
    ShotScale,
)
from videoclaw.drama.pre_production_gate import (
    GateResult,
    check_pre_production_gate,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal valid fixtures
# ---------------------------------------------------------------------------

def _make_character(name: str = "Alice", num_refs: int = 4) -> Character:
    """Return a character with *num_refs* reference images."""
    return Character(
        name=name,
        description="A 26-year-old detective with sharp eyes",
        visual_prompt="Tall woman, auburn hair, green eyes",
        reference_images=[f"ref_{name}_{i}.png" for i in range(num_refs)],
    )


def _make_scene(
    scene_id: str = "ep01_s01",
    visual_prompt: str = "A dimly lit office at night",
    shot_scale: ShotScale | None = ShotScale.MEDIUM,
    camera_movement: str = "static",
    scene_group: str = "A",
) -> DramaScene:
    """Return a minimal valid DramaScene."""
    return DramaScene(
        scene_id=scene_id,
        visual_prompt=visual_prompt,
        shot_scale=shot_scale,
        camera_movement=camera_movement,
        scene_group=scene_group,
        characters_present=["Alice"],
    )


def _make_series(**overrides) -> DramaSeries:
    defaults = dict(
        title="Test Drama",
        genre="romance",
        language="en",
        aspect_ratio="9:16",
        characters=[_make_character("Alice"), _make_character("Bob")],
        consistency_manifest=ConsistencyManifest(
            scene_references={"A": "scenes/a.png"},
        ),
    )
    defaults.update(overrides)
    return DramaSeries(**defaults)


def _make_episode(**overrides) -> Episode:
    defaults = dict(
        number=1,
        title="Pilot",
        opening_hook="A shocking discovery changes everything",
        scenes=[_make_scene("ep01_s01"), _make_scene("ep01_s02")],
    )
    defaults.update(overrides)
    return Episode(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreProductionGate:

    def test_fully_prepared_episode_passes(self):
        """A well-prepared series+episode should pass all 7 checks."""
        series = _make_series()
        episode = _make_episode()
        result = check_pre_production_gate(series, episode)
        assert result.passed is True
        assert len(result.items) == 7
        assert all(item.passed for item in result.items)
        assert "All 7" in result.summary()

    def test_empty_episode_fails(self):
        """An episode with no scenes fails check 1."""
        series = _make_series()
        episode = _make_episode(scenes=[])
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item1 = result.items[0]
        assert item1.name == "Episode has scenes"
        assert item1.passed is False
        assert "No scenes" in item1.violations[0]

    def test_missing_character_refs_fails(self):
        """A character with 0 reference images fails check 2."""
        char_no_refs = Character(
            name="NoRef",
            description="A mysterious figure",
            visual_prompt="Shadowy figure",
            reference_images=[],
        )
        series = _make_series(characters=[char_no_refs])
        episode = _make_episode()
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item2 = result.items[1]
        assert item2.name == "Character reference images (≥4/character)"
        assert item2.passed is False
        assert "'NoRef' has 0 reference images" in item2.violations[0]

    def test_insufficient_refs_fails(self):
        """A character with only 1 reference image fails check 2."""
        char_one_ref = Character(
            name="OneRef",
            description="A lone wolf",
            visual_prompt="Man in black",
            reference_images=["ref_0.png"],
        )
        series = _make_series(characters=[char_one_ref])
        episode = _make_episode()
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item2 = result.items[1]
        assert item2.passed is False
        assert "'OneRef' has 1 reference images" in item2.violations[0]

    def test_incomplete_storyboard_fails(self):
        """A scene missing shot_scale fails check 4."""
        bad_scene = _make_scene(shot_scale=None)
        series = _make_series()
        episode = _make_episode(scenes=[bad_scene])
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item4 = result.items[3]
        assert item4.name == "Storyboard completeness"
        assert item4.passed is False
        assert "shot_scale" in item4.violations[0]

    def test_unknown_camera_movement_fails(self):
        """A scene with an unrecognised camera_movement fails check 5."""
        bad_scene = _make_scene(camera_movement="unknown_zoom_blast")
        series = _make_series()
        episode = _make_episode(scenes=[bad_scene])
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item5 = result.items[4]
        assert item5.name == "Camera movement vocabulary"
        assert item5.passed is False
        assert "unknown_zoom_blast" in item5.violations[0]

    def test_wrong_aspect_ratio_fails(self):
        """A series with 16:9 aspect ratio fails check 6."""
        series = _make_series(aspect_ratio="16:9")
        episode = _make_episode()
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item6 = result.items[5]
        assert item6.name == "Aspect ratio is 9:16"
        assert item6.passed is False
        assert "16:9" in item6.violations[0]

    def test_missing_opening_hook_fails(self):
        """An episode with no opening_hook fails check 7."""
        series = _make_series()
        episode = _make_episode(opening_hook="")
        result = check_pre_production_gate(series, episode)
        assert result.passed is False
        item7 = result.items[6]
        assert item7.name == "Episode opening_hook defined"
        assert item7.passed is False
        assert "Missing opening_hook" in item7.violations[0]

    def test_strict_mode_raises(self):
        """When strict=True and checks fail, ValueError is raised."""
        series = _make_series()
        episode = _make_episode(scenes=[])  # fails check 1
        with pytest.raises(ValueError, match="Pre-production gate failed"):
            check_pre_production_gate(series, episode, strict=True)

    def test_summary_format(self):
        """Summary output should be human-readable multi-line text."""
        series = _make_series(aspect_ratio="16:9")
        episode = _make_episode(opening_hook="")
        result = check_pre_production_gate(series, episode)
        summary = result.summary()
        # Should contain the count line
        assert "checks failed:" in summary
        # Should list specific failures
        assert "Aspect ratio" in summary
        assert "opening_hook" in summary
        # Each failure line should start with the cross mark
        lines = summary.strip().split("\n")
        failure_lines = [l for l in lines if l.strip().startswith("✗")]
        assert len(failure_lines) >= 2
