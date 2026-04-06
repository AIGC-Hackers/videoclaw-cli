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
    # Multi-agent collaboration loop
    # ------------------------------------------------------------------

    async def run_collaboration(
        self,
        context: dict[str, Any],
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        """Run multi-agent collaboration loop.

        Flow per round:

        1. Director thinks + acts (produces plan)
        2. Cameraman thinks + acts (enhances prompts)
        3. Reviewer reviews the combined result
        4. If APPROVED -> return results
        5. If RETRY -> Director.collaborate(reviewer feedback) -> next round
        6. If REJECT -> return with rejection info

        Returns dict with: rounds, final_verdict, agent_results, cost_usd
        """
        from videoclaw.agents.base import AgentMessage

        total_cost = 0.0
        agent_results: list[dict[str, Any]] = []
        final_verdict = ReviewVerdict.RETRY
        current_context = dict(context)

        for round_num in range(1, max_rounds + 1):
            logger.info(
                "Collaboration round %d/%d starting", round_num, max_rounds,
            )
            await event_bus.emit("collaboration.round.start", {
                "round": round_num,
                "max_rounds": max_rounds,
            })

            round_results: dict[str, Any] = {"round": round_num}

            # --- Step 1: Director thinks + acts ---
            director_result = None
            if self._registry.has(AgentRole.DIRECTOR):
                director = self._registry.get(AgentRole.DIRECTOR)
                logger.info("Round %d: Director thinking", round_num)
                await event_bus.emit("collaboration.stage", {
                    "round": round_num, "stage": "director.think",
                })

                director_plan = await director.think(current_context)
                director_result = await director.act(director_plan)
                total_cost += director_result.cost_usd
                round_results["director"] = {
                    "success": director_result.success,
                    "data": director_result.data,
                    "cost_usd": director_result.cost_usd,
                }

                if not director_result.success:
                    logger.warning(
                        "Round %d: Director failed: %s",
                        round_num, director_result.error,
                    )
                    final_verdict = ReviewVerdict.REJECT
                    agent_results.append(round_results)
                    break

            # --- Step 2: Cameraman thinks + acts ---
            cameraman_result = None
            if self._registry.has(AgentRole.CAMERAMAN):
                cameraman = self._registry.get(AgentRole.CAMERAMAN)
                logger.info("Round %d: Cameraman thinking", round_num)
                await event_bus.emit("collaboration.stage", {
                    "round": round_num, "stage": "cameraman.think",
                })

                cameraman_plan = await cameraman.think(current_context)
                cameraman_result = await cameraman.act(cameraman_plan)
                total_cost += cameraman_result.cost_usd
                round_results["cameraman"] = {
                    "success": cameraman_result.success,
                    "data": cameraman_result.data,
                    "cost_usd": cameraman_result.cost_usd,
                }

            # --- Step 3: Reviewer reviews ---
            review_target = director_result or cameraman_result
            if self._registry.has(AgentRole.REVIEWER) and review_target is not None:
                reviewer = self._registry.get(AgentRole.REVIEWER)
                logger.info("Round %d: Reviewer reviewing", round_num)
                await event_bus.emit("collaboration.stage", {
                    "round": round_num, "stage": "reviewer.review",
                })

                review = await reviewer.review(review_target)
                round_results["review"] = {
                    "verdict": review.verdict.value,
                    "score": review.score,
                    "feedback": review.feedback,
                    "suggestions": review.suggestions,
                }

                final_verdict = review.verdict
                agent_results.append(round_results)

                # --- Step 4: APPROVED -> done ---
                if review.verdict == ReviewVerdict.APPROVED:
                    logger.info(
                        "Round %d: Reviewer APPROVED (score=%.1f)",
                        round_num, review.score,
                    )
                    await event_bus.emit("collaboration.approved", {
                        "round": round_num, "score": review.score,
                    })
                    break

                # --- Step 6: REJECT -> stop ---
                if review.verdict == ReviewVerdict.REJECT:
                    logger.warning(
                        "Round %d: Reviewer REJECTED: %s",
                        round_num, review.feedback,
                    )
                    await event_bus.emit("collaboration.rejected", {
                        "round": round_num, "feedback": review.feedback,
                    })
                    break

                # --- Step 5: RETRY -> Director refine ---
                if review.verdict == ReviewVerdict.RETRY:
                    logger.info(
                        "Round %d: Reviewer requested RETRY: %s",
                        round_num, review.feedback,
                    )
                    await event_bus.emit("collaboration.retry", {
                        "round": round_num, "feedback": review.feedback,
                    })

                    if self._registry.has(AgentRole.DIRECTOR):
                        director = self._registry.get(AgentRole.DIRECTOR)
                        feedback_msg = AgentMessage(
                            from_role=AgentRole.REVIEWER,
                            to_role=AgentRole.DIRECTOR,
                            content=review.feedback,
                            data={
                                "suggestions": review.suggestions,
                                "original_prompt": current_context.get("prompt", ""),
                            },
                        )
                        reply = await director.collaborate(feedback_msg)
                        # Merge refined data back into context
                        if reply.data:
                            current_context.update(reply.data)

                    continue

                # MODIFY or other verdicts — treat as retry
                logger.info(
                    "Round %d: Reviewer verdict=%s, continuing",
                    round_num, review.verdict.value,
                )
                continue
            else:
                # No reviewer or no results to review — auto-approve
                final_verdict = ReviewVerdict.APPROVED
                agent_results.append(round_results)
                break

        await event_bus.emit("collaboration.complete", {
            "rounds": len(agent_results),
            "final_verdict": final_verdict.value,
            "cost_usd": total_cost,
        })

        return {
            "rounds": len(agent_results),
            "final_verdict": final_verdict,
            "agent_results": agent_results,
            "cost_usd": total_cost,
        }

    # ------------------------------------------------------------------
    # Agent access
    # ------------------------------------------------------------------

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    def __repr__(self) -> str:
        return f"<AgentTeam agents={len(self._registry)}>"
