"""Human checkpoint / breakpoint system for the drama production pipeline.

Provides structured breakpoints at critical production nodes so humans can:

- **Review** generated assets (turnaround sheets, video clips, audit reports)
- **Control** the pipeline (continue, redo a stage, or abort)
- **Resume** from any saved checkpoint
- **Audit** the full intermediate asset trail after automated runs

Every checkpoint is persisted to disk regardless of mode (interactive or
automated), ensuring a complete audit trail.

Layout::

    {projects_dir}/dramas/{series_id}/checkpoints/
        ep{NN}_{stage}_{checkpoint_id}.json
"""

from __future__ import annotations

import json as _json
import logging
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
        # 1. Collect current assets
        assets = self._collect_assets(stage)

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
        )

        # 3. Always save (audit trail)
        await self.manager.save_async(snapshot)

        # 4. Emit event
        from videoclaw.core.events import CHECKPOINT_SAVED, event_bus
        await event_bus.emit(CHECKPOINT_SAVED, {
            "checkpoint_id": snapshot.checkpoint_id,
            "stage": stage.value,
            "series_id": snapshot.series_id,
            "episode_number": snapshot.episode_number,
            "assets_count": len(assets),
        })

        # 5. Pause if interactive and this stage is in breakpoints
        if self._should_pause(stage):
            return self._display_checkpoint_ui(snapshot)

        return CheckpointAction.CONTINUE

    def _collect_assets(self, stage: CheckpointStage) -> dict[str, str]:
        """Scan the series directory for assets relevant to this checkpoint.

        Returns a dict mapping logical asset name to path relative to
        ``projects_dir``, so checkpoints survive directory relocation.
        """
        from videoclaw.config import get_config
        projects_dir = get_config().projects_dir
        series_dir = projects_dir / "dramas" / self.series.series_id
        assets: dict[str, str] = {}

        if not series_dir.is_dir():
            return assets

        def _rel(p: Path) -> str:
            try:
                return str(p.relative_to(projects_dir))
            except ValueError:
                return str(p)

        # Character turnaround sheets
        chars_dir = series_dir / "characters"
        if chars_dir.is_dir():
            for f in chars_dir.iterdir():
                if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    assets[f"characters/{f.name}"] = _rel(f)

        # Consistency manifest
        manifest_path = series_dir / "consistency_manifest.json"
        if manifest_path.exists():
            assets["consistency_manifest.json"] = _rel(manifest_path)

        # Episode-specific assets
        ep_num = self.episode.number
        ep_prefix = f"ep{ep_num:02d}"

        # Video clips
        video_dir = series_dir / f"{ep_prefix}_video"
        if video_dir.is_dir():
            for f in video_dir.iterdir():
                if f.suffix.lower() in (".mp4", ".wav", ".aac"):
                    assets[f"{ep_prefix}_video/{f.name}"] = _rel(f)

        # Audit reports
        audit_dir = series_dir / f"{ep_prefix}_audit"
        if audit_dir.is_dir():
            for f in audit_dir.iterdir():
                if f.suffix.lower() in (".json", ".jsonl"):
                    assets[f"{ep_prefix}_audit/{f.name}"] = _rel(f)

        # ProjectState snapshots (in projects/{project_id}/)
        if self.episode.project_id:
            proj_dir = projects_dir / self.episode.project_id
            if proj_dir.is_dir():
                state_file = proj_dir / "state.json"
                if state_file.exists():
                    assets["project/state.json"] = _rel(state_file)
                shots_dir = proj_dir / "shots"
                if shots_dir.is_dir():
                    for f in shots_dir.iterdir():
                        if f.suffix.lower() in (".mp4",):
                            assets[f"project/shots/{f.name}"] = _rel(f)

        # Character reference images from DramaScene.video_asset_path
        for scene in self.episode.scenes:
            if scene.video_asset_path:
                vp = Path(scene.video_asset_path)
                if vp.exists():
                    key = f"scene_videos/{vp.name}"
                    assets[key] = _rel(vp)

        return assets

    def _display_checkpoint_ui(self, snapshot: CheckpointSnapshot) -> CheckpointAction:
        """Rich interactive UI: show assets and prompt for action."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        # Asset table
        table = Table(
            title=f"Checkpoint: {snapshot.stage.value}",
            show_lines=False,
        )
        table.add_column("Asset", style="cyan")
        table.add_column("Path", style="dim")

        for logical_name, rel_path in sorted(snapshot.assets.items()):
            table.add_row(logical_name, rel_path)

        console.print()
        console.print(table)

        # Summary panel
        remaining = ", ".join(snapshot.remaining_stages) if snapshot.remaining_stages else "(none)"
        console.print(
            Panel(
                f"[bold]Stage:[/bold]      {snapshot.stage.value}\n"
                f"[bold]Episode:[/bold]    {snapshot.episode_number}\n"
                f"[bold]Assets:[/bold]     {len(snapshot.assets)} files\n"
                f"[bold]Cost:[/bold]       ${snapshot.cost_usd:.4f}\n"
                f"[bold]Remaining:[/bold]  {remaining}\n"
                f"[bold]Checkpoint:[/bold] {snapshot.checkpoint_id}",
                title="[bold cyan]Checkpoint Breakpoint[/bold cyan]",
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
