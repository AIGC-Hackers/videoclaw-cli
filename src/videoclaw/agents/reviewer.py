"""Reviewer agent — wraps VisionAuditor and DramaQualityValidator."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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
from videoclaw.drama.quality import DramaQualityValidator
from videoclaw.drama.vision_auditor import VisionAuditor

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """Agent wrapper around :class:`VisionAuditor` and :class:`DramaQualityValidator`.

    Provides vision-based clip auditing and structural quality validation
    through the unified agent protocol.
    """

    def __init__(self, llm_service: LLMService | None = None) -> None:
        super().__init__(role=AgentRole.REVIEWER, llm_service=llm_service)
        self._auditor = VisionAuditor(
            llm=self._ensure_llm().client if llm_service else None,
        )
        self._quality = DramaQualityValidator()

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[str]:
        return ["vision.audit", "quality.validate"]

    # ------------------------------------------------------------------
    # think
    # ------------------------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentPlan:
        """Determine which audit actions to run based on *context* keys.

        Recognised context keys
        -----------------------
        * ``episode``, ``series``, ``drama_manager`` -- series-aware audit
        * ``scenes``, ``clip_dir`` -- standalone clip audit
        * ``series``, ``episode_scripts`` -- quality validation
        """
        steps: list[AgentStep] = []

        # Series-aware episode audit
        if "episode" in context and "series" in context:
            steps.append(
                AgentStep(
                    action="audit_episode",
                    params={
                        "series": context["series"],
                        "episode": context["episode"],
                        "drama_manager": context.get("drama_manager"),
                    },
                    description=(
                        f"Audit episode {context['episode']} clips via VisionAuditor"
                    ),
                ),
            )

        # Standalone clip directory audit
        elif "scenes" in context and "clip_dir" in context:
            steps.append(
                AgentStep(
                    action="audit_clips",
                    params={
                        "scenes": context["scenes"],
                        "clip_dir": context["clip_dir"],
                    },
                    description="Audit clips in directory via VisionAuditor",
                ),
            )

        # Quality validation (can run alongside audit)
        if "series" in context and "episode_scripts" in context:
            steps.append(
                AgentStep(
                    action="validate_quality",
                    params={
                        "series": context["series"],
                        "episode_scripts": context["episode_scripts"],
                    },
                    description="Run DramaQualityValidator checks",
                ),
            )

        if not steps:
            steps.append(
                AgentStep(
                    action="noop",
                    params={},
                    description="No audit targets found in context",
                ),
            )

        return AgentPlan(
            agent_role=AgentRole.REVIEWER,
            steps=steps,
            reasoning=f"Planned {len(steps)} audit step(s)",
        )

    # ------------------------------------------------------------------
    # act
    # ------------------------------------------------------------------

    async def act(self, plan: AgentPlan) -> AgentResult:
        """Execute audit steps."""
        await self._emit("agent.act.start", {"plan_steps": len(plan.steps)})

        combined_data: dict[str, Any] = {}

        try:
            for step in plan.steps:
                if step.action == "audit_episode":
                    params = step.params
                    report = await self._auditor.audit_series_episode(
                        series=params["series"],
                        episode_number=params["episode"],
                        drama_manager=params.get("drama_manager"),
                    )
                    combined_data["audit_report"] = report.to_dict()
                    combined_data["regen_required"] = report.regen_required
                    combined_data["total_shots"] = report.total_shots
                    combined_data["passed_shots"] = report.passed_shots

                elif step.action == "audit_clips":
                    params = step.params
                    report = await self._auditor.audit_clip_dir(
                        scenes=params["scenes"],
                        clip_dir=Path(params["clip_dir"]),
                    )
                    combined_data["audit_report"] = report.to_dict()
                    combined_data["regen_required"] = report.regen_required
                    combined_data["total_shots"] = report.total_shots
                    combined_data["passed_shots"] = report.passed_shots

                elif step.action == "validate_quality":
                    params = step.params
                    violations = self._quality.validate(
                        series=params["series"],
                        episode_scripts=params["episode_scripts"],
                    )
                    combined_data["quality_violations"] = violations

                elif step.action == "noop":
                    pass

            return AgentResult(
                agent_role=AgentRole.REVIEWER,
                success=True,
                data=combined_data,
            )

        except (OSError, RuntimeError, asyncio.TimeoutError, ValueError) as exc:
            logger.exception("ReviewerAgent.act failed")
            return AgentResult(
                agent_role=AgentRole.REVIEWER,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # review — the core quality gate
    # ------------------------------------------------------------------

    async def review(self, result: AgentResult) -> ReviewResult:
        """Evaluate audit data and decide the verdict.

        Decision matrix
        ---------------
        * ``regen_required`` is empty -> APPROVED
        * >50% shots failed -> REJECT (re-plan needed)
        * Otherwise -> RETRY with specific scene IDs
        """
        if not result.success:
            return ReviewResult(
                verdict=ReviewVerdict.REJECT,
                score=0.0,
                feedback=f"Audit failed: {result.error}",
            )

        regen_required: list[str] = result.data.get("regen_required", [])
        total_shots: int = result.data.get("total_shots", 0)
        passed_shots: int = result.data.get("passed_shots", 0)
        quality_violations: list[str] = result.data.get("quality_violations", [])

        # Build feedback parts
        feedback_parts: list[str] = []
        suggestions: list[str] = []

        if quality_violations:
            feedback_parts.append(
                f"{len(quality_violations)} quality violation(s) detected"
            )
            suggestions.extend(quality_violations)

        # No regen needed — everything passed vision audit
        if not regen_required:
            score = 9.0 if not quality_violations else 7.0
            feedback_parts.insert(
                0,
                f"All {total_shots} shots passed vision audit.",
            )
            return ReviewResult(
                verdict=ReviewVerdict.APPROVED,
                score=score,
                feedback=" ".join(feedback_parts),
                suggestions=suggestions,
            )

        # Calculate failure ratio
        fail_ratio = len(regen_required) / total_shots if total_shots > 0 else 1.0

        if fail_ratio > 0.50:
            feedback_parts.insert(
                0,
                (
                    f"{len(regen_required)}/{total_shots} shots need regen "
                    f"({fail_ratio:.0%}) — exceeds 50% threshold."
                ),
            )
            suggestions.append(
                "Consider re-planning the episode with adjusted prompts."
            )
            return ReviewResult(
                verdict=ReviewVerdict.REJECT,
                score=2.0,
                feedback=" ".join(feedback_parts),
                suggestions=suggestions,
            )

        # Partial failure — retry specific shots
        feedback_parts.insert(
            0,
            (
                f"{len(regen_required)}/{total_shots} shots need regen: "
                f"{', '.join(regen_required)}"
            ),
        )
        suggestions.append(
            f"Regenerate shots: {', '.join(regen_required)}"
        )
        score = max(3.0, 8.0 - len(regen_required))

        return ReviewResult(
            verdict=ReviewVerdict.RETRY,
            score=score,
            feedback=" ".join(feedback_parts),
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------
    # collaborate
    # ------------------------------------------------------------------

    async def collaborate(self, message: AgentMessage) -> AgentMessage:
        """Handle inter-agent messages.

        From DIRECTOR: acknowledge refined prompts.
        """
        if message.from_role == AgentRole.DIRECTOR:
            return AgentMessage(
                from_role=AgentRole.REVIEWER,
                to_role=AgentRole.DIRECTOR,
                content="Acknowledged: refined prompts received, ready for re-audit.",
                data=message.data,
            )

        return await super().collaborate(message)
