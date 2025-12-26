"""Error response builder for FastAPI exceptions."""
import logging
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.shared.exceptions.http import HTTPError
from src.shared.exceptions.llm import LLMError
from src.shared.exceptions.external_api import ExternalAPIError
from src.shared.exceptions.config import ConfigError
from src.shared.exceptions.cache import CacheError
from src.shared.exceptions.database import DatabaseError


logger = logging.getLogger(__name__)


def error_response(
    exception: Exception,
    request: Optional[Request] = None,
    status_code: Optional[int] = None,
) -> JSONResponse:
    """Convert exception to JSONResponse.
    
    Args:
        exception: Exception instance
        request: Current FastAPI request (for correlation_id)
        status_code: Override HTTP status code
    
    Returns:
        FastAPI JSONResponse with error details
    
    Response format:
        {
            "error": {
                "code": "ERROR_CODE",
                "message": "Error message",
                ...other details
            },
            "correlation_id": "xxx-xxx" (if available from context)
        }
    """
    # Extract correlation ID from request or context
    correlation_id = _get_correlation_id(request)
    
    # Build error details based on exception type
    if isinstance(exception, HTTPError):
        # Use HTTPError's to_dict() method
        error_dict = exception.to_dict()
        if status_code is None:
            status_code = exception.status_code
    elif isinstance(exception, LLMError):
        # Convert LLMError to HTTP error format
        error_dict = {
            "code": exception.__class__.__name__.upper(),
            "message": exception.message,
        }
        if exception.provider:
            error_dict["provider"] = exception.provider
        if exception.model:
            error_dict["model"] = exception.model
        if exception.details:
            error_dict.update(exception.details)
        status_code = status_code or 500
    elif isinstance(exception, ExternalAPIError):
        # Convert ExternalAPIError to HTTP error format
        error_dict = {
            "code": exception.__class__.__name__.upper(),
            "message": exception.message,
        }
        if exception.provider:
            error_dict["provider"] = exception.provider
        if exception.status_code:
            error_dict["api_status_code"] = exception.status_code
        if exception.details:
            error_dict.update(exception.details)
        status_code = status_code or 500
    elif isinstance(exception, ConfigError):
        # Convert ConfigError to HTTP error format
        error_dict = {
            "code": exception.__class__.__name__.upper(),
            "message": exception.message,
        }
        if exception.config_file:
            error_dict["config_file"] = exception.config_file
        if exception.details:
            error_dict.update(exception.details)
        status_code = status_code or 500
    elif isinstance(exception, CacheError):
        # Convert CacheError to HTTP error format
        error_dict = {
            "code": exception.__class__.__name__.upper(),
            "message": exception.message,
        }
        if exception.cache_key:
            error_dict["cache_key"] = exception.cache_key
        if exception.details:
            error_dict.update(exception.details)
        status_code = status_code or 500
    elif isinstance(exception, DatabaseError):
        # Convert DatabaseError to HTTP error format
        error_dict = {
            "code": exception.__class__.__name__.upper(),
            "message": exception.message,
        }
        # DatabaseError doesn't have details attribute, but may have original
        if hasattr(exception, 'original') and exception.original:
            error_dict["original_error"] = str(exception.original)
        status_code = status_code or 500
    else:
        # Generic exception
        error_dict = {
            "code": "INTERNAL_SERVER_ERROR",
            "message": str(exception),
        }
        status_code = status_code or 500
    
    # Build final response
    response_body = {
        "error": error_dict,
    }
    
    if correlation_id:
        response_body["correlation_id"] = correlation_id
    
    # Log the error
    logger.error(
        f"Returning error response: {error_dict.get('code')}",
        extra={
            "error_code": error_dict.get("code"),
            "error_message": error_dict.get("message"),
            "correlation_id": correlation_id,
            "exception_type": type(exception).__name__,
            "status_code": status_code,
        },
        exc_info=True if not isinstance(exception, (DatabaseError, ConfigError, CacheError)) else False,
    )
    
    return JSONResponse(
        content=response_body,
        status_code=status_code,
    )


def _get_correlation_id(request: Optional[Request]) -> Optional[str]:
    """Extract correlation ID from request or context."""
    if request:
        # Try to get from request headers
        correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("x-correlation-id")
        if correlation_id:
            return correlation_id
    
    # Try to get from logging context (if implemented)
    # This would need to integrate with logging context manager
    # For now, return None
    return None


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Global exception handler for FastAPI.
    
    Catches all exceptions and converts them to standardized error responses.
    """
    
    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug
    
    async def dispatch(self, request: Request, call_next):
        """Process request and handle any exceptions."""
        try:
            response = await call_next(request)
            return response
        except Exception as exception:
            # Convert exception to JSONResponse
            return error_response(exception, request, debug=self.debug and not isinstance(exception, (DatabaseError, ConfigError, CacheError)))

