"""Unit tests for circuit breaker - tests actual async behavior."""
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


async def test_circuit_breaker_opens_after_threshold():
    """Should open circuit after N consecutive failures."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # First two failures - circuit stays closed
    async def failing_func_1():
        raise RuntimeError("failure 1")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_1)

    assert breaker.state == "closed"
    assert breaker.failures == 1

    async def failing_func_2():
        raise RuntimeError("failure 2")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_2)

    assert breaker.state == "closed"
    assert breaker.failures == 2

    # Third failure - circuit opens
    async def failing_func_3():
        raise RuntimeError("failure 3")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_3)

    assert breaker.state == "open"
    assert breaker.failures == 3
    assert breaker.is_open
    assert not breaker.is_closed


async def test_circuit_breaker_rejects_when_open():
    """Should raise CircuitBreakerOpenError when circuit is open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=10.0)

    # Simulate 3 failures to open circuit
    for i in range(3):
        async def fail():
            raise RuntimeError(f"failure {i}")
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.is_open

    # Should raise CircuitBreakerOpenError on next call
    async def fail_func():
        raise RuntimeError("test")

    with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker is open"):
        await breaker.call(fail_func)


async def test_circuit_breaker_calls_function_when_closed():
    """Should execute function when circuit is closed."""
    breaker = CircuitBreaker(failure_threshold=3)

    async def succeed_func():
        return "success"

    result = await breaker.call(succeed_func)

    assert result == "success"
    assert breaker.state == "closed"
    assert breaker.failures == 0


async def test_circuit_breaker_resets_on_success():
    """Should reset failure count on success."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # Add failures
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.failures == 2

    # Success should reset
    async def succeed_func():
        return "success"

    result = await breaker.call(succeed_func)

    assert result == "success"
    assert breaker.failures == 0
    assert breaker.state == "closed"


async def test_circuit_breaker_recovers_after_timeout():
    """Should move to half-open after timeout, then succeed to close."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.2)  # 200ms

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.state == "open"

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)  # Wait 300ms (timeout + buffer)

    # After timeout, circuit will transition to half-open on next call
    # If that call succeeds, it should close
    async def success_func():
        return "success"

    result = await breaker.call(success_func)

    assert result == "success"
    assert breaker.state == "closed"  # Should be closed after successful half-open test
    assert breaker.failures == 0


async def test_circuit_breaker_closes_after_half_open_success():
    """Should close circuit after successful call in half-open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.2)

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)

    # Success in half-open should close circuit
    async def succeed_func():
        return "success"

    result = await breaker.call(succeed_func)

    assert result == "success"
    assert breaker.state == "closed"
    assert breaker.failures == 0


async def test_circuit_breaker_opens_again_after_half_open_failure():
    """Should open circuit again after failure in half-open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.2)

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.state == "open"

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)

    # State is still "open" until we make a call - the transition to half-open
    # happens inside call() when timeout has expired

    # First call will transition to half-open, then fail and re-open
    with pytest.raises(RuntimeError):
        await breaker.call(fail_func)

    assert breaker.state == "open"


def test_circuit_breaker_manually_reset():
    """Should reset circuit breaker manually."""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # Manually set state to simulate opened circuit
    breaker.state = "open"
    breaker.failures = 3
    breaker.last_failure_time = time.time()

    assert breaker.state == "open"

    # Manual reset
    breaker.reset()

    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.is_closed
    assert not breaker.is_open


async def test_circuit_breaker_decorator():
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
    result = await protected_func()
    assert result == "result"


async def test_circuit_breaker_decorator_opens():
    """Decorator should open circuit after failures."""
    @circuit_breaker(failure_threshold=3, timeout=60.0)
    async def failing_func():
        raise RuntimeError("failure")

    wrapper = failing_func
    breaker = wrapper._circuit_breaker

    # Trigger failures to open circuit
    with pytest.raises(RuntimeError):
        await failing_func()

    with pytest.raises(RuntimeError):
        await failing_func()

    with pytest.raises(RuntimeError):
        await failing_func()

    # Circuit should be open
    assert breaker.is_open

    # Next call should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await failing_func()


def test_circuit_breaker_string_repr():
    """Should have informative string representation."""
    breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)

    # Manually set some failures for testing
    breaker.failures = 2

    repr_str = repr(breaker)

    assert "CircuitBreaker" in repr_str
    assert "state=closed" in repr_str
    assert "failures=2" in repr_str
    assert "threshold=5" in repr_str
