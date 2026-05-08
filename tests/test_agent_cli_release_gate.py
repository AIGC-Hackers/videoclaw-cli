from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agent-cli-release-gate.sh"


def _run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_agent_cli_release_gate_is_root_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_agent_cli_release_gate_help_documents_agent_contract() -> None:
    result = _run_gate("--help")

    assert result.returncode == 0, result.stderr
    assert "changed" in result.stdout
    assert "version" in result.stdout
    assert "release" in result.stdout
    assert "setup" in result.stdout
    assert "package" in result.stdout
    assert "--print-plan" in result.stdout
    assert "AGENT_CLI_REAL_VIDEO" in result.stdout
    assert "packaged claw CLI" in result.stdout


def test_ci_plan_is_deterministic_and_network_free() -> None:
    result = _run_gate("ci", "--print-plan")

    assert result.returncode == 0, result.stderr
    assert "uv run pytest tests/" in result.stdout
    assert "uv build --wheel" in result.stdout
    assert "claw --json setup --dry-run --no-npx" in result.stdout
    assert "claw --json setup --dry-run >" not in result.stdout
    assert "E2E_REAL_VIDEO=1" not in result.stdout


def test_setup_plan_documents_dependency_bootstrap() -> None:
    result = _run_gate("setup", "--print-plan", "--with-npx", "--with-bin", "--with-docker")

    assert result.returncode == 0, result.stderr
    assert "uv python install 3.12" in result.stdout
    assert "uv sync --extra dev" in result.stdout
    assert "command -v npx" in result.stdout
    assert "uv pip install pyinstaller" in result.stdout
    assert "docker version" in result.stdout
    assert "uv build --wheel" not in result.stdout


def test_package_plan_runs_one_command_recommended_flow() -> None:
    result = _run_gate("package", "--print-plan")

    assert result.returncode == 0, result.stderr
    assert "uv python install 3.12" in result.stdout
    assert "uv sync --extra dev" in result.stdout
    assert "STAGE_BIN=1 STAGE_DOCKER=0 bash packaging/dist-verify.sh" in result.stdout
    assert "claw --json setup --dry-run --no-npx" in result.stdout
    assert "claw --json setup --dry-run >" in result.stdout
    assert "npx setup JSON installer == npx-skills" in result.stdout
    assert "E2E_REAL_VIDEO=1" not in result.stdout


def test_version_plan_runs_distribution_and_packaged_cli_checks() -> None:
    result = _run_gate("version", "--print-plan")

    assert result.returncode == 0, result.stderr
    assert "packaging/dist-verify.sh" in result.stdout
    assert "STAGE_DOCKER=0" in result.stdout
    assert "claw version" in result.stdout
    assert "claw --json setup --dry-run --no-npx" in result.stdout
    assert "python fallback setup JSON installer == python-fallback" in result.stdout


def test_release_plan_exposes_optional_registry_and_real_video_gates() -> None:
    result = _run_gate(
        "release",
        "--print-plan",
        "--with-npx",
        "--with-real-llm",
        "--with-real-video",
    )

    assert result.returncode == 0, result.stderr
    assert "claw --json setup --dry-run >" in result.stdout
    assert "npx setup JSON installer == npx-skills" in result.stdout
    assert "E2E_REAL_LLM=1" in result.stdout
    assert "E2E_REAL_VIDEO=1" in result.stdout
    assert "tests-external/test_e2e_first_3_shots.py::test_T9" in result.stdout
