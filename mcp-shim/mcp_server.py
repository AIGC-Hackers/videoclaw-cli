"""FastMCP stdio server exposing videoclaw read-only surface.

Run via ``python -m mcp_server`` or the installed ``videoclaw-mcp-server`` script.

Tools surface (all read-only — no mutation of videoclaw state):
- ``list_drama_series`` → series IDs persisted under ``$projects_dir/dramas/``.
- ``get_drama_series`` → metadata for one series (title, status, episode count).
- ``list_video_models`` → registered video adapters via ``ModelRegistry``.
- ``get_videoclaw_version`` → installed videoclaw version string.

The shim imports videoclaw as a library and never edits ``src/videoclaw/**`` —
per the videoclaw-packaging blueprint write-scope lock.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

mcp: FastMCP = FastMCP("videoclaw")


@mcp.tool
def list_drama_series() -> list[str]:
    """Return drama series IDs available on this host."""
    from videoclaw.drama.models import DramaManager

    return DramaManager().list_series()


@mcp.tool
def get_drama_series(series_id: str) -> dict[str, Any]:
    """Return metadata for one drama series."""
    from videoclaw.drama.models import DramaManager

    series = DramaManager().load(series_id)
    return {
        "series_id": series.series_id,
        "title": getattr(series, "title", None),
        "status": str(getattr(series, "status", "")),
        "episode_count": len(getattr(series, "episodes", []) or []),
    }


@mcp.tool
def list_video_models() -> list[dict[str, Any]]:
    """Return registered video-model adapters."""
    from videoclaw.models.registry import get_registry

    registry = get_registry()
    return registry.list_models() if hasattr(registry, "list_models") else []


@mcp.tool
def get_videoclaw_version() -> str:
    """Return installed videoclaw version."""
    import videoclaw

    return getattr(videoclaw, "__version__", "unknown")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
