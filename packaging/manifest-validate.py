#!/usr/bin/env python3
"""Validate an agent-cli/v1 deployment manifest.

Usage::

    python packaging/manifest-validate.py packaging/agent-cli.yaml

Exit codes (matching the agent-cli contract):
    0 — manifest valid
    2 — usage error (missing argument, file not found)
    1 — manifest invalid (missing / malformed required field)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Required (R018 minimum-fields) plus optional surface that still needs
# type-checking when present.
REQUIRED = {
    "schema": str,
    "name": str,
    "binary": str,
    "version": str,
    "commands": list,
    "config_dir": str,
    "health_check": dict,
}

OPTIONAL_TYPES = {
    "description": str,
    "env_prefix": str,
    "mcp": dict,
    "acp": dict,
    "distribution": list,
}


def _check_required(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_type in REQUIRED.items():
        if key not in manifest:
            errors.append(f"missing required field: {key!r}")
            continue
        if not isinstance(manifest[key], expected_type):
            errors.append(
                f"field {key!r} expected {expected_type.__name__}, "
                f"got {type(manifest[key]).__name__}"
            )
    if manifest.get("schema") != "agent-cli/v1":
        errors.append(
            f"schema field must be 'agent-cli/v1', got {manifest.get('schema')!r}"
        )
    return errors


def _check_optional(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_type in OPTIONAL_TYPES.items():
        if key in manifest and not isinstance(manifest[key], expected_type):
            errors.append(
                f"field {key!r} expected {expected_type.__name__} when present, "
                f"got {type(manifest[key]).__name__}"
            )
    return errors


def _check_commands(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    commands = manifest.get("commands", [])
    if not isinstance(commands, list) or not commands:
        return ["commands must be a non-empty list"]
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict):
            errors.append(f"commands[{i}] must be a mapping")
            continue
        for key in ("name", "path"):
            if key not in cmd or not isinstance(cmd[key], str):
                errors.append(f"commands[{i}] missing or non-string {key!r}")
    return errors


def _check_health_check(manifest: dict[str, Any]) -> list[str]:
    hc = manifest.get("health_check", {})
    if not isinstance(hc, dict):
        return ["health_check must be a mapping"]
    if "command" not in hc or not isinstance(hc["command"], str):
        return ["health_check.command must be a non-empty string"]
    return []


def validate(manifest: dict[str, Any]) -> list[str]:
    return (
        _check_required(manifest)
        + _check_optional(manifest)
        + _check_commands(manifest)
        + _check_health_check(manifest)
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <manifest.yaml>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.is_file():
        print(f"manifest not found: {path}", file=sys.stderr)
        return 2

    try:
        import yaml
    except ImportError:
        print("PyYAML required: pip install pyyaml", file=sys.stderr)
        return 1

    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        print(f"manifest must be a YAML mapping, got {type(manifest).__name__}", file=sys.stderr)
        return 1

    errors = validate(manifest)
    if errors:
        print(f"INVALID: {len(errors)} error(s) in {path}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"VALID: {path} conforms to agent-cli/v1")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
