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


def _safe_symlink(src: Path, dst: Path) -> None:
    """Create a symlink, silently skipping on failure (e.g. Windows without dev mode)."""
    try:
        if dst.exists() or dst.is_symlink():
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
    ) -> None:
        self.series = series
        self.episode = episode
        self.manager = manager
        self.drama_manager = drama_manager

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
        # 1. Build semantic review directory (symlinks to real assets)
        review_dir, assets = self._build_review_snapshot(stage)

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

    def _build_review_snapshot(
        self, stage: CheckpointStage,
    ) -> tuple[Path, dict[str, str]]:
        """Create a semantic review directory with symlinks to actual assets.

        The review directory is the primary interface for human inspection:
        every file name is derived from scene descriptions, not from IDs or
        hashes.  Symlinks avoid duplicating large media files.

        Returns ``(review_dir_path, assets_dict)``.
        """
        projects_dir = self.manager.base_dir
        series_dir = projects_dir / "dramas" / self.series.series_id

        ep_num = self.episode.number
        review_dir = series_dir / "review" / f"ep{ep_num:02d}_{stage.value}"

        # Clean previous review for this stage (idempotent)
        if review_dir.exists():
            import shutil
            shutil.rmtree(review_dir)
        review_dir.mkdir(parents=True, exist_ok=True)

        assets: dict[str, str] = {}

        # -- Characters --
        chars_review = review_dir / "characters"
        chars_review.mkdir(exist_ok=True)
        for char in self.series.characters:
            # Turnaround image (local file)
            if char.reference_image:
                src = Path(char.reference_image)
                if src.exists():
                    name = f"{_slugify(char.name)}_turnaround{src.suffix}"
                    dst = chars_review / name
                    _safe_symlink(src, dst)
                    assets[f"characters/{name}"] = str(dst)
            # URL reference (write a .url file for quick access)
            url = getattr(char, "reference_image_url", None)
            if url:
                url_file = chars_review / f"{_slugify(char.name)}_url.txt"
                url_file.write_text(url, encoding="utf-8")
                assets[f"characters/{url_file.name}"] = str(url_file)

        # -- Prompts (text files named after scene descriptions) --
        prompts_review = review_dir / "prompts"
        prompts_review.mkdir(exist_ok=True)
        for idx, scene in enumerate(self.episode.scenes):
            slug = _scene_slug(idx, scene.description)
            prompt_file = prompts_review / f"{slug}.txt"
            prompt_text = (
                f"Scene: {scene.scene_id}\n"
                f"Description: {scene.description}\n"
                f"Duration: {scene.duration_seconds}s\n"
                f"Characters: {', '.join(scene.characters_present)}\n"
                f"Dialogue: {scene.dialogue}\n"
                f"Camera: {scene.camera_movement}\n"
                f"Shot scale: {scene.shot_scale.value if scene.shot_scale else 'n/a'}\n"
                f"\n--- Prompt ---\n{scene.effective_prompt}\n"
            )
            prompt_file.write_text(prompt_text, encoding="utf-8")
            assets[f"prompts/{slug}.txt"] = str(prompt_file)

        # -- Videos (symlinks with semantic names) --
        videos_review = review_dir / "videos"
        videos_review.mkdir(exist_ok=True)
        for idx, scene in enumerate(self.episode.scenes):
            if scene.video_asset_path:
                src = Path(scene.video_asset_path)
                if src.exists():
                    slug = _scene_slug(idx, scene.description)
                    dst = videos_review / f"{slug}{src.suffix}"
                    _safe_symlink(src, dst)
                    assets[f"videos/{slug}{src.suffix}"] = str(dst)

        # Also check project shots dir for video files not yet in scene state
        if self.episode.project_id:
            shots_dir = projects_dir / self.episode.project_id / "shots"
            if shots_dir.is_dir():
                scene_map = {s.scene_id: (i, s) for i, s in enumerate(self.episode.scenes)}
                for f in sorted(shots_dir.iterdir()):
                    if f.suffix.lower() != ".mp4":
                        continue
                    # Match shot file to scene by scene_id in filename
                    matched = False
                    for sid, (i, sc) in scene_map.items():
                        if sid in f.name:
                            slug = _scene_slug(i, sc.description)
                            dst = videos_review / f"{slug}{f.suffix}"
                            if not dst.exists():
                                _safe_symlink(f, dst)
                                assets[f"videos/{slug}{f.suffix}"] = str(dst)
                            matched = True
                            break
                    if not matched:
                        # No scene match — link with original name
                        dst = videos_review / f.name
                        if not dst.exists():
                            _safe_symlink(f, dst)
                            assets[f"videos/{f.name}"] = str(dst)

        # -- Audio (symlinks) --
        audio_review = review_dir / "audio"
        audio_review.mkdir(exist_ok=True)
        for idx, scene in enumerate(self.episode.scenes):
            slug = _scene_slug(idx, scene.description)
            if scene.dialogue_audio_path:
                src = Path(scene.dialogue_audio_path)
                if src.exists():
                    dst = audio_review / f"{slug}_dialogue{src.suffix}"
                    _safe_symlink(src, dst)
                    assets[f"audio/{slug}_dialogue{src.suffix}"] = str(dst)
            if scene.narration_audio_path:
                src = Path(scene.narration_audio_path)
                if src.exists():
                    dst = audio_review / f"{slug}_narration{src.suffix}"
                    _safe_symlink(src, dst)
                    assets[f"audio/{slug}_narration{src.suffix}"] = str(dst)

        # -- Audit reports --
        ep_prefix = f"ep{ep_num:02d}"
        audit_src_dir = series_dir / f"{ep_prefix}_audit"
        if audit_src_dir.is_dir():
            audit_review = review_dir / "audit"
            audit_review.mkdir(exist_ok=True)
            for f in sorted(audit_src_dir.iterdir()):
                if f.suffix.lower() in (".json", ".jsonl"):
                    dst = audit_review / f.name
                    _safe_symlink(f, dst)
                    assets[f"audit/{f.name}"] = str(dst)

        # -- Composed video --
        video_src_dir = series_dir / f"{ep_prefix}_video"
        if video_src_dir.is_dir():
            for f in video_src_dir.iterdir():
                if "final" in f.name.lower() or "composed" in f.name.lower():
                    dst = review_dir / f"composed_{f.name}"
                    _safe_symlink(f, dst)
                    assets[f"composed_{f.name}"] = str(dst)

        return review_dir, assets

    def _write_review_summary(
        self, review_dir: Path, snapshot: CheckpointSnapshot,
    ) -> None:
        """Write a human-readable _REVIEW.txt summary into the review dir."""
        remaining = ", ".join(snapshot.remaining_stages) or "(done)"
        lines = [
            f"Checkpoint: {snapshot.stage.value}",
            f"Series:     {self.series.title} ({self.series.series_id})",
            f"Episode:    {snapshot.episode_number}",
            f"Cost:       ${snapshot.cost_usd:.4f}",
            f"Created:    {snapshot.created_at}",
            f"ID:         {snapshot.checkpoint_id}",
            f"Remaining:  {remaining}",
            "",
            "=== Directory Layout ===",
            "characters/  — Character turnaround sheets + reference URLs",
            "prompts/     — Enhanced visual prompts per scene (editable!)",
            "videos/      — Generated video clips per scene",
            "audio/       — Dialogue + narration audio per scene",
            "audit/       — Vision QA audit reports",
            "",
            "=== Scenes ===",
        ]
        for idx, scene in enumerate(self.episode.scenes):
            slug = _scene_slug(idx, scene.description)
            status = scene.scene_status or "pending"
            lines.append(f"  {slug}  [{status}]  {scene.description[:60]}")

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
