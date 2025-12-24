"""Circuit breaker implementation for resilient external calls."""
import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Callable, Optional

from src.shared.exceptions import CircuitOpenError


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Allow requests
    OPEN = "open"          # Block requests
    HALF_OPEN = "half_open"  # Allow limited requests (test if system recovered)


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.
    
    Tracks consecutive failures and transitions to OPEN state after threshold.
    After timeout, transitions to HALF_OPEN to test if system recovered.
    Requires multiple successes in HALF_OPEN to transition back to CLOSED.
    
    Args:
        failure_threshold: Number of consecutive failures before opening
        timeout_seconds: How long to stay in OPEN before testing
        success_threshold: Number of successes in HALF_OPEN to close circuit
        circuit_name: Name for logging/metrics
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: int = 60,
        success_threshold: int = 2,
        circuit_name: str = "default",
    ):
        self.circuit_name = circuit_name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0  # Only used in HALF_OPEN
        self.opened_at: Optional[float] = None
        
        logger.debug(
            f"Circuit breaker '{circuit_name}' initialized",
            extra={
                "circuit_name": circuit_name,
                "failure_threshold": failure_threshold,
                "timeout_seconds": timeout_seconds,
                "success_threshold": success_threshold,
            },
        )
    
    def _check_timeout(self) -> bool:
        """Check if circuit should transition from OPEN to HALF_OPEN."""
        if self.state == CircuitState.OPEN and self.opened_at:
            elapsed = time.time() - self.opened_at
            if elapsed >= self.timeout_seconds:
                logger.info(
                    f"Circuit '{self.circuit_name}' timeout elapsed, transitioning to HALF_OPEN",
                    extra={
                        "circuit_name": self.circuit_name,
                        "state_from": self.state.value,
                        "state_to": CircuitState.HALF_OPEN.value,
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )
                self.state = CircuitState.HALF_OPEN
                self.failure_count = 0
                self.success_count = 0
                self.opened_at = None
                return True
        
        return False
    
    def _record_failure(self):
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            # Failure in HALF_OPEN: go back to OPEN
            logger.warning(
                f"Circuit '{self.circuit_name}' failed in HALF_OPEN, transitioning to OPEN",
                extra={
                    "circuit_name": self.circuit_name,
                    "state_from": self.state.value,
                    "state_to": CircuitState.OPEN.value,
                    "failure_count": self.failure_count,
                },
            )
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            self.success_count = 0
        elif self.failure_count >= self.failure_threshold:
            # Threshold exceeded: open circuit
            if self.state != CircuitState.OPEN:
                logger.warning(
                    f"Circuit '{self.circuit_name}' failure threshold ({self.failure_threshold}) reached, opening circuit",
                    extra={
                        "circuit_name": self.circuit_name,
                        "state_from": self.state.value,
                        "state_to": CircuitState.OPEN.value,
                        "failure_count": self.failure_count,
                    },
                )
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
        else:
            logger.debug(
                f"Circuit '{self.circuit_name}' failure recorded (count: {self.failure_count})",
                extra={
                    "circuit_name": self.circuit_name,
                    "failure_count": self.failure_count,
                    "state": self.state.value,
                },
            )
    
    def _record_success(self):
        """Record a success and potentially close circuit."""
        if self.state == CircuitState.CLOSED:
            # Success in CLOSED: reset failure count
            self.failure_count = 0
            logger.debug(
                f"Circuit '{self.circuit_name}' success in CLOSED, failure count reset",
                extra={
                    "circuit_name": self.circuit_name,
                    "state": self.state.value,
                },
            )
        elif self.state == CircuitState.HALF_OPEN:
            # Success in HALF_OPEN: increment and check threshold
            self.success_count += 1
            logger.debug(
                f"Circuit '{self.circuit_name}' success in HALF_OPEN (count: {self.success_count}/{self.success_threshold})",
                extra={
                    "circuit_name": self.circuit_name,
                    "success_count": self.success_count,
                    "success_threshold": self.success_threshold,
                },
            )
            
            if self.success_count >= self.success_threshold:
                # Success threshold reached: close circuit
                logger.info(
                    f"Circuit '{self.circuit_name}' success threshold ({self.success_threshold}) reached, closing circuit",
                    extra={
                        "circuit_name": self.circuit_name,
                        "state_from": self.state.value,
                        "state_to": CircuitState.CLOSED.value,
                        "success_count": self.success_count,
                    },
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
    
    async def call(self, func: Callable):
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
        
        Returns:
            Function result
        
        Raises:
            CircuitOpenError: If circuit is OPEN
            Exception: Propagated from func
        """
        # Check timeout first (OPEN → HALF_OPEN transition)
        self._check_timeout()
        
        # Block if OPEN
        if self.state == CircuitState.OPEN:
            logger.debug(
                f"Circuit '{self.circuit_name}' is OPEN, blocking request",
                extra={
                    "circuit_name": self.circuit_name,
                    "state": self.state.value,
                },
            )
            raise CircuitOpenError(
                circuit_name=self.circuit_name,
                cooldown_until=self.opened_at + self.timeout_seconds if self.opened_at else None,
            )
        
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func()
            else:
                result = func()
            
            # Record success
            self._record_success()
            
            return result
        
        except Exception as e:
            # Record failure
            self._record_failure()
            raise
    
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.state
    
    def reset(self):
        """Reset circuit breaker to CLOSED state."""
        logger.info(
            f"Circuit '{self.circuit_name}' manually reset to CLOSED",
            extra={"circuit_name": self.circuit_name},
        )
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = None


def circuit_breaker(
    failure_threshold: int = 3,
    timeout_seconds: int = 60,
    success_threshold: int = 2,
    circuit_name: str = "default",
):
    """Decorator for circuit breaker pattern.
    
    Args:
        failure_threshold: Consecutive failures before opening
        timeout_seconds: Time to stay in OPEN before testing
        success_threshold: Successes in HALF_OPEN to close circuit
        circuit_name: Circuit identifier for logging
    
    Example:
        @circuit_breaker(failure_threshold=3, circuit_name="anthropic_api")
        async def call_anthropic():
            # Will block after 3 consecutive failures for 60 seconds
            # After timeout, will allow 2 successful calls to close circuit
            return await anthropic_client.complete(...)
    """
    # Create singleton circuit breaker instance per unique circuit_name
    # Store in function's __dict__ to reuse across calls
    def decorator(func: Callable):
        if not hasattr(func, "_circuit_breaker"):
            func._circuit_breaker = CircuitBreaker(
                failure_threshold=failure_threshold,
                timeout_seconds=timeout_seconds,
                success_threshold=success_threshold,
                circuit_name=circuit_name,
            )
        
        breaker = func._circuit_breaker
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call(lambda: func(*args, **kwargs))
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return breaker.call(lambda: func(*args, **kwargs))
        
        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

