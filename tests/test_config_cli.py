from __future__ import annotations

import json

from typer.testing import CliRunner

from videoclaw.cli import app
from videoclaw.cli._output import get_output
from videoclaw.config import get_config


def _reset_output() -> None:
    out = get_output()
    out.json_mode = False
    out._command = ""
    out._result = None
    out._error = None
    out._exit_code = 0


def _json_envelope(stdout: str) -> dict:
    return json.loads(stdout.strip().splitlines()[-1])


def test_config_show_json_reports_deliverables_dir(tmp_path, monkeypatch) -> None:
    _reset_output()
    get_config.cache_clear()
    projects = tmp_path / "projects"
    deliverables = tmp_path / "deliverables"
    monkeypatch.setenv("VIDEOCLAW_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("VIDEOCLAW_DELIVERABLES_DIR", str(deliverables))

    try:
        result = CliRunner().invoke(app, ["--json", "config", "show"])
    finally:
        get_config.cache_clear()

    assert result.exit_code == 0
    envelope = _json_envelope(result.stdout)
    assert envelope["data"]["projects_dir"] == str(projects.resolve())
    assert envelope["data"]["deliverables_dir"] == str(deliverables.resolve())
