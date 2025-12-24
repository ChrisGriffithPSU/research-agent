"""Anthropic (Claude) LLM client implementation."""

import time
from typing import Any, Dict, List, Optional
from anthropic import AsyncAnthropic

from .base import BaseLLMClient, LLMProvider, LLMResponse


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
        """
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
                system=system if system else [],
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

        except Exception as e:
            raise RuntimeError(f"Anthropic completion failed: {str(e)}")

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
        """Check if Anthropic API is reachable."""
        try:
            # Make a minimal request to test connectivity
            await self.client.messages.create(
                model="claude-haiku-3-5",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except Exception:
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
