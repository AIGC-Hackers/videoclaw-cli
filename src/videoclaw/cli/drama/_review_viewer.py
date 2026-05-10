"""Helpers for opening human review surfaces."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path


def storyboard_html_for(review_dir: Path) -> Path | None:
    """Return the storyboard HTML path when the review directory has one."""
    html = review_dir / "storyboard.html"
    return html if html.is_file() else None


def open_review_surface(review_dir: Path) -> Path:
    """Open ``storyboard.html`` in a browser, falling back to the directory."""
    html = storyboard_html_for(review_dir)
    if html is not None:
        webbrowser.open(html.resolve().as_uri())
        return html

    _open_in_file_manager(review_dir)
    return review_dir


def _open_in_file_manager(path: Path) -> None:
    """Open a directory in the platform file manager."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
