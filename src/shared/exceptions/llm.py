"""LLM-related exceptions."""


from src.shared.exceptions.base import ResearchAgentError


class LLMError(ResearchAgentError):
    """Base exception for LLM errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        details: dict | None = None,
        original: Exception | None = None,
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
        provider: str | None = None,
        model: str | None = None,
        provider_code: str | None = None,
        original_error: Exception | None = None,
    ):
        details = {}
        if provider_code is not None:
            details["provider_code"] = provider_code
        super().__init__(message, provider, model, details, original_error)
