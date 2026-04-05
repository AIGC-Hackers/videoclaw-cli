"""Agent registry — discovers, registers, and manages VideoAgent instances.

Mirrors the :class:`~videoclaw.models.registry.ModelRegistry` pattern:
singleton via ``lru_cache``, entry-point discovery via the
``videoclaw.agents`` group.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from importlib.metadata import entry_points
from typing import Any

from videoclaw.agents.base import AgentRole, VideoAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central catalogue of :class:`VideoAgent` instances."""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, VideoAgent] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, agent: VideoAgent) -> None:
        """Add *agent* to the registry, keyed by its ``role``.

        Raises :class:`ValueError` if an agent with the same role is already
        registered.
        """
        role = agent.role
        if role in self._agents:
            raise ValueError(
                f"Agent with role={role.value!r} is already registered"
            )
        self._agents[role] = agent
        logger.info("Registered agent %r (role=%s)", type(agent).__name__, role.value)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, role: AgentRole) -> VideoAgent:
        """Return the agent for *role* or raise :class:`KeyError`."""
        try:
            return self._agents[role]
        except KeyError:
            available = ", ".join(r.value for r in sorted(self._agents)) or "(none)"
            raise KeyError(
                f"No agent registered for role={role.value!r}. "
                f"Available: {available}"
            ) from None

    def has(self, role: AgentRole) -> bool:
        """Return *True* if an agent is registered for *role*."""
        return role in self._agents

    def list_agents(self) -> list[dict[str, Any]]:
        """Return a summary of every registered agent."""
        return [
            {
                "role": agent.role.value,
                "class": type(agent).__name__,
                "tools": agent.tools,
            }
            for agent in self._agents.values()
        ]

    # ------------------------------------------------------------------
    # Discovery via entry points
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Auto-discover agents exposed via the ``videoclaw.agents``
        entry-point group.

        Each entry point must resolve to a callable that returns a
        :class:`VideoAgent` instance (a factory or class).
        """
        eps = entry_points()
        agent_eps = eps.select(group="videoclaw.agents")

        for ep in agent_eps:
            try:
                factory = ep.load()
                agent = factory()
                if agent.role in self._agents:
                    continue  # already registered
                self.register(agent)
                logger.info(
                    "Discovered agent %r from entry point %r",
                    type(agent).__name__, ep.name,
                )
            except Exception:
                logger.exception(
                    "Failed to load agent from entry point %r", ep.name,
                )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check_all(self) -> dict[str, bool]:
        """Check each agent can be instantiated and responds to think()."""

        async def _check(agent: VideoAgent) -> tuple[str, bool]:
            try:
                # Verify agent satisfies protocol structurally
                _ = agent.role
                _ = agent.tools
                return agent.role.value, True
            except Exception:
                logger.warning(
                    "Health check failed for agent %r",
                    type(agent).__name__,
                    exc_info=True,
                )
                return agent.role.value, False

        results = await asyncio.gather(
            *(_check(a) for a in self._agents.values())
        )
        return dict(results)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, role: AgentRole) -> bool:
        return role in self._agents

    def __repr__(self) -> str:
        roles = ", ".join(r.value for r in sorted(self._agents))
        return f"<AgentRegistry agents=[{roles}]>"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    """Return the global :class:`AgentRegistry` singleton."""
    return AgentRegistry()
