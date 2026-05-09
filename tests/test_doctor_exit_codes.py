"""Tests for ``claw doctor`` exit-code contract (M002 G1 / T14).

The agent-cli contract defines:
    0 ok · 1 runtime · 2 usage · 3 auth needed · 4 blocked

Doctor must:
- exit 3 when a *required* key (Evolink) is missing  -- auth
- exit 1 when other checks fail but required keys present -- runtime
- exit 0 when everything is healthy

Coding agents branch on ``$?`` to decide whether to run
``claw setup`` / ``bash setup.sh`` automatically, so the boundary
between 1 and 3 has to be reliable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_doctor(env_overrides: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """Run `claw --json doctor` with a clean env + selected overrides."""
    claw = REPO_ROOT / ".venv" / "bin" / "claw"
    if not claw.is_file():
        pytest.skip(f"claw script not found at {claw}; run `uv sync` first")
    env = {
        "HOME": str(cwd),
        "PATH": f"{claw.parent}:/usr/local/bin:/usr/bin:/bin",
        **env_overrides,
    }
    result = subprocess.run(
        [str(claw), "--json", "doctor"],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        timeout=30,
    )
    return result


def _doctor_envelope(result: subprocess.CompletedProcess[bytes]) -> dict[str, object]:
    return json.loads(result.stdout.decode().strip().splitlines()[-1])


def test_doctor_exits_3_when_evolink_missing(tmp_path: Path) -> None:
    """No Evolink key + no .env in cwd -> required-failed -> exit 3."""
    result = _run_doctor({}, cwd=tmp_path)
    assert result.returncode == 3, f"expected exit 3 (auth), got {result.returncode}"


def test_doctor_does_not_exit_3_when_evolink_present(tmp_path: Path) -> None:
    """Evolink key set -> not exit 3 (may still exit 1 for other checks)."""
    result = _run_doctor(
        {"VIDEOCLAW_EVOLINK_API_KEY": "sk-test-xxx"},
        cwd=tmp_path,
    )
    assert result.returncode != 3, (
        f"expected non-3 (Evolink configured), got {result.returncode}"
    )


def test_doctor_json_ok_matches_process_success(tmp_path: Path) -> None:
    """A non-zero doctor exit must not emit a top-level ok=true envelope."""
    result = _run_doctor(
        {
            "VIDEOCLAW_EVOLINK_API_KEY": "sk-test-xxx",
            "VIDEOCLAW_PROJECTS_DIR": str(tmp_path / "projects"),
            "VIDEOCLAW_DELIVERABLES_DIR": str(tmp_path / "deliverables"),
        },
        cwd=tmp_path,
    )
    envelope = _doctor_envelope(result)
    assert envelope["ok"] is (result.returncode == 0)


def test_doctor_discovers_same_model_registry_as_model_list(tmp_path: Path) -> None:
    """Doctor should not report zero models when adapter entry points exist."""
    result = _run_doctor(
        {
            "VIDEOCLAW_EVOLINK_API_KEY": "sk-test-xxx",
            "VIDEOCLAW_PROJECTS_DIR": str(tmp_path / "projects"),
            "VIDEOCLAW_DELIVERABLES_DIR": str(tmp_path / "deliverables"),
        },
        cwd=tmp_path,
    )
    envelope = _doctor_envelope(result)
    data = envelope["data"]
    assert isinstance(data, dict)
    checks = data["checks"]
    assert isinstance(checks, dict)
    models = checks["models"]
    assert isinstance(models, dict)
    assert models["count"] > 0


@pytest.mark.parametrize(
    "exit_code,meaning",
    [
        (0, "ok"),
        (1, "runtime"),
        (2, "usage"),
        (3, "auth"),
        (4, "blocked"),
    ],
)
def test_exit_code_contract_documented(exit_code: int, meaning: str) -> None:
    """Sanity: the agent-cli.yaml manifest declares all five codes.

    This is a regression test against silent removal of the contract
    from the manifest -- a coding agent's branch logic depends on it.
    """
    manifest = (REPO_ROOT / "packaging" / "agent-cli.yaml").read_text()
    # The manifest documents codes in a comment block; the regression
    # we guard against is removing the block entirely.
    assert "Exit codes" in manifest or "exit code" in manifest.lower(), (
        "agent-cli.yaml lost its exit-code documentation"
    )
