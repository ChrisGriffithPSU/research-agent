"""Simplified OpenAI-compatible LLM client for custom endpoints.

Supports any OpenAI-compatible API endpoint with configurable
base URL, API key, and model name via environment variables.
"""

import json
import os
import re
import time
from abc import abstractmethod
from typing import Any, Protocol

from src.shared.exceptions.llm import LLMError, LLMProviderError


class LLMResponse:
    """Standardized LLM response format."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        latency_ms: float | None = None,
        reasoning_details: Any | None = None,
    ):
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.reasoning_details = reasoning_details

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
        prompt: str | None = None,
        system: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
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

    Configured via environment variables.

    Global defaults:
    - CUSTOM_LLM_BASE_URL
    - CUSTOM_LLM_API_KEY
    - CUSTOM_LLM_MODEL
    - CUSTOM_LLM_MAX_RETRIES
    - CUSTOM_LLM_TIMEOUT_SECONDS

    Optional per-agent overrides (when `profile` is provided):
    - CUSTOM_LLM_<PROFILE>_BASE_URL
    - CUSTOM_LLM_<PROFILE>_API_KEY
    - CUSTOM_LLM_<PROFILE>_MODEL
    - CUSTOM_LLM_<PROFILE>_MAX_RETRIES
    - CUSTOM_LLM_<PROFILE>_TIMEOUT_SECONDS

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
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
        profile: str | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            base_url: API base URL (falls back to env var)
            api_key: API key (falls back to env var)
            model: Model name (falls back to env var)
            max_retries: Max retry attempts (falls back to env var)
            timeout_seconds: Request timeout (falls back to env var)
            profile: Optional agent profile for env override lookup
        """
        self.profile = self._normalize_profile(profile)

        self.base_url = base_url or self._get_env_value(
            "BASE_URL",
            default="https://api.openai.com/v1",
        )
        self.api_key = api_key or self._get_env_value("API_KEY", default="")
        self.model = model or self._get_env_value("MODEL", default="default")
        self.max_retries = max_retries or int(self._get_env_value("MAX_RETRIES", default="3"))
        self.timeout_seconds = timeout_seconds or float(
            self._get_env_value("TIMEOUT_SECONDS", default="120")
        )

        if not self.api_key:
            if self.profile:
                raise LLMError(
                    "LLM API key not set. Expected CUSTOM_LLM_"
                    f"{self.profile}_API_KEY or CUSTOM_LLM_API_KEY"
                )
            raise LLMError("CUSTOM_LLM_API_KEY environment variable not set")

        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            max_retries=self.max_retries,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _normalize_profile(profile: str | None) -> str | None:
        if profile is None:
            return None
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", profile.strip()).strip("_").upper()
        return normalized or None

    def _get_env_value(self, key_suffix: str, default: str) -> str:
        if self.profile:
            profile_key = f"CUSTOM_LLM_{self.profile}_{key_suffix}"
            value = os.getenv(profile_key)
            if value not in (None, ""):
                return value

        default_key = f"CUSTOM_LLM_{key_suffix}"
        value = os.getenv(default_key)
        if value in (None, ""):
            return default
        return value

    async def complete(
        self,
        prompt: str | None = None,
        system: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion from LLM.

        Args:
            prompt: User prompt/message (mutually exclusive with messages)
            system: System prompt/instructions (ignored when messages is provided)
            messages: Full message list for multi-turn conversations.
                Use this when you need to pass back reasoning_details from
                a previous response for continued reasoning.
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            response_format: JSON schema for structured output
            **kwargs: Additional API-specific arguments.
                Pass extra_body={"reasoning": {"enabled": True}} to enable
                reasoning mode (e.g., for OpenRouter's free reasoning model).

        Returns:
            LLMResponse with generated content

        Raises:
            LLMProviderError: If the API call fails
        """
        start_time = time.time()

        # Build messages: either from raw list or from prompt+system
        if messages is not None:
            api_messages = list(messages)
        else:
            if prompt is None:
                raise LLMError("Must provide either 'prompt' or 'messages'")
            api_messages = []
            if system:
                api_messages.append({"role": "system", "content": system})
            api_messages.append({"role": "user", "content": prompt})

        try:
            params: dict[str, Any] = {
                "model": self.model,
                "messages": api_messages,
                "temperature": temperature,
            }

            # Only add extra_body if caller explicitly provides one
            extra_body = kwargs.pop("extra_body", None)
            if extra_body:
                params["extra_body"] = dict(extra_body)

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            if response_format:
                params["response_format"] = response_format

            params.update(kwargs)

            response = await self._client.chat.completions.create(**params)

            latency_ms = (time.time() - start_time) * 1000

            message = response.choices[0].message
            content = self._extract_message_content(message)
            reasoning_details = getattr(message, "reasoning_details", None)

            usage: dict[str, int] = {}
            if response.usage is not None:
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
                reasoning_details=reasoning_details,
            )

        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(
                message=f"LLM completion failed: {str(e)}",
                provider="openai",
                model=self.model,
                original_error=e,
            ) from e

    @staticmethod
    def _extract_message_content(message: Any) -> str:
        """Extract text content from OpenAI-compatible message payloads."""
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            return "\n".join(p for p in text_parts if p)

        if content is None:
            refusal = getattr(message, "refusal", None)
            if isinstance(refusal, str) and refusal:
                return refusal
            return ""

        try:
            return json.dumps(content)
        except Exception:
            return str(content)

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

    def get_model_info(self) -> dict[str, Any]:
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
