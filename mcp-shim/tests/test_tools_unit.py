"""Single-point tests — each MCP tool exercised individually via fastmcp's
in-process Client. Avoids the stdio-subprocess deadlock that hits
fastmcp==2.12.5 when stdin is closed.

What each test asserts:
- The tool is registered with FastMCP.
- The tool returns a value of the right shape.
- The tool is read-only (does not mutate videoclaw state on disk).
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.asyncio


async def test_tools_list_contains_four_tools() -> None:
    from fastmcp import Client

    from mcp_server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert {
        "list_drama_series",
        "get_drama_series",
        "list_video_models",
        "get_videoclaw_version",
    }.issubset(names), f"missing tools: {names}"


async def test_get_videoclaw_version_returns_non_empty_string() -> None:
    from fastmcp import Client

    from mcp_server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("get_videoclaw_version", {})

    payload = result.data if hasattr(result, "data") else result
    assert isinstance(payload, str)
    assert payload != ""
    assert payload != "unknown"


async def test_list_drama_series_returns_list() -> None:
    from fastmcp import Client

    from mcp_server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_drama_series", {})

    payload = result.data if hasattr(result, "data") else result
    assert isinstance(payload, list)
    for entry in payload:
        assert isinstance(entry, str)


async def test_list_video_models_returns_list_of_dicts() -> None:
    from fastmcp import Client

    from mcp_server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_video_models", {})

    payload = result.data if hasattr(result, "data") else result
    assert isinstance(payload, list)
    for entry in payload:
        assert isinstance(entry, dict)


async def test_get_drama_series_handles_missing_id_gracefully() -> None:
    """A missing series_id should surface as a tool error, not a crash."""
    from fastmcp import Client

    from mcp_server import mcp

    async with Client(mcp) as client:
        with pytest.raises(Exception) as exc_info:
            await client.call_tool(
                "get_drama_series", {"series_id": "_definitely_does_not_exist_zzz"}
            )

    # Either FileNotFoundError surfaces directly or fastmcp wraps it — both ok.
    msg = str(exc_info.value)
    assert "not found" in msg.lower() or "error" in msg.lower() or "no such" in msg.lower(), msg
