#!/usr/bin/env python3
"""Validate the videoclaw skills/ directory.

Mirrors ``packaging/manifest-validate.py`` for ``packaging/agent-cli.yaml``:
checks that every skill subdirectory carries a well-formed ``SKILL.md`` so
``claw setup`` (M002 task T8) can rely on the schema when copying skills
into coding-agent skill paths.

Usage::

    python packaging/skills-validate.py skills/

Exit codes (matching the agent-cli contract):
    0 — every skill valid
    2 — usage error (missing argument, path not found)
    1 — at least one skill invalid
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_FRONTMATTER_KEYS = {
    "name": str,
    "description": str,
    "metadata": dict,
}
REQUIRED_METADATA_KEYS = {
    "author": str,
    "license": str,
    "version": str,
    "requires": dict,
}
REQUIRED_REQUIRES_KEYS = {
    "bins": list,
    "install": str,
}


def _read_pyproject_version(repo_root: Path) -> str | None:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    return None


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (yaml_text, body) or None if no frontmatter."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end], text[end + 5 :]


def _load_yaml() -> Any:
    try:
        import yaml
    except ImportError:
        print("PyYAML required: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    return yaml


def _validate_skill(skill_dir: Path, expected_version: str | None) -> list[str]:
    yaml = _load_yaml()
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]

    text = skill_md.read_text(encoding="utf-8")
    parts = _split_frontmatter(text)
    if parts is None:
        return [
            f"{skill_dir.name}/SKILL.md: missing or malformed YAML frontmatter "
            "(must start with '---\\n')"
        ]

    yaml_text, body = parts
    try:
        front = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:  # type: ignore[attr-defined]
        return [f"{skill_dir.name}/SKILL.md: frontmatter YAML parse error: {e}"]

    if not isinstance(front, dict):
        return [f"{skill_dir.name}/SKILL.md: frontmatter must be a mapping"]

    for key, expected_type in REQUIRED_FRONTMATTER_KEYS.items():
        if key not in front:
            errors.append(f"{skill_dir.name}/SKILL.md: missing required field {key!r}")
        elif not isinstance(front[key], expected_type):
            errors.append(
                f"{skill_dir.name}/SKILL.md: field {key!r} must be "
                f"{expected_type.__name__}, got {type(front[key]).__name__}"
            )

    name = front.get("name")
    if isinstance(name, str) and name != skill_dir.name:
        errors.append(
            f"{skill_dir.name}/SKILL.md: frontmatter name {name!r} != "
            f"directory name {skill_dir.name!r}"
        )

    metadata = front.get("metadata")
    if isinstance(metadata, dict):
        for key, expected_type in REQUIRED_METADATA_KEYS.items():
            if key not in metadata:
                errors.append(f"{skill_dir.name}/SKILL.md: metadata missing {key!r}")
            elif not isinstance(metadata[key], expected_type):
                errors.append(
                    f"{skill_dir.name}/SKILL.md: metadata.{key} must be "
                    f"{expected_type.__name__}, got {type(metadata[key]).__name__}"
                )
        version = metadata.get("version")
        if isinstance(version, str) and expected_version and version != expected_version:
            errors.append(
                f"{skill_dir.name}/SKILL.md: metadata.version {version!r} != "
                f"pyproject.toml version {expected_version!r}"
            )
        requires = metadata.get("requires")
        if isinstance(requires, dict):
            for key, expected_type in REQUIRED_REQUIRES_KEYS.items():
                if key not in requires:
                    errors.append(
                        f"{skill_dir.name}/SKILL.md: metadata.requires missing {key!r}"
                    )
                elif not isinstance(requires[key], expected_type):
                    errors.append(
                        f"{skill_dir.name}/SKILL.md: metadata.requires.{key} must be "
                        f"{expected_type.__name__}, got {type(requires[key]).__name__}"
                    )
            bins = requires.get("bins")
            if isinstance(bins, list) and "claw" not in bins:
                errors.append(
                    f"{skill_dir.name}/SKILL.md: metadata.requires.bins must include 'claw'"
                )

    if not body.strip():
        errors.append(f"{skill_dir.name}/SKILL.md: body is empty")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <skills-dir>", file=sys.stderr)
        return 2

    skills_root = Path(argv[1])
    if not skills_root.is_dir():
        print(f"skills directory not found: {skills_root}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    expected_version = _read_pyproject_version(repo_root)
    if expected_version is None:
        print(
            f"warning: could not read version from {repo_root / 'pyproject.toml'}; "
            "skipping version-consistency check",
            file=sys.stderr,
        )

    skill_dirs = sorted(
        d for d in skills_root.iterdir() if d.is_dir() and d.name.startswith("videoclaw-")
    )
    if not skill_dirs:
        print(f"INVALID: no videoclaw-* skills found under {skills_root}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for skill_dir in skill_dirs:
        all_errors.extend(_validate_skill(skill_dir, expected_version))

    if all_errors:
        print(
            f"INVALID: {len(all_errors)} error(s) across {len(skill_dirs)} skill(s):",
            file=sys.stderr,
        )
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"VALID: {len(skill_dirs)} skill(s) under {skills_root} conform "
        f"(version {expected_version})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
