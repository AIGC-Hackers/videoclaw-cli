"""AgentTeam — coordinates agents and installs them as DAG handlers."""

from __future__ import annotations

import logging
from typing import Any

from videoclaw.agents.base import (
    AgentRole,
    ReviewVerdict,
    VideoAgent,
)
from videoclaw.agents.registry import AgentRegistry, get_agent_registry
from videoclaw.core.events import event_bus
from videoclaw.core.planner import TaskType

logger = logging.getLogger(__name__)

# Default mapping from TaskType to the AgentRole that handles it.
_DEFAULT_TASK_ROLE_MAP: dict[TaskType, AgentRole] = {
    TaskType.SCRIPT_GEN: AgentRole.DIRECTOR,
    TaskType.STORYBOARD: AgentRole.DIRECTOR,
    TaskType.SCENE_VALIDATE: AgentRole.REVIEWER,
    TaskType.VIDEO_GEN: AgentRole.CAMERAMAN,
}


class AgentTeam:
    """Wires agents together and registers them as DAG handlers.

    Usage::

        team = AgentTeam()
        team.register_defaults()        # auto-discover agents
        team.install_handlers(executor)  # plug into DAGExecutor
    """

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or get_agent_registry()
        self._task_role_map: dict[TaskType, AgentRole] = dict(_DEFAULT_TASK_ROLE_MAP)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def register_defaults(self) -> None:
        """Discover and register all agents from entry points."""
        self._registry.discover()

    def set_handler_role(self, task_type: TaskType, role: AgentRole) -> None:
        """Override which agent role handles a given task type."""
        self._task_role_map[task_type] = role

    # ------------------------------------------------------------------
    # DAGExecutor integration
    # ------------------------------------------------------------------

    def install_handlers(self, executor: Any) -> None:
        """Register agent-backed handlers on a :class:`DAGExecutor`.

        For each ``TaskType → AgentRole`` mapping, if the registry has an
        agent for that role, a handler wrapping ``agent.think() → act()``
        is installed on the executor via ``register_handler()``.
        """
        from videoclaw.core.planner import TaskNode
        from videoclaw.core.state import ProjectState

        installed = 0
        for task_type, role in self._task_role_map.items():
            if not self._registry.has(role):
                logger.debug(
                    "No agent for role=%s — keeping default handler for %s",
                    role.value, task_type.value,
                )
                continue

            agent = self._registry.get(role)

            async def _handler(
                node: TaskNode,
                state: ProjectState,
                *,
                _agent: VideoAgent = agent,
            ) -> Any:
                context = {
                    "node_id": node.node_id,
                    "task_type": node.task_type.value,
                    "params": node.params,
                    "state_project_id": state.project_id,
                }
                plan = await _agent.think(context)
                result = await _agent.act(plan)

                if not result.success:
                    raise RuntimeError(
                        f"Agent {_agent.role.value} failed: {result.error}"
                    )

                # Optional cross-review by ReviewerAgent
                if (
                    _agent.role != AgentRole.REVIEWER
                    and self._registry.has(AgentRole.REVIEWER)
                ):
                    reviewer = self._registry.get(AgentRole.REVIEWER)
                    review = await reviewer.review(result)
                    if review.verdict == ReviewVerdict.REJECT:
                        raise RuntimeError(
                            f"Reviewer rejected {_agent.role.value} output: "
                            f"{review.feedback}"
                        )
                    if review.verdict == ReviewVerdict.RETRY:
                        logger.warning(
                            "Reviewer requested retry for %s: %s",
                            _agent.role.value, review.feedback,
                        )
                        # DAGExecutor's own retry logic will handle this
                        raise RuntimeError(
                            f"Reviewer retry: {review.feedback}"
                        )

                return result.data

            executor.register_handler(task_type, _handler)
            installed += 1
            logger.info(
                "Installed agent handler: %s → %s (%s)",
                task_type.value, role.value, type(agent).__name__,
            )

        logger.info(
            "AgentTeam installed %d/%d handlers",
            installed, len(self._task_role_map),
        )

    # ------------------------------------------------------------------
    # Agent access
    # ------------------------------------------------------------------

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    def __repr__(self) -> str:
        return f"<AgentTeam agents={len(self._registry)}>"
