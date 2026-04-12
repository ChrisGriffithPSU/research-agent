"""Custom exceptions for arXiv fetcher plugin.

Extends existing exception patterns from src/shared/exceptions/
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ArxivFetcherError(Exception):
    """Base exception for arXiv fetcher errors.
    
    Attributes:
        message: Error message
        original: Original exception if any
        context: Additional context information
    """

    def __init__(
        self,
        message: str,
        original: Exception | None = None,
        context: dict | None = None,
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


class ArxivAPIError(ArxivFetcherError):
    """Exception for arXiv API errors.
    
    Attributes:
        status_code: HTTP status code if available
        response_text: Response text from API
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
        original: Exception | None = None,
        context: dict | None = None,
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


class RateLimitError(ArxivAPIError):
    """Raised when arXiv rate limit is exceeded.
    
    Attributes:
        retry_after: Seconds to wait before retrying
    """

    def __init__(
        self,
        message: str = "arXiv rate limit exceeded",
        retry_after: int | None = None,
        original: Exception | None = None,
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


class APITimeoutError(ArxivAPIError):
    """Raised when arXiv API request times out.
    
    Attributes:
        timeout_seconds: Request timeout in seconds
    """

    def __init__(
        self,
        message: str = "arXiv API request timed out",
        timeout_seconds: int | None = None,
        original: Exception | None = None,
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


class APIResponseError(ArxivAPIError):
    """Raised when arXiv API returns an error response.
    
    Attributes:
        error_code: arXiv error code if available
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        original: Exception | None = None,
        context: dict | None = None,
    ):
        self.error_code = error_code

        full_context = {"error_code": error_code}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            status_code=status_code,
            response_text=message,
            original=original,
            context=full_context,
        )


class PDFProcessingError(ArxivFetcherError):
    """Exception for PDF processing errors.
    
    Attributes:
        paper_id: arXiv ID of the paper
        pdf_url: URL to the PDF
    """

    def __init__(
        self,
        message: str,
        paper_id: str | None = None,
        pdf_url: str | None = None,
        original: Exception | None = None,
        context: dict | None = None,
    ):
        self.paper_id = paper_id
        self.pdf_url = pdf_url

        full_context = {"paper_id": paper_id, "pdf_url": pdf_url}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class PDFDownloadError(PDFProcessingError):
    """Raised when PDF download fails."""

    def __init__(
        self,
        pdf_url: str,
        paper_id: str | None = None,
        status_code: int | None = None,
        original: Exception | None = None,
    ):
        self.status_code = status_code

        super().__init__(
            message=f"Failed to download PDF: {pdf_url}",
            paper_id=paper_id,
            pdf_url=pdf_url,
            original=original,
            context={"status_code": status_code},
        )


class PDFParseError(PDFProcessingError):
    """Raised when PDF parsing fails."""

    def __init__(
        self,
        message: str = "Failed to parse PDF",
        paper_id: str | None = None,
        pdf_url: str | None = None,
        parse_stage: str | None = None,
        original: Exception | None = None,
    ):
        self.parse_stage = parse_stage

        super().__init__(
            message=message,
            paper_id=paper_id,
            pdf_url=pdf_url,
            original=original,
            context={"parse_stage": parse_stage},
        )


class PDFSizeError(PDFProcessingError):
    """Raised when PDF exceeds size limit."""

    def __init__(
        self,
        pdf_url: str,
        paper_id: str,
        size_bytes: int,
        max_size_bytes: int,
    ):
        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes

        super().__init__(
            message=f"PDF too large: {size_bytes} bytes (max: {max_size_bytes})",
            paper_id=paper_id,
            pdf_url=pdf_url,
            context={
                "size_bytes": size_bytes,
                "max_size_bytes": max_size_bytes,
            },
        )


class CacheError(ArxivFetcherError):
    """Exception for cache operation errors.
    
    Attributes:
        operation: Cache operation (get, set, delete)
        key: Cache key involved
    """

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        key: str | None = None,
        original: Exception | None = None,
        context: dict | None = None,
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
        original: Exception | None = None,
    ):
        super().__init__(
            message=message,
            operation="connect",
            original=original,
        )


class MessagePublishingError(ArxivFetcherError):
    """Exception for message publishing errors.
    
    Attributes:
        queue_name: Queue where publishing failed
        message_type: Type of message being published
    """

    def __init__(
        self,
        message: str,
        queue_name: str | None = None,
        message_type: str | None = None,
        correlation_id: str | None = None,
        original: Exception | None = None,
        context: dict | None = None,
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
        original: Exception | None = None,
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


class QueryProcessingError(ArxivFetcherError):
    """Exception for query processing errors.
    
    Attributes:
        query: The query that failed
        stage: Processing stage where error occurred
    """

    def __init__(
        self,
        message: str,
        query: str | None = None,
        stage: str | None = None,
        original: Exception | None = None,
        context: dict | None = None,
    ):
        self.query = query
        self.stage = stage

        full_context = {"query": query, "stage": stage}
        if context:
            full_context.update(context)

        super().__init__(
            message=message,
            original=original,
            context=full_context,
        )


class LLMError(QueryProcessingError):
    """Raised when LLM query generation fails."""

    def __init__(
        self,
        message: str = "LLM query generation failed",
        provider: str | None = None,
        model: str | None = None,
        query: str | None = None,
        original: Exception | None = None,
    ):
        self.provider = provider
        self.model = model

        super().__init__(
            message=message,
            query=query,
            stage="llm_generation",
            original=original,
            context={
                "provider": provider,
                "model": model,
            },
        )


class ValidationError(ArxivFetcherError):
    """Raised when validation fails.
    
    Attributes:
        field_name: Name of the field that failed validation
        value: The invalid value
        reason: Why validation failed
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        value: Any | None = None,
        reason: str | None = None,
        context: dict | None = None,
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


class ConfigurationError(ArxivFetcherError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        config_value: Any | None = None,
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

