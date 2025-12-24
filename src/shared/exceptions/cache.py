"""Cache-related exceptions."""
from typing import Optional


class CacheError(Exception):
    """Base exception for cache errors.
    
    Args:
        message: Human-readable error message
        cache_key: Cache key involved
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        cache_key: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.cache_key = cache_key
        self.details = details or {}
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.cache_key:
            parts.append(f"Key: {self.cache_key}")
        return " | ".join(parts)


class CacheConnectionError(CacheError):
    """Failed to connect to cache (Redis)."""
    
    def __init__(
        self,
        message: str = "Cache connection failed",
        cache_url: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if cache_url is not None:
            details["cache_url"] = cache_url
        super().__init__(message, None, details)
        self.original_error = original_error


class CacheTimeoutError(CacheError):
    """Cache operation timed out."""
    
    def __init__(
        self,
        message: str = "Cache operation timed out",
        cache_key: Optional[str] = None,
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        details = {}
        if operation is not None:
            details["operation"] = operation
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, cache_key, details)


class CacheSerializationError(CacheError):
    """Failed to serialize/deserialize cache value."""
    
    def __init__(
        self,
        message: str = "Cache serialization failed",
        cache_key: Optional[str] = None,
        value_type: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if value_type is not None:
            details["value_type"] = value_type
        super().__init__(message, cache_key, details)
        self.original_error = original_error


class CacheKeyError(CacheError):
    """Invalid cache key."""
    
    def __init__(
        self,
        message: str = "Invalid cache key",
        cache_key: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        details = {}
        if cache_key is not None:
            details["cache_key"] = cache_key
        if reason is not None:
            details["reason"] = reason
        super().__init__(message, cache_key, details)


class CacheCapacityError(CacheError):
    """Cache at capacity (memory full)."""
    
    def __init__(
        self,
        message: str = "Cache at capacity",
        cache_key: Optional[str] = None,
        value_size: Optional[int] = None,
    ):
        details = {}
        if value_size is not None:
            details["value_size_bytes"] = value_size
        super().__init__(message, cache_key, details)


class CacheQuotaExceededError(CacheError):
    """Cache operation exceeded quota (e.g., max key length)."""
    
    def __init__(
        self,
        message: str = "Cache quota exceeded",
        cache_key: Optional[str] = None,
        limit: Optional[str] = None,
        actual: Optional[int] = None,
    ):
        details = {}
        if limit is not None:
            details["limit"] = limit
        if actual is not None:
            details["actual"] = actual
        super().__init__(message, cache_key, details)

