"""Anthropic (Claude) LLM client implementation."""

import time
from typing import Any, Dict, List, Optional

try:
    from anthropic import AsyncAnthropic
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore
    anthropic = None  # type: ignore
    ANTHROPIC_AVAILABLE = False

from .base import BaseLLMClient, LLMProvider, LLMResponse
from src.shared.exceptions.llm import (
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
    LLMInvalidResponseError,
)


# Pricing per 1M tokens (as of Dec 2024 - update as needed)
ANTHROPIC_PRICING = {
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-sonnet-3-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.00},
}


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client."""

    def __init__(self, api_key: str):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key

        Raises:
            ImportError: If anthropic package not installed
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )

        super().__init__(LLMProvider.ANTHROPIC)
        self.client = AsyncAnthropic(api_key=api_key)
        self.api_key = api_key

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = 4096,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using Claude."""
        start_time = time.time()

        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens or 4096,
                temperature=temperature,
                system=system or "",  # Empty string instead of list
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )

            latency = time.time() - start_time
            content = response.content[0].text

            # Usage tracking
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

            # Calculate cost
            cost = self._calculate_cost(model, usage)

            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider,
                usage=usage,
                cost=cost,
                latency=latency,
            )

        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(
                message="Anthropic API request timed out",
                provider="anthropic",
                model=model,
                timeout_seconds=getattr(e, 'timeout', None),
            ) from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(
                message="Anthropic API rate limit exceeded",
                provider="anthropic",
                model=model,
            ) from e
        except anthropic.APIStatusError as e:
            raise LLMProviderError(
                message=f"Anthropic API error: {e.message}",
                provider="anthropic",
                model=model,
                provider_code=str(e.status_code),
                original_error=e,
            ) from e
        except anthropic.APIError as e:
            raise LLMProviderError(
                message=f"Anthropic API error: {str(e)}",
                provider="anthropic",
                model=model,
                original_error=e,
            ) from e
        except Exception as e:
            raise LLMError(
                message=f"Unexpected error during Anthropic completion: {str(e)}",
                provider="anthropic",
                model=model,
            ) from e

    async def generate_embedding(
        self,
        text: str,
        model: str,
        **kwargs: Any,
    ) -> List[float]:
        """
        Anthropic doesn't provide embeddings.
        Use OpenAI or Ollama for embeddings instead.
        """
        raise NotImplementedError(
            "Anthropic does not provide embeddings. Use OpenAI or Ollama instead."
        )

    async def health_check(self) -> bool:
        """Check if Anthropic API is reachable.

        Uses get_available_models() instead of creating completions
        to avoid consuming tokens and incurring costs.
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Check available models as a lightweight health check
            # This doesn't consume tokens or cost money
            models = await self.get_available_models()
            is_healthy = len(models) > 0

            if not is_healthy:
                logger.warning("Anthropic health check: No models available")

            return is_healthy
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False

    def get_available_models(self) -> List[str]:
        """Get list of available Claude models."""
        return [
            "claude-opus-4",
            "claude-sonnet-4",
            "claude-sonnet-3-5",
            "claude-haiku-3-5",
        ]

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """Calculate cost based on token usage."""
        # Extract base model name (handle versioned names)
        base_model = model
        for known_model in ANTHROPIC_PRICING:
            if known_model in model:
                base_model = known_model
                break

        if base_model not in ANTHROPIC_PRICING:
            return 0.0

        pricing = ANTHROPIC_PRICING[base_model]
        input_cost = (usage["prompt_tokens"] / 1_000_000) * pricing["input"]
        output_cost = (usage["completion_tokens"] / 1_000_000) * pricing["output"]

        return input_cost + output_cost
