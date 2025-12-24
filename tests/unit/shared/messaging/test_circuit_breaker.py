"""Unit tests for circuit breaker."""
import pytest
import asyncio
import time

from src.shared.messaging.circuit_breaker import (
    CircuitBreaker,
    circuit_breaker,
)
from src.shared.messaging.exceptions import CircuitBreakerOpenError


def test_circuit_breaker_initial_state():
    """Should start in closed state with no failures."""
    breaker = CircuitBreaker()

    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.is_closed
    assert not breaker.is_open


def test_circuit_breaker_opens_after_threshold():
    """Should open circuit after N failures."""
    breaker = CircuitBreaker(failure_threshold=3)

    # First two failures - circuit stays closed
    breaker._on_failure()
    assert breaker.state == "closed"
    assert breaker.failures == 1

    breaker._on_failure()
    assert breaker.state == "closed"
    assert breaker.failures == 2

    # Third failure - circuit opens
    breaker._on_failure()
    assert breaker.state == "open"
    assert breaker.failures == 3
    assert breaker.is_open
    assert not breaker.is_closed


def test_circuit_breaker_rejects_when_open():
    """Should raise CircuitBreakerOpenError when circuit is open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # Simulate 3 failures to open circuit
    for _ in range(3):
        breaker._on_failure()

    assert breaker.is_open

    # Should raise error
    with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker is open"):
        asyncio.run(breaker.call(async def: raise RuntimeError("test")))


def test_circuit_breaker_calls_function_when_closed():
    """Should execute function when circuit is closed."""
    breaker = CircuitBreaker(failure_threshold=3)

    async def succeed_func():
        return "success"

    result = asyncio.run(breaker.call(succeed_func))

    assert result == "success"
    assert breaker.state == "closed"
    assert breaker.failures == 0


def test_circuit_breaker_resets_on_success():
    """Should reset failure count on success."""
    breaker = CircuitBreaker(failure_threshold=3)

    # Add failures
    breaker._on_failure()
    breaker._on_failure()
    assert breaker.failures == 2

    # Success should reset
    async def succeed_func():
        return "success"

    asyncio.run(breaker.call(succeed_func))

    assert breaker.failures == 0
    assert breaker.state == "closed"


def test_circuit_breaker_recovers_after_timeout():
    """Should move to half-open after timeout."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.1)  # 100ms

    # Open circuit
    for _ in range(3):
        breaker._on_failure()
    assert breaker.state == "open"

    # Wait for timeout
    time.sleep(0.15)  # Wait 150ms (timeout + buffer)

    # Should be in half-open (allow one attempt)
    assert breaker.state == "half-open"


def test_circuit_breaker_closes_after_half_open_success():
    """Should close circuit after successful call in half-open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.1)

    # Open circuit
    for _ in range(3):
        breaker._on_failure()

    # Wait for timeout
    time.sleep(0.15)

    # Success in half-open should close circuit
    async def succeed_func():
        return "success"

    asyncio.run(breaker.call(succeed_func))

    assert breaker.state == "closed"
    assert breaker.failures == 0


def test_circuit_breaker_manually_reset():
    """Should reset circuit breaker manually."""
    breaker = CircuitBreaker(failure_threshold=3)

    # Add failures to open circuit
    for _ in range(3):
        breaker._on_failure()

    assert breaker.state == "open"

    # Manual reset
    breaker.reset()

    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.is_closed
    assert not breaker.is_open


def test_circuit_breaker_decorator():
    """Decorator should protect functions."""
    @circuit_breaker(failure_threshold=3, timeout=60.0)
    async def protected_func():
        return "result"

    # Get circuit breaker from wrapper
    wrapper = protected_func
    breaker = wrapper._circuit_breaker

    # Should be in closed state
    assert breaker.state == "closed"

    # Execute protected function
    result = asyncio.run(protected_func())
    assert result == "result"


def test_circuit_breaker_decorator_opens():
    """Decorator should open circuit after failures."""
    @circuit_breaker(failure_threshold=3, timeout=60.0)
    async def failing_func():
        raise RuntimeError("failure")

    wrapper = failing_func
    breaker = wrapper._circuit_breaker

    # Trigger failures to open circuit
    with pytest.raises(RuntimeError):
        asyncio.run(failing_func())

    with pytest.raises(RuntimeError):
        asyncio.run(failing_func())

    with pytest.raises(RuntimeError):
        asyncio.run(failing_func())

    # Circuit should be open
    assert breaker.is_open

    # Next call should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        asyncio.run(failing_func())


def test_circuit_breaker_string_repr():
    """Should have informative string representation."""
    breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)

    # Add some failures
    for _ in range(2):
        breaker._on_failure()

    repr_str = repr(breaker)

    assert "CircuitBreaker" in repr_str
    assert "state=closed" in repr_str
    assert "failures=2" in repr_str
    assert "threshold=5" in repr_str

