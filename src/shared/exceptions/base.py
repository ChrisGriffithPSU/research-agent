"""Base exception classes for the application."""
from typing import Optional, Dict, Any


class ResearchAgentError(Exception):
    """Base exception for all research agent errors.

    All custom exceptions in the application should inherit from this.
    Provides structured error information with error codes and details.

    Args:
        message: Human-readable error message
        error_code: Machine-readable error code (e.g., "DB_CONNECTION_FAILED")
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original: Optional[Exception] = None,
    ):
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.original = original

        # Build full error message
        full_message = f"[{self.error_code}] {message}"
        if original:
            full_message += f" (caused by: {type(original).__name__}: {original})"

        super().__init__(full_message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses.

        Returns:
            Dict with error details
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "exception_type": self.__class__.__name__,
        }


class CircuitOpenError(ResearchAgentError):
    """Circuit breaker is open, blocking requests.

    Raised when a circuit breaker has opened due to repeated failures
    and is blocking further requests until timeout expires.

    Args:
        circuit_name: Name of the circuit breaker
        cooldown_until: Timestamp when circuit will move to half-open (optional)
    """

    def __init__(
        self,
        circuit_name: str,
        cooldown_until: Optional[float] = None,
    ):
        import time

        message = f"Circuit '{circuit_name}' is open"
        details = {"circuit_name": circuit_name}

        if cooldown_until:
            cooldown_iso = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(cooldown_until)
            )
            message += f" until {cooldown_iso}"
            details["cooldown_until"] = cooldown_until

        super().__init__(
            message=message,
            error_code="CIRCUIT_OPEN",
            details=details,
        )

        self.circuit_name = circuit_name
        self.cooldown_until = cooldown_until
