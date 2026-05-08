"""PyInstaller / `python -m` entry point for the claw binary.

Lives under packaging/ rather than src/videoclaw/ to honor the blueprint's
write-scope lock — zero edits under src/videoclaw/.
"""

from __future__ import annotations


def main() -> None:
    from videoclaw.cli import app

    app()


if __name__ == "__main__":
    main()
