"""ProducerAgent — pipeline orchestration and budget management.

Wraps :func:`~videoclaw.drama.runner.build_episode_dag` to construct
execution DAGs for episode production, and monitors cost against budget.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from videoclaw.agents._base_agent import BaseAgent
from videoclaw.agents.base import (
    AgentMessage,
    AgentPlan,
    AgentResult,
    AgentRole,
    AgentStep,
    ReviewResult,
    ReviewVerdict,
)

if TYPE_CHECKING:
    from videoclaw.core.planner import DAG
    from videoclaw.core.state import ProjectState
    from videoclaw.drama.models import DramaSeries, Episode

logger = logging.getLogger(__name__)

# Default budget cap when none is specified (USD).
_DEFAULT_BUDGET_USD = 50.0


class ProducerAgent(BaseAgent):
    """Orchestrates episode production pipelines and manages budgets.

    Builds DAGs from episode scripts via :func:`build_episode_dag` and
    tracks costs to ensure production stays within budget.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(role=AgentRole.PRODUCER, **kwargs)

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[str]:
        return ["drama_runner", "cost_tracker", "dag_builder"]

    # ------------------------------------------------------------------
    # Core agent methods
    # ------------------------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentPlan:
        """Analyze context and decide pipeline steps.

        Parameters
        ----------
        context:
            Expected keys:

            - ``series_id`` (str): identifier for the drama series.
            - ``episode_number`` (int): which episode to produce.
            - ``budget_usd`` (float, optional): maximum budget in USD.
            - ``series`` (:class:`DramaSeries`): full series data.
            - ``episode`` (:class:`Episode`): full episode data.
            - ``max_shots`` (int | None): limit shots for test runs.
        """
        budget_usd: float = context.get("budget_usd", _DEFAULT_BUDGET_USD)
        series_id: str = context.get("series_id", "unknown")
        episode_number: int = context.get("episode_number", 1)
        max_shots: int | None = context.get("max_shots")

        steps: list[AgentStep] = []

        # Always check budget first if cost data is available
        if context.get("current_cost_usd") is not None:
            steps.append(
                AgentStep(
                    action="check_budget",
                    params={
                        "current_cost_usd": context["current_cost_usd"],
                        "budget_usd": budget_usd,
                    },
                    description=f"Verify cost ${context['current_cost_usd']:.2f} within budget ${budget_usd:.2f}",
                ),
            )

        # Build the DAG for pipeline execution
        steps.append(
            AgentStep(
                action="run_pipeline",
                params={
                    "series": context.get("series"),
                    "episode": context.get("episode"),
                    "max_shots": max_shots,
                },
                description=(
                    f"Build episode DAG for series={series_id} "
                    f"ep={episode_number}"
                ),
            ),
        )

        return AgentPlan(
            agent_role=AgentRole.PRODUCER,
            steps=steps,
            reasoning=(
                f"Preparing pipeline for series {series_id}, "
                f"episode {episode_number}, budget ${budget_usd:.2f}."
            ),
        )

    async def act(self, plan: AgentPlan) -> AgentResult:
        """Execute the production plan.

        Supports two actions:

        - ``check_budget``: compare current cost against budget limit.
        - ``run_pipeline``: build an episode DAG via
          :func:`~videoclaw.drama.runner.build_episode_dag`.
        """
        data: dict[str, Any] = {}
        errors: list[str] = []
        budget_exceeded = False

        for step in plan.steps:
            try:
                if step.action == "check_budget":
                    current = step.params.get("current_cost_usd", 0.0)
                    budget = step.params.get("budget_usd", _DEFAULT_BUDGET_USD)
                    remaining = budget - current
                    budget_exceeded = current > budget
                    data["budget"] = {
                        "current_cost_usd": current,
                        "budget_usd": budget,
                        "remaining_usd": remaining,
                        "exceeded": budget_exceeded,
                    }
                    if budget_exceeded:
                        errors.append(
                            f"Budget exceeded: ${current:.2f} > ${budget:.2f}"
                        )
                        logger.warning(
                            "Budget exceeded: $%.2f / $%.2f",
                            current,
                            budget,
                        )

                elif step.action == "run_pipeline":
                    series: DramaSeries = step.params["series"]
                    episode: Episode = step.params["episode"]
                    max_shots: int | None = step.params.get("max_shots")

                    dag, state = self._build_dag(episode, series, max_shots=max_shots)

                    # Collect DAG summary info
                    node_count = len(dag.nodes)
                    task_types: dict[str, int] = {}
                    for node in dag.nodes:
                        ttype = node.task_type.value if hasattr(node.task_type, "value") else str(node.task_type)
                        task_types[ttype] = task_types.get(ttype, 0) + 1

                    data["dag"] = {
                        "node_count": node_count,
                        "task_types": task_types,
                        "project_id": state.project_id,
                        "shot_count": len(state.storyboard),
                    }
                    logger.info(
                        "DAG built: %d nodes, %d shots",
                        node_count,
                        len(state.storyboard),
                    )

                else:
                    errors.append(f"Unknown action: {step.action}")

            except (OSError, RuntimeError, asyncio.TimeoutError, ValueError) as exc:
                logger.exception("Producer step %s failed", step.action)
                errors.append(f"{step.action}: {exc}")

        success = not errors or (budget_exceeded and len(errors) == 1)

        await self._emit(
            "producer.pipeline_built",
            {"success": success, "data": data},
        )

        return AgentResult(
            agent_role=AgentRole.PRODUCER,
            success=success and not budget_exceeded,
            data=data,
            error="; ".join(errors) if errors else None,
        )

    async def review(self, result: AgentResult) -> ReviewResult:
        """Review pipeline result.

        - Success → APPROVED.
        - Budget exceeded → MODIFY (can proceed with reduced scope).
        - Failed → RETRY.
        """
        budget_info = result.data.get("budget", {})
        budget_exceeded = budget_info.get("exceeded", False)

        if not result.success and budget_exceeded:
            return ReviewResult(
                verdict=ReviewVerdict.MODIFY,
                score=4.0,
                feedback=(
                    f"Budget exceeded: ${budget_info.get('current_cost_usd', 0):.2f} "
                    f"/ ${budget_info.get('budget_usd', 0):.2f}."
                ),
                suggestions=[
                    "Reduce max_shots to lower cost",
                    "Increase budget allocation",
                    "Skip non-essential scenes",
                ],
            )

        if not result.success:
            return ReviewResult(
                verdict=ReviewVerdict.RETRY,
                score=2.0,
                feedback=f"Pipeline build failed: {result.error}",
                suggestions=["Check series/episode data", "Verify model availability"],
            )

        dag_info = result.data.get("dag", {})
        return ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            score=8.5,
            feedback=(
                f"Pipeline ready: {dag_info.get('node_count', 0)} DAG nodes, "
                f"{dag_info.get('shot_count', 0)} shots."
            ),
        )

    async def collaborate(self, message: AgentMessage) -> AgentMessage:
        """Handle inter-agent messages.

        From REVIEWER: receive audit report and acknowledge.
        """
        if message.from_role == AgentRole.REVIEWER:
            audit_summary = message.data.get("summary", message.content)
            return AgentMessage(
                from_role=AgentRole.PRODUCER,
                to_role=message.from_role,
                content=f"Acknowledged audit report: {audit_summary}",
                data={"acknowledged": True},
            )

        return await super().collaborate(message)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dag(
        episode: Episode,
        series: DramaSeries,
        *,
        max_shots: int | None = None,
    ) -> tuple[DAG, ProjectState]:
        """Delegate to :func:`~videoclaw.drama.runner.build_episode_dag`."""
        from videoclaw.drama.runner import build_episode_dag

        return build_episode_dag(episode, series, max_shots=max_shots)
