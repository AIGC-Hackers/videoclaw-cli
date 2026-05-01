"""Integration tests — exercise the full MCP stdio surface end-to-end.

We spawn ``videoclaw-mcp-server`` (the entry-point script registered by
mcp-shim/pyproject.toml) as a real subprocess, send a ``tools/list`` JSON-RPC
request over stdin, read the response from stdout, then terminate the
process. Pattern 2b from the toolkit's S05 known-limitations notes:
``asyncio.create_subprocess_exec + readline + terminate`` to avoid the
stdio deadlock that hits ``subprocess.run(input=..., capture_output=True)``
against fastmcp==2.12.5.

Each test exercises a different consumer scenario:
- ``initialize → tools/list`` (the Claude Code / openclaw discovery flow).
- ``initialize → tools/call get_videoclaw_version`` (single tool invocation
  end-to-end through the JSON-RPC envelope).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys

import pytest

pytestmark = pytest.mark.asyncio

_SERVER_BIN = shutil.which("videoclaw-mcp-server")


def _missing_server_reason() -> str | None:
    if _SERVER_BIN is None:
        return "videoclaw-mcp-server not on PATH (run: uv pip install -e mcp-shim/)"
    return None


_SKIP_REASON = _missing_server_reason()


async def _send_jsonrpc(
    messages: list[tuple[dict[str, object], bool]],
) -> list[dict[str, object]]:
    """Spawn the MCP server and send a sequence of (message, expect_response)
    tuples. Returns the parsed responses (one per ``expect_response=True``
    entry, in order).

    Notifications (``expect_response=False``) consume no stdout line — required
    for ``notifications/initialized`` which the MCP spec mandates between the
    ``initialize`` response and subsequent ``tools/list`` / ``tools/call``
    requests.
    """
    assert _SERVER_BIN is not None
    proc = await asyncio.create_subprocess_exec(
        _SERVER_BIN,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        responses: list[dict[str, object]] = []
        for msg, expect_response in messages:
            line = (json.dumps(msg) + "\n").encode("utf-8")
            proc.stdin.write(line)
            await proc.stdin.drain()
            if expect_response:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
                if not raw:
                    break
                responses.append(json.loads(raw.decode("utf-8")))
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


def _initialize_pair() -> list[tuple[dict[str, object], bool]]:
    """Standard ``initialize`` + ``notifications/initialized`` opener."""
    return [
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "videoclaw-mcp-shim-tests",
                        "version": "0.1.0",
                    },
                },
            },
            True,
        ),
        ({"jsonrpc": "2.0", "method": "notifications/initialized"}, False),
    ]


@pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "")
async def test_initialize_then_tools_list_over_stdio() -> None:
    """Claude-Code-style discovery: initialize handshake, then tools/list."""
    messages = _initialize_pair() + [
        ({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, True),
    ]
    responses = await _send_jsonrpc(messages)
    assert len(responses) == 2, f"expected 2 responses, got {len(responses)}: {responses}"

    init_resp = responses[0]
    assert init_resp.get("id") == 1
    assert "result" in init_resp, init_resp

    tools_resp = responses[1]
    assert tools_resp.get("id") == 2
    assert "result" in tools_resp, tools_resp
    tools = tools_resp["result"].get("tools", [])
    names = {t.get("name") for t in tools}
    assert {
        "list_drama_series",
        "get_drama_series",
        "list_video_models",
        "get_videoclaw_version",
    }.issubset(names), f"missing tools, got: {names}"


@pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "")
async def test_tools_call_get_videoclaw_version_over_stdio() -> None:
    """End-to-end tool call: initialize → tools/call → assert non-empty version."""
    messages = _initialize_pair() + [
        (
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_videoclaw_version", "arguments": {}},
            },
            True,
        ),
    ]
    responses = await _send_jsonrpc(messages)
    assert len(responses) == 2, responses

    call_resp = responses[1]
    assert call_resp.get("id") == 2
    assert "result" in call_resp, call_resp
    content = call_resp["result"].get("content", [])
    assert content, f"empty content in tool response: {call_resp}"
    # First content block should carry the version string.
    text = content[0].get("text") if isinstance(content[0], dict) else None
    assert isinstance(text, str) and text and text != "unknown", call_resp
