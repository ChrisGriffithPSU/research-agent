"""HTTP and API-related exceptions."""
from typing import Any, Dict, Optional


class HTTPError(Exception):
    """Base exception for HTTP errors.
    
    Args:
        message: Human-readable error message
        status_code: HTTP status code (4xx or 5xx)
        error_code: Machine-readable error code
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self._default_error_code()
        self.details = details or {}
        super().__init__(message)
    
    def _default_error_code(self) -> str:
        """Generate default error code from class name."""
        return f"{self.__class__.__name__.upper()}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "code": self.error_code,
            "message": self.message,
            **self.details,
        }


class ValidationError(HTTPError):
    """400 Bad Request - Invalid request data."""
    
    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class AuthenticationError(HTTPError):
    """401 Unauthorized - Authentication failed."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, details=details)


class PermissionDeniedError(HTTPError):
    """403 Forbidden - Insufficient permissions."""
    
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, details=details)


class NotFoundError(HTTPError):
    """404 Not Found - Resource not found."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, details=details)


class ConflictError(HTTPError):
    """409 Conflict - Resource conflict."""
    
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=409, details=details)


class RateLimitError(HTTPError):
    """429 Too Many Requests - Rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        full_details = details or {}
        if retry_after is not None:
            full_details["retry_after"] = retry_after
        super().__init__(message, status_code=429, details=full_details)


class InternalServerError(HTTPError):
    """500 Internal Server Error - Unexpected server error."""
    
    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class ServiceUnavailableError(HTTPError):
    """503 Service Unavailable - Service temporarily unavailable."""
    
    def __init__(self, message: str = "Service unavailable", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=503, details=details)

