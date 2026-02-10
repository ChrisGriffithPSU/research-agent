"""LLM-related exceptions."""

from typing import Optional

from src.shared.exceptions.base import ResearchAgentError


class LLMError(ResearchAgentError):
    """Base exception for LLM errors."""

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
