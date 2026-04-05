"""Base agent implementation with shared boilerplate."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from videoclaw.agents.base import (
    AgentMessage,
    AgentPlan,
    AgentResult,
    AgentRole,
    ReviewResult,
    ReviewVerdict,
)
from videoclaw.agents.llm_service import LLMService, get_llm_service
from videoclaw.core.events import event_bus

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base implementing :class:`VideoAgent` protocol with shared infra.

    Concrete agents inherit from this class and implement :meth:`think` and
    :meth:`act`.  Default implementations of :meth:`review` and
    :meth:`collaborate` are provided and can be overridden.
    """

    def __init__(
        self,
        role: AgentRole,
        llm_service: LLMService | None = None,
    ) -> None:
        self._role = role
        self._llm = llm_service
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def role(self) -> AgentRole:
        return self._role

    @property
    @abstractmethod
    def tools(self) -> list[str]:
        """List of tool identifiers this agent can use."""
        ...

    # ------------------------------------------------------------------
    # Lazy LLM access
    # ------------------------------------------------------------------

    def _ensure_llm(self) -> LLMService:
        """Return (and lazily create) the shared LLM service."""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    # ------------------------------------------------------------------
    # Abstract methods — must be implemented by concrete agents
    # ------------------------------------------------------------------

    @abstractmethod
    async def think(self, context: dict[str, Any]) -> AgentPlan:
        """Analyze context and produce an action plan."""
        ...

    @abstractmethod
    async def act(self, plan: AgentPlan) -> AgentResult:
        """Execute the plan using available tools."""
        ...

    # ------------------------------------------------------------------
    # Default implementations — may be overridden
    # ------------------------------------------------------------------

    async def review(self, result: AgentResult) -> ReviewResult:
        """Review a result and decide whether it passes quality.

        Default: approve everything with a neutral score.  Override in
        agents that perform actual quality assessment (e.g. ReviewerAgent).
        """
        return ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            score=7.0,
            feedback="Default pass-through (no reviewer configured)",
        )

    async def collaborate(self, message: AgentMessage) -> AgentMessage:
        """Receive and respond to a message from another agent.

        Default: acknowledge the message.  Override in agents that react
        to inter-agent communication (e.g. DirectorAgent handling feedback).
        """
        return AgentMessage(
            from_role=self._role,
            to_role=message.from_role,
            content=f"Acknowledged: {message.content}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Emit an event through the shared event bus."""
        payload = {"agent_role": self._role.value, **(data or {})}
        await self._event_bus.emit(event, payload)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} role={self._role.value}>"
