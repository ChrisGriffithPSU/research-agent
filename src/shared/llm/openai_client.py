"""Simplified OpenAI-compatible LLM client for custom endpoints.

Supports any OpenAI-compatible API endpoint with configurable
base URL, API key, and model name via environment variables.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol

from openai import AsyncOpenAI

from src.shared.exceptions.llm import LLMError, LLMProviderError


class LLMResponse:
    """Standardized LLM response format."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: Optional[Dict[str, int]] = None,
        latency_ms: Optional[float] = None,
    ):
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.latency_ms = latency_ms

    def __repr__(self) -> str:
        return (
            f"LLMResponse(model={self.model}, "
            f"content_length={len(self.content)}, "
            f"latency={self.latency_ms:.0f}ms)"
        )


class ILLMClient(Protocol):
    """Protocol for LLM client operations."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion from LLM."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if LLM service is healthy."""
        ...


class OpenAIClient:
    """OpenAI-compatible client for custom endpoints.

    Configured via environment variables:
    - CUSTOM_LLM_BASE_URL: Base URL for the API endpoint
    - CUSTOM_LLM_API_KEY: API key for authentication
    - CUSTOM_LLM_MODEL: Model name to use (default: "default")
    - CUSTOM_LLM_MAX_RETRIES: Max retries for failed requests (default: 3)
    - CUSTOM_LLM_TIMEOUT_SECONDS: Request timeout (default: 120)

    Example:
        client = OpenAIClient()
        response = await client.complete(
            prompt="Extract concepts from this paper...",
            system="You are a research assistant...",
            temperature=0.3,
        )
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ):
        """Initialize OpenAI client.

        Args:
            base_url: API base URL (falls back to env var)
            api_key: API key (falls back to env var)
            model: Model name (falls back to env var)
            max_retries: Max retry attempts (falls back to env var)
            timeout_seconds: Request timeout (falls back to env var)
        """
        self.base_url = base_url or os.getenv("CUSTOM_LLM_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("CUSTOM_LLM_API_KEY", "")
        self.model = model or os.getenv("CUSTOM_LLM_MODEL", "default")
        self.max_retries = max_retries or int(os.getenv("CUSTOM_LLM_MAX_RETRIES", "3"))
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("CUSTOM_LLM_TIMEOUT_SECONDS", "120")
        )

        if not self.api_key:
            raise LLMError("CUSTOM_LLM_API_KEY environment variable not set")

        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            max_retries=self.max_retries,
            timeout=self.timeout_seconds,
        )

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion from LLM.

        Args:
            prompt: User prompt/message
            system: System prompt/instructions
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            response_format: JSON schema for structured output
            **kwargs: Additional API-specific arguments

        Returns:
            LLMResponse with generated content

        Raises:
            LLMProviderError: If the API call fails
        """
        start_time = time.time()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            params: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            if response_format:
                params["response_format"] = response_format

            params.update(kwargs)

            response = await self._client.chat.completions.create(**params)

            latency_ms = (time.time() - start_time) * 1000

            content = response.choices[0].message.content or ""

            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                latency_ms=latency_ms,
            )

        except Exception as e:
            raise LLMProviderError(
                message=f"LLM completion failed: {str(e)}",
                provider="openai",
                model=self.model,
                original_error=e,
            ) from e

    async def health_check(self) -> bool:
        """Check if LLM service is accessible.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the configured model.

        Returns:
            Dict with model configuration
        """
        return {
            "model": self.model,
            "base_url": self.base_url,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }
