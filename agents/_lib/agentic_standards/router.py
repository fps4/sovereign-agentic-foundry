"""
LLMRouter — provider abstraction and model-tier routing.

The foundry currently routes all tasks through a single Ollama model
(llama3.1:8b). This module makes the routing rules explicit and swappable
without changing agent code.

Model tiers
-----------
FAST    — local Ollama, cheap, suitable for classification and summarisation
STANDARD — local Ollama (larger) or cloud, suitable for general generation
STRONG  — cloud (Claude / GPT-4o), suitable for compliance, complex reasoning

Usage:
    router = LLMRouter()
    client = router.get_client(ModelTier.STRONG)
    response = await client.acomplete(messages)
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

try:
    import litellm  # type: ignore[import-untyped]
    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False


class ModelTier(str, Enum):
    """
    Routing hint passed by the orchestrator or workflow to agents.

    Agents should not hard-code model names — they should accept a tier
    and let the router resolve the actual model identifier.
    """

    FAST = "fast"         # Intent classification, log summarisation, short rewrites
    STANDARD = "standard" # Code scaffolding, spec generation, test generation
    STRONG = "strong"     # Compliance review, security audit, complex reasoning


# Default model map — override via environment variables
_DEFAULT_MODEL_MAP: dict[ModelTier, str] = {
    ModelTier.FAST: os.environ.get("MODEL_FAST", "ollama/llama3.1:8b"),
    ModelTier.STANDARD: os.environ.get("MODEL_STANDARD", "ollama/llama3.1:8b"),
    ModelTier.STRONG: os.environ.get("MODEL_STRONG", "ollama/llama3.1:70b"),
}

_DEFAULT_API_BASE = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")

_UNSET = object()  # sentinel — distinguishes "not passed" from explicit None


class LLMRouter:
    """
    Thin wrapper around LiteLLM that enforces the model-tier contract.

    All agents should use this router rather than instantiating LLM clients
    directly. This decouples model selection from agent logic and makes it
    trivial to swap local for cloud without touching agent code.

    When litellm is not installed, ``complete()`` raises ImportError with
    a clear message — fail loudly at call time, not at import time.
    """

    def __init__(
        self,
        model_map: dict[ModelTier, str] | None = None,
        api_base: str | None = _UNSET,  # type: ignore[assignment]
    ) -> None:
        self._model_map = model_map or _DEFAULT_MODEL_MAP
        # Explicit None → do not pass api_base to litellm (cloud providers).
        # Unset → fall back to OLLAMA_BASE_URL default.
        self._api_base = _DEFAULT_API_BASE if api_base is _UNSET else api_base

    def resolve(self, tier: ModelTier) -> str:
        """Return the concrete model identifier for a given tier."""
        return self._model_map[tier]

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: ModelTier = ModelTier.STANDARD,
        *,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        """
        Call the LLM for the given tier and return the text response.

        Args:
            messages: OpenAI-style message list.
            tier: Which model tier to use.
            response_format: Optional JSON schema for structured output.
            temperature: Sampling temperature (low = more deterministic).
            **kwargs: Passed through to litellm.acompletion().

        Returns:
            The assistant message content as a string.

        Raises:
            ImportError: If litellm is not installed.
            litellm.exceptions.APIError: On provider errors.
        """
        if not _LITELLM_AVAILABLE:
            raise ImportError(
                "litellm is required for LLMRouter. "
                "Install it with: pip install agentic-standards[litellm]"
            )

        model = self.resolve(tier)
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        if self._api_base is not None:
            call_kwargs["api_base"] = self._api_base
        if response_format:
            call_kwargs["response_format"] = response_format

        response = await litellm.acompletion(**call_kwargs)
        return response.choices[0].message.content  # type: ignore[no-any-return]

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        tier: ModelTier = ModelTier.STANDARD,
        **kwargs: Any,
    ) -> str:
        """Convenience wrapper that sets response_format to JSON mode."""
        return await self.complete(
            messages,
            tier=tier,
            response_format={"type": "json_object"},
            **kwargs,
        )
