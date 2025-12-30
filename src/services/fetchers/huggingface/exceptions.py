"""Custom exceptions for HuggingFace fetcher.

Design Principles (from code-quality.mdc):
- Fail Fast: Clear, actionable error messages
- Error Hierarchy: Domain-specific exception types
- Context Preservation: Original exception preserved for debugging
"""
from typing import Optional
from src.shared.exceptions.base import BaseError, ErrorCode


class HuggingFaceErrorCode(ErrorCode):
    """Error codes for HuggingFace fetcher."""
    
    API_ERROR = ("hf_api_error", "HuggingFace API error")
    RATE_LIMIT = ("hf_rate_limit", "HuggingFace rate limit exceeded")
    MODEL_NOT_FOUND = ("hf_model_not_found", "Model not found on HuggingFace")
    MODEL_CARD_PARSE_ERROR = ("hf_card_parse_error", "Failed to parse model card")
    CACHE_ERROR = ("hf_cache_error", "Cache operation failed")
    PUBLISH_ERROR = ("hf_publish_error", "Message publishing failed")
    HEALTH_CHECK_FAILED = ("hf_health_check_failed", "Health check failed")


class HuggingFaceError(BaseError):
    """Base exception for HuggingFace fetcher errors.
    
    Attributes:
        message: Human-readable error message
        code: Error code enum value
        model_id: Optional model ID related to the error
        query: Optional query that caused the error
        original: Original exception if any
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[HuggingFaceErrorCode] = None,
        model_id: Optional[str] = None,
        query: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.model_id = model_id
        self.query = query
        self.original = original
        
        error_code = code or HuggingFaceErrorCode.API_ERROR
        super().__init__(
            message=message,
            code=error_code[0],
            details=error_code[1],
            original=original,
        )


class APIError(HuggingFaceError):
    """Exception raised when HuggingFace API returns an error."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        query: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.status_code = status_code
        details = f"API error (status={status_code})" if status_code else "API error"
        super().__init__(
            message=message,
            code=HuggingFaceErrorCode.API_ERROR,
            query=query,
            original=original,
        )
        self.details = details


class RateLimitError(HuggingFaceError):
    """Exception raised when HuggingFace rate limit is exceeded."""
    
    def __init__(
        self,
        message: str = "HuggingFace rate limit exceeded",
        retry_after: Optional[int] = None,
        original: Optional[Exception] = None,
    ):
        self.retry_after = retry_after
        super().__init__(
            message=message,
            code=HuggingFaceErrorCode.RATE_LIMIT,
            original=original,
        )


class ModelNotFoundError(HuggingFaceError):
    """Exception raised when a model is not found on HuggingFace."""
    
    def __init__(
        self,
        model_id: str,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=f"Model not found: {model_id}",
            code=HuggingFaceErrorCode.MODEL_NOT_FOUND,
            model_id=model_id,
            original=original,
        )


class ModelCardParseError(HuggingFaceError):
    """Exception raised when model card parsing fails."""
    
    def __init__(
        self,
        model_id: str,
        message: str = "Failed to parse model card",
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=f"Failed to parse model card for {model_id}: {message}",
            code=HuggingFaceErrorCode.MODEL_CARD_PARSE_ERROR,
            model_id=model_id,
            original=original,
        )


class CacheError(HuggingFaceError):
    """Exception raised when cache operations fail."""
    
    def __init__(
        self,
        message: str,
        operation: str = "cache",
        original: Optional[Exception] = None,
    ):
        self.operation = operation
        super().__init__(
            message=message,
            code=HuggingFaceErrorCode.CACHE_ERROR,
            original=original,
        )


class PublishError(HuggingFaceError):
    """Exception raised when message publishing fails."""
    
    def __init__(
        self,
        message: str,
        queue_name: Optional[str] = None,
        message_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.queue_name = queue_name
        self.message_type = message_type
        self.correlation_id = correlation_id
        super().__init__(
            message=message,
            code=HuggingFaceErrorCode.PUBLISH_ERROR,
            original=original,
        )


class HealthCheckError(HuggingFaceError):
    """Exception raised when health check fails."""
    
    def __init__(
        self,
        component: str,
        message: str,
        original: Optional[Exception] = None,
    ):
        self.component = component
        super().__init__(
            message=f"Health check failed for {component}: {message}",
            code=HuggingFaceErrorCode.HEALTH_CHECK_FAILED,
            original=original,
        )

