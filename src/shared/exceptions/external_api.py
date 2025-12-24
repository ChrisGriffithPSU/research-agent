"""External API-related exceptions."""
from typing import Optional


class ExternalAPIError(Exception):
    """Base exception for external API errors.
    
    Args:
        message: Human-readable error message
        provider: External service (arxiv, kaggle, huggingface, etc.)
        status_code: HTTP status code if available
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"Provider: {self.provider}")
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        return " | ".join(parts)


class APITimeoutError(ExternalAPIError):
    """External API request timed out."""
    
    def __init__(
        self,
        message: str = "API request timed out",
        provider: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        details = {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, provider, None, details)


class APIConnectionError(ExternalAPIError):
    """Failed to connect to external API."""
    
    def __init__(
        self,
        message: str = "Failed to connect to API",
        provider: Optional[str] = None,
        endpoint: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if endpoint is not None:
            details["endpoint"] = endpoint
        super().__init__(message, provider, None, details)
        self.original_error = original_error


class APIAuthError(ExternalAPIError):
    """External API authentication failed."""
    
    def __init__(
        self,
        message: str = "API authentication failed",
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message, provider, status_code)


class APIRateLimitError(ExternalAPIError):
    """External API rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "API rate limit exceeded",
        provider: Optional[str] = None,
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        full_details = details or {}
        if retry_after is not None:
            full_details["retry_after_seconds"] = retry_after
        if limit is not None:
            full_details["limit_per_interval"] = limit
        super().__init__(message, provider, 429, full_details)


class APIServerError(ExternalAPIError):
    """External API returned 5xx error."""
    
    def __init__(
        self,
        message: str = "External API server error",
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        details = {}
        if error_code is not None:
            details["api_error_code"] = error_code
        super().__init__(message, provider, status_code, details)


class APIInvalidResponseError(ExternalAPIError):
    """External API returned invalid/unexpected response."""
    
    def __init__(
        self,
        message: str = "Invalid API response",
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        response_snippet: Optional[str] = None,
    ):
        details = {}
        if response_snippet is not None:
            details["response_snippet"] = response_snippet[:500]
        super().__init__(message, provider, status_code, details)


class APIClientError(ExternalAPIError):
    """External API returned 4xx client error (not auth/rate limit)."""
    
    def __init__(
        self,
        message: str = "API client error",
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        details = {}
        if error_code is not None:
            details["api_error_code"] = error_code
        super().__init__(message, provider, status_code, details)

