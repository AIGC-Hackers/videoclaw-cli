"""Tests for the agent framework — protocol compliance, delegation, orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videoclaw.agents.base import (
    AgentMessage,
    AgentPlan,
    AgentResult,
    AgentRole,
    AgentStep,
    ReviewResult,
    ReviewVerdict,
    VideoAgent,
)
from videoclaw.agents.cameraman import CameramanAgent
from videoclaw.agents.director import DirectorAgent
from videoclaw.agents.producer import ProducerAgent
from videoclaw.agents.registry import AgentRegistry
from videoclaw.agents.reviewer import ReviewerAgent
from videoclaw.agents.team import AgentTeam


# =====================================================================
# Protocol compliance — every agent must satisfy VideoAgent
# =====================================================================


class TestProtocolCompliance:
    """All concrete agents must be runtime-checkable VideoAgent instances."""

    @pytest.mark.parametrize("cls,role", [
        (DirectorAgent, AgentRole.DIRECTOR),
        (ReviewerAgent, AgentRole.REVIEWER),
        (CameramanAgent, AgentRole.CAMERAMAN),
        (ProducerAgent, AgentRole.PRODUCER),
    ])
    def test_isinstance_video_agent(self, cls: type, role: AgentRole) -> None:
        agent = cls()
        assert isinstance(agent, VideoAgent)
        assert agent.role == role

    @pytest.mark.parametrize("cls", [
        DirectorAgent, ReviewerAgent, CameramanAgent, ProducerAgent,
    ])
    def test_has_tools(self, cls: type) -> None:
        agent = cls()
        assert isinstance(agent.tools, list)
        assert len(agent.tools) > 0
        assert all(isinstance(t, str) for t in agent.tools)


# =====================================================================
# DirectorAgent
# =====================================================================


class TestDirectorAgent:
    async def test_think_returns_plan(self) -> None:
        agent = DirectorAgent()
        context = {"prompt": "test video", "duration": 30.0}
        plan = await agent.think(context)
        assert isinstance(plan, AgentPlan)
        assert plan.agent_role == AgentRole.DIRECTOR
        assert len(plan.steps) > 0

    async def test_act_delegates_to_director(self) -> None:
        mock_state = MagicMock()
        mock_state.storyboard = [MagicMock(), MagicMock()]
        mock_state.to_dict.return_value = {"shots": 2}

        with patch("videoclaw.agents.director.Director") as MockDirector:
            mock_director = MockDirector.return_value
            mock_director.plan = AsyncMock(return_value=mock_state)

            agent = DirectorAgent()
            plan = AgentPlan(
                agent_role=AgentRole.DIRECTOR,
                steps=[AgentStep(
                    action="plan",
                    params={"prompt": "test", "duration": 30.0},
                )],
            )
            result = await agent.act(plan)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.data["shot_count"] == 2

    async def test_review_approves_good_plan(self) -> None:
        agent = DirectorAgent()
        result = AgentResult(
            agent_role=AgentRole.DIRECTOR,
            success=True,
            data={
                "shot_count": 5,
                "total_duration": 28.0,  # within 10% of 30
                "target_duration": 30.0,
            },
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.APPROVED

    async def test_review_rejects_empty_plan(self) -> None:
        agent = DirectorAgent()
        result = AgentResult(
            agent_role=AgentRole.DIRECTOR,
            success=True,
            data={"shot_count": 0, "total_duration": 0, "target_duration": 30.0},
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.REJECT

    async def test_collaborate_refines_prompt(self) -> None:
        with patch("videoclaw.agents.director.Director") as MockDirector:
            mock_director = MockDirector.return_value
            mock_director.refine_prompt = AsyncMock(return_value="improved prompt")

            agent = DirectorAgent()
            message = AgentMessage(
                from_role=AgentRole.REVIEWER,
                to_role=AgentRole.DIRECTOR,
                content="Fix the lighting",
                data={"original_prompt": "dark scene"},
            )
            reply = await agent.collaborate(message)

        assert isinstance(reply, AgentMessage)
        assert reply.from_role == AgentRole.DIRECTOR
        assert "improved prompt" in reply.data.get("refined_prompt", "")


# =====================================================================
# ReviewerAgent
# =====================================================================


class TestReviewerAgent:
    async def test_think_returns_plan(self) -> None:
        agent = ReviewerAgent()
        context = {
            "scenes": [{"scene_id": "s01"}],
            "clip_dir": "/tmp/clips",
        }
        plan = await agent.think(context)
        assert isinstance(plan, AgentPlan)
        assert plan.agent_role == AgentRole.REVIEWER

    async def test_review_approves_clean_audit(self) -> None:
        agent = ReviewerAgent()
        result = AgentResult(
            agent_role=AgentRole.REVIEWER,
            success=True,
            data={
                "total_shots": 10,
                "regen_required": [],
                "pass_rate": 1.0,
            },
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.APPROVED

    async def test_review_retries_partial_failure(self) -> None:
        agent = ReviewerAgent()
        result = AgentResult(
            agent_role=AgentRole.REVIEWER,
            success=True,
            data={
                "total_shots": 10,
                "regen_required": ["s01", "s02", "s03"],
                "pass_rate": 0.7,
            },
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.RETRY
        # Suggestions contain scene IDs in some form
        assert any("s01" in s for s in review.suggestions)

    async def test_review_rejects_majority_failure(self) -> None:
        agent = ReviewerAgent()
        result = AgentResult(
            agent_role=AgentRole.REVIEWER,
            success=True,
            data={
                "total_shots": 10,
                "regen_required": ["s01", "s02", "s03", "s04", "s05", "s06"],
                "pass_rate": 0.4,
            },
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.REJECT


# =====================================================================
# CameramanAgent
# =====================================================================


class TestCameramanAgent:
    async def test_think_returns_plan(self) -> None:
        agent = CameramanAgent()
        mock_episode = MagicMock()
        mock_episode.scenes = [MagicMock(scene_id="s01")]
        context = {
            "series": MagicMock(title="Test Series"),
            "episode": mock_episode,
        }
        plan = await agent.think(context)
        assert isinstance(plan, AgentPlan)
        assert plan.agent_role == AgentRole.CAMERAMAN

    async def test_review_approves_enhanced_prompts(self) -> None:
        agent = CameramanAgent()
        result = AgentResult(
            agent_role=AgentRole.CAMERAMAN,
            success=True,
            data={"enhanced_count": 5},
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.APPROVED

    async def test_review_flags_zero_enhanced(self) -> None:
        agent = CameramanAgent()
        result = AgentResult(
            agent_role=AgentRole.CAMERAMAN,
            success=True,
            data={"enhanced_count": 0},
        )
        review = await agent.review(result)
        # Zero enhanced should not be APPROVED
        assert review.verdict in (ReviewVerdict.RETRY, ReviewVerdict.MODIFY)


# =====================================================================
# ProducerAgent
# =====================================================================


class TestProducerAgent:
    async def test_think_returns_plan(self) -> None:
        agent = ProducerAgent()
        context = {
            "series_id": "test123",
            "episode_number": 1,
            "budget_usd": 10.0,
        }
        plan = await agent.think(context)
        assert isinstance(plan, AgentPlan)
        assert plan.agent_role == AgentRole.PRODUCER

    async def test_review_approves_success(self) -> None:
        agent = ProducerAgent()
        result = AgentResult(
            agent_role=AgentRole.PRODUCER,
            success=True,
            data={"node_count": 15},
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.APPROVED

    async def test_review_modifies_on_budget_exceed(self) -> None:
        agent = ProducerAgent()
        result = AgentResult(
            agent_role=AgentRole.PRODUCER,
            success=False,
            data={
                "budget": {
                    "exceeded": True,
                    "current_cost_usd": 15.0,
                    "budget_usd": 10.0,
                },
            },
        )
        review = await agent.review(result)
        assert review.verdict == ReviewVerdict.MODIFY


# =====================================================================
# AgentRegistry
# =====================================================================


class TestAgentRegistry:
    def test_register_and_get(self) -> None:
        registry = AgentRegistry()
        agent = DirectorAgent()
        registry.register(agent)
        assert registry.get(AgentRole.DIRECTOR) is agent

    def test_register_duplicate_raises(self) -> None:
        registry = AgentRegistry()
        registry.register(DirectorAgent())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(DirectorAgent())

    def test_get_missing_raises(self) -> None:
        registry = AgentRegistry()
        with pytest.raises(KeyError, match="No agent registered"):
            registry.get(AgentRole.DIRECTOR)

    def test_has(self) -> None:
        registry = AgentRegistry()
        assert not registry.has(AgentRole.DIRECTOR)
        registry.register(DirectorAgent())
        assert registry.has(AgentRole.DIRECTOR)

    def test_list_agents(self) -> None:
        registry = AgentRegistry()
        registry.register(DirectorAgent())
        registry.register(ReviewerAgent())
        agents = registry.list_agents()
        assert len(agents) == 2
        roles = {a["role"] for a in agents}
        assert "director" in roles
        assert "reviewer" in roles

    def test_len_and_contains(self) -> None:
        registry = AgentRegistry()
        assert len(registry) == 0
        registry.register(DirectorAgent())
        assert len(registry) == 1
        assert AgentRole.DIRECTOR in registry


# =====================================================================
# AgentTeam
# =====================================================================


class TestAgentTeam:
    def test_install_handlers_on_executor(self) -> None:
        registry = AgentRegistry()
        registry.register(DirectorAgent())
        registry.register(CameramanAgent())

        team = AgentTeam(registry=registry)
        executor = MagicMock()
        team.install_handlers(executor)

        # Should have called register_handler for SCRIPT_GEN, STORYBOARD (director)
        # and VIDEO_GEN (cameraman)
        assert executor.register_handler.call_count >= 2

    def test_skips_missing_agents(self) -> None:
        registry = AgentRegistry()
        # Only register director, not cameraman or reviewer
        registry.register(DirectorAgent())

        team = AgentTeam(registry=registry)
        executor = MagicMock()
        team.install_handlers(executor)

        # Should only install handlers for director's task types
        for call in executor.register_handler.call_args_list:
            task_type = call[0][0]
            from videoclaw.core.planner import TaskType
            assert task_type in (TaskType.SCRIPT_GEN, TaskType.STORYBOARD)

    # ------------------------------------------------------------------
    # run_collaboration tests
    # ------------------------------------------------------------------

    async def test_collaboration_loop_approves(self) -> None:
        """Mock all agents; reviewer approves immediately — 1 round."""
        registry = AgentRegistry()

        # --- Director mock ---
        director = MagicMock(spec=DirectorAgent)
        director.role = AgentRole.DIRECTOR
        director.tools = ["llm.plan"]
        director_plan = AgentPlan(
            agent_role=AgentRole.DIRECTOR,
            steps=[AgentStep(action="plan", params={"prompt": "test"})],
        )
        director_result = AgentResult(
            agent_role=AgentRole.DIRECTOR,
            success=True,
            data={"shot_count": 5, "total_duration": 30.0},
            cost_usd=0.01,
        )
        director.think = AsyncMock(return_value=director_plan)
        director.act = AsyncMock(return_value=director_result)
        registry.register(director)

        # --- Cameraman mock ---
        cameraman = MagicMock(spec=CameramanAgent)
        cameraman.role = AgentRole.CAMERAMAN
        cameraman.tools = ["prompt.enhance"]
        cam_plan = AgentPlan(
            agent_role=AgentRole.CAMERAMAN,
            steps=[AgentStep(action="enhance_all", params={})],
        )
        cam_result = AgentResult(
            agent_role=AgentRole.CAMERAMAN,
            success=True,
            data={"enhanced_count": 5},
            cost_usd=0.005,
        )
        cameraman.think = AsyncMock(return_value=cam_plan)
        cameraman.act = AsyncMock(return_value=cam_result)
        registry.register(cameraman)

        # --- Reviewer mock ---
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.role = AgentRole.REVIEWER
        reviewer.tools = ["vision.audit"]
        reviewer.review = AsyncMock(return_value=ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            score=9.0,
            feedback="All shots passed.",
        ))
        registry.register(reviewer)

        team = AgentTeam(registry=registry)
        result = await team.run_collaboration({"prompt": "test video"})

        assert result["rounds"] == 1
        assert result["final_verdict"] == ReviewVerdict.APPROVED
        assert result["cost_usd"] == pytest.approx(0.015)
        director.think.assert_awaited_once()
        director.act.assert_awaited_once()
        cameraman.think.assert_awaited_once()
        reviewer.review.assert_awaited_once()

    async def test_collaboration_loop_retries(self) -> None:
        """Reviewer returns RETRY first, then APPROVED — 2 rounds."""
        registry = AgentRegistry()

        # --- Director mock ---
        director = MagicMock(spec=DirectorAgent)
        director.role = AgentRole.DIRECTOR
        director.tools = ["llm.plan"]
        director_plan = AgentPlan(
            agent_role=AgentRole.DIRECTOR,
            steps=[AgentStep(action="plan", params={"prompt": "test"})],
        )
        director_result = AgentResult(
            agent_role=AgentRole.DIRECTOR,
            success=True,
            data={"shot_count": 5, "total_duration": 30.0},
            cost_usd=0.01,
        )
        director.think = AsyncMock(return_value=director_plan)
        director.act = AsyncMock(return_value=director_result)
        director.collaborate = AsyncMock(return_value=AgentMessage(
            from_role=AgentRole.DIRECTOR,
            to_role=AgentRole.REVIEWER,
            content="Prompt refined.",
            data={"refined_prompt": "improved prompt"},
        ))
        registry.register(director)

        # --- Reviewer mock: RETRY then APPROVED ---
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.role = AgentRole.REVIEWER
        reviewer.tools = ["vision.audit"]
        reviewer.review = AsyncMock(side_effect=[
            ReviewResult(
                verdict=ReviewVerdict.RETRY,
                score=4.0,
                feedback="Lighting is wrong",
                suggestions=["Fix lighting"],
            ),
            ReviewResult(
                verdict=ReviewVerdict.APPROVED,
                score=8.5,
                feedback="Looks good now.",
            ),
        ])
        registry.register(reviewer)

        team = AgentTeam(registry=registry)
        result = await team.run_collaboration({"prompt": "test video"})

        assert result["rounds"] == 2
        assert result["final_verdict"] == ReviewVerdict.APPROVED
        assert result["cost_usd"] == pytest.approx(0.02)
        assert director.think.await_count == 2
        assert director.collaborate.await_count == 1
        assert reviewer.review.await_count == 2

    async def test_collaboration_loop_max_rounds(self) -> None:
        """Reviewer always returns RETRY — loop stops after max_rounds."""
        registry = AgentRegistry()

        # --- Director mock ---
        director = MagicMock(spec=DirectorAgent)
        director.role = AgentRole.DIRECTOR
        director.tools = ["llm.plan"]
        director.think = AsyncMock(return_value=AgentPlan(
            agent_role=AgentRole.DIRECTOR,
            steps=[AgentStep(action="plan", params={})],
        ))
        director.act = AsyncMock(return_value=AgentResult(
            agent_role=AgentRole.DIRECTOR,
            success=True,
            data={"shot_count": 3},
            cost_usd=0.01,
        ))
        director.collaborate = AsyncMock(return_value=AgentMessage(
            from_role=AgentRole.DIRECTOR,
            to_role=AgentRole.REVIEWER,
            content="Refined.",
            data={},
        ))
        registry.register(director)

        # --- Reviewer mock: always RETRY ---
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.role = AgentRole.REVIEWER
        reviewer.tools = ["vision.audit"]
        reviewer.review = AsyncMock(return_value=ReviewResult(
            verdict=ReviewVerdict.RETRY,
            score=3.0,
            feedback="Still not good enough",
            suggestions=["Try harder"],
        ))
        registry.register(reviewer)

        team = AgentTeam(registry=registry)
        result = await team.run_collaboration(
            {"prompt": "stubborn test"}, max_rounds=3,
        )

        assert result["rounds"] == 3
        assert result["final_verdict"] == ReviewVerdict.RETRY
        assert result["cost_usd"] == pytest.approx(0.03)
        assert director.think.await_count == 3
        assert director.collaborate.await_count == 3
        assert reviewer.review.await_count == 3
