"""``claw drama checkpoint-*`` -- manage pipeline checkpoints."""

from __future__ import annotations

import asyncio
import json as _json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    pass

from videoclaw.cli._app import (
    configure_logging,
    drama_app,
    show_banner,
)
from videoclaw.cli._output import get_console, get_output


# ---------------------------------------------------------------------------
# claw drama checkpoint-list
# ---------------------------------------------------------------------------

@drama_app.command("checkpoint-list")
def checkpoint_list(
    series_id: Annotated[str, typer.Argument(help="Drama series ID.")],
    episode: Annotated[
        int | None,
        typer.Option("--episode", "-e", help="Filter by episode number."),
    ] = None,
    stage: Annotated[
        str | None,
        typer.Option("--stage", "-s", help="Filter by checkpoint stage."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """List all saved checkpoints for a drama series.

    \b
    Shows a table of checkpoints with ID, stage, episode, timestamp, cost,
    and asset count.  Use --episode and --stage to filter.

    \b
    Examples:
        claw drama checkpoint-list 97e8424712d24fb2
        claw drama checkpoint-list abc123 -e 1
        claw drama checkpoint-list abc123 -s after_design
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.checkpoint-list"

    from videoclaw.drama.checkpoint import CheckpointManager, CheckpointStage

    mgr = CheckpointManager()
    stage_filter = CheckpointStage(stage) if stage else None
    summaries = mgr.list_checkpoints(series_id, episode=episode, stage=stage_filter)

    if not summaries:
        console.print("[yellow]No checkpoints found.[/yellow]")
        out.set_result({"count": 0})
        out.emit()
        return

    from rich.table import Table

    table = Table(title=f"Checkpoints — {series_id}")
    table.add_column("ID", style="cyan")
    table.add_column("Stage", style="bold")
    table.add_column("EP", justify="right")
    table.add_column("Created", style="dim")
    table.add_column("Cost", justify="right")
    table.add_column("Assets", justify="right")
    table.add_column("Remaining", style="dim")

    for s in summaries:
        table.add_row(
            s["checkpoint_id"],
            s["stage"],
            str(s["episode_number"]),
            s["created_at"][:19],
            f"${s['cost_usd']:.4f}",
            str(s["assets_count"]),
            ", ".join(s["remaining_stages"]) if s["remaining_stages"] else "—",
        )

    console.print(table)
    out.set_result({"count": len(summaries)})
    out.emit()


# ---------------------------------------------------------------------------
# claw drama checkpoint-show
# ---------------------------------------------------------------------------

@drama_app.command("checkpoint-show")
def checkpoint_show(
    series_id: Annotated[str, typer.Argument(help="Drama series ID.")],
    checkpoint_id: Annotated[str, typer.Argument(help="Checkpoint ID.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Display full checkpoint details: stage, assets, cost, metadata.

    \b
    Examples:
        claw drama checkpoint-show 97e8424712d24fb2 a1b2c3d4e5f6
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.checkpoint-show"

    from videoclaw.drama.checkpoint import CheckpointManager

    mgr = CheckpointManager()
    try:
        snapshot = mgr.load(series_id, checkpoint_id)
    except FileNotFoundError:
        console.print(f"[red]Checkpoint {checkpoint_id!r} not found.[/red]")
        out.set_error(f"Checkpoint {checkpoint_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    from rich.panel import Panel
    from rich.table import Table

    # Summary panel
    remaining = ", ".join(snapshot.remaining_stages) if snapshot.remaining_stages else "(none)"
    console.print(
        Panel(
            f"[bold]Checkpoint:[/bold]  {snapshot.checkpoint_id}\n"
            f"[bold]Stage:[/bold]       {snapshot.stage.value}\n"
            f"[bold]Series:[/bold]      {snapshot.series_id}\n"
            f"[bold]Episode:[/bold]     {snapshot.episode_number}\n"
            f"[bold]Created:[/bold]     {snapshot.created_at}\n"
            f"[bold]Cost:[/bold]        ${snapshot.cost_usd:.4f}\n"
            f"[bold]Assets:[/bold]      {len(snapshot.assets)} files\n"
            f"[bold]Remaining:[/bold]   {remaining}",
            title="[bold cyan]Checkpoint Details[/bold cyan]",
            border_style="cyan",
        )
    )

    # Asset table
    if snapshot.assets:
        table = Table(title="Assets")
        table.add_column("Logical Name", style="cyan")
        table.add_column("Relative Path", style="dim")

        for name, path in sorted(snapshot.assets.items()):
            table.add_row(name, path)
        console.print(table)

    # Stage result
    if snapshot.stage_result:
        console.print("\n[bold]Stage Result:[/bold]")
        console.print_json(data=snapshot.stage_result)

    out.set_result(snapshot.to_dict())
    out.emit()


# ---------------------------------------------------------------------------
# claw drama checkpoint-resume
# ---------------------------------------------------------------------------

@drama_app.command("checkpoint-resume")
def checkpoint_resume(
    series_id: Annotated[str, typer.Argument(help="Drama series ID.")],
    checkpoint_id: Annotated[str, typer.Argument(help="Checkpoint ID to resume from.")],
    breakpoints_opt: Annotated[
        str,
        typer.Option(
            "--breakpoints", "-B",
            help="Comma-separated checkpoint stages to pause at ('all' or 'none').",
        ),
    ] = "none",
    audit_rounds: Annotated[
        int, typer.Option("--audit-rounds", "-n", help="Max audit-regen iterations.")
    ] = 3,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help="Max parallel tasks.")
    ] = 4,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resume the pipeline from a saved checkpoint.

    \b
    Loads the series state from the checkpoint, determines which stages are
    remaining, and continues execution from there.

    \b
    Examples:
        claw drama checkpoint-resume 97e8424712d24fb2 a1b2c3d4e5f6
        claw drama checkpoint-resume abc123 a1b2c3 --breakpoints all
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.checkpoint-resume"

    from videoclaw.drama.checkpoint import (
        CheckpointManager,
        CheckpointStage,
        resolve_skip_flags,
        restore_from_checkpoint,
    )
    from videoclaw.drama.models import DramaManager

    ckpt_mgr = CheckpointManager()
    try:
        snapshot = ckpt_mgr.load(series_id, checkpoint_id)
    except FileNotFoundError:
        console.print(f"[red]Checkpoint {checkpoint_id!r} not found.[/red]")
        out.set_error(f"Checkpoint {checkpoint_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    series = restore_from_checkpoint(snapshot)
    skip_flags = resolve_skip_flags(snapshot.remaining_stages)

    ep = next((e for e in series.episodes if e.number == snapshot.episode_number), None)
    if ep is None:
        console.print(f"[red]Episode {snapshot.episode_number} not found in checkpoint state.[/red]")
        raise typer.Exit(code=1)

    # Parse breakpoints
    bp_list: list[CheckpointStage] | None
    if breakpoints_opt == "all":
        bp_list = None
    elif breakpoints_opt == "none":
        bp_list = []
    else:
        bp_list = [CheckpointStage(s.strip()) for s in breakpoints_opt.split(",") if s.strip()]

    console.print(
        f"[bold green]Resuming from checkpoint {checkpoint_id} "
        f"(stage: {snapshot.stage.value})[/bold green]"
    )
    console.print(f"  Remaining stages: {', '.join(snapshot.remaining_stages) or '(none)'}")

    from videoclaw.cli.drama._quality import _drama_pipeline_async

    mgr = DramaManager()
    # Save restored series so pipeline can load it
    mgr.save(series)

    try:
        result = asyncio.run(
            _drama_pipeline_async(
                series, mgr, ep,
                skip_flags["skip_design"],
                skip_flags["skip_refresh"],
                skip_flags["skip_run"],
                skip_flags["skip_audit"],
                audit_rounds, concurrency,
                breakpoints=bp_list,
            )
        )
    except Exception as exc:
        out.set_error(str(exc))
        out.emit()
        raise typer.Exit(code=1)

    out.set_result(result)
    out.emit()


# ---------------------------------------------------------------------------
# claw drama checkpoint-redo
# ---------------------------------------------------------------------------

@drama_app.command("checkpoint-redo")
def checkpoint_redo(
    series_id: Annotated[str, typer.Argument(help="Drama series ID.")],
    checkpoint_id: Annotated[str, typer.Argument(help="Checkpoint ID to redo from.")],
    breakpoints_opt: Annotated[
        str,
        typer.Option(
            "--breakpoints", "-B",
            help="Comma-separated checkpoint stages to pause at ('all' or 'none').",
        ),
    ] = "none",
    audit_rounds: Annotated[
        int, typer.Option("--audit-rounds", "-n", help="Max audit-regen iterations.")
    ] = 3,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help="Max parallel tasks.")
    ] = 4,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Re-execute the stage that produced a checkpoint.

    \b
    Restores series state from the checkpoint, then re-runs the stage that
    created it (and all subsequent stages).  Useful after manually adjusting
    assets (e.g. replacing a turnaround sheet or editing prompts).

    \b
    Examples:
        claw drama checkpoint-redo 97e8424712d24fb2 a1b2c3d4e5f6
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.checkpoint-redo"

    from videoclaw.drama.checkpoint import (
        CheckpointManager,
        CheckpointStage,
        resolve_skip_flags,
        restore_from_checkpoint,
    )
    from videoclaw.drama.models import DramaManager

    ckpt_mgr = CheckpointManager()
    try:
        snapshot = ckpt_mgr.load(series_id, checkpoint_id)
    except FileNotFoundError:
        console.print(f"[red]Checkpoint {checkpoint_id!r} not found.[/red]")
        out.set_error(f"Checkpoint {checkpoint_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    series = restore_from_checkpoint(snapshot)

    ep = next((e for e in series.episodes if e.number == snapshot.episode_number), None)
    if ep is None:
        console.print(f"[red]Episode {snapshot.episode_number} not found in checkpoint state.[/red]")
        raise typer.Exit(code=1)

    # Determine which stage to redo
    _STAGE_MAP = {
        "after_design": "design-characters",
        "after_refresh": "refresh-urls",
        "after_generation": "run",
        "after_audit": "audit-regen",
        "after_storyboard": "run",
        "after_video_tts": "run",
        "after_compose": "run",
    }
    redo_pipeline_stage = _STAGE_MAP.get(snapshot.stage.value, "run")
    remaining = [redo_pipeline_stage] + snapshot.remaining_stages
    skip_flags = resolve_skip_flags(remaining)

    # Parse breakpoints
    bp_list: list[CheckpointStage] | None
    if breakpoints_opt == "all":
        bp_list = None
    elif breakpoints_opt == "none":
        bp_list = []
    else:
        bp_list = [CheckpointStage(s.strip()) for s in breakpoints_opt.split(",") if s.strip()]

    console.print(
        f"[bold yellow]Redo from checkpoint {checkpoint_id} "
        f"(re-running: {redo_pipeline_stage})[/bold yellow]"
    )

    from videoclaw.cli.drama._quality import _drama_pipeline_async

    mgr = DramaManager()
    mgr.save(series)

    try:
        result = asyncio.run(
            _drama_pipeline_async(
                series, mgr, ep,
                skip_flags["skip_design"],
                skip_flags["skip_refresh"],
                skip_flags["skip_run"],
                skip_flags["skip_audit"],
                audit_rounds, concurrency,
                breakpoints=bp_list,
            )
        )
    except Exception as exc:
        out.set_error(str(exc))
        out.emit()
        raise typer.Exit(code=1)

    out.set_result(result)
    out.emit()


# ---------------------------------------------------------------------------
# claw drama checkpoint-assets
# ---------------------------------------------------------------------------

@drama_app.command("checkpoint-assets")
def checkpoint_assets(
    series_id: Annotated[str, typer.Argument(help="Drama series ID.")],
    checkpoint_id: Annotated[str, typer.Argument(help="Checkpoint ID.")],
    open_dir: Annotated[
        bool,
        typer.Option("--open", help="Open the asset directory in Finder/Explorer."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """List assets saved at a checkpoint, optionally open in file manager.

    \b
    Examples:
        claw drama checkpoint-assets 97e8424712d24fb2 a1b2c3d4e5f6
        claw drama checkpoint-assets abc123 a1b2c3 --open
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.checkpoint-assets"

    from videoclaw.drama.checkpoint import CheckpointManager

    mgr = CheckpointManager()
    try:
        snapshot = mgr.load(series_id, checkpoint_id)
    except FileNotFoundError:
        console.print(f"[red]Checkpoint {checkpoint_id!r} not found.[/red]")
        out.set_error(f"Checkpoint {checkpoint_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    # Show the semantic review directory prominently
    if snapshot.review_dir:
        from rich.panel import Panel
        review_path = Path(snapshot.review_dir)
        exists_str = "[green]exists[/green]" if review_path.is_dir() else "[red]missing[/red]"
        console.print(
            Panel(
                f"[bold]{snapshot.review_dir}[/bold]  ({exists_str})",
                title="[bold green] Review Directory [/bold green]",
                border_style="green",
            )
        )

    from rich.table import Table

    table = Table(title=f"Assets — checkpoint {checkpoint_id}")
    table.add_column("Name", style="cyan")
    table.add_column("Exists", justify="center")

    for name, abs_path_str in sorted(snapshot.assets.items()):
        abs_path = Path(abs_path_str)
        exists = "[green]Y[/green]" if abs_path.exists() else "[red]N[/red]"
        table.add_row(name, exists)

    console.print(table)

    if open_dir:
        # Open the REVIEW directory (not the checkpoints JSON dir)
        target = Path(snapshot.review_dir) if snapshot.review_dir else None
        if target and target.is_dir():
            _open_in_file_manager(target)
            console.print(f"[green]Opened {target}[/green]")
        else:
            console.print("[yellow]Review directory not found on disk.[/yellow]")

    out.set_result({"assets_count": len(snapshot.assets), "review_dir": snapshot.review_dir})
    out.emit()


def _open_in_file_manager(path: Path) -> None:
    """Open a directory in the platform file manager."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)  # noqa: S603, S607
    elif sys.platform == "win32":
        subprocess.run(["explorer", str(path)], check=False)  # noqa: S603, S607
    else:
        subprocess.run(["xdg-open", str(path)], check=False)  # noqa: S603, S607
