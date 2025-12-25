"""Circuit breaker pattern to prevent cascading failures."""
import logging
import time
import asyncio
from typing import Callable, Any, Optional
from functools import wraps

from src.shared.messaging.exceptions import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker to stop calling failing operations.

    After N consecutive failures, circuit opens and rejects
    all calls for timeout period. Then moves to half-open
    to test if service recovered.

    Prevents cascading failures when RabbitMQ is down.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before moving to half-open
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state: str = "closed"  # closed, open, half-open

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Re-raises any exception from func
        """
        # If circuit is open, check if timeout expired
        if self.state == "open":
            if self.last_failure_time and (time.time() - self.last_failure_time) < self.timeout:
                logger.warning(
                    f"Circuit breaker is open (failures={self.failures}, "
                    f"remaining_timeout={self.timeout - (time.time() - self.last_failure_time):.1f}s)"
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is open (timeout not expired)"
                )
            else:
                # Timeout expired, move to half-open
                self.state = "half-open"
                logger.info("Circuit breaker moved to half-open state")

        # Execute function
        try:
            result = await func(*args, **kwargs)
            # Success: reset failures
            self._on_success()
            return result

        except Exception as e:
            # Failure: increment counter
            self._on_failure(str(e))
            raise

    def _on_success(self) -> None:
        """Handle successful function call."""
        if self.failures > 0:
            # Had failures, now recovered
            logger.info(
                f"Circuit breaker success (reset failures from {self.failures} to 0)"
            )

        self.failures = 0
        self.last_failure_time = None

        if self.state == "half-open":
            # Success in half-open, close circuit
            self.state = "closed"
            logger.info("Circuit breaker closed (half-open test succeeded)")

    def _on_failure(self, error: str) -> None:
        """Handle failed function call."""
        self.failures += 1
        self.last_failure_time = time.time()

        logger.warning(
            f"Circuit breaker failure #{self.failures}/{self.failure_threshold}: {error}"
        )

        # In half-open state, any failure immediately opens the circuit
        if self.state == "half-open":
            self.state = "open"
            logger.warning("Circuit breaker OPEN (half-open test failed)")
        # In closed state, check if threshold reached
        elif self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker OPEN (threshold {self.failure_threshold} reached)"
            )

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state.

        Use this to force-close circuit (e.g., after maintenance).
        """
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"
        logger.info("Circuit breaker manually reset to closed state")

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        return self.state == "open"

    @property
    def is_closed(self) -> bool:
        """Check if circuit breaker is currently closed."""
        return self.state == "closed"

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CircuitBreaker(state={self.state}, failures={self.failures}, "
            f"threshold={self.failure_threshold})"
        )


def circuit_breaker(
    failure_threshold: int = 3,
    timeout: float = 60.0,
):
    """Decorator to apply circuit breaker to async functions.

    Args:
        failure_threshold: Number of failures before opening circuit
        timeout: Seconds to wait before half-open

    Usage:
        @circuit_breaker(failure_threshold=3, timeout=60)
        async def publish_message():
            # This function will be protected by circuit breaker
            pass
    """

    def decorator(func):
        breaker = CircuitBreaker(failure_threshold=failure_threshold, timeout=timeout)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        # Attach circuit breaker to wrapper for manual control
        wrapper._circuit_breaker = breaker

        return wrapper

    return decorator

