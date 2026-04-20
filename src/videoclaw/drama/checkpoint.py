"""Human checkpoint / breakpoint system for the drama production pipeline.

Provides structured breakpoints at critical production nodes so humans can:

- **Review** generated assets (turnaround sheets, video clips, audit reports)
- **Control** the pipeline (continue, redo a stage, or abort)
- **Resume** from any saved checkpoint
- **Audit** the full intermediate asset trail after automated runs

Every checkpoint is persisted to disk regardless of mode (interactive or
automated), ensuring a complete audit trail.

At each checkpoint a **semantic review directory** is created with human-
readable file names derived from scene descriptions.  Symlinks point back
to the actual generated assets so no disk space is wasted::

    {projects_dir}/dramas/{series_id}/
        review/
            ep01_after_generation/
                characters/
                    Lucian_turnaround.png → ../../characters/...
                videos/
                    s01_poolside_arrival.mp4 → ../../ep01_video/...
                prompts/
                    s01_poolside_arrival.txt
                audit/
                    round_1.json
        checkpoints/
            ep01_after_generation_{id}.json
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from videoclaw.utils import _now_iso

if TYPE_CHECKING:
    from videoclaw.core.events import EventBus
    from videoclaw.core.planner import DAG
    from videoclaw.core.state import ProjectState
    from videoclaw.drama.models import DramaManager, DramaSeries, Episode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 40) -> str:
    """Convert free-form text to a filesystem-safe slug.

    >>> _slugify("Poolside  Confrontation!")
    'poolside_confrontation'
    """
    # Lowercase, keep only alphanumerics / spaces / underscores / hyphens
    s = re.sub(r"[^\w\s-]", "", text.lower().strip())
    s = re.sub(r"[\s-]+", "_", s)
    return s[:max_len].rstrip("_")


def _scene_slug(index: int, description: str) -> str:
    """Build a semantic scene file name: ``s01_poolside_arrival``."""
    slug = _slugify(description, max_len=35)
    if not slug:
        slug = "scene"
    return f"s{index + 1:02d}_{slug}"


def _normalize_char_name(name: str) -> str:
    """Normalize a character name to a case-insensitive filename slug.

    Equivalent to ``_slugify`` for typical names; additionally strips
    leading underscores so names with leading punctuation
    (``"!Ivy"`` → ``"ivy"``) match cleanly across episode boundaries.
    """
    return _slugify(name).strip("_")


def _episode_locations(episode: Episode, scene_ref_keys: set[str]) -> set[str]:
    """Extract location keys actually referenced in an episode's scenes.

    DramaScene has no location field — match scene.description against
    known scene_reference keys via case-insensitive whole-word regex.
    Whole-word matching avoids false positives like ``"carpool"`` →
    ``"pool"`` (Audit A9).
    """
    descriptions = " ".join(s.description for s in episode.scenes)
    matched: set[str] = set()
    for key in scene_ref_keys:
        pattern = r"\b" + re.escape(key) + r"\b"
        if re.search(pattern, descriptions, re.IGNORECASE):
            matched.add(key)
    return matched


def _relative_symlink_to_series_root(
    src_in_series_root: Path,
    dst_in_episode_dir: Path,
) -> None:
    """Create a relative symlink ``dst → ../../<rel-path-to-src>``.

    Used so episode-level filtered subsets (``characters/``, ``scenes/``)
    point back to the series-root truth via portable relative paths.

    **Audit-safety (A4):** if ``dst`` is a regular file (not a symlink),
    a human placed it during a checkpoint pause. Preserve as
    ``<dst>.user.bak`` and log a warning — never silently delete.
    """
    dst_in_episode_dir.parent.mkdir(parents=True, exist_ok=True)

    if dst_in_episode_dir.is_symlink():
        dst_in_episode_dir.unlink()
    elif dst_in_episode_dir.exists():
        backup = dst_in_episode_dir.with_name(dst_in_episode_dir.name + ".user.bak")
        dst_in_episode_dir.rename(backup)
        logger.warning(
            "Preserved user file at %s -> %s (rebuilding symlink to series root)",
            dst_in_episode_dir,
            backup,
        )

    rel = os.path.relpath(src_in_series_root, dst_in_episode_dir.parent)
    dst_in_episode_dir.symlink_to(rel)


def _episode_status(episode: Episode, ep_dir: Path) -> str:
    """Derive a human-friendly episode status.

    Terminal enum states (``COMPLETED`` / ``FAILED``) are authoritative
    and override disk evidence (Audit A7) — useful when an episode is
    marked complete but its review dir hasn't been built yet.

    For non-terminal enum states, derive from filesystem evidence with
    most-complete-wins precedence:
        composed > audited > generating > pending
    """
    from videoclaw.drama.models import EpisodeStatus

    if episode.status == EpisodeStatus.COMPLETED:
        return "completed"
    if episode.status == EpisodeStatus.FAILED:
        return "failed"

    final_dir = ep_dir / "final"
    if final_dir.is_dir() and any(final_dir.iterdir()):
        return "composed"
    audit_dir = ep_dir / "audit"
    videos_dir = ep_dir / "videos"
    has_videos = videos_dir.is_dir() and any(videos_dir.iterdir())
    has_audit = audit_dir.is_dir() and any(audit_dir.iterdir())
    if has_videos and has_audit:
        return "audited"
    if has_videos:
        return "generating"
    return "pending"


def review_dir_for_episode(
    series: DramaSeries,
    episode: Episode,
    base_dir: Path,
) -> Path:
    """Compute the cumulative review directory for an episode.

    The review directory lives under *base_dir* (typically
    ``get_config().deliverables_dir`` → ``docs/deliverables/`` at the
    project root — the most visible location for producers).  No UUIDs
    in the path.

    Layout::

        {base_dir}/{series_slug}/ep{NN}_{ep_slug}/

    ``base_dir`` is **required** — no silent fallback to config.  This
    prevents test fixtures from leaking into the production deliverables
    directory when callers forget to pass it.
    """
    series_root = _series_root_for(series, base_dir)
    ep_num = episode.number
    ep_slug = _slugify(episode.title, max_len=20)
    ep_dir = f"ep{ep_num:02d}"
    if ep_slug:
        ep_dir += f"_{ep_slug}"
    return series_root / ep_dir


def _series_root_for(series: DramaSeries, deliverables_dir: Path) -> Path:
    """Return the deliverables directory for a series.

    Single source of truth for the ``<deliverables_dir>/<series_slug>/``
    path. All series-view code derives its location from this helper to
    prevent drift between :func:`review_dir_for_episode` and the
    series-root paths used by ``_SERIES.md`` and ep-level filtered
    symlinks (Audit A8).
    """
    series_slug = _slugify(series.title) or series.series_id[:8]
    return deliverables_dir / series_slug


# Scale labels shared between standalone generator and controller
_SCALE_LABELS: dict[str, str] = {
    "close_up": "特写",
    "medium_close": "中近景",
    "medium": "中景",
    "wide": "全景",
    "extreme_wide": "远景",
}


def generate_storyboard_md(
    series: DramaSeries,
    episode: Episode,
    review_dir: Path,
) -> Path:
    """Generate ``storyboard.md`` into the review directory.

    Callable standalone — no :class:`CheckpointController` needed.
    Returns the path to the written ``storyboard.md``.

    ``review_dir`` is **required**.  Callers must compute the target
    directory explicitly (typically via :func:`review_dir_for_episode`).
    This prevents silent writes to a config-driven default.
    """
    review_dir.mkdir(parents=True, exist_ok=True)

    scenes = episode.scenes
    if not scenes:
        # Write an empty placeholder so the file always exists
        p = review_dir / "storyboard.md"
        p.write_text(f"# {series.title} — EP{episode.number:02d} 分镜表\n\n> 暂无分镜数据\n", encoding="utf-8")
        return p

    lines: list[str] = []
    ep_num = episode.number

    lines.append(f"# {series.title} — EP{ep_num:02d} 分镜表\n")
    lines.append(
        f"> {len(scenes)} scenes | "
        f"预估总时长 ~{sum(s.duration_seconds for s in scenes):.0f}s | "
        f"{series.aspect_ratio} | {series.model_id}\n"
    )

    # ---- 制作分析 ----
    lines.append("## 制作分析\n")
    _write_duration_analysis(lines, scenes)
    _write_scale_distribution(lines, scenes)
    _write_character_screentime(lines, scenes)

    # ---- 分镜详情 ----
    lines.append("## 分镜详情\n")
    _write_scene_details(lines, scenes)

    # ---- 台词逐字稿 (subtitle source of truth) ----
    _write_dialogue_transcript(lines, scenes)

    p = review_dir / "storyboard.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def build_review_dir(
    series: DramaSeries,
    episode: Episode,
    *,
    deliverables_dir: Path,
    projects_dir: Path,
) -> Path:
    """Build / refresh the complete review directory for an episode.

    This is the **stage-agnostic** entry point shared by
    :class:`CheckpointController` (per-stage incremental updates) and
    ``claw drama export`` (one-shot rebuild).  Both produce the exact
    same on-disk layout so auditors never see two conflicting shapes.

    Layout::

        {deliverables_dir}/{drama_slug}/{episode_slug}/
        ├── storyboard.md
        ├── characters/   (lazy)
        ├── scenes/       (lazy)
        ├── videos/       (lazy)
        ├── audio/        (lazy)
        ├── audit/        (lazy)
        └── final/        (lazy)

    The function is idempotent and non-destructive — existing files are
    either preserved or versioned (``{stem}_v{N}{ext}``) per the rules
    in :func:`_safe_symlink`.

    Returns the review directory path.
    """
    # Series-root must be populated BEFORE ep-filtered symlinks resolve
    # (Audit A9). Full rebuild here — cheap, idempotent, keeps the
    # function self-contained for direct callers like drama_export.
    series_root = build_series_view(
        series, deliverables_dir=deliverables_dir, projects_dir=projects_dir
    )

    review_dir = review_dir_for_episode(series, episode, base_dir=deliverables_dir)
    review_dir.mkdir(parents=True, exist_ok=True)

    series_dir = projects_dir / "dramas" / series.series_id

    _update_characters_dir(
        series,
        review_dir / "characters",
        episode=episode,
        series_root=series_root,
    )
    _update_scenes_dir(
        series,
        review_dir / "scenes",
        episode=episode,
        series_root=series_root,
    )
    _update_videos_dir(series, episode, review_dir / "videos", projects_dir)
    _update_audio_dir(series, episode, review_dir / "audio")
    _update_audit_dir(episode, review_dir / "audit", series_dir)
    _update_final_dir(episode, review_dir / "final", series_dir)

    generate_storyboard_md(series, episode, review_dir=review_dir)
    return review_dir


# ---------------------------------------------------------------------------
# Module-level subdirectory updaters
#
# These are the atoms used by both CheckpointController and build_review_dir.
# Each updater must ``mkdir(parents=True, exist_ok=True)`` *only* before
# writing the first file / symlink, so empty subdirectories never appear.
# ---------------------------------------------------------------------------


def _update_characters_dir(
    series: DramaSeries,
    chars_dir: Path,
    *,
    episode: Episode | None = None,
    series_root: Path | None = None,
) -> None:
    """Materialize character turnarounds into ``chars_dir``.

    Two modes:

    - ``episode is None`` — series-level source-of-truth mode: write all
      ``series.characters`` with their projects-side ``reference_image``
      as the symlink target (legacy default).
    - ``episode`` provided — episode-filtered mode: write only characters
      appearing in ``episode.scenes[*].characters_present``; the symlink
      target is the series-level real file at
      ``<series_root>/characters/<name>_turnaround.<ext>`` via a relative
      chain (``../../characters/...``). ``series_root`` is required.
    """
    if episode is None:
        for char in series.characters:
            if char.reference_image:
                src = Path(char.reference_image)
                if src.exists():
                    chars_dir.mkdir(parents=True, exist_ok=True)
                    name = f"{_normalize_char_name(char.name)}_turnaround{src.suffix}"
                    _safe_symlink(src, chars_dir / name)
            url = getattr(char, "reference_image_url", None)
            if url:
                chars_dir.mkdir(parents=True, exist_ok=True)
                url_file = chars_dir / f"{_normalize_char_name(char.name)}_url.txt"
                url_file.write_text(url, encoding="utf-8")
        return

    if series_root is None:
        raise ValueError("series_root is required when episode is provided")

    series_chars = {_normalize_char_name(c.name): c for c in series.characters}
    present: set[str] = set()
    for sc in episode.scenes:
        for raw_name in sc.characters_present:
            norm = _normalize_char_name(raw_name)
            if norm in series_chars:
                present.add(norm)
            else:
                logger.warning(
                    "Character %r in ep%d not found in series.characters",
                    raw_name,
                    episode.number,
                )

    for norm in sorted(present):
        char = series_chars[norm]
        if not char.reference_image:
            continue
        ext = Path(char.reference_image).suffix
        src_in_root = series_root / "characters" / f"{norm}_turnaround{ext}"
        if not src_in_root.exists():
            continue
        dst = chars_dir / f"{norm}_turnaround{ext}"
        _relative_symlink_to_series_root(src_in_root, dst)


def _update_series_characters_dir(series: DramaSeries, chars_dir: Path) -> None:
    """Series-level source-of-truth for character turnarounds + URLs.

    Iterates *all* ``series.characters`` and materializes each turnaround
    into ``chars_dir`` (the series root). Episode-level filtered subsets
    (added by Task 10/12) symlink back here via
    :func:`_relative_symlink_to_series_root`.

    Uses :func:`_normalize_char_name` (vs ``_slugify``) for filename
    consistency with the per-episode filter logic that joins on
    ``Scene.characters_present``.
    """
    for char in series.characters:
        if char.reference_image:
            src = Path(char.reference_image)
            if src.exists():
                chars_dir.mkdir(parents=True, exist_ok=True)
                name = f"{_normalize_char_name(char.name)}_turnaround{src.suffix}"
                _safe_symlink(src, chars_dir / name)
        url = getattr(char, "reference_image_url", None)
        if url:
            chars_dir.mkdir(parents=True, exist_ok=True)
            url_file = chars_dir / f"{_normalize_char_name(char.name)}_url.txt"
            url_file.write_text(url, encoding="utf-8")


def _update_series_scenes_dir(series: DramaSeries, scenes_dir: Path) -> None:
    """Series-level source-of-truth for scene/location reference images.

    Episode-level filtered subsets (added by Task 11/12) symlink back here.
    """
    manifest = getattr(series, "consistency_manifest", None)
    refs = getattr(manifest, "scene_references", None) or {}
    for loc_name, ref_path in refs.items():
        if not ref_path:
            continue
        src = Path(ref_path)
        if not src.exists():
            continue
        scenes_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(loc_name, max_len=40) or "location"
        dst = scenes_dir / f"{slug}{src.suffix}"
        _safe_symlink(src, dst)


_SERIES_MD_TIMESTAMP_LINE_PREFIX = "| 最后更新 |"


def _render_series_md(series: DramaSeries, series_root: Path) -> str:
    """Render the ``_SERIES.md`` content from in-memory series state.

    Pure function — deterministic for the same input. ``series_root`` is
    used only to derive each episode's filesystem state for status
    inference. Inline image paths are relative to ``_SERIES.md`` itself,
    so the file is portable across drama_slug renames.

    The "最后更新" line carries a wall-clock timestamp; callers that want
    the no-write-if-unchanged guarantee must strip this line before
    comparison (see :func:`_write_series_md`, Audit A5).
    """
    from datetime import datetime, timezone

    deliverables_dir = series_root.parent
    lines: list[str] = []
    lines.append(f"# {series.title}\n")

    # 1. Metadata
    audited = 0
    generating = 0
    for ep in series.episodes:
        ep_dir = review_dir_for_episode(series, ep, deliverables_dir)
        st = _episode_status(ep, ep_dir)
        if st in ("audited", "composed", "completed"):
            audited += 1
        elif st == "generating":
            generating += 1
    pending = len(series.episodes) - audited - generating
    total_dur = sum(ep.duration_seconds for ep in series.episodes)
    total_cost = sum(ep.cost for ep in series.episodes)

    lines.append("## 元数据\n")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| Series ID | {series.series_id} |")
    lines.append(
        f"| 集数 | {len(series.episodes)} "
        f"(audited {audited} / generating {generating} / pending {pending}) |"
    )
    lines.append(f"| 累计成本 | ${total_cost:.2f} |")
    lines.append(f"| 累计预估时长 | {total_dur:.0f}s |")
    # Audit A9: spec promised 720p; series has no resolution field — flag it
    lines.append(
        f"| 视频规格 | {series.model_id} · {series.aspect_ratio} · (分辨率: 未配置) |"
    )
    lines.append(
        f"{_SERIES_MD_TIMESTAMP_LINE_PREFIX} {datetime.now(timezone.utc).isoformat()} |"
    )
    lines.append("")

    # 2. Characters
    if series.characters:
        lines.append(f"## 角色 ({len(series.characters)})\n")
        lines.append("| 预览 | 名字 | 身份 | URL |")
        lines.append("|---|---|---|---|")
        for char in series.characters:
            slug = _normalize_char_name(char.name)
            preview = ""
            if char.reference_image:
                ext = Path(char.reference_image).suffix or ".png"
                preview = f"![](characters/{slug}_turnaround{ext})"
            url_cell = "—"
            if getattr(char, "reference_image_url", None):
                url_cell = f"[link](characters/{slug}_url.txt)"
            lines.append(
                f"| {preview} | {char.name} | {char.description or '—'} | {url_cell} |"
            )
        lines.append("")

    # 3. Scenes
    manifest = getattr(series, "consistency_manifest", None)
    refs = getattr(manifest, "scene_references", None) or {}
    if refs:
        appearance: dict[str, list[int]] = {}
        ref_keys = set(refs.keys())
        for ep in series.episodes:
            for loc in _episode_locations(ep, ref_keys):
                appearance.setdefault(loc, []).append(ep.number)

        lines.append(f"## 场景 ({len(refs)})\n")
        lines.append("| 预览 | location | 出场集 |")
        lines.append("|---|---|---|")
        for loc_name in sorted(refs):
            ref_path = refs[loc_name]
            ext = Path(ref_path).suffix or ".png"
            slug = _slugify(loc_name, max_len=40) or "location"
            preview = f"![](scenes/{slug}{ext})"
            eps = appearance.get(loc_name, [])
            ep_cell = ", ".join(f"EP{n:02d}" for n in sorted(eps)) or "—"
            lines.append(f"| {preview} | {loc_name} | {ep_cell} |")
        lines.append("")

    # 4. Episodes
    lines.append("## 集列表\n")
    if not series.episodes:
        lines.append("> 暂无 episode\n")
    else:
        lines.append("| # | 标题 | 状态 | 时长 | 成本 | 入口 |")
        lines.append("|---|---|---|---|---|---|")
        status_emoji = {
            "audited": "✅", "composed": "✅", "completed": "✅",
            "generating": "⏳", "pending": "⏸", "failed": "❌",
        }
        for ep in sorted(series.episodes, key=lambda e: e.number):
            ep_dir = review_dir_for_episode(series, ep, deliverables_dir)
            ep_dirname = ep_dir.name
            status = _episode_status(ep, ep_dir)
            emoji = status_emoji.get(status, "•")
            link = f"[{ep_dirname}/]({ep_dirname}/)"
            lines.append(
                f"| {ep.number:02d} | {ep.title or '—'} | {emoji} {status} "
                f"| {ep.duration_seconds:.0f}s | ${ep.cost:.2f} | {link} |"
            )
        lines.append("")

    # 5. Logline
    if series.episodes:
        lines.append("## Logline\n")
        for ep in sorted(series.episodes, key=lambda e: e.number):
            line = ep.synopsis or ep.title or "(无 synopsis)"
            title_part = (" " + ep.title) if ep.title else ""
            lines.append(f"- **EP{ep.number:02d}{title_part}** — {line}")
        lines.append("")

    return "\n".join(lines)


def _strip_timestamp(md: str) -> str:
    """Drop the volatile timestamp line for content-equality comparison."""
    return "\n".join(
        ln for ln in md.splitlines()
        if not ln.startswith(_SERIES_MD_TIMESTAMP_LINE_PREFIX)
    )


def _write_series_md(series: DramaSeries, series_root: Path) -> Path:
    """Write ``_SERIES.md`` if (and only if) the rendered content changed.

    Audit A5: the rendered MD includes a wall-clock timestamp that would
    otherwise force a rewrite on every checkpoint. Compare the
    timestamp-stripped form to the existing file's timestamp-stripped
    form; only write if they differ. This preserves mtime when the
    series state hasn't actually changed.
    """
    series_root.mkdir(parents=True, exist_ok=True)
    path = series_root / "_SERIES.md"
    new_md = _render_series_md(series, series_root)

    if path.exists():
        old_md = path.read_text(encoding="utf-8")
        if _strip_timestamp(old_md) == _strip_timestamp(new_md):
            return path

    path.write_text(new_md, encoding="utf-8")
    return path


_SERIES_STAGE_WORK: dict[str, set[str]] = {
    "after_design": {"chars", "scenes", "md"},
    "after_refresh": {"chars", "scenes", "md"},
    "after_storyboard": {"md"},
    "after_video_tts": {"md"},
    "after_generation": {"md"},
    "after_compose": {"md"},
    "after_audit": {"md"},
}


def build_series_view(
    series: DramaSeries,
    *,
    deliverables_dir: Path,
    projects_dir: Path,  # noqa: ARG001 — reserved for future asset resolution
    work: set[str] | None = None,
) -> Path:
    """Build / refresh the series-level view at ``deliverables_dir/<slug>/``.

    ``work`` is a subset of ``{"chars", "scenes", "md"}``. ``None`` = full
    rebuild (``claw drama series-view``, ``claw drama export``, tests).
    ``CheckpointController`` passes a stage-specific subset derived from
    :data:`_SERIES_STAGE_WORK` to skip unnecessary I/O.
    """
    series_root = _series_root_for(series, deliverables_dir)
    series_root.mkdir(parents=True, exist_ok=True)
    todo = work if work is not None else {"chars", "scenes", "md"}
    if "chars" in todo:
        _update_series_characters_dir(series, series_root / "characters")
    if "scenes" in todo:
        _update_series_scenes_dir(series, series_root / "scenes")
    if "md" in todo:
        _write_series_md(series, series_root)
    return series_root


def _update_scenes_dir(
    series: DramaSeries,
    scenes_dir: Path,
    *,
    episode: Episode | None = None,
    series_root: Path | None = None,
) -> None:
    """Symlink scene/location reference images (景别图 / 场景参考图).

    Two modes (mirror of :func:`_update_characters_dir`):

    - ``episode is None`` — series-level source-of-truth mode: write all
      ``consistency_manifest.scene_references`` entries.
    - ``episode`` provided — episode-filtered mode: write only refs whose
      location key appears in ``episode.scenes[*].description`` (whole-
      word match via :func:`_episode_locations`), target =
      ``../../scenes/<slug>.<ext>`` in ``series_root``. Requires
      ``series_root``.
    """
    manifest = getattr(series, "consistency_manifest", None)
    refs = getattr(manifest, "scene_references", None) or {}

    if episode is None:
        for loc_name, ref_path in refs.items():
            if not ref_path:
                continue
            src = Path(ref_path)
            if not src.exists():
                continue
            scenes_dir.mkdir(parents=True, exist_ok=True)
            slug = _slugify(loc_name, max_len=40) or "location"
            dst = scenes_dir / f"{slug}{src.suffix}"
            _safe_symlink(src, dst)
        return

    if series_root is None:
        raise ValueError("series_root is required when episode is provided")

    appearing = _episode_locations(episode, set(refs.keys()))
    for loc_name in sorted(appearing):
        ref_path = refs.get(loc_name)
        if not ref_path:
            continue
        ext = Path(ref_path).suffix
        slug = _slugify(loc_name, max_len=40) or "location"
        src_in_root = series_root / "scenes" / f"{slug}{ext}"
        if not src_in_root.exists():
            continue
        dst = scenes_dir / f"{slug}{ext}"
        _relative_symlink_to_series_root(src_in_root, dst)


def _update_videos_dir(
    series: DramaSeries,
    episode: Episode,
    videos_dir: Path,
    projects_dir: Path,
) -> None:
    for idx, scene in enumerate(episode.scenes):
        if scene.video_asset_path:
            src = Path(scene.video_asset_path)
            if src.exists():
                videos_dir.mkdir(parents=True, exist_ok=True)
                slug = _scene_slug(idx, scene.description)
                dst = videos_dir / f"{slug}{src.suffix}"
                _safe_symlink(src, dst, keep_versions=True)

    # Also check project shots dir for video files not yet in scene state
    if episode.project_id:
        shots_dir = projects_dir / episode.project_id / "shots"
        if shots_dir.is_dir():
            scene_map = {s.scene_id: (i, s) for i, s in enumerate(episode.scenes)}
            for f in sorted(shots_dir.iterdir()):
                if f.suffix.lower() != ".mp4":
                    continue
                for sid, (i, sc) in scene_map.items():
                    if sid in f.name:
                        videos_dir.mkdir(parents=True, exist_ok=True)
                        slug = _scene_slug(i, sc.description)
                        dst = videos_dir / f"{slug}{f.suffix}"
                        if not (dst.exists() or dst.is_symlink()):
                            _safe_symlink(f, dst, keep_versions=True)
                        break


def _update_audio_dir(
    series: DramaSeries,
    episode: Episode,
    audio_dir: Path,
) -> None:
    for idx, scene in enumerate(episode.scenes):
        slug = _scene_slug(idx, scene.description)
        if scene.dialogue_audio_path:
            src = Path(scene.dialogue_audio_path)
            if src.exists():
                audio_dir.mkdir(parents=True, exist_ok=True)
                _safe_symlink(src, audio_dir / f"{slug}_dialogue{src.suffix}", keep_versions=True)
        if scene.narration_audio_path:
            src = Path(scene.narration_audio_path)
            if src.exists():
                audio_dir.mkdir(parents=True, exist_ok=True)
                _safe_symlink(src, audio_dir / f"{slug}_narration{src.suffix}", keep_versions=True)


def _update_audit_dir(
    episode: Episode,
    audit_dir: Path,
    series_dir: Path,
) -> None:
    ep_prefix = f"ep{episode.number:02d}"
    audit_src = series_dir / f"{ep_prefix}_audit"
    if audit_src.is_dir():
        for f in sorted(audit_src.iterdir()):
            if f.suffix.lower() in (".json", ".jsonl"):
                audit_dir.mkdir(parents=True, exist_ok=True)
                _safe_symlink(f, audit_dir / f.name)


def _update_final_dir(
    episode: Episode,
    final_dir: Path,
    series_dir: Path,
) -> None:
    """Symlink the composed episode video into ``final/``."""
    ep_prefix = f"ep{episode.number:02d}"
    video_src = series_dir / f"{ep_prefix}_video"
    if video_src.is_dir():
        for f in video_src.iterdir():
            if "final" in f.name.lower() or "composed" in f.name.lower():
                final_dir.mkdir(parents=True, exist_ok=True)
                _safe_symlink(f, final_dir / f.name, keep_versions=True)


def _write_duration_analysis(lines: list[str], scenes: list) -> None:
    """Append duration-per-act table to *lines*."""
    total_dur = sum(s.duration_seconds for s in scenes)
    acts: dict[str, float] = {}
    for s in scenes:
        act = s.act_number or "unassigned"
        acts[act] = acts.get(act, 0.0) + s.duration_seconds

    lines.append("### 时长分布\n")
    lines.append("| 幕 | 时长 | 占比 |")
    lines.append("|---|---:|---:|")
    for act in sorted(acts):
        dur = acts[act]
        pct = dur / total_dur * 100 if total_dur else 0
        label = act.replace("_", " ").title() if act != "unassigned" else "未分配"
        lines.append(f"| {label} | {dur:.1f}s | {pct:.0f}% |")
    lines.append(f"| **合计** | **{total_dur:.1f}s** | **100%** |")
    lines.append("")


def _write_scale_distribution(lines: list[str], scenes: list) -> None:
    """Append shot-scale histogram to *lines*."""
    counts: dict[str, int] = {}
    for s in scenes:
        scale = s.shot_scale.value if s.shot_scale else "unknown"
        counts[scale] = counts.get(scale, 0) + 1

    lines.append("### 景别分布\n")
    lines.append("| 景别 | 数量 | 占比 |")
    lines.append("|---|---:|---:|")
    total = len(scenes)
    for scale in ("close_up", "medium_close", "medium", "wide", "extreme_wide", "unknown"):
        cnt = counts.get(scale, 0)
        if cnt == 0:
            continue
        label = _SCALE_LABELS.get(scale, scale)
        pct = cnt / total * 100 if total else 0
        lines.append(f"| {label} ({scale}) | {cnt} | {pct:.0f}% |")
    lines.append("")


def _write_character_screentime(lines: list[str], scenes: list) -> None:
    """Append character screen-time table to *lines*."""
    char_counts: dict[str, int] = {}
    for s in scenes:
        for c in s.characters_present:
            char_counts[c] = char_counts.get(c, 0) + 1

    if not char_counts:
        return

    lines.append("### 角色出镜\n")
    lines.append("| 角色 | 出镜场次 | 占比 |")
    lines.append("|---|---:|---:|")
    total = len(scenes)
    for char, cnt in sorted(char_counts.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100 if total else 0
        lines.append(f"| {char} | {cnt}/{total} | {pct:.0f}% |")
    lines.append("")


def _write_scene_details(lines: list[str], scenes: list) -> None:
    """Append per-scene storyboard breakdown grouped by ACT → scene_group."""
    from collections import OrderedDict
    groups: dict[str, dict[str, list]] = OrderedDict()
    for idx, s in enumerate(scenes):
        act = s.act_number or "unassigned"
        grp = s.scene_group or "—"
        groups.setdefault(act, OrderedDict()).setdefault(grp, []).append((idx, s))

    for act, scene_groups in groups.items():
        act_label = act.replace("_", " ").title() if act != "unassigned" else "未分幕"
        lines.append(f"### {act_label}\n")

        for grp, indexed_scenes in scene_groups.items():
            if grp != "—":
                lines.append(f"**场景组 {grp}**\n")

            for idx, s in indexed_scenes:
                slug = _scene_slug(idx, s.description)
                scale = _SCALE_LABELS.get(
                    s.shot_scale.value if s.shot_scale else "", ""
                )
                scale_raw = s.shot_scale.value if s.shot_scale else "n/a"
                status = s.scene_status or "pending"
                role = s.shot_role or "normal"

                lines.append(f"#### {slug} · {s.description[:50]} ({s.duration_seconds:.0f}s)  `[{status}]`\n")

                meta_parts = []
                if scale:
                    meta_parts.append(f"**景别**: {scale} ({scale_raw})")
                if s.camera_movement and s.camera_movement != "static":
                    meta_parts.append(f"**运镜**: {s.camera_movement}")
                if s.characters_present:
                    meta_parts.append(f"**人物**: {', '.join(s.characters_present)}")
                if s.emotion:
                    meta_parts.append(f"**情绪**: {s.emotion}")
                if role != "normal":
                    meta_parts.append(f"**作用**: {role}")
                lines.append(" | ".join(meta_parts) + "\n")

                desc = s.description
                if desc:
                    lines.append(f"> {desc}\n")

                if s.dialogue:
                    speaker = s.speaking_character or "?"
                    dlg_type = "内心独白" if s.dialogue_line_type == "inner_monologue" else "台词"
                    lines.append(f'**{dlg_type}** ({speaker}): "{s.dialogue}"\n')

                if s.narration:
                    nar_type = "旁白" if s.narration_type == "voiceover" else "字幕卡"
                    lines.append(f"**{nar_type}**: {s.narration}\n")

                if s.transition:
                    lines.append(f"*转场: {s.transition}*\n")

                lines.append("---\n")


def _write_dialogue_transcript(lines: list[str], scenes: list[Any]) -> None:
    """Append the ``## 台词逐字稿`` section — every dialogue and
    narration line, in scene order.

    This section is the single source of truth for subtitles.  Seedance
    bakes subtitles directly into the generated video, so VideoClaw does
    not maintain a separate ``subtitles/`` directory; producers who need
    to review or re-edit subtitle text read this section instead.

    Scenes with neither dialogue nor narration are skipped so the
    transcript stays dense and scannable.
    """
    has_any = any(
        (s.dialogue and s.dialogue.strip())
        or (s.narration and s.narration.strip())
        for s in scenes
    )
    if not has_any:
        return

    lines.append("## 台词逐字稿\n")
    lines.append(
        "> 字幕由 Seedance 直接烧录到视频中；本段为原文备份，供后期复核 / 重录使用。\n"
    )

    for idx, s in enumerate(scenes):
        dialogue = (s.dialogue or "").strip()
        narration = (s.narration or "").strip()
        if not dialogue and not narration:
            continue

        slug = _scene_slug(idx, s.description)
        lines.append(f"### {slug}\n")

        if dialogue:
            speaker = s.speaking_character or "?"
            dlg_type = (
                "内心独白"
                if s.dialogue_line_type == "inner_monologue"
                else "台词"
            )
            lines.append(f'**{dlg_type}** ({speaker}): "{dialogue}"\n')

        if narration:
            nar_type = (
                "旁白"
                if s.narration_type == "voiceover"
                else "字幕卡"
            )
            lines.append(f"**{nar_type}**: {narration}\n")


def _version_existing(path: Path) -> None:
    """If *path* exists, rename it to ``{stem}_v{N}{suffix}`` to preserve history.

    Finds the next available version number so repeated redos produce
    ``_v1``, ``_v2``, etc.
    """
    if not (path.exists() or path.is_symlink()):
        return
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    version = 1
    while True:
        versioned = parent / f"{stem}_v{version}{suffix}"
        if not versioned.exists() and not versioned.is_symlink():
            path.rename(versioned)
            logger.debug("Versioned: %s → %s", path.name, versioned.name)
            return
        version += 1


def _first_symlink_source(subdir: Path) -> str:
    """Return a human-readable source path for the first symlink in *subdir*.

    Used by ``_REVIEW.txt``'s ``=== Sources ===`` section so auditors can
    see the real location (typically ``projects/<uuid>/shots/``) of the
    files that ``ls -la`` otherwise hides behind opaque symlink targets.

    - If *subdir* does not exist or is empty, returns ``"(empty)"``.
    - If the first file is a symlink, returns its parent directory as a
      path relative to the current working directory (so ``projects/foo``
      rather than the full absolute path when possible).
    - If the first file is a regular file (not a symlink), returns
      ``"(local files)"`` — meaning the review dir owns the bytes directly.
    """
    if not subdir.is_dir():
        return "(empty)"
    entries = [f for f in sorted(subdir.iterdir()) if f.is_file() or f.is_symlink()]
    if not entries:
        return "(empty)"
    first = entries[0]
    if first.is_symlink():
        target_parent = first.readlink()
        if not target_parent.is_absolute():
            target_parent = (subdir / target_parent).resolve().parent
        else:
            target_parent = target_parent.parent
        try:
            return str(target_parent.relative_to(Path.cwd()))
        except ValueError:
            return str(target_parent)
    return "(local files)"


def _safe_symlink(src: Path, dst: Path, *, keep_versions: bool = False) -> None:
    """Create a symlink, silently skipping on failure.

    When *keep_versions* is True and *dst* already exists, the existing
    file is renamed to ``{stem}_v{N}{suffix}`` before linking.
    """
    try:
        if dst.exists() or dst.is_symlink():
            if keep_versions:
                _version_existing(dst)
            else:
                dst.unlink()
        dst.symlink_to(src.resolve())
    except OSError:
        logger.debug("Symlink failed (%s → %s), falling back to skip", dst, src)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CheckpointStage(StrEnum):
    """Production pipeline breakpoint locations."""

    # Tier 1: pipeline-level (between the 4 major stages)
    AFTER_DESIGN = "after_design"
    AFTER_REFRESH = "after_refresh"
    AFTER_GENERATION = "after_generation"
    AFTER_AUDIT = "after_audit"

    # Tier 2: DAG-internal (inside the ``run`` stage)
    AFTER_STORYBOARD = "after_storyboard"
    AFTER_VIDEO_TTS = "after_video_tts"
    AFTER_COMPOSE = "after_compose"


class CheckpointAction(StrEnum):
    """Action a human (or auto-mode) selects at a checkpoint."""

    CONTINUE = "continue"  # proceed to next stage
    REDO = "redo"          # re-execute the stage that just completed
    ABORT = "abort"        # stop the pipeline


# ---------------------------------------------------------------------------
# Snapshot data model
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CheckpointSnapshot:
    """Self-contained snapshot of pipeline state at a checkpoint.

    Stores a deep copy of the series/project/DAG state plus an asset
    manifest, so every checkpoint is independently loadable and resumable.
    """

    checkpoint_id: str
    stage: CheckpointStage
    series_id: str
    episode_number: int
    created_at: str

    # State snapshots (serialised copies, not live references)
    series_state: dict[str, Any]
    project_state: dict[str, Any] | None = None
    dag_state: dict[str, Any] | None = None

    # Asset manifest: logical name → path relative to projects_dir
    assets: dict[str, str] = field(default_factory=dict)

    # Stage-specific result data (e.g. audit report, URL validation results)
    stage_result: dict[str, Any] = field(default_factory=dict)

    # Accumulated cost up to this point
    cost_usd: float = 0.0

    # Pipeline context for resume
    pipeline_config: dict[str, Any] = field(default_factory=dict)
    remaining_stages: list[str] = field(default_factory=list)

    # Arbitrary metadata (user notes, git commit, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Absolute path to the semantic review directory (set after build)
    review_dir: str = ""

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "stage": self.stage.value,
            "series_id": self.series_id,
            "episode_number": self.episode_number,
            "created_at": self.created_at,
            "series_state": self.series_state,
            "project_state": self.project_state,
            "dag_state": self.dag_state,
            "assets": self.assets,
            "stage_result": self.stage_result,
            "cost_usd": self.cost_usd,
            "pipeline_config": self.pipeline_config,
            "remaining_stages": self.remaining_stages,
            "metadata": self.metadata,
            "review_dir": self.review_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointSnapshot:
        return cls(
            checkpoint_id=data["checkpoint_id"],
            stage=CheckpointStage(data["stage"]),
            series_id=data["series_id"],
            episode_number=data["episode_number"],
            created_at=data["created_at"],
            series_state=data.get("series_state", {}),
            project_state=data.get("project_state"),
            dag_state=data.get("dag_state"),
            assets=data.get("assets", {}),
            stage_result=data.get("stage_result", {}),
            cost_usd=data.get("cost_usd", 0.0),
            pipeline_config=data.get("pipeline_config", {}),
            remaining_stages=data.get("remaining_stages", []),
            metadata=data.get("metadata", {}),
            review_dir=data.get("review_dir", ""),
        )


# ---------------------------------------------------------------------------
# Checkpoint manager (persistence)
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Persists checkpoint snapshots as JSON files on disk.

    Follows the same patterns as :class:`DramaManager` (compact JSON,
    ``save_async`` via ``asyncio.to_thread``).

    Layout::

        {base_dir}/dramas/{series_id}/checkpoints/
            ep{NN}_{stage}_{checkpoint_id}.json
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            from videoclaw.config import get_config
            base_dir = get_config().projects_dir
        self.base_dir = base_dir

    def _checkpoints_dir(self, series_id: str) -> Path:
        return self.base_dir / "dramas" / series_id / "checkpoints"

    def _snapshot_filename(self, snapshot: CheckpointSnapshot) -> str:
        return (
            f"ep{snapshot.episode_number:02d}"
            f"_{snapshot.stage.value}"
            f"_{snapshot.checkpoint_id}.json"
        )

    def _snapshot_path(self, series_id: str, snapshot: CheckpointSnapshot) -> Path:
        return self._checkpoints_dir(series_id) / self._snapshot_filename(snapshot)

    # -- CRUD ---------------------------------------------------------------

    def save(self, snapshot: CheckpointSnapshot) -> Path:
        """Write snapshot to disk as compact JSON. Returns file path."""
        path = self._snapshot_path(snapshot.series_id, snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _json.dumps(
                snapshot.to_dict(),
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Checkpoint saved: %s [%s] ep%02d → %s",
            snapshot.stage.value,
            snapshot.checkpoint_id,
            snapshot.episode_number,
            path,
        )
        return path

    async def save_async(self, snapshot: CheckpointSnapshot) -> Path:
        """Async variant — offloads disk I/O to a thread."""
        import asyncio
        return await asyncio.to_thread(self.save, snapshot)

    def load(self, series_id: str, checkpoint_id: str) -> CheckpointSnapshot:
        """Load a specific checkpoint by ID.

        Scans the checkpoints directory for a file matching the ID suffix.
        """
        ckpt_dir = self._checkpoints_dir(series_id)
        if not ckpt_dir.is_dir():
            raise FileNotFoundError(
                f"No checkpoints directory for series {series_id!r}"
            )
        for path in ckpt_dir.iterdir():
            if path.suffix == ".json" and checkpoint_id in path.stem:
                data = _json.loads(path.read_text(encoding="utf-8"))
                return CheckpointSnapshot.from_dict(data)
        raise FileNotFoundError(
            f"Checkpoint {checkpoint_id!r} not found in series {series_id!r}"
        )

    async def load_async(self, series_id: str, checkpoint_id: str) -> CheckpointSnapshot:
        """Async load variant."""
        import asyncio
        return await asyncio.to_thread(self.load, series_id, checkpoint_id)

    def list_checkpoints(
        self,
        series_id: str,
        episode: int | None = None,
        stage: CheckpointStage | None = None,
    ) -> list[dict[str, Any]]:
        """List checkpoints as summary dicts, sorted by created_at.

        Returns a list of lightweight dicts (no full series_state) for
        efficient listing.
        """
        ckpt_dir = self._checkpoints_dir(series_id)
        if not ckpt_dir.is_dir():
            return []

        results: list[dict[str, Any]] = []
        for path in sorted(ckpt_dir.glob("*.json")):
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue

            if episode is not None and data.get("episode_number") != episode:
                continue
            if stage is not None and data.get("stage") != stage.value:
                continue

            results.append({
                "checkpoint_id": data["checkpoint_id"],
                "stage": data["stage"],
                "episode_number": data["episode_number"],
                "created_at": data["created_at"],
                "cost_usd": data.get("cost_usd", 0.0),
                "assets_count": len(data.get("assets", {})),
                "remaining_stages": data.get("remaining_stages", []),
                "file": str(path),
            })

        results.sort(key=lambda d: d["created_at"])
        return results

    def latest(
        self,
        series_id: str,
        episode: int,
        stage: CheckpointStage | None = None,
    ) -> CheckpointSnapshot | None:
        """Get the most recent checkpoint for a given series/episode/stage."""
        summaries = self.list_checkpoints(series_id, episode=episode, stage=stage)
        if not summaries:
            return None
        latest_id = summaries[-1]["checkpoint_id"]
        return self.load(series_id, latest_id)

    def delete(self, series_id: str, checkpoint_id: str) -> None:
        """Remove a checkpoint file from disk."""
        ckpt_dir = self._checkpoints_dir(series_id)
        if not ckpt_dir.is_dir():
            return
        for path in ckpt_dir.iterdir():
            if path.suffix == ".json" and checkpoint_id in path.stem:
                path.unlink()
                logger.info("Checkpoint deleted: %s", path)
                return


# ---------------------------------------------------------------------------
# Checkpoint controller (pipeline integration)
# ---------------------------------------------------------------------------

class CheckpointController:
    """Controls checkpoint behaviour during pipeline execution.

    Handles three modes:

    - **Interactive** (TTY): pause + display Rich UI at each breakpoint
    - **Non-interactive** (CI): save checkpoint silently, continue
    - **Selective**: only pause at specified stages via *breakpoints*

    In all modes, every checkpoint is persisted to disk for audit trail.
    """

    def __init__(
        self,
        series: DramaSeries,
        episode: Episode,
        manager: CheckpointManager,
        drama_manager: DramaManager,
        breakpoints: list[CheckpointStage] | None = None,
        interactive: bool | None = None,
        pipeline_config: dict[str, Any] | None = None,
        deliverables_dir: Path | None = None,
    ) -> None:
        self.series = series
        self.episode = episode
        self.manager = manager
        self.drama_manager = drama_manager

        # Resolve deliverables_dir now (not lazily) so downstream code can
        # rely on a concrete Path. None → read from config once.
        if deliverables_dir is None:
            from videoclaw.config import get_config
            deliverables_dir = get_config().deliverables_dir
        self._deliverables_dir = deliverables_dir

        # None → pause at all; empty list → pause at none (auto)
        self._breakpoints = breakpoints

        # Auto-detect TTY if not explicitly set
        if interactive is None:
            self._interactive = sys.stdin.isatty()
        else:
            self._interactive = interactive

        self._pipeline_config = pipeline_config or {}

    def _should_pause(self, stage: CheckpointStage) -> bool:
        """Return True if the pipeline should pause at this stage."""
        if not self._interactive:
            return False
        if self._breakpoints is None:
            # None means "all breakpoints"
            return True
        return stage in self._breakpoints

    async def checkpoint(
        self,
        stage: CheckpointStage,
        *,
        project_state: ProjectState | None = None,
        dag: DAG | None = None,
        stage_result: dict[str, Any] | None = None,
        cost_usd: float = 0.0,
        remaining_stages: list[str] | None = None,
    ) -> CheckpointAction:
        """Save a checkpoint and optionally pause for human review.

        Always persists the snapshot (audit trail). Only pauses when
        interactive mode is enabled and the stage is in the breakpoints list.

        Returns the action selected by the human, or CONTINUE in auto mode.
        """
        # 1. Sync generated assets from ProjectState → DramaScene state.
        # Video/audio outputs live in projects/{project_id}/ but scene
        # metadata (video_asset_path, scene_status) must be updated before
        # we build the review directory — otherwise the review would see
        # stale "pending" scenes even after successful generation.
        self._sync_scene_assets_from_project_state()

        # 2. Refresh the series-level view BEFORE the episode review dir so
        # ep-filtered symlinks resolve against an already-populated series
        # root (Audit A9). Work set is stage-scoped per _SERIES_STAGE_WORK
        # so `after_generation` etc. don't needlessly re-symlink assets.
        build_series_view(
            self.series,
            deliverables_dir=self._deliverables_dir,
            projects_dir=self.manager.base_dir,
            work=_SERIES_STAGE_WORK.get(stage.value, {"md"}),
        )

        # 3. Update cumulative review directory (additive, not destructive)
        review_dir, assets = self._update_review_dir(stage)

        # 2. Build snapshot
        snapshot = CheckpointSnapshot(
            checkpoint_id=uuid.uuid4().hex[:12],
            stage=stage,
            series_id=self.series.series_id,
            episode_number=self.episode.number,
            created_at=_now_iso(),
            series_state=self.series.to_dict(),
            project_state=project_state.to_dict() if project_state else None,
            dag_state=dag.to_dict() if dag else None,
            assets=assets,
            stage_result=stage_result or {},
            cost_usd=cost_usd,
            pipeline_config=self._pipeline_config,
            remaining_stages=remaining_stages or [],
            review_dir=str(review_dir),
        )

        # 3. Write a human-readable summary into the review directory
        self._write_review_summary(review_dir, snapshot)

        # 4. Always save JSON checkpoint (audit trail)
        await self.manager.save_async(snapshot)

        # 5. Emit event
        from videoclaw.core.events import CHECKPOINT_SAVED, event_bus
        await event_bus.emit(CHECKPOINT_SAVED, {
            "checkpoint_id": snapshot.checkpoint_id,
            "stage": stage.value,
            "series_id": snapshot.series_id,
            "episode_number": snapshot.episode_number,
            "assets_count": len(assets),
            "review_dir": str(review_dir),
        })

        # 6. Pause if interactive and this stage is in breakpoints
        if self._should_pause(stage):
            return self._display_checkpoint_ui(snapshot)

        return CheckpointAction.CONTINUE

    # ------------------------------------------------------------------
    # Semantic review snapshot
    # ------------------------------------------------------------------

    # Stage → subdirectories to update (only these are touched per checkpoint).
    # storyboard.md is always regenerated at every stage (handled separately).
    _STAGE_SUBDIRS: dict[str, list[str]] = {
        "after_design":     ["characters", "scenes"],
        "after_refresh":    ["characters", "scenes"],
        "after_storyboard": [],
        "after_video_tts":  ["videos", "audio"],
        "after_generation": ["videos", "audio", "final"],
        "after_compose":    ["final"],
        "after_audit":      ["audit"],
    }

    # All subdirectories that may appear in the review folder.
    # Subdirectories are created lazily — they only exist if they have content.
    _ALL_SUBDIRS = ("characters", "scenes", "audio", "videos", "audit", "final")

    # ------------------------------------------------------------------
    # Asset sync: ProjectState → DramaScene
    # ------------------------------------------------------------------

    def _sync_scene_assets_from_project_state(self) -> None:
        """Copy generated asset paths from ProjectState shots → DramaScene.

        The DAG executor writes generated video files to
        ``projects/{project_id}/shots/`` and updates
        ``ProjectState.storyboard[].asset_path``.  But the
        ``DramaSeries.episodes[].scenes[]`` (what the review directory
        reads from) is a separate object and doesn't get updated.

        This sync is idempotent and cheap — it only copies when:
        - the scene has a matching project_id
        - the shot has a non-null asset_path
        - the file on disk still exists

        After syncing, the updated series is persisted so subsequent
        checkpoints and CLI commands see the latest state.
        """
        if not self.episode.project_id:
            return

        from videoclaw.core.state import StateManager

        try:
            state = StateManager().load(self.episode.project_id)
        except FileNotFoundError:
            return

        shot_map = {s.shot_id: s for s in state.storyboard}
        changed = False

        for scene in self.episode.scenes:
            shot = shot_map.get(scene.scene_id)
            if shot is None:
                continue

            # Sync video path if missing or stale
            if shot.asset_path and Path(shot.asset_path).exists():
                if scene.video_asset_path != shot.asset_path:
                    scene.video_asset_path = shot.asset_path
                    changed = True
                if shot.status.value == "completed" and scene.scene_status != "completed":
                    scene.scene_status = "completed"
                    changed = True

        # Sync audio files from projects/{project_id}/audio/ by filename match.
        # TTS handlers write to {audio_dir}/{scene_id}_dialogue.{ext} and
        # {scene_id}_narration.{ext} — pick up whatever is there.
        from videoclaw.config import get_config
        audio_dir = Path(get_config().projects_dir) / self.episode.project_id / "audio"
        if audio_dir.is_dir():
            for scene in self.episode.scenes:
                for f in audio_dir.iterdir():
                    if not f.is_file():
                        continue
                    name = f.name
                    if scene.scene_id not in name:
                        continue
                    if "dialogue" in name and scene.dialogue_audio_path != str(f):
                        scene.dialogue_audio_path = str(f)
                        changed = True
                    elif "narration" in name and scene.narration_audio_path != str(f):
                        scene.narration_audio_path = str(f)
                        changed = True

        if changed:
            try:
                self.drama_manager.save(self.series)
                logger.info(
                    "Synced scene assets from ProjectState %s → series %s",
                    self.episode.project_id, self.series.series_id,
                )
            except OSError:
                logger.exception("Failed to persist synced scene assets")

    def _update_review_dir(
        self, stage: CheckpointStage,
    ) -> tuple[Path, dict[str, str]]:
        """Incrementally update the cumulative review directory.

        One directory per episode: ``{deliverables_dir}/{drama}/{ep}/``.
        Each checkpoint only touches the subdirectories relevant to its
        stage.  Existing files from earlier stages are preserved.  When
        a file is replaced (e.g. redo), the old version is renamed to
        ``{name}_v{N}{ext}``.

        Subdirectories are created **lazily**: the ``_update_*`` helpers
        only ``mkdir`` when they actually have content to write.  This
        keeps the review folder free of empty placeholder directories
        so ``ls`` shows exactly what has been produced.

        Returns ``(review_dir_path, assets_dict)`` where assets_dict
        contains ALL files currently in the review directory (cumulative).
        """
        projects_dir = self.manager.base_dir
        series_dir = projects_dir / "dramas" / self.series.series_id
        review_dir = review_dir_for_episode(
            self.series, self.episode, base_dir=self._deliverables_dir,
        )

        # Only create the root — subdirectories are lazy
        review_dir.mkdir(parents=True, exist_ok=True)

        # Only update subdirectories relevant to this stage
        active_subdirs = set(self._STAGE_SUBDIRS.get(stage.value, []))

        if "characters" in active_subdirs:
            self._update_characters(review_dir / "characters")

        if "scenes" in active_subdirs:
            self._update_scenes(review_dir / "scenes")

        if "videos" in active_subdirs:
            self._update_videos(review_dir / "videos", projects_dir)

        if "audio" in active_subdirs:
            self._update_audio(review_dir / "audio")

        if "audit" in active_subdirs:
            self._update_audit(review_dir / "audit", series_dir)

        if "final" in active_subdirs:
            self._update_final(review_dir / "final", series_dir)

        # Storyboard: always regenerated (cheap text, reflects latest state)
        self._update_storyboard(review_dir)

        # Collect ALL assets across the entire review dir (cumulative)
        assets = self._collect_all_assets(review_dir)
        return review_dir, assets

    # -- Per-subdirectory updaters (thin wrappers around module-level helpers) --
    #
    # Kept as methods for backwards compatibility with any existing tests
    # that patched them; all production logic lives in the module-level
    # ``_update_*_dir`` functions so ``build_review_dir`` and the controller
    # stay byte-for-byte identical.

    def _update_characters(self, chars_dir: Path) -> None:
        series_root = _series_root_for(self.series, self._deliverables_dir)
        _update_characters_dir(
            self.series,
            chars_dir,
            episode=self.episode,
            series_root=series_root,
        )

    def _update_scenes(self, scenes_dir: Path) -> None:
        series_root = _series_root_for(self.series, self._deliverables_dir)
        _update_scenes_dir(
            self.series,
            scenes_dir,
            episode=self.episode,
            series_root=series_root,
        )

    def _update_videos(self, videos_dir: Path, projects_dir: Path) -> None:
        _update_videos_dir(self.series, self.episode, videos_dir, projects_dir)

    def _update_audio(self, audio_dir: Path) -> None:
        _update_audio_dir(self.series, self.episode, audio_dir)

    def _update_audit(self, audit_dir: Path, series_dir: Path) -> None:
        _update_audit_dir(self.episode, audit_dir, series_dir)

    def _update_final(self, final_dir: Path, series_dir: Path) -> None:
        _update_final_dir(self.episode, final_dir, series_dir)

    # ------------------------------------------------------------------
    # Storyboard document — delegates to module-level functions
    # ------------------------------------------------------------------

    def _update_storyboard(self, review_dir: Path) -> None:
        """Delegate to :func:`generate_storyboard_md`."""
        generate_storyboard_md(self.series, self.episode, review_dir=review_dir)

    @staticmethod
    def _collect_all_assets(review_dir: Path) -> dict[str, str]:
        """Walk the entire review directory and return all files as assets dict."""
        assets: dict[str, str] = {}
        for path in sorted(review_dir.rglob("*")):
            if path.is_file() or path.is_symlink():
                rel = str(path.relative_to(review_dir))
                assets[rel] = str(path)
        return assets

    def _write_review_summary(
        self, review_dir: Path, snapshot: CheckpointSnapshot,
    ) -> None:
        """Write a human-readable _REVIEW.txt with full cumulative state."""
        remaining = ", ".join(snapshot.remaining_stages) or "(done)"

        # Count files per subdirectory (missing subdirs are simply absent)
        subdir_counts: dict[str, int] = {}
        for subdir in self._ALL_SUBDIRS:
            d = review_dir / subdir
            if d.is_dir():
                subdir_counts[subdir] = sum(1 for f in d.iterdir() if f.is_file() or f.is_symlink())
            else:
                subdir_counts[subdir] = 0

        _SUBDIR_LABELS = {
            "characters": "turnaround sheets + reference URLs",
            "scenes":     "location / shot framing references",
            "videos":     "generated video clips",
            "audio":      "dialogue + narration audio",
            "audit":      "vision QA reports",
            "final":      "composed episode video",
        }

        lines = [
            f"Series:      {self.series.title} ({self.series.series_id})",
            f"Episode:     {snapshot.episode_number}",
            f"Last stage:  {snapshot.stage.value}",
            f"Cost:        ${snapshot.cost_usd:.4f}",
            f"Updated:     {snapshot.created_at}",
            f"Checkpoint:  {snapshot.checkpoint_id}",
            f"Remaining:   {remaining}",
            "",
            "=== Assets ===",
        ]
        for subdir in self._ALL_SUBDIRS:
            count = subdir_counts.get(subdir, 0)
            label = _SUBDIR_LABELS.get(subdir, "")
            lines.append(f"  {subdir + '/':<14s} {count:>3d} files  ({label})")

        # --- Sources: show where each populated subdir's symlinks point ---
        lines.append("")
        lines.append("=== Sources ===")
        for subdir in self._ALL_SUBDIRS:
            source = _first_symlink_source(review_dir / subdir)
            lines.append(f"  {subdir + '/':<14s} → {source}")

        lines.append("")
        lines.append("=== Scenes ===")
        for idx, scene in enumerate(self.episode.scenes):
            slug = _scene_slug(idx, scene.description)
            status = scene.scene_status or "pending"
            lines.append(f"  {slug:<40s} [{status:<9s}]  {scene.description[:50]}")

        summary_path = review_dir / "_REVIEW.txt"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _display_checkpoint_ui(self, snapshot: CheckpointSnapshot) -> CheckpointAction:
        """Rich interactive UI: show review dir and prompt for action."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.tree import Tree

        console = Console()
        console.print()

        # Review directory — the most important thing
        review_path = snapshot.review_dir
        console.print(
            Panel(
                f"[bold green]{review_path}[/bold green]",
                title="[bold] Review Directory — open this folder [/bold]",
                border_style="green",
            )
        )

        # Asset tree (grouped by subdirectory)
        tree = Tree(f"[bold cyan]{snapshot.stage.value}[/bold cyan]")
        groups: dict[str, list[str]] = {}
        for name in sorted(snapshot.assets):
            parts = name.split("/", 1)
            group = parts[0] if len(parts) > 1 else "(root)"
            groups.setdefault(group, []).append(parts[-1] if len(parts) > 1 else name)

        for group, files in sorted(groups.items()):
            branch = tree.add(f"[bold]{group}/[/bold]  ({len(files)} files)")
            for f in files[:8]:  # show at most 8 per group
                branch.add(f"[dim]{f}[/dim]")
            if len(files) > 8:
                branch.add(f"[dim]... +{len(files) - 8} more[/dim]")

        console.print(tree)

        # Summary
        remaining = ", ".join(snapshot.remaining_stages) if snapshot.remaining_stages else "(none)"
        console.print(
            Panel(
                f"[bold]Episode:[/bold]    {snapshot.episode_number}\n"
                f"[bold]Assets:[/bold]     {len(snapshot.assets)} files\n"
                f"[bold]Cost:[/bold]       ${snapshot.cost_usd:.4f}\n"
                f"[bold]Remaining:[/bold]  {remaining}\n"
                f"[bold]Checkpoint:[/bold] {snapshot.checkpoint_id}",
                title=f"[bold cyan]Checkpoint: {snapshot.stage.value}[/bold cyan]",
                border_style="cyan",
            )
        )

        # Prompt for action
        while True:
            choice = console.input(
                "\n[yellow][C]ontinue / [R]edo / [A]bort > [/yellow]"
            ).strip().lower()
            if choice in ("c", "continue", ""):
                return CheckpointAction.CONTINUE
            if choice in ("r", "redo"):
                return CheckpointAction.REDO
            if choice in ("a", "abort"):
                return CheckpointAction.ABORT
            console.print("[red]Invalid choice. Enter C, R, or A.[/red]")


# ---------------------------------------------------------------------------
# Resume / Redo helpers
# ---------------------------------------------------------------------------

def resolve_skip_flags(
    remaining_stages: list[str],
) -> dict[str, bool]:
    """Convert remaining_stages list to pipeline skip flags.

    Maps the stage names used in the pipeline to ``skip_*`` booleans.
    Stages NOT in ``remaining_stages`` are skipped.
    """
    all_stages = ["design-characters", "refresh-urls", "run", "audit-regen"]
    remaining_set = set(remaining_stages)
    return {
        "skip_design": "design-characters" not in remaining_set,
        "skip_refresh": "refresh-urls" not in remaining_set,
        "skip_run": "run" not in remaining_set,
        "skip_audit": "audit-regen" not in remaining_set,
    }


def restore_from_checkpoint(
    snapshot: CheckpointSnapshot,
) -> DramaSeries:
    """Restore a DramaSeries from a checkpoint snapshot.

    Returns a fully hydrated DramaSeries rebuilt from the checkpoint's
    ``series_state`` dict.
    """
    from videoclaw.drama.models import DramaSeries
    return DramaSeries.from_dict(snapshot.series_state)
