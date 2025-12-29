"""LLM-related exceptions."""
from typing import Optional

from src.shared.exceptions.base import ResearchAgentError
from src.shared.constants import MAX_ERROR_SNIPPET_LENGTH


class LLMError(ResearchAgentError):
    """Base exception for LLM errors.

    All LLM-related exceptions inherit from this class.
    Provides structured error information with error codes and details.

    Args:
        message: Human-readable error message
        provider: LLM provider (anthropic, openai, ollama)
        model: Model name that failed
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        self.provider = provider
        self.model = model
        super().__init__(
            message=message,
            error_code="LLM_ERROR",
            details=details,
            original=original,
        )

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"Provider: {self.provider}")
        if self.model:
            parts.append(f"Model: {self.model}")
        return " | ".join(parts)


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    def __init__(
        self,
        message: str = "LLM request timed out",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        original: Optional[Exception] = None,
    ):
        details = {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, provider, model, details, original)


class LLMRateLimitError(LLMError):
    """LLM provider rate limit exceeded."""

    def __init__(
        self,
        message: str = "LLM rate limit exceeded",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        original: Optional[Exception] = None,
    ):
        details = {}
        if retry_after is not None:
            details["retry_after_seconds"] = retry_after
        if limit is not None:
            details["limit_per_minute"] = limit
        super().__init__(message, provider, model, details, original)


class LLMProviderError(LLMError):
    """LLM provider returned an error."""

    def __init__(
        self,
        message: str = "LLM provider error",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        provider_code: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if provider_code is not None:
            details["provider_code"] = provider_code
        super().__init__(message, provider, model, details, original_error)


class LLMQuotaExceededError(LLMError):
    """LLM daily cost cap exceeded."""

    def __init__(
        self,
        message: str = "LLM cost cap exceeded",
        provider: Optional[str] = None,
        daily_cap: Optional[float] = None,
        current_spend: Optional[float] = None,
        original: Optional[Exception] = None,
    ):
        details = {}
        if daily_cap is not None:
            details["daily_cap_usd"] = daily_cap
        if current_spend is not None:
            details["current_spend_usd"] = current_spend
        super().__init__(message, provider, None, details, original)


class LLMInvalidResponseError(LLMError):
    """LLM provider returned invalid/unexpected response."""

    def __init__(
        self,
        message: str = "Invalid LLM response",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        response_snippet: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        details = {}
        if response_snippet is not None:
            details["response_snippet"] = response_snippet[:MAX_ERROR_SNIPPET_LENGTH]
        super().__init__(message, provider, model, details, original)


class AllLLMProvidersFailedError(LLMError):
    """All LLM providers failed to complete request."""

    def __init__(
        self,
        message: str = "All LLM providers failed",
        attempted_providers: Optional[list] = None,
        errors: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        details = {}
        if attempted_providers is not None:
            details["attempted_providers"] = attempted_providers
        if errors is not None:
            details["errors"] = errors
        super().__init__(message, None, None, details, original)

