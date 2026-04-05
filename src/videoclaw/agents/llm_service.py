"""Shared LLM service for all agents — single client, cumulative cost tracking."""

from __future__ import annotations

import functools
import logging
from typing import Any

from videoclaw.config import get_config
from videoclaw.models.llm.litellm_wrapper import LLMClient, TokenUsage

logger = logging.getLogger(__name__)


class LLMService:
    """Shared LLM access for all Video Agents.

    Wraps :class:`LLMClient` with role-specific system prompts and cumulative
    cost tracking across all agents.  Use :func:`get_llm_service` to obtain
    the singleton instance.
    """

    def __init__(self, default_model: str | None = None) -> None:
        self._client = LLMClient(
            default_model=default_model or get_config().default_llm,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def think(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Return a plain-text completion with a role-specific system prompt."""
        return await self._client.complete(
            user_prompt,
            system=system_prompt,
            model=model,
            temperature=temperature,
        )

    async def think_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Return a parsed JSON dict with a role-specific system prompt."""
        return await self._client.complete_json(
            user_prompt,
            system=system_prompt,
            model=model,
            temperature=temperature,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def usage(self) -> TokenUsage:
        """Cumulative token usage across all agents."""
        return self._client.usage

    @property
    def client(self) -> LLMClient:
        """Direct access to the underlying LLM client."""
        return self._client

    def __repr__(self) -> str:
        return f"<LLMService tokens_used={self.usage.total_tokens}>"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Return the global :class:`LLMService` singleton."""
    return LLMService()
