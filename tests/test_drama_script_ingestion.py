from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from videoclaw.cli import app
from videoclaw.cli._output import get_output
from videoclaw.drama.models import DramaSeries
from videoclaw.drama.planner import DramaPlanner


def _reset_output() -> None:
    out = get_output()
    out.json_mode = False
    out._command = ""
    out._result = None
    out._error = None
    out._exit_code = 0


def _json_envelope(stdout: str) -> dict[str, Any]:
    return json.loads(stdout.strip().splitlines()[-1])


def _pdf_bytes(page_texts: list[str]) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
    ]
    kids = " ".join(f"{3 + index * 2} 0 R" for index in range(len(page_texts)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_texts)} >>".encode())

    for index, text in enumerate(page_texts):
        page_id = 3 + index * 2
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
                f"/Resources << /Font << /F1 99 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 72 Td ({escaped}) Tj ET".encode()
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_object_id = 99

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id, body in zip([1, 2, *range(3, 3 + len(page_texts) * 2), font_object_id], objects):
        offsets[object_id] = len(pdf)
        pdf.extend(f"{object_id} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    size = font_object_id + 1
    pdf.extend(f"xref\n0 {size}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for object_id in range(1, size):
        if object_id in offsets:
            pdf.extend(f"{offsets[object_id]:010d} 00000 n \n".encode())
        else:
            pdf.extend(b"0000000000 65535 f \n")
    pdf.extend(
        (
            f"trailer\n<< /Size {size} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(pdf)


def test_read_script_file_extracts_pdf_text_in_page_order(tmp_path: Path) -> None:
    pdf_path = tmp_path / "script.pdf"
    pdf_path.write_bytes(_pdf_bytes(["PAGE ONE HOOK", "PAGE TWO PAYOFF"]))

    text = DramaPlanner.read_script_file(pdf_path)

    assert "PAGE ONE HOOK" in text
    assert "PAGE TWO PAYOFF" in text
    assert text.index("PAGE ONE HOOK") < text.index("PAGE TWO PAYOFF")


def test_read_script_file_rejects_pdf_without_extractable_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(_pdf_bytes([""]))

    try:
        DramaPlanner.read_script_file(pdf_path)
    except ValueError as exc:
        assert "No extractable text found in PDF" in str(exc)
    else:
        raise AssertionError("blank PDF should be rejected")


def test_read_script_file_rejects_unsupported_binary_format(tmp_path: Path) -> None:
    source = tmp_path / "script.rtf"
    source.write_bytes(b"{\\rtf1\\ansi invalid \\xff}")

    try:
        DramaPlanner.read_script_file(source)
    except ValueError as exc:
        assert "Unsupported script file format: .rtf" in str(exc)
        assert ".docx, .txt, .pdf" in str(exc)
    else:
        raise AssertionError("unsupported extension should be rejected")


def test_drama_import_help_lists_pdf_as_supported_format() -> None:
    _reset_output()

    result = CliRunner().invoke(app, ["drama", "import", "--help"])

    assert result.exit_code == 0
    assert ".pdf" in result.stdout


def test_info_json_advertises_pdf_import_support() -> None:
    _reset_output()

    result = CliRunner().invoke(app, ["--json", "info"])

    assert result.exit_code == 0
    envelope = _json_envelope(result.stdout)
    import_command = next(
        cmd for cmd in envelope["data"]["commands"]["drama"]
        if cmd["command"] == "claw drama import"
    )
    assert ".pdf" in import_command["description"]


def test_import_text_keeps_preamble_and_first_episode_only() -> None:
    source = (
        "人物小传：\n"
        "苏念念：带货主播。\n\n"
        "第一集\n"
        "场 1-1 日/外 居民楼下\n"
        "苏念念：有瓜吃！\n\n"
        "第二集\n"
        "场 2-1 日/内 苏家客厅\n"
        "陆北辰：先出去吃点。\n"
    )

    selected = DramaPlanner._select_import_episode_text(source)

    assert "人物小传" in selected
    assert "第一集" in selected
    assert "苏念念：有瓜吃！" in selected
    assert "第二集" not in selected
    assert "陆北辰：先出去吃点。" not in selected


def test_infer_title_from_script_prefers_declared_title() -> None:
    script = "人物小传\n剧名：《恋爱好啊，得谈！》\n第一集\n场 1-1"

    assert DramaPlanner.infer_title_from_script(script) == "恋爱好啊，得谈！"


def test_script_text_to_llm_html_escapes_source_text() -> None:
    html = DramaPlanner.script_text_to_llm_html(
        "剧名：《测试》\n苏念念：1 < 2",
        language="zh",
        source_format="txt",
    )

    assert 'data-videoclaw-format="script-source-v1"' in html
    assert "<h1>测试</h1>" in html
    assert "苏念念：1 &lt; 2" in html


def test_required_array_validation_handles_null_values() -> None:
    try:
        DramaPlanner._validate_required_arrays(
            {"episodes": [{"number": 1, "scenes": None}]},
            ("episodes", "episodes.scenes"),
        )
    except ValueError as exc:
        assert "episodes.scenes" in str(exc)
    else:
        raise AssertionError("null scenes should be treated as missing")


@pytest.mark.asyncio
async def test_import_complete_script_uses_structured_scene_parser_without_llm() -> None:
    class FailingLLM:
        async def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
            raise AssertionError("structured Chinese scripts should not need LLM JSON")

    script = (
        "人物小传：\n"
        "苏念念（女一）：嘴硬心软的带货主播。\n"
        "第二行继续描述她渴望被爱的内心。\n"
        "陆北辰（男一）：航天教授。\n\n"
        "第一集\n"
        "场 1-1 日/外 居民楼下\n"
        "△ 苏念念走在老小区的路上。\n"
        "苏念念：阿姨，出啥事儿了？\n"
        "邻居阿姨：有人上门提亲！\n"
        "△ 苏念念跑上楼。\n"
        "场 1-2 日/内 苏家客厅\n"
        "△ 客厅里坐满亲戚。\n"
        "姑姑：来来来，我们家的心意。\n"
        "苏念念（os）：谁来救救我！\n"
        "陆北辰：不舒服？还是低血糖？\n"
    )
    planner = DramaPlanner(llm=FailingLLM())  # type: ignore[arg-type]
    series = DramaSeries(series_id="test", title="恋爱好啊", language="zh", model_id="mock")

    imported = await planner.import_complete_script(series, script)

    assert imported.episodes[0].scenes
    assert imported.episodes[0].scenes[0].dialogue
    assert {c.name for c in imported.characters} >= {"苏念念", "陆北辰"}
    su = next(c for c in imported.characters if c.name == "苏念念")
    assert "嘴硬心软" in su.description
    assert "第二行继续描述" in su.description


@pytest.mark.asyncio
async def test_import_complete_script_retries_invalid_json_with_repair_prompt() -> None:
    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]]] = []

        async def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
            self.calls.append(messages)
            if len(self.calls) == 1:
                return '{"episodes": ['
            assert "Previous response was not valid JSON" in messages[-1]["content"]
            return json.dumps(
                {
                    "characters": [
                        {
                            "name": "苏念念",
                            "description": "带货主播",
                            "visual_prompt": "young Chinese woman, Y2K outfit",
                            "voice_style": "playful",
                        }
                    ],
                    "episodes": [
                        {
                            "number": 1,
                            "title": "提亲现场",
                            "synopsis": "苏念念吃瓜吃到自己头上。",
                            "opening_hook": "楼下提亲卡车。",
                            "duration_seconds": 60,
                            "scenes": [
                                {
                                    "scene_id": "ep01_s01",
                                    "description": "苏念念看到提亲卡车。",
                                    "visual_prompt": "old apartment courtyard, young Chinese woman",
                                    "camera_movement": "static",
                                    "duration_seconds": 5,
                                    "dialogue": "有瓜吃！",
                                    "shot_scale": "medium",
                                    "shot_type": "action",
                                    "emotion": "shock",
                                    "characters_present": ["苏念念"],
                                    "transition": "cut",
                                    "sfx": "",
                                    "time_of_day": "day",
                                    "scene_group": "A",
                                    "shot_role": "hook",
                                }
                            ],
                            "voice_over": {"text": "有瓜吃！", "tone": "playful", "language": "zh"},
                            "music": {"style": "acoustic", "mood": "romantic", "tempo": 100},
                            "cliffhanger": "她发现提亲对象是自己。",
                        }
                    ],
                },
                ensure_ascii=False,
            )

    llm = FakeLLM()
    planner = DramaPlanner(llm=llm)  # type: ignore[arg-type]
    series = DramaSeries(series_id="test", title="恋爱好啊", language="zh", model_id="mock")

    imported = await planner.import_complete_script(series, "第一集\n苏念念：有瓜吃！")

    assert len(llm.calls) == 2
    first_payload = llm.calls[0][-1]["content"]
    assert 'data-videoclaw-format="script-source-v1"' in first_payload
    assert "STANDARDIZED SCRIPT HTML" in first_payload
    assert imported.metadata["llm_import_payload_format"] == "html"
    assert 'data-videoclaw-format="script-source-v1"' in imported.metadata["llm_import_html"]
    assert imported.script_locked is True
    assert imported.episodes[0].scenes[0].dialogue == "有瓜吃！"


@pytest.mark.asyncio
async def test_import_complete_script_retries_episode_without_scenes() -> None:
    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]]] = []

        async def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
            self.calls.append(messages)
            if len(self.calls) == 1:
                return json.dumps({"episodes": [{"number": 1, "title": "空镜头", "scenes": []}]})
            assert "episodes.scenes" in messages[-1]["content"]
            return json.dumps(
                {
                    "characters": [],
                    "episodes": [
                        {
                            "number": 1,
                            "title": "提亲现场",
                            "scenes": [
                                {
                                    "scene_id": "ep01_s01",
                                    "description": "苏念念看到提亲卡车。",
                                    "visual_prompt": "old apartment courtyard, young Chinese woman",
                                    "duration_seconds": 5,
                                    "dialogue": "有瓜吃！",
                                    "shot_scale": "medium",
                                    "shot_type": "action",
                                    "characters_present": ["苏念念"],
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            )

    planner = DramaPlanner(llm=FakeLLM())  # type: ignore[arg-type]
    series = DramaSeries(series_id="test", title="恋爱好啊", language="zh", model_id="mock")

    imported = await planner.import_complete_script(series, "第一集\n苏念念：有瓜吃！")

    assert imported.episodes[0].scenes
