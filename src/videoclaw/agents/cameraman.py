"""CameramanAgent — prompt enhancement for drama scenes.

Wraps :class:`~videoclaw.drama.prompt_enhancer.PromptEnhancer` to enrich
scene visual prompts with Seedance 2.0 optimised structure (camera, subject,
scene, style, constraints, text directives).
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
    from videoclaw.drama.models import DramaScene, DramaSeries, Episode

logger = logging.getLogger(__name__)

# Minimum acceptable length for an enhanced prompt (characters).
_MIN_PROMPT_LENGTH = 50


class CameramanAgent(BaseAgent):
    """Enhances scene visual prompts for Seedance 2.0 video generation.

    Uses :class:`PromptEnhancer` to build director-style prompts following
    the five-part anatomy: Camera → Subject → Scene → Style → Constraints.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(role=AgentRole.CAMERAMAN, **kwargs)
        self._enhancer: PromptEnhancer | None = None

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[str]:
        return ["prompt.enhance", "video.generate"]

    # ------------------------------------------------------------------
    # Lazy enhancer access
    # ------------------------------------------------------------------

    def _ensure_enhancer(self) -> PromptEnhancer:
        if self._enhancer is None:
            from videoclaw.drama.prompt_enhancer import PromptEnhancer

            self._enhancer = PromptEnhancer()
        return self._enhancer

    # ------------------------------------------------------------------
    # Core agent methods
    # ------------------------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentPlan:
        """Determine which scenes need prompt enhancement.

        Parameters
        ----------
        context:
            Must contain ``"series"`` and ``"episode"`` keys (both dicts or
            model instances).  Optionally includes ``"scene_index"`` to
            target a single scene.
        """
        series: DramaSeries = context["series"]
        episode: Episode = context["episode"]
        scene_index: int | None = context.get("scene_index")

        if scene_index is not None:
            # Single-scene enhancement
            scene: DramaScene = episode.scenes[scene_index]
            return AgentPlan(
                agent_role=AgentRole.CAMERAMAN,
                steps=[
                    AgentStep(
                        action="enhance_scene",
                        params={
                            "scene_index": scene_index,
                            "scene": scene,
                            "series": series,
                        },
                        description=f"Enhance prompt for scene {scene_index}",
                    ),
                ],
                reasoning=f"Single scene {scene_index} targeted for enhancement.",
            )

        # Enhance all scenes in one pass
        return AgentPlan(
            agent_role=AgentRole.CAMERAMAN,
            steps=[
                AgentStep(
                    action="enhance_all",
                    params={"series": series, "episode": episode},
                    description=f"Enhance all {len(episode.scenes)} scene prompts",
                ),
            ],
            reasoning=(
                f"Episode has {len(episode.scenes)} scenes; "
                "batch enhancement is most efficient."
            ),
        )

    async def act(self, plan: AgentPlan) -> AgentResult:
        """Execute the enhancement plan.

        Supports two actions:

        - ``enhance_all``: enhance every scene prompt in the episode.
        - ``enhance_scene``: enhance a single scene prompt.
        """
        enhancer = self._ensure_enhancer()
        enhanced_count = 0
        errors: list[str] = []

        for step in plan.steps:
            try:
                if step.action == "enhance_all":
                    series: DramaSeries = step.params["series"]
                    episode: Episode = step.params["episode"]
                    enhancer.enhance_all_scenes(episode, series)
                    enhanced_count = len(episode.scenes)

                elif step.action == "enhance_scene":
                    scene: DramaScene = step.params["scene"]
                    series = step.params["series"]
                    prompt = enhancer.enhance_scene_prompt(scene, series)
                    scene.enhanced_visual_prompt = prompt
                    enhanced_count = 1

                else:
                    errors.append(f"Unknown action: {step.action}")

            except (OSError, RuntimeError, asyncio.TimeoutError, ValueError) as exc:
                logger.exception("Enhancement failed for step %s", step.action)
                errors.append(f"{step.action}: {exc}")

        await self._emit(
            "cameraman.enhanced",
            {"enhanced_count": enhanced_count, "errors": errors},
        )

        return AgentResult(
            agent_role=AgentRole.CAMERAMAN,
            success=not errors,
            data={"enhanced_count": enhanced_count, "errors": errors},
            error="; ".join(errors) if errors else None,
        )

    async def review(self, result: AgentResult) -> ReviewResult:
        """Validate enhanced prompts: check none are empty and length is reasonable."""
        if not result.success:
            return ReviewResult(
                verdict=ReviewVerdict.RETRY,
                score=2.0,
                feedback=f"Enhancement failed: {result.error}",
                suggestions=["Check series/episode data integrity"],
            )

        enhanced_count = result.data.get("enhanced_count", 0)
        if enhanced_count == 0:
            return ReviewResult(
                verdict=ReviewVerdict.MODIFY,
                score=4.0,
                feedback="No scenes were enhanced.",
                suggestions=["Verify episode contains scenes with visual prompts"],
            )

        # If act() stored the episode in data for deeper validation
        episode: Episode | None = result.data.get("episode")
        if episode is not None:
            empty_prompts: list[int] = []
            short_prompts: list[int] = []
            for i, scene in enumerate(episode.scenes):
                prompt = getattr(scene, "enhanced_visual_prompt", "") or ""
                if not prompt:
                    empty_prompts.append(i)
                elif len(prompt) < _MIN_PROMPT_LENGTH:
                    short_prompts.append(i)

            suggestions: list[str] = []
            if empty_prompts:
                suggestions.append(
                    f"Scenes with empty prompts: {empty_prompts}"
                )
            if short_prompts:
                suggestions.append(
                    f"Scenes with suspiciously short prompts (<{_MIN_PROMPT_LENGTH} chars): "
                    f"{short_prompts}"
                )

            if empty_prompts:
                return ReviewResult(
                    verdict=ReviewVerdict.RETRY,
                    score=3.0,
                    feedback=f"{len(empty_prompts)} scenes have empty enhanced prompts.",
                    suggestions=suggestions,
                )

            if short_prompts:
                return ReviewResult(
                    verdict=ReviewVerdict.MODIFY,
                    score=6.0,
                    feedback=f"{len(short_prompts)} scenes have unusually short prompts.",
                    suggestions=suggestions,
                )

        return ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            score=8.0,
            feedback=f"Successfully enhanced {enhanced_count} scene prompt(s).",
        )

    async def collaborate(self, message: AgentMessage) -> AgentMessage:
        """Handle inter-agent messages.

        From REVIEWER: receive defect info, acknowledge for re-enhancement.
        Learned constraints are injected into the enhancer so subsequent
        prompts avoid previously detected issues.
        """
        if message.from_role == AgentRole.REVIEWER:
            # Extract defect constraints from reviewer feedback
            defects: list[str] = message.data.get("defects", [])
            if defects:
                enhancer = self._ensure_enhancer()
                enhancer.inject_learned_constraints(defects)
                content = (
                    f"Acknowledged {len(defects)} defect(s) from reviewer. "
                    f"Constraints injected for re-enhancement."
                )
            else:
                content = "Acknowledged reviewer feedback; no specific defects to inject."

            return AgentMessage(
                from_role=AgentRole.CAMERAMAN,
                to_role=message.from_role,
                content=content,
            )

        return await super().collaborate(message)
