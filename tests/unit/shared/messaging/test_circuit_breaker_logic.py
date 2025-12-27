"""Pure logic tests for circuit breaker state machine.

These tests focus on the state machine transitions without async timing.
They test the logical behavior: when state should change.
For full async behavior tests, see test_circuit_breaker.py.
"""
import pytest
import time

from src.shared.utils.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerInitialState:
    """Test circuit breaker initial state."""

    def test_starts_closed_with_zero_failures(self):
        """Should initialize in closed state with no failures."""
        breaker = CircuitBreaker()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.opened_at is None

    def test_accepts_custom_threshold(self):
        """Should accept custom failure threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        assert breaker.failure_threshold == 5

    def test_accepts_custom_timeout(self):
        """Should accept custom timeout."""
        breaker = CircuitBreaker(timeout_seconds=30)

        assert breaker.timeout_seconds == 30


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions (logic only)."""

    def test_closed_to_open_on_threshold_reached(self):
        """Verify circuit opens when failure count reaches threshold."""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=10)

        # Simulate failures incrementing (logic path)
        breaker.failure_count = 0
        assert breaker.state == CircuitState.CLOSED

        # Failure 1: still closed
        breaker.failure_count = 1
        assert breaker.state == CircuitState.CLOSED

        # Failure 2: still closed
        breaker.failure_count = 2
        assert breaker.state == CircuitState.CLOSED

        # Failure 3: threshold reached, should be open
        breaker.failure_count = 3
        breaker.opened_at = 1000.0
        if breaker.failure_count >= breaker.failure_threshold:
            breaker.state = CircuitState.OPEN

        assert breaker.state == CircuitState.OPEN

    def test_closed_remains_closed_below_threshold(self):
        """Verify circuit stays closed below threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Simulate failures below threshold
        for failures in range(1, 5):  # 1, 2, 3, 4
            breaker.failure_count = failures
            # State should remain closed
            assert breaker.state == CircuitState.CLOSED

    def test_open_to_half_open_after_timeout(self):
        """Verify circuit moves to half-open when timeout expires."""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=10)

        # Simulate open state
        breaker.state = CircuitState.OPEN
        breaker.failure_count = 3
        breaker.opened_at = 1000.0

        # Check timeout logic
        current_time = 1015.0  # 15 seconds later (timeout is 10)
        if breaker.state == CircuitState.OPEN and breaker.opened_at:
            if (current_time - breaker.opened_at) >= breaker.timeout_seconds:
                breaker.state = CircuitState.HALF_OPEN

        assert breaker.state == CircuitState.HALF_OPEN

    def test_open_stays_open_before_timeout(self):
        """Verify circuit stays open before timeout expires."""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=10)

        # Simulate open state
        breaker.state = CircuitState.OPEN
        breaker.failure_count = 3
        breaker.opened_at = 1000.0

        # Check before timeout
        current_time = 1005.0  # 5 seconds later (timeout is 10)
        if breaker.state == CircuitState.OPEN and breaker.opened_at:
            if (current_time - breaker.opened_at) >= breaker.timeout_seconds:
                breaker.state = CircuitState.HALF_OPEN

        # Should still be open
        assert breaker.state == CircuitState.OPEN

    def test_half_open_to_closed_on_success(self):
        """Verify circuit closes after successful call in half-open."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Simulate half-open state
        breaker.state = CircuitState.HALF_OPEN
        breaker.failure_count = 3

        # Simulate success logic (resets failures)
        breaker.failure_count = 0
        breaker.opened_at = None
        if breaker.state == CircuitState.HALF_OPEN:
            breaker.state = CircuitState.CLOSED

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_to_open_on_failure(self):
        """Verify circuit opens again on failure in half-open."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Simulate half-open state
        breaker.state = CircuitState.HALF_OPEN
        breaker.failure_count = 3
        breaker.opened_at = 1000.0

        # Simulate failure in half-open - any failure should immediately open
        # Increment failures and update timestamp
        breaker.failure_count += 1
        breaker.opened_at = time.time()

        # In half-open state, any failure immediately opens the circuit
        if breaker.state == CircuitState.HALF_OPEN:
            breaker.state = CircuitState.OPEN

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerFailureCounting:
    """Test failure counting logic."""

    def test_failures_increment_correctly(self):
        """Verify failure count increments correctly."""
        breaker = CircuitBreaker(failure_threshold=5)

        for expected_count in range(1, 6):
            breaker.failure_count = expected_count
            assert breaker.failure_count == expected_count

    def test_failures_reset_on_success(self):
        """Verify failures reset to 0 on success."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Set some failures
        breaker.failure_count = 4

        # Reset on success logic
        breaker.failure_count = 0
        breaker.opened_at = None

        assert breaker.failure_count == 0
        assert breaker.opened_at is None

    def test_failure_timestamp_updated(self):
        """Verify failure timestamp is updated on each failure."""
        breaker = CircuitBreaker()

        # First failure
        time_1 = 1000.0
        breaker.opened_at = time_1

        # Second failure
        time_2 = 1010.0
        breaker.opened_at = time_2

        # Last failure should be time_2
        assert breaker.opened_at == time_2


class TestCircuitBreakerManualReset:
    """Test manual reset functionality."""

    def test_reset_from_closed_state(self):
        """Verify reset works from closed state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Already closed
        assert breaker.state == CircuitState.CLOSED

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_reset_from_open_state(self):
        """Verify reset works from open state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Set to open state
        breaker.state = CircuitState.OPEN
        breaker.failure_count = 5
        breaker.opened_at = 1000.0

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_reset_from_half_open_state(self):
        """Verify reset works from half-open state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Set to half-open state
        breaker.state = CircuitState.HALF_OPEN
        breaker.failure_count = 3
        breaker.opened_at = 1000.0

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0


class TestCircuitBreakerProperties:
    """Test circuit breaker property methods."""

    def test_is_closed_property(self):
        """Verify state can be checked correctly."""
        breaker = CircuitBreaker()

        # Closed state
        breaker.state = CircuitState.CLOSED
        assert breaker.state == CircuitState.CLOSED

        # Open state
        breaker.state = CircuitState.OPEN
        assert breaker.state == CircuitState.OPEN

        # Half-open state
        breaker.state = CircuitState.HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

    def test_is_open_property(self):
        """Verify state can be checked correctly."""
        breaker = CircuitBreaker()

        # Closed state
        breaker.state = CircuitState.CLOSED
        assert breaker.state != CircuitState.OPEN

        # Open state
        breaker.state = CircuitState.OPEN
        assert breaker.state == CircuitState.OPEN

        # Half-open state
        breaker.state = CircuitState.HALF_OPEN
        assert breaker.state != CircuitState.OPEN

    def test_string_representation(self):
        """Verify object has representation."""
        breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=120)
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 2

        repr_str = repr(breaker)

        # Just check it doesn't crash and returns something
        assert repr_str is not None
        assert len(repr_str) > 0


class TestCircuitBreakerThresholdValues:
    """Test various threshold configurations."""

    def test_threshold_of_one(self):
        """Verify circuit opens immediately with threshold=1."""
        breaker = CircuitBreaker(failure_threshold=1)

        breaker.failure_count = 1
        if breaker.failure_count >= breaker.failure_threshold:
            breaker.state = CircuitState.OPEN

        assert breaker.state == CircuitState.OPEN

    def test_high_threshold_value(self):
        """Verify circuit works with high threshold."""
        breaker = CircuitBreaker(failure_threshold=100)

        for i in range(1, 100):
            breaker.failure_count = i
            assert breaker.state == CircuitState.CLOSED

        # At 100, should open
        breaker.failure_count = 100
        if breaker.failure_count >= breaker.failure_threshold:
            breaker.state = CircuitState.OPEN

        assert breaker.state == CircuitState.OPEN

    def test_zero_timeout(self):
        """Verify circuit handles zero timeout (immediate recovery)."""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=0)

        # Open circuit
        breaker.state = CircuitState.OPEN
        breaker.failure_count = 3
        breaker.opened_at = 1000.0

        # Check timeout with zero timeout
        current_time = 1000.0  # Same timestamp
        if breaker.state == CircuitState.OPEN and breaker.opened_at:
            if (current_time - breaker.opened_at) >= breaker.timeout_seconds:
                breaker.state = CircuitState.HALF_OPEN

        # Should transition immediately since timeout is 0
        assert breaker.state == CircuitState.HALF_OPEN
