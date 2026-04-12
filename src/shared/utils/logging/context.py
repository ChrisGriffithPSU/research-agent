"""Log context management using contextvars for async-safe metadata."""

import contextvars
import logging
import uuid
from typing import Any

# Context variables for async-safe context propagation
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_service_name_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "service_name", default=None
)
_operation_name_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "operation_name", default=None
)
_logger = logging.getLogger(__name__)


def get_correlation_id() -> str | None:
    """Get current correlation ID from context."""
    return _correlation_id_var.get(None)


def get_request_id() -> str | None:
    """Get current request ID from context."""
    return _request_id_var.get(None)


def get_service_name() -> str | None:
    """Get current service name from context."""
    return _service_name_var.get(None)


def get_operation_name() -> str | None:
    """Get current operation name from context."""
    return _operation_name_var.get(None)


def get_context() -> dict[str, Any]:
    """Get all context values as a dictionary."""
    return {
        "correlation_id": get_correlation_id(),
        "request_id": get_request_id(),
        "service_name": get_service_name(),
        "operation_name": get_operation_name(),
    }


def _set_context(
    correlation_id: str | None = None,
    request_id: str | None = None,
    service_name: str | None = None,
    operation_name: str | None = None,
) -> None:
    """Set context variables."""
    if correlation_id is not None:
        _correlation_id_var.set(correlation_id)
    if request_id is not None:
        _request_id_var.set(request_id)
    if service_name is not None:
        _service_name_var.set(service_name)
    if operation_name is not None:
        _operation_name_var.set(operation_name)


def _clear_context() -> None:
    """Clear all context variables."""
    _correlation_id_var.set(None)
    _request_id_var.set(None)
    # Note: Don't clear service_name as it's usually set globally


class log_context:
    """Async context manager for adding metadata to logs.

    Example:
        async with log_context(operation="digest_generation", digest_id="123"):
            logger.info("Starting digest generation")
            # All logs in this scope have operation and digest_id in context
    """

    def __init__(
        self,
        correlation_id: str | None = None,
        request_id: str | None = None,
        service_name: str | None = None,
        operation_name: str | None = None,
        **extra_context: Any,
    ):
        """Initialize log context.

        Args:
            correlation_id: Request correlation ID
            request_id: Request ID (if different from correlation)
            service_name: Service name
            operation_name: Operation name (e.g., "digest_generation")
            **extra_context: Additional context key-value pairs
        """
        self.correlation_id = correlation_id
        self.request_id = request_id
        self.service_name = service_name
        self.operation_name = operation_name
        self.extra_context = extra_context
        self._old_context: dict[str, Any] = {}

    async def __aenter__(self) -> "log_context":
        """Enter context and set variables."""
        # Save old context to restore on exit
        self._old_context = get_context()

        # Set new context
        _set_context(
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            service_name=self.service_name,
            operation_name=self.operation_name,
        )

        _logger.debug(
            "Context entered",
            extra={
                "correlation_id": self.correlation_id,
                "request_id": self.request_id,
                "service_name": self.service_name,
                "operation_name": self.operation_name,
                "extra_keys": list(self.extra_context.keys()) if self.extra_context else [],
            },
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and restore previous context."""
        # Restore old context directly (including None values)
        _correlation_id_var.set(self._old_context.get("correlation_id"))
        _request_id_var.set(self._old_context.get("request_id"))
        _service_name_var.set(self._old_context.get("service_name"))
        _operation_name_var.set(self._old_context.get("operation_name"))

        _logger.debug(
            "Context exited",
            extra={
                "correlation_id": self.correlation_id,
                "operation_name": self.operation_name,
                "exc_type": str(exc_type) if exc_type else None,
            },
        )


def correlation_id_generator(func):
    """Decorator to auto-generate correlation ID for function.

    Example:
        @correlation_id_generator
        async def my_function():
            # correlation_id will be auto-generated and available in logs
            pass
    """

    def wrapper(*args, **kwargs):
        # Generate new correlation ID
        new_id = str(uuid.uuid4())

        # Call function with context
        with log_context(correlation_id=new_id):
            return func(*args, **kwargs)

    return wrapper


async def async_correlation_id_generator(func):
    """Async decorator to auto-generate correlation ID."""

    async def wrapper(*args, **kwargs):
        # Generate new correlation ID
        new_id = str(uuid.uuid4())

        # Call function with context
        async with log_context(correlation_id=new_id):
            return await func(*args, **kwargs)

    return wrapper
