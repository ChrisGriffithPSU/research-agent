"""Unit tests for circuit breaker - tests actual async behavior."""
import pytest
import asyncio
import time

from src.shared.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker,
)
from src.shared.exceptions import CircuitOpenError


def test_circuit_breaker_initial_state():
    """Should start in closed state with no failures."""
    breaker = CircuitBreaker()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_circuit_breaker_opens_after_threshold():
    """Should open circuit after N consecutive failures."""
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=60)

    # First two failures - circuit stays closed
    async def failing_func_1():
        raise RuntimeError("failure 1")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_1)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    async def failing_func_2():
        raise RuntimeError("failure 2")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_2)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 2

    # Third failure - circuit opens
    async def failing_func_3():
        raise RuntimeError("failure 3")

    with pytest.raises(RuntimeError):
        await breaker.call(failing_func_3)

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 3


async def test_circuit_breaker_rejects_when_open():
    """Should raise CircuitOpenError when circuit is open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=10)

    # Simulate 3 failures to open circuit
    for i in range(3):
        async def fail():
            raise RuntimeError(f"failure {i}")
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.state == CircuitState.OPEN

    # Should raise CircuitOpenError on next call
    async def fail_func():
        raise RuntimeError("test")

    with pytest.raises(CircuitOpenError):
        await breaker.call(fail_func)


async def test_circuit_breaker_calls_function_when_closed():
    """Should execute function when circuit is closed."""
    breaker = CircuitBreaker(failure_threshold=3)

    async def succeed_func():
        return "success"

    result = await breaker.call(succeed_func)

    assert result == "success"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_circuit_breaker_resets_on_success():
    """Should reset failure count on success."""
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=60)

    # Add failures
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.failure_count == 2

    # Success should reset
    async def succeed_func():
        return "success"

    result = await breaker.call(succeed_func)

    assert result == "success"
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED


async def test_circuit_breaker_recovers_after_timeout():
    """Should move to half-open after timeout, then succeed to close."""
    # Use success_threshold=1 so one success closes the circuit
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=0.2, success_threshold=1)

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.state == CircuitState.OPEN

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)  # Wait 300ms (timeout + buffer)

    # After timeout, circuit will transition to half-open on next call
    # If that call succeeds, it should close (with success_threshold=1)
    async def success_func():
        return "success"

    result = await breaker.call(success_func)

    assert result == "success"
    assert breaker.state == CircuitState.CLOSED  # Should be closed after successful half-open test
    assert breaker.failure_count == 0


async def test_circuit_breaker_closes_after_half_open_success():
    """Should close circuit after successful calls in half-open."""
    # Default success_threshold is 2, so we need 2 successes
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=0.2, success_threshold=2)

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)

    # First success in half-open
    async def succeed_func():
        return "success"

    result1 = await breaker.call(succeed_func)
    assert result1 == "success"
    assert breaker.state == CircuitState.HALF_OPEN  # Still half-open after 1 success

    # Second success should close circuit
    result2 = await breaker.call(succeed_func)
    assert result2 == "success"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_circuit_breaker_opens_again_after_half_open_failure():
    """Should open circuit again after failure in half-open."""
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=0.2)

    # Open circuit
    async def fail_func():
        raise RuntimeError("failure")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail_func)

    assert breaker.state == CircuitState.OPEN

    # Wait for timeout - use asyncio.sleep for async tests
    await asyncio.sleep(0.3)

    # State is still "open" until we make a call - the transition to half-open
    # happens inside call() when timeout has expired

    # First call will transition to half-open, then fail and re-open
    with pytest.raises(RuntimeError):
        await breaker.call(fail_func)

    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_manually_reset():
    """Should reset circuit breaker manually."""
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=60)

    # Manually set state to simulate opened circuit
    breaker.state = CircuitState.OPEN
    breaker.failure_count = 3
    breaker.opened_at = time.time()

    assert breaker.state == CircuitState.OPEN

    # Manual reset
    breaker.reset()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_circuit_breaker_decorator():
    """Decorator should protect functions."""
    @circuit_breaker(failure_threshold=3, timeout_seconds=60)
    async def protected_func():
        return "result"

    # Get circuit breaker from wrapper
    wrapper = protected_func
    breaker = wrapper._circuit_breaker

    # Should be in closed state
    assert breaker.state == CircuitState.CLOSED

    # Execute protected function
    result = await protected_func()
    assert result == "result"


async def test_circuit_breaker_decorator_opens():
    """Decorator should open circuit after failures."""
    @circuit_breaker(failure_threshold=3, timeout_seconds=60)
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
    assert breaker.state == CircuitState.OPEN

    # Next call should raise CircuitOpenError
    with pytest.raises(CircuitOpenError):
        await failing_func()


def test_circuit_breaker_string_repr():
    """Should have informative string representation."""
    breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=120, circuit_name="test")

    # Check basic representation exists
    repr_str = repr(breaker)

    # The repr should at least contain the class name
    assert "CircuitBreaker" in repr_str or "circuit" in repr_str.lower()
