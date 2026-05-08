from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from videoclaw.cli import app
from videoclaw.cli._output import get_output
from videoclaw.generation import byteplus_image, evolink_image, gemini_image
from videoclaw.generation.gemini_image import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL


def _reset_output() -> None:
    out = get_output()
    out.json_mode = False
    out._command = ""
    out._result = None
    out._error = None
    out._exit_code = 0


def _json_envelope(stdout: str) -> dict[str, Any]:
    return json.loads(stdout.strip().splitlines()[-1])


def test_image_help_exposes_provider_model_resolution_and_quality_options() -> None:
    _reset_output()

    result = CliRunner().invoke(app, ["image", "--help"])

    assert result.exit_code == 0
    assert "--provider" in result.stdout
    assert "--model" in result.stdout
    assert "--resolution" in result.stdout
    assert "--quality" in result.stdout


def test_drama_design_commands_expose_image_provider_overrides() -> None:
    _reset_output()

    runner = CliRunner()
    for command in ("design-characters", "design-scenes", "design-cover"):
        result = runner.invoke(app, ["drama", command, "--help"])

        assert result.exit_code == 0
        assert "--image-provider" in result.stdout
        assert "--image-model" in result.stdout


def test_image_defaults_to_evolink_gpt_image_2_1k_medium(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []
    generated = tmp_path / "generated.png"

    class FakeEvolinkImageGenerator:
        def __init__(self) -> None:
            calls.append({"provider": "evolink-init"})

        async def generate(self, **kwargs: Any) -> Path:
            calls.append({"provider": "evolink-generate", **kwargs})
            generated.write_bytes(b"png")
            return generated

    class FakeGeminiImageGenerator:
        async def generate(self, **kwargs: Any) -> Path:
            raise AssertionError("default image provider should not be gemini")

    monkeypatch.setattr(evolink_image, "EvolinkImageGenerator", FakeEvolinkImageGenerator)
    monkeypatch.setattr(gemini_image, "GeminiImageGenerator", FakeGeminiImageGenerator)

    _reset_output()
    output = tmp_path / "out.png"
    result = CliRunner().invoke(
        app,
        ["--json", "image", "cinematic portrait", "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    assert calls[-1]["prompt"] == "cinematic portrait"
    assert calls[-1]["model"] == "gpt-image-2"
    assert calls[-1]["size"] == "3:4"
    assert calls[-1]["resolution"] == "1K"
    assert calls[-1]["quality"] == "medium"

    envelope = _json_envelope(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["provider"] == "evolink"
    assert envelope["data"]["model"] == "gpt-image-2"
    assert envelope["data"]["resolution"] == "1K"
    assert envelope["data"]["quality"] == "medium"


def test_image_keeps_byteplus_model_override_compatibility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []
    generated = tmp_path / "byteplus.png"

    class FakeBytePlusImageGenerator:
        def __init__(self, *, model: str) -> None:
            calls.append({"provider": "byteplus-init", "model": model})

        async def generate(self, **kwargs: Any) -> Path:
            calls.append({"provider": "byteplus-generate", **kwargs})
            generated.write_bytes(b"png")
            return generated

    monkeypatch.setattr(byteplus_image, "BytePlusImageGenerator", FakeBytePlusImageGenerator)

    _reset_output()
    output = tmp_path / "out.png"
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "image",
            "scene concept",
            "--provider",
            "byteplus",
            "--model",
            "seedream-5.0-lite",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls[0] == {"provider": "byteplus-init", "model": "seedream-5.0-lite"}
    assert calls[-1]["prompt"] == "scene concept"
    assert calls[-1]["size"] == "3:4"

    envelope = _json_envelope(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["provider"] == "byteplus"
    assert envelope["data"]["model"] == "seedream-5.0-lite"


def test_image_keeps_gemini_provider_default_model_compatibility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []
    generated = tmp_path / "gemini.png"

    class FakeGeminiImageGenerator:
        def __init__(self, *, model: str = GEMINI_DEFAULT_MODEL) -> None:
            calls.append({"provider": "gemini-init", "model": model})

        async def generate(self, **kwargs: Any) -> Path:
            calls.append({"provider": "gemini-generate", **kwargs})
            generated.write_bytes(b"png")
            return generated

    monkeypatch.setattr(gemini_image, "GeminiImageGenerator", FakeGeminiImageGenerator)

    _reset_output()
    output = tmp_path / "out.png"
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "image",
            "legacy image",
            "--provider",
            "gemini",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls[0] == {"provider": "gemini-init", "model": GEMINI_DEFAULT_MODEL}
    assert calls[-1]["prompt"] == "legacy image"
    assert calls[-1]["size"] == "3:4"

    envelope = _json_envelope(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["provider"] == "gemini"
    assert envelope["data"]["model"] == GEMINI_DEFAULT_MODEL
