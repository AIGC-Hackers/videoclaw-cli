"""Agent framework — autonomous video production agents."""

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
from videoclaw.agents.registry import AgentRegistry, get_agent_registry
from videoclaw.agents.reviewer import ReviewerAgent
from videoclaw.agents.team import AgentTeam

__all__ = [
    "AgentMessage",
    "AgentPlan",
    "AgentRegistry",
    "AgentResult",
    "AgentRole",
    "AgentStep",
    "AgentTeam",
    "CameramanAgent",
    "DirectorAgent",
    "ProducerAgent",
    "ReviewResult",
    "ReviewVerdict",
    "ReviewerAgent",
    "VideoAgent",
    "get_agent_registry",
]
