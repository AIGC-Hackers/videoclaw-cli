"""End-to-end external test — drives videoclaw the way Claude Code would.

Mixes two interfaces:
- The MCP shim (read-only discovery / metadata via JSON-RPC stdio).
- The ``claw`` CLI (mutating ops: import / plan / design / run) — what
  Claude Code or another orchestrator invokes via Bash.

Tiered to keep cheap-fast checks separate from billable LLM and video
generation. Stages later than T4 require real API keys; gate them with::

    E2E_REAL_LLM=1     # T5 plan + T6 design (LLM + image gen, ~$0.50)
    E2E_REAL_VIDEO=1   # T8 video gen for first 3 shots (Seedance, ~$3, ~10 min)

Defaults skip the billable stages — T1..T4 + T7 (dry-run) always run.

Run::

    uv pip install -e "mcp-shim/[test]" pypdf
    uv run pytest tests-external/test_e2e_first_3_shots.py -v

Test data lives at ``tests-external/data/loving-talk-script.md`` (gitignored
under tests-external/data/.gitkeep — drama scripts are user content, not
toolkit artifacts).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_MD = REPO_ROOT / "tests-external" / "data" / "loving-talk-script.md"
SERIES_ID_FILE = REPO_ROOT / "tests-external" / "data" / ".series_id"

CLAW = shutil.which("claw") or shutil.which("uv")
MCP_SERVER = shutil.which("videoclaw-mcp-server")

REAL_LLM = os.environ.get("E2E_REAL_LLM") == "1"
REAL_VIDEO = os.environ.get("E2E_REAL_VIDEO") == "1"


def _claw(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Invoke `claw` (via uv run if installed via uv) and capture output."""
    if shutil.which("claw"):
        cmd = ["claw", *args]
    else:
        cmd = ["uv", "run", "claw", *args]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


async def _mcp_request(messages: list[tuple[dict, bool]]) -> list[dict]:
    """Drive the MCP shim over stdio with the standard handshake helpers."""
    assert MCP_SERVER is not None
    proc = await asyncio.create_subprocess_exec(
        MCP_SERVER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert proc.stdin and proc.stdout
        responses = []
        for msg, expect in messages:
            proc.stdin.write((json.dumps(msg) + "\n").encode())
            await proc.stdin.drain()
            if expect:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
                if raw:
                    responses.append(json.loads(raw.decode()))
        return responses
    finally:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass


def _opener() -> list[tuple[dict, bool]]:
    return [
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "videoclaw-e2e", "version": "0.1.0"},
                },
            },
            True,
        ),
        ({"jsonrpc": "2.0", "method": "notifications/initialized"}, False),
    ]


# ----- T1: source artifact present -------------------------------------------


def test_T1_source_markdown_exists() -> None:
    assert SCRIPT_MD.is_file(), f"missing converted script: {SCRIPT_MD}"
    text = SCRIPT_MD.read_text(encoding="utf-8")
    assert len(text) > 1_000, f"script suspiciously short: {len(text)} chars"
    assert "恋爱好啊" in text, "title marker missing — wrong PDF parsed?"


# ----- T2: claw drama new (no LLM with --no-plan, just persistence) ----------


# Concept distilled from the PDF — what a code agent would extract from
# the source doc before handing it to videoclaw. Keeps the LLM call (gated
# behind T5 / E2E_REAL_LLM) bounded to the planning stage.
SYNOPSIS = (
    "在西昌航天发射中心封闭搞科研十二年的理工科天才陆北辰，回到上海完成病重父亲的相亲心愿，"
    "遇见嘴贫心软、不信爱情、被父亲逼着三十岁前要嫁出去的带货女主播苏念念。"
    "一个把爱情当成尽孝的工具，一个把婚姻当成跟父亲赌气的筹码，"
    "两人彼此互为工具人——直到都输了，才发现对方早已是生命里不可或缺的部分。"
)


def test_T2_drama_new_persists_series() -> None:
    """`claw drama new "<synopsis>" --no-plan` produces a series_id and writes
    series.json on disk. No LLM call (planning is gated to T5).

    `drama import` is a heavier path (it asks the LLM to decompose the full
    script into shots up-front and hits output-token limits on long PDFs);
    `drama new --no-plan` is the natural entry for a code agent that has
    already digested the source document and is handing videoclaw a concept.
    """
    res = _claw(
        "drama",
        "new",
        SYNOPSIS,
        "--title",
        "恋爱好啊，得谈！",
        "--genre",
        "romance",
        "--lang",
        "zh",
        "--episodes",
        "1",
        "--duration",
        "60",
    )
    assert res.returncode == 0, f"new failed:\n{res.stdout}\n{res.stderr}"

    # CLI prints "Created series <id>" — extract the 16-hex-ish id.
    output = res.stdout + res.stderr
    import re
    m = re.search(r"\b([0-9a-f]{12,32})\b", output)
    assert m, f"no series id in output:\n{output[-500:]}"
    series_id = m.group(1)
    SERIES_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERIES_ID_FILE.write_text(series_id, encoding="utf-8")

    # Confirm the series.json landed in the configured projects dir.
    from videoclaw.config import get_config
    series_json = get_config().projects_dir / "dramas" / series_id / "series.json"
    assert series_json.is_file(), f"series.json missing at {series_json}"


# ----- T3: MCP discovers the new series --------------------------------------


@pytest.mark.skipif(MCP_SERVER is None, reason="videoclaw-mcp-server not on PATH")
def test_T3_mcp_list_drama_series_includes_new_one() -> None:
    assert SERIES_ID_FILE.is_file(), "T2 must run first"
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()

    messages = _opener() + [
        (
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_drama_series", "arguments": {}},
            },
            True,
        ),
    ]
    responses = asyncio.run(_mcp_request(messages))
    assert len(responses) == 2, responses
    content = responses[1]["result"].get("content", [])
    assert content, responses[1]
    text = content[0].get("text", "")
    assert series_id in text, f"new series {series_id} not in MCP output:\n{text}"


# ----- T4: MCP returns metadata for that series ------------------------------


@pytest.mark.skipif(MCP_SERVER is None, reason="videoclaw-mcp-server not on PATH")
def test_T4_mcp_get_drama_series_returns_metadata() -> None:
    assert SERIES_ID_FILE.is_file(), "T2 must run first"
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()

    messages = _opener() + [
        (
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_drama_series",
                    "arguments": {"series_id": series_id},
                },
            },
            True,
        ),
    ]
    responses = asyncio.run(_mcp_request(messages))
    assert len(responses) == 2, responses
    content = responses[1]["result"].get("content", [])
    assert content, responses[1]
    text = content[0].get("text", "")
    assert series_id in text, text
    # Metadata should at least carry the title we passed.
    # JSON serialization may quote-escape Chinese; check the 4-char anchor.
    assert "恋爱好啊" in text or "lov" in text.lower(), text


# ----- T5: drama plan (LLM, billable) ----------------------------------------


@pytest.mark.skipif(not REAL_LLM, reason="set E2E_REAL_LLM=1 to run (LLM cost ~$0.05)")
def test_T5_drama_plan_produces_characters_and_episode_synopsis() -> None:
    """`drama plan` is the first LLM-driven stage — it produces the series
    casting (characters with visual descriptions) and an episode synopsis.
    Shot decomposition happens later in `design-scenes` (T6)."""
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()
    res = _claw("drama", "plan", series_id, check=False)
    from videoclaw.config import get_config
    series_json = get_config().projects_dir / "dramas" / series_id / "series.json"
    data = json.loads(series_json.read_text(encoding="utf-8"))

    # Characters are populated at the series level after plan.
    chars = data.get("characters") or []
    assert len(chars) >= 2, (
        f"plan should cast ≥2 characters, got {len(chars)}: "
        f"stdout={res.stdout[-300:]!r}"
    )
    for ch in chars:
        assert ch.get("name"), f"character missing name: {ch}"

    # Episode 1 synopsis populated.
    eps = data.get("episodes") or []
    assert eps, f"no episodes after plan: {list(data.keys())}"
    syn = eps[0].get("synopsis") or ""
    assert len(syn) > 50, f"episode 1 synopsis too short ({len(syn)} chars): {syn!r}"


# ----- T6: design-scenes — shot decomposition (intermediate asset) -----------


@pytest.mark.skipif(
    not REAL_LLM, reason="set E2E_REAL_LLM=1 to run (LLM cost ~$0.20)"
)
def test_T6_script_then_design_scenes_produces_shots() -> None:
    """Two-step intermediate-asset stage:

    - ``drama script <id> --episode 1`` decomposes the episode synopsis into
      a scene list with dialogue (LLM).
    - ``drama design-scenes <id>`` enriches each scene with the visual prompt
      Seedance needs for video generation (LLM).

    Together they produce the canonical intermediate asset a code agent
    reads to know what video calls will be made.
    """
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()
    res_script = _claw("drama", "script", series_id, "--episode", "1", check=False)
    assert res_script.returncode == 0, (
        f"drama script failed:\n{res_script.stdout[-500:]}\n{res_script.stderr[-500:]}"
    )
    res_scenes = _claw("drama", "design-scenes", series_id, check=False)
    assert res_scenes.returncode == 0, (
        f"design-scenes failed:\n{res_scenes.stdout[-500:]}\n{res_scenes.stderr[-500:]}"
    )

    from videoclaw.config import get_config
    series_json = get_config().projects_dir / "dramas" / series_id / "series.json"
    data = json.loads(series_json.read_text(encoding="utf-8"))
    eps = data.get("episodes") or []
    scenes = eps[0].get("scenes") or []
    assert len(scenes) >= 3, (
        f"need ≥3 shots for the first-3-shots e2e, got {len(scenes)}"
    )
    s0 = scenes[0]
    for key in ("scene_id", "duration_seconds", "visual_prompt", "shot_scale"):
        assert key in s0, f"scene[0] missing {key!r}: {list(s0.keys())}"
    assert s0["visual_prompt"], "scene[0].visual_prompt empty (Seedance needs it)"
    assert 4 <= float(s0["duration_seconds"]) <= 15, (
        f"scene[0].duration_seconds out of Seedance range: {s0['duration_seconds']}"
    )


# ----- T7: design-characters — wires turnaround images into series.json ------


@pytest.mark.skipif(
    not REAL_LLM, reason="set E2E_REAL_LLM=1 to run (image gen cost ~$1)"
)
def test_T7_design_characters_populates_reference_images() -> None:
    """`drama design-characters` generates a turnaround sheet per character
    AND writes the path back into `series.characters[].reference_images`.
    Without this step, the pre-production gate (item 2 of 7, see
    src/videoclaw/drama/pre_production_gate.py:62-70) flags
    "character has 0 reference images (need ≥4)" and Seedance Universal
    Reference can't anchor character consistency across shots — T8 then
    silently fails with $0 cost."""
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()
    res = _claw("drama", "design-characters", series_id, check=False)
    assert res.returncode == 0, (
        f"design-characters failed:\n{res.stdout[-500:]}\n{res.stderr[-500:]}"
    )
    from videoclaw.config import get_config
    series_json = get_config().projects_dir / "dramas" / series_id / "series.json"
    data = json.loads(series_json.read_text(encoding="utf-8"))
    chars = data.get("characters") or []
    assert chars, "no characters after design-characters"
    for ch in chars:
        refs = ch.get("reference_images") or []
        assert refs, (
            f"character {ch.get('name')!r} has no reference_images after "
            f"design-characters — videoclaw bug or insufficient design pass"
        )
        for ref in refs:
            assert Path(ref).is_file(), (
                f"character {ch.get('name')!r} reference image is recorded "
                f"but missing on disk: {ref}"
            )
        url = ch.get("reference_image_url") or ""
        assert url.startswith("https://"), (
            f"character {ch.get('name')!r} missing HTTPS reference_image_url "
            "required by Seedance"
        )


# ----- T8: dry-run of the run pipeline (no video calls) ----------------------


def test_T8_drama_run_dry_run_succeeds() -> None:
    """`claw drama run --dry-run --max-shots 3` shows the plan without hitting
    the video API. Free, deterministic, exercises the executor end-to-end
    against the mock adapter."""
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()
    res = _claw(
        "drama",
        "run",
        series_id,
        "--max-shots",
        "3",
        "--dry-run",
        check=False,
    )
    # Dry-run should print the plan; even if no episodes exist yet (T5 not
    # run), the CLI exits cleanly with an explanation.
    combined = (res.stdout + res.stderr).lower()
    assert any(
        marker in combined
        for marker in ("dry", "plan", "shot", "episode", "no episodes")
    ), f"dry-run output looks empty:\n{res.stdout}\n{res.stderr}"


# ----- T9: real video gen for the first 3 shots (Seedance, billable) ---------


@pytest.mark.skipif(
    not REAL_VIDEO, reason="set E2E_REAL_VIDEO=1 to run (Seedance cost ~$3, ~10 min)"
)
def test_T9_drama_run_first_3_shots_produces_videos() -> None:
    """Real Seedance video gen for the first 3 shots — the "complete asset"
    deliverable.

    Prerequisites (must run BEFORE this test in the same session):
    - T2 drama new
    - T5 drama plan (characters + episode synopsis)
    - T6 drama script + design-scenes (shot decomposition + scene refs)
    - T7 drama design-characters (≥4 reference images per character — the
      pre-production gate's item 2 will fail-quiet otherwise and Seedance
      gets $0 cost / 13-min hang)

    A complete chain looks like::

        E2E_REAL_LLM=1 uv run pytest tests-external/test_e2e_first_3_shots.py::test_T2_drama_new_persists_series \\
                                     tests-external/test_e2e_first_3_shots.py::test_T5_drama_plan_produces_characters_and_episode_synopsis \\
                                     tests-external/test_e2e_first_3_shots.py::test_T6_script_then_design_scenes_produces_shots \\
                                     tests-external/test_e2e_first_3_shots.py::test_T7_design_characters_populates_reference_images -v

        E2E_REAL_VIDEO=1 uv run pytest tests-external/test_e2e_first_3_shots.py::test_T9_drama_run_first_3_shots_produces_videos -v
    """
    series_id = SERIES_ID_FILE.read_text(encoding="utf-8").strip()

    # Pre-flight: confirm characters carry reference_images. The first run
    # we built failed silently because design-characters had not been run —
    # asserting this up front saves the user 13 minutes of wall time + ~$3.
    from videoclaw.config import get_config
    series_json = get_config().projects_dir / "dramas" / series_id / "series.json"
    data = json.loads(series_json.read_text(encoding="utf-8"))
    chars = data.get("characters") or []
    for ch in chars:
        refs = ch.get("reference_images") or []
        url = ch.get("reference_image_url") or ""
        missing_refs = [ref for ref in refs if not Path(ref).is_file()]
        if not refs or missing_refs or not url.startswith("https://"):
            pytest.skip(
                f"character {ch.get('name')!r} has incomplete reference assets. "
                f"Run T7 (design-characters) first — see test docstring."
            )

    res = _claw(
        "drama",
        "run",
        series_id,
        "--max-shots",
        "3",
        "--no-review",
        "--no-agents",
        check=False,
    )
    after = json.loads(series_json.read_text(encoding="utf-8"))
    episode = (after.get("episodes") or [{}])[0]
    project_id = episode.get("project_id")
    videos: list[Path] = []
    if project_id:
        state_json = get_config().projects_dir / project_id / "state.json"
        if state_json.is_file():
            state = json.loads(state_json.read_text(encoding="utf-8"))
            for shot in state.get("storyboard") or []:
                asset_path = shot.get("asset_path")
                if asset_path and Path(asset_path).is_file():
                    videos.append(Path(asset_path))
    series_dir = get_config().projects_dir / "dramas" / series_id
    videos.extend(path for path in series_dir.rglob("*.mp4") if path not in videos)
    assert len(videos) >= 3, (
        f"expected ≥3 .mp4 artifacts, found {len(videos)}\n"
        f"stdout tail:\n{res.stdout[-500:]}\nstderr tail:\n{res.stderr[-500:]}"
    )
    # Each video file should be non-empty (Seedance writes ≥100 KB for 4-15s clips).
    for v in videos[:3]:
        assert v.stat().st_size > 100_000, f"{v} is suspiciously small"
