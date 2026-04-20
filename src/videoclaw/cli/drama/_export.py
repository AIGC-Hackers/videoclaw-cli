"""``claw drama export`` — rebuild the human-readable review directory.

Exports an episode's deliverables into the canonical review layout shared
with the checkpoint system::

    docs/deliverables/{drama_slug}/{episode_slug}/
    ├── _REVIEW.txt
    ├── storyboard.md
    ├── characters/   (symlinks, if present)
    ├── scenes/       (symlinks, if present)
    ├── audio/        (symlinks, if present)
    ├── videos/       (symlinks, if present)
    ├── audit/        (symlinks, if present)
    └── final/        (symlinks, if present)

Historically this command wrote its own stage-numbered layout
(``00_metadata/``, ``01_script/``, …, ``10_audit/``) that conflicted with
the checkpoint system.  It now delegates to
:func:`videoclaw.drama.checkpoint.build_review_dir` so there is exactly
one on-disk shape.

With ``--copy``, symlinks are dereferenced into physical files after the
build — used when packaging deliverables for clients who can't follow
local symlinks.  With ``--publish``, the composed final video is pushed
to a platform after export completes.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Annotated

import typer

from videoclaw.cli._app import (
    configure_logging,
    drama_app,
    show_banner,
)
from videoclaw.cli._output import get_console, get_output


@drama_app.command("series-view")
def drama_series_view(
    series_id: Annotated[
        str, typer.Argument(help="Drama series ID to rebuild the series view for.")
    ],
    output_dir: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="Override the deliverables root (default: config.deliverables_dir).",
        ),
    ] = "",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Rebuild the series-level view (full, idempotent).

    Creates / refreshes ``<deliverables_dir>/<series_slug>/``:
    ``_SERIES.md``, ``characters/``, ``scenes/``. Independent of the
    checkpoint flow — useful for manual recovery or ad-hoc refresh.
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.series-view"

    from videoclaw.config import get_config
    from videoclaw.drama.checkpoint import build_series_view
    from videoclaw.drama.models import DramaManager

    cfg = get_config()
    mgr = DramaManager()
    try:
        series = mgr.load(series_id)
    except FileNotFoundError:
        console.print(f"[red]Series {series_id!r} not found.[/red]")
        out.set_error(f"Series {series_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    deliverables_dir = Path(output_dir) if output_dir else cfg.deliverables_dir
    series_root = build_series_view(
        series,
        deliverables_dir=deliverables_dir,
        projects_dir=cfg.projects_dir,
    )
    console.print(f"[bold green]Series view rebuilt:[/bold green] {series_root}")
    out.set_result({
        "series_id": series_id,
        "series_root": str(series_root),
    })
    out.emit()


def _materialize_symlinks(review_dir: Path) -> int:
    """Replace every symlink under *review_dir* with a real file copy.

    Returns the number of symlinks materialized.  Used by ``--copy`` so
    the exported directory is self-contained (portable across machines).
    """
    count = 0
    for path in review_dir.rglob("*"):
        if path.is_symlink():
            target = path.resolve()
            if not target.is_file():
                continue
            path.unlink()
            shutil.copy2(target, path)
            count += 1
    return count


@drama_app.command("export")
def drama_export(
    series_id: Annotated[
        str, typer.Argument(help="Drama series ID.")
    ],
    episode: Annotated[
        int,
        typer.Option("--episode", "-e", help="Episode number (default: all)."),
    ] = 0,
    output_dir: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help=(
                "Override the deliverables root "
                "(default: config.deliverables_dir → docs/deliverables)."
            ),
        ),
    ] = "",
    copy_mode: Annotated[
        bool,
        typer.Option(
            "--copy",
            help=(
                "Replace symlinks with physical file copies so the "
                "exported directory is self-contained (client delivery)."
            ),
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v")
    ] = False,
    publish: Annotated[
        bool,
        typer.Option(
            "--publish",
            help="After export, publish the final video to a platform.",
        ),
    ] = False,
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            help="Target platform for publishing (youtube, tiktok, bilibili).",
        ),
    ] = "youtube",
) -> None:
    """Export an episode's deliverables in the canonical review layout.

    \b
    Produces the same directory structure as the checkpoint system, so
    auditors see one shape regardless of whether the assets were built
    incrementally via ``claw drama run`` or re-exported after the fact.

    \b
    Examples:
        claw drama export 97e8424712d24fb2
        claw drama export abc123 -e 1
        claw drama export abc123 -e 1 --copy           # self-contained bundle
        claw drama export abc123 --publish --platform tiktok
    """
    configure_logging(verbose)
    show_banner()
    console = get_console()
    out = get_output()
    out._command = "drama.export"

    from videoclaw.config import get_config
    from videoclaw.drama.checkpoint import build_review_dir, build_series_view
    from videoclaw.drama.models import DramaManager

    cfg = get_config()
    mgr = DramaManager()

    try:
        series = mgr.load(series_id)
    except FileNotFoundError:
        console.print(f"[red]Series {series_id!r} not found.[/red]")
        out.set_error(f"Series {series_id!r} not found.")
        out.emit()
        raise typer.Exit(code=1)

    # Resolve deliverables root
    deliverables_dir = Path(output_dir) if output_dir else cfg.deliverables_dir
    projects_dir = cfg.projects_dir

    # Select episodes
    if episode > 0:
        episodes = [ep for ep in series.episodes if ep.number == episode]
        if not episodes:
            console.print(f"[red]Episode {episode} not found.[/red]")
            raise typer.Exit(code=1)
    else:
        episodes = series.episodes

    console.print(
        f"[bold cyan]Exporting deliverables:[/bold cyan] "
        f"{series.title or series_id}  →  {deliverables_dir}"
    )

    # Ensure the series-level view is fresh before the per-episode review
    # dirs symlink back through it. Idempotent and cheap; explicit here so
    # export works even when drama_run hasn't been invoked recently.
    build_series_view(
        series,
        deliverables_dir=deliverables_dir,
        projects_dir=projects_dir,
    )

    review_dirs: list[Path] = []
    total_symlinks_copied = 0
    for ep in episodes:
        review_dir = build_review_dir(
            series,
            ep,
            deliverables_dir=deliverables_dir,
            projects_dir=projects_dir,
        )
        review_dirs.append(review_dir)
        console.print(f"  [green]ep{ep.number:02d}[/green] → {review_dir}")

        if copy_mode:
            materialized = _materialize_symlinks(review_dir)
            total_symlinks_copied += materialized
            console.print(
                f"    [cyan]materialized[/cyan] {materialized} symlinks "
                f"into physical copies"
            )

    # ── Publish bridge ──────────────────────────────────────────────────
    publish_result_data: dict[str, object] | None = None
    if publish:
        platform_lower = platform.lower()
        valid_platforms = ("youtube", "tiktok", "bilibili")
        if platform_lower not in valid_platforms:
            console.print(
                f"[red]Unknown platform {platform!r}. "
                f"Choose from: {', '.join(valid_platforms)}[/red]"
            )
            raise typer.Exit(code=1)

        # Find the final video in the first episode's final/ directory
        final_video: Path | None = None
        for review_dir in review_dirs:
            final_dir = review_dir / "final"
            if final_dir.is_dir():
                candidates = sorted(final_dir.glob("*.mp4"))
                if candidates:
                    final_video = candidates[0]
                    break

        if final_video is None:
            console.print(
                "[yellow]No final video found in any episode's final/ "
                "directory. Skipping publish.[/yellow]"
            )
        else:
            console.print(
                f"\n[bold cyan]Publishing to {platform_lower}:[/bold cyan] "
                f"{final_video.name}"
            )

            from videoclaw.publishers.base import PublishRequest, PublishStatus

            ep0 = episodes[0]
            ep_title = (
                ep0.title if hasattr(ep0, "title") and ep0.title
                else f"Episode {ep0.number}"
            )
            title = f"{series.title} - {ep_title}" if series.title else ep_title
            description = series.metadata.get("description", "")

            request = PublishRequest(
                video_path=final_video,
                title=title,
                description=description,
            )

            from videoclaw.publishers.base import Publisher

            publisher: Publisher
            if platform_lower == "youtube":
                from videoclaw.publishers.youtube import YouTubePublisher
                publisher = YouTubePublisher()
            elif platform_lower == "tiktok":
                from videoclaw.publishers.tiktok import TikTokPublisher
                publisher = TikTokPublisher()
            else:
                from videoclaw.publishers.bilibili import BilibiliPublisher
                publisher = BilibiliPublisher()

            result = asyncio.run(publisher.publish(request))

            if result.status == PublishStatus.FAILED:
                console.print(
                    f"[yellow]Publisher for {platform_lower} is not yet "
                    f"implemented. Video exported to {final_video}.[/yellow]"
                )
            elif result.status == PublishStatus.PUBLISHED:
                console.print(
                    f"[bold green]Published:[/bold green] {result.url}"
                )
            else:
                console.print(
                    f"[cyan]Publish status:[/cyan] {result.status.value}"
                )

            publish_result_data = {
                "platform": result.platform,
                "status": result.status.value,
                "url": result.url,
                "error": result.error,
            }

    # ── Summary ─────────────────────────────────────────────────────────
    console.print(
        f"\n[bold green]Export complete:[/bold green] "
        f"{len(review_dirs)} episode(s)"
    )
    if copy_mode:
        console.print(
            f"  physical copies: {total_symlinks_copied} files"
        )

    out.set_result({
        "series_id": series_id,
        "deliverables_dir": str(deliverables_dir),
        "review_dirs": [str(d) for d in review_dirs],
        "copy_mode": copy_mode,
        "symlinks_materialized": total_symlinks_copied,
        **({"publish": publish_result_data} if publish_result_data else {}),
    })
    out.emit()
