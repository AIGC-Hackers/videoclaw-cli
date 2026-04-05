"""Director agent — wraps core.director.Director with the agent protocol."""

from __future__ import annotations

import logging
from typing import Any

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
from videoclaw.agents.llm_service import LLMService
from videoclaw.core.director import Director

logger = logging.getLogger(__name__)


class DirectorAgent(BaseAgent):
    """Agent wrapper around :class:`Director` for the multi-agent loop.

    Translates the ``think / act / review / collaborate`` protocol into
    calls against the underlying :class:`Director` planning and refinement
    API.
    """

    def __init__(self, llm_service: LLMService | None = None) -> None:
        super().__init__(role=AgentRole.DIRECTOR, llm_service=llm_service)
        self._director = Director(
            llm=self._ensure_llm().client if llm_service else None,
        )

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[str]:
        return ["llm.plan", "llm.refine_prompt"]

    # ------------------------------------------------------------------
    # think
    # ------------------------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentPlan:
        """Extract planning parameters from *context* and build an action plan."""
        prompt = context.get("prompt", "")
        duration = float(context.get("duration", 30.0))
        style = context.get("style")
        aspect_ratio = context.get("aspect_ratio", "16:9")

        steps = [
            AgentStep(
                action="plan",
                params={
                    "prompt": prompt,
                    "duration": duration,
                    "style": style,
                    "aspect_ratio": aspect_ratio,
                },
                description=f"Generate production plan for {duration:.0f}s video",
            ),
        ]

        return AgentPlan(
            agent_role=AgentRole.DIRECTOR,
            steps=steps,
            reasoning=(
                f"Planning a {duration:.0f}s video "
                f"(style={style or 'default'}, ratio={aspect_ratio})"
            ),
        )

    # ------------------------------------------------------------------
    # act
    # ------------------------------------------------------------------

    async def act(self, plan: AgentPlan) -> AgentResult:
        """Execute the plan by delegating to :meth:`Director.plan`."""
        await self._emit("agent.act.start", {"plan_steps": len(plan.steps)})

        try:
            for step in plan.steps:
                if step.action == "plan":
                    params = step.params
                    state = await self._director.plan(
                        prompt_or_state=params["prompt"],
                        duration=params.get("duration", 30.0),
                        style=params.get("style"),
                        aspect_ratio=params.get("aspect_ratio", "16:9"),
                    )

                    return AgentResult(
                        agent_role=AgentRole.DIRECTOR,
                        success=True,
                        data={
                            "project_id": state.project_id,
                            "shot_count": len(state.storyboard),
                            "total_duration": sum(
                                s.duration_seconds for s in state.storyboard
                            ),
                            "state": state,
                        },
                    )

            # No recognised steps executed
            return AgentResult(
                agent_role=AgentRole.DIRECTOR,
                success=False,
                error="No recognised action steps in plan",
            )

        except Exception as exc:
            logger.exception("DirectorAgent.act failed")
            return AgentResult(
                agent_role=AgentRole.DIRECTOR,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # review
    # ------------------------------------------------------------------

    async def review(self, result: AgentResult) -> ReviewResult:
        """Sanity-check the director's own output.

        Rules
        -----
        * Plan must contain at least 1 scene.
        * Total duration must be within 10% of the requested target.
        """
        if not result.success:
            return ReviewResult(
                verdict=ReviewVerdict.REJECT,
                score=0.0,
                feedback=f"Plan failed: {result.error}",
            )

        shot_count = result.data.get("shot_count", 0)
        if shot_count < 1:
            return ReviewResult(
                verdict=ReviewVerdict.REJECT,
                score=1.0,
                feedback="Plan has no scenes — cannot proceed.",
            )

        total_duration = result.data.get("total_duration", 0.0)
        state = result.data.get("state")
        target_duration = (
            float(state.metadata.get("target_duration", 30.0))
            if state and hasattr(state, "metadata")
            else 30.0
        )

        if target_duration > 0:
            deviation = abs(total_duration - target_duration) / target_duration
            if deviation > 0.10:
                return ReviewResult(
                    verdict=ReviewVerdict.RETRY,
                    score=5.0,
                    feedback=(
                        f"Total duration {total_duration:.1f}s deviates "
                        f"{deviation:.0%} from target {target_duration:.1f}s "
                        f"(>10% threshold)"
                    ),
                    suggestions=[
                        "Adjust scene durations to fit the target window",
                    ],
                )

        return ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            score=8.0,
            feedback=(
                f"Plan approved: {shot_count} scenes, "
                f"total {total_duration:.1f}s"
            ),
        )

    # ------------------------------------------------------------------
    # collaborate
    # ------------------------------------------------------------------

    async def collaborate(self, message: AgentMessage) -> AgentMessage:
        """Handle inter-agent messages.

        When the :const:`REVIEWER` sends feedback, call
        :meth:`Director.refine_prompt` and return the improved prompt.
        """
        if message.from_role == AgentRole.REVIEWER:
            original_prompt = message.data.get("original_prompt", "")
            feedback = message.content

            if original_prompt:
                refined = await self._director.refine_prompt(
                    original_prompt, feedback
                )
                return AgentMessage(
                    from_role=AgentRole.DIRECTOR,
                    to_role=AgentRole.REVIEWER,
                    content=f"Prompt refined based on feedback.",
                    data={"refined_prompt": refined},
                )

            return AgentMessage(
                from_role=AgentRole.DIRECTOR,
                to_role=AgentRole.REVIEWER,
                content="Feedback received but no original_prompt provided.",
            )

        # Default acknowledgement for other roles
        return await super().collaborate(message)
