"""Pre-production gate — 7-item checklist that must pass before generation starts.

Blocks ``claw drama run`` unless all production prerequisites are satisfied.
Each check returns violation strings (empty = passed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from videoclaw.drama.models import DramaSeries, Episode

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GateItem:
    """A single checklist item with pass/fail status."""
    name: str
    passed: bool = True
    violations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GateResult:
    """Result of the pre-production gate check."""
    passed: bool = True
    items: list[GateItem] = field(default_factory=list)

    def summary(self) -> str:
        failed = [i for i in self.items if not i.passed]
        if not failed:
            return "All 7 pre-production checks passed"
        lines = [f"{len(failed)}/{len(self.items)} checks failed:"]
        for item in failed:
            lines.append(f"  ✗ {item.name}: {'; '.join(item.violations)}")
        return "\n".join(lines)


def check_pre_production_gate(
    series: DramaSeries,
    episode: Episode,
    *,
    strict: bool = False,
) -> GateResult:
    """Run the 7-item pre-production checklist.

    When *strict* is True, any failing item raises ValueError.
    When *strict* is False (default), warnings are logged but generation proceeds.
    """
    result = GateResult()

    # 1. Episode scenes non-empty
    item1 = GateItem(name="Episode has scenes")
    if not episode.scenes:
        item1.passed = False
        item1.violations.append("No scenes in episode")
    result.items.append(item1)

    # 2. Character reference images >= 4 per character
    item2 = GateItem(name="Character reference images (≥4/character)")
    for char in series.characters:
        refs = getattr(char, "reference_images", None) or []
        if len(refs) < 4:
            item2.passed = False
            item2.violations.append(
                f"'{char.name}' has {len(refs)} reference images (need ≥4)"
            )
    result.items.append(item2)

    # 3. Scene/background references cover all locations
    item3 = GateItem(name="Scene references cover all locations")
    manifest = getattr(series, "consistency_manifest", None)
    scene_refs: dict[str, str] = {}
    if manifest:
        scene_refs = getattr(manifest, "scene_references", {}) or {}
    episode_locations: set[str] = set()
    for scene in episode.scenes:
        loc = getattr(scene, "scene_group", "") or getattr(scene, "time_of_day", "")
        if loc:
            episode_locations.add(loc)
    missing_locs = episode_locations - set(scene_refs.keys())
    if missing_locs and episode_locations:
        item3.passed = False
        item3.violations.append(f"Missing scene refs for: {', '.join(sorted(missing_locs))}")
    result.items.append(item3)

    # 4. Every scene has scene_id + visual_prompt + shot_scale
    item4 = GateItem(name="Storyboard completeness")
    for scene in episode.scenes:
        missing_fields = []
        if not scene.scene_id:
            missing_fields.append("scene_id")
        if not scene.visual_prompt:
            missing_fields.append("visual_prompt")
        if not scene.shot_scale:
            missing_fields.append("shot_scale")
        if missing_fields:
            item4.passed = False
            item4.violations.append(
                f"Scene '{scene.scene_id or '?'}' missing: {', '.join(missing_fields)}"
            )
    result.items.append(item4)

    # 5. camera_movement is a valid vocabulary term
    from videoclaw.drama.prompt_enhancer import CAMERA_MOVEMENT_LABELS
    item5 = GateItem(name="Camera movement vocabulary")
    for scene in episode.scenes:
        cm = scene.camera_movement or ""
        if cm and cm not in CAMERA_MOVEMENT_LABELS:
            item5.passed = False
            item5.violations.append(
                f"Scene '{scene.scene_id}': unknown camera_movement '{cm}'"
            )
    result.items.append(item5)

    # 6. Series aspect_ratio is 9:16
    item6 = GateItem(name="Aspect ratio is 9:16")
    ar = getattr(series, "aspect_ratio", "9:16") or "9:16"
    if ar != "9:16":
        item6.passed = False
        item6.violations.append(f"aspect_ratio='{ar}' (must be 9:16 for TikTok safe zone)")
    result.items.append(item6)

    # 7. Episode opening_hook is non-empty
    item7 = GateItem(name="Episode opening_hook defined")
    if not episode.opening_hook:
        item7.passed = False
        item7.violations.append("Missing opening_hook (needed for cover frame)")
    result.items.append(item7)

    # Compute overall result
    result.passed = all(item.passed for item in result.items)

    if not result.passed:
        if strict:
            raise ValueError(f"Pre-production gate failed:\n{result.summary()}")
        logger.warning("Pre-production gate warnings:\n%s", result.summary())

    return result
