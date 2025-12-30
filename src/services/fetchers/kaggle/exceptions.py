"""Custom exceptions for Kaggle fetcher plugin.

Extends existing exception patterns from src/shared/exceptions/
"""
from typing import Optional, Any
import logging


logger = logging.getLogger(__name__)


class KaggleFetcherError(Exception):
    """Base exception for Kaggle fetcher errors.

    Attributes:
        message: Error message
        original: Original exception if any
        context: Additional context information
    """

    def __init__(
        self,
        message: str,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.message = message
        self.original = original
        self.context = context or {}
        super().__init__(self.message)

        logger.error(
            f"{self.__class__.__name__}: {message}",
            extra={"context": self.context},
            exc_info=original is not None,
        )

    def __str__(self) -> str:
        if self.original:
            return f"{self.message} (original: {self.original})"
        return self.message


class KaggleAPIError(KaggleFetcherError):
    """Exception for Kaggle API errors.

    Attributes:
        status_code: HTTP status code if available
        response_text: Response text from API
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.response_text = response_text

        full_context = {"status_code": status_code, "response_text": response_text}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class RateLimitError(KaggleAPIError):
    """Raised when Kaggle rate limit is exceeded.

    Attributes:
        retry_after: Seconds to wait before retrying
    """

    def __init__(
        self,
        message: str = "Kaggle rate limit exceeded",
        retry_after: Optional[int] = None,
        original: Optional[Exception] = None,
    ):
        self.retry_after = retry_after

        context = {"retry_after": retry_after}
        super().__init__(
            message=message,
            status_code=429,
            response_text="Rate limit exceeded",
            original=original,
            context=context,
        )


class APITimeoutError(KaggleAPIError):
    """Raised when Kaggle API request times out.

    Attributes:
        timeout_seconds: Request timeout in seconds
    """

    def __init__(
        self,
        message: str = "Kaggle API request timed out",
        timeout_seconds: Optional[int] = None,
        original: Optional[Exception] = None,
    ):
        self.timeout_seconds = timeout_seconds

        context = {"timeout_seconds": timeout_seconds}
        super().__init__(
            message=message,
            status_code=408,
            response_text="Request timeout",
            original=original,
            context=context,
        )


class NotebookDownloadError(KaggleFetcherError):
    """Exception for notebook download errors.

    Attributes:
        notebook_path: Path to the notebook
        status_code: HTTP status code if available
    """

    def __init__(
        self,
        message: str,
        notebook_path: Optional[str] = None,
        status_code: Optional[int] = None,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.notebook_path = notebook_path
        self.status_code = status_code

        full_context = {"notebook_path": notebook_path, "status_code": status_code}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class NotebookParseError(KaggleFetcherError):
    """Exception for notebook parsing errors.

    Attributes:
        notebook_path: Path to the notebook
        parse_stage: Stage where parsing failed
    """

    def __init__(
        self,
        message: str,
        notebook_path: Optional[str] = None,
        parse_stage: Optional[str] = None,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.notebook_path = notebook_path
        self.parse_stage = parse_stage

        full_context = {"notebook_path": notebook_path, "parse_stage": parse_stage}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class CacheError(KaggleFetcherError):
    """Exception for cache operation errors.

    Attributes:
        operation: Cache operation (get, set, delete)
        key: Cache key involved
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        key: Optional[str] = None,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.operation = operation
        self.key = key

        full_context = {"operation": operation, "key": key}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class CacheKeyError(CacheError):
    """Raised when cache key is invalid."""

    def __init__(
        self,
        key: str,
        reason: str = "Invalid cache key",
    ):
        super().__init__(
            message=f"Invalid cache key: {key} - {reason}",
            operation="validate",
            key=key,
        )


class CacheConnectionError(CacheError):
    """Raised when cache connection fails."""

    def __init__(
        self,
        message: str = "Cache connection failed",
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            operation="connect",
            original=original,
        )


class MessagePublishingError(KaggleFetcherError):
    """Exception for message publishing errors.

    Attributes:
        queue_name: Queue where publishing failed
        message_type: Type of message being published
    """

    def __init__(
        self,
        message: str,
        queue_name: Optional[str] = None,
        message_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        original: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.queue_name = queue_name
        self.message_type = message_type
        self.correlation_id = correlation_id

        full_context = {
            "queue_name": queue_name,
            "message_type": message_type,
            "correlation_id": correlation_id,
        }
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class CircuitOpenError(MessagePublishingError):
    """Raised when circuit breaker is open."""

    def __init__(
        self,
        component: str,
        failure_count: int,
        original: Optional[Exception] = None,
    ):
        self.failure_count = failure_count

        super().__init__(
            message=f"Circuit breaker open for {component} after {failure_count} failures",
            message_type="circuit_breaker",
            context={
                "component": component,
                "failure_count": failure_count,
            },
            original=original,
        )


class ValidationError(KaggleFetcherError):
    """Raised when validation fails.

    Attributes:
        field_name: Name of the field that failed validation
        value: The invalid value
        reason: Why validation failed
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        value: Optional[Any] = None,
        reason: Optional[str] = None,
        context: Optional[dict] = None,
    ):
        self.field_name = field_name
        self.value = value
        self.reason = reason

        full_context = {
            "field_name": field_name,
            "value": str(value) if value is not None else None,
            "reason": reason,
        }
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            context=full_context,
        )


class ConfigurationError(KaggleFetcherError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
    ):
        self.config_key = config_key
        self.config_value = config_value

        super().__init__(
            message=message,
            context={
                "config_key": config_key,
                "config_value": str(config_value) if config_value else None,
            },
        )


__all__ = [
    "KaggleFetcherError",
    "KaggleAPIError",
    "RateLimitError",
    "APITimeoutError",
    "NotebookDownloadError",
    "NotebookParseError",
    "CacheError",
    "CacheKeyError",
    "CacheConnectionError",
    "MessagePublishingError",
    "CircuitOpenError",
    "ValidationError",
    "ConfigurationError",
]

