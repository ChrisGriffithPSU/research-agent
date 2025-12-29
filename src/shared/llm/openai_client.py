"""OpenAI LLM client implementation."""

import time
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI

from .base import BaseLLMClient, LLMProvider, LLMResponse
from src.shared.exceptions.llm import (
    LLMError,
    LLMProviderError,
)


# Pricing per 1M tokens (as of Dec 2024 - update as needed)
OPENAI_PRICING = {
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
    "text-embedding-ada-002": {"input": 0.10, "output": 0.0},
}


class OpenAIClient(BaseLLMClient):
    """OpenAI client for GPT models and embeddings."""

    def __init__(self, api_key: str):
        """
        Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
        """
        super().__init__(LLMProvider.OPENAI)
        self.client = AsyncOpenAI(api_key=api_key)
        self.api_key = api_key

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using OpenAI."""
        start_time = time.time()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            latency = time.time() - start_time
            content = response.choices[0].message.content

            # Usage tracking
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
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
            raise LLMProviderError(
                message=f"OpenAI completion failed: {str(e)}",
                provider="openai",
                model=model,
                original_error=e,
            ) from e

    async def generate_embedding(
        self,
        text: str,
        model: str = "text-embedding-3-small",
        **kwargs: Any,
    ) -> List[float]:
        """Generate embeddings using OpenAI."""
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=text,
                **kwargs
            )

            return response.data[0].embedding

        except Exception as e:
            raise LLMProviderError(
                message=f"OpenAI embedding generation failed: {str(e)}",
                provider="openai",
                model=model,
                original_error=e,
            ) from e

    async def health_check(self) -> bool:
        """Check if OpenAI API is reachable."""
        try:
            # Make a minimal embedding request to test connectivity
            await self.client.embeddings.create(
                model="text-embedding-3-small",
                input="test"
            )
            return True
        except Exception:
            return False

    def get_available_models(self) -> List[str]:
        """Get list of available OpenAI models."""
        return [
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ]

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """Calculate cost based on token usage."""
        # Extract base model name
        base_model = model
        for known_model in OPENAI_PRICING:
            if known_model in model:
                base_model = known_model
                break

        if base_model not in OPENAI_PRICING:
            return 0.0

        pricing = OPENAI_PRICING[base_model]
        input_cost = (usage["prompt_tokens"] / 1_000_000) * pricing["input"]
        output_cost = (usage["completion_tokens"] / 1_000_000) * pricing["output"]

        return input_cost + output_cost
