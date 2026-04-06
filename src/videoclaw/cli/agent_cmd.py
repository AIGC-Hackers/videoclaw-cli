"""``claw agent`` -- agent management commands."""

from __future__ import annotations

from videoclaw.cli._app import agent_app
from videoclaw.cli._output import get_console, get_output


@agent_app.command("list")
def agent_list() -> None:
    """List all registered video production agents."""
    console = get_console()
    out = get_output()
    out._command = "agent.list"

    from videoclaw.agents.registry import AgentRegistry

    registry = AgentRegistry()
    registry.discover()

    agents = registry.list_agents()
    if not agents:
        console.print("[yellow]No agents discovered.[/yellow]")
        console.print(
            "Agents are auto-discovered via the"
            " [cyan]videoclaw.agents[/cyan] entry-point group."
        )
        out.set_result({"agents": []})
        out.emit()
        return

    from rich.table import Table
    table = Table(
        title="Registered Agents",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Role", style="cyan", min_width=14)
    table.add_column("Class", style="white")
    table.add_column("Tools", style="magenta")

    result_agents = []
    for a in agents:
        role = a["role"]
        cls = a["class"]
        tools = ", ".join(a["tools"]) if a["tools"] else "(none)"
        table.add_row(role, cls, tools)
        result_agents.append(a)

    console.print(table)

    out.set_result({"agents": result_agents})
    out.emit()
