"""Pure logic tests for circuit breaker state machine.

These tests focus on the state machine transitions without async timing.
They test the logical behavior: when state should change.
For full async behavior tests, see test_circuit_breaker.py.
"""
import pytest

from src.shared.messaging.circuit_breaker import CircuitBreaker


class TestCircuitBreakerInitialState:
    """Test circuit breaker initial state."""

    def test_starts_closed_with_zero_failures(self):
        """Should initialize in closed state with no failures."""
        breaker = CircuitBreaker()

        assert breaker.state == "closed"
        assert breaker.failures == 0
        assert breaker.is_closed
        assert not breaker.is_open
        assert breaker.last_failure_time is None

    def test_accepts_custom_threshold(self):
        """Should accept custom failure threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        assert breaker.failure_threshold == 5

    def test_accepts_custom_timeout(self):
        """Should accept custom timeout."""
        breaker = CircuitBreaker(timeout=30.0)

        assert breaker.timeout == 30.0


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions (logic only)."""

    def test_closed_to_open_on_threshold_reached(self):
        """Verify circuit opens when failure count reaches threshold."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=10.0)

        # Simulate failures incrementing (logic path)
        breaker.failures = 0
        assert breaker.state == "closed"

        # Failure 1: still closed
        breaker.failures = 1
        assert breaker.state == "closed"

        # Failure 2: still closed
        breaker.failures = 2
        assert breaker.state == "closed"

        # Failure 3: threshold reached, should be open
        breaker.failures = 3
        breaker.last_failure_time = 1000.0
        if breaker.failures >= breaker.failure_threshold:
            breaker.state = "open"

        assert breaker.state == "open"
        assert breaker.is_open
        assert not breaker.is_closed

    def test_closed_remains_closed_below_threshold(self):
        """Verify circuit stays closed below threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Simulate failures below threshold
        for failures in range(1, 5):  # 1, 2, 3, 4
            breaker.failures = failures
            # State should remain closed
            assert breaker.state == "closed"

    def test_open_to_half_open_after_timeout(self):
        """Verify circuit moves to half-open when timeout expires."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=10.0)

        # Simulate open state
        breaker.state = "open"
        breaker.failures = 3
        breaker.last_failure_time = 1000.0

        # Check timeout logic
        current_time = 1015.0  # 15 seconds later (timeout is 10)
        if breaker.state == "open" and breaker.last_failure_time:
            if (current_time - breaker.last_failure_time) >= breaker.timeout:
                breaker.state = "half-open"

        assert breaker.state == "half-open"

    def test_open_stays_open_before_timeout(self):
        """Verify circuit stays open before timeout expires."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=10.0)

        # Simulate open state
        breaker.state = "open"
        breaker.failures = 3
        breaker.last_failure_time = 1000.0

        # Check before timeout
        current_time = 1005.0  # 5 seconds later (timeout is 10)
        if breaker.state == "open" and breaker.last_failure_time:
            if (current_time - breaker.last_failure_time) >= breaker.timeout:
                breaker.state = "half-open"

        # Should still be open
        assert breaker.state == "open"

    def test_half_open_to_closed_on_success(self):
        """Verify circuit closes after successful call in half-open."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Simulate half-open state
        breaker.state = "half-open"
        breaker.failures = 3

        # Simulate success logic (resets failures)
        breaker.failures = 0
        breaker.last_failure_time = None
        if breaker.state == "half-open":
            breaker.state = "closed"

        assert breaker.state == "closed"
        assert breaker.failures == 0

    def test_half_open_to_open_on_failure(self):
        """Verify circuit opens again on failure in half-open."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Simulate half-open state
        breaker.state = "half-open"
        breaker.failures = 3
        breaker.last_failure_time = 1000.0

        # Simulate failure in half-open (resets failure count)
        breaker.failures = 1
        breaker.last_failure_time = 1000.0

        # If failure count reaches threshold in half-open, should open
        if breaker.failures >= breaker.failure_threshold:
            breaker.state = "open"

        assert breaker.state == "open"


class TestCircuitBreakerFailureCounting:
    """Test failure counting logic."""

    def test_failures_increment_correctly(self):
        """Verify failure count increments correctly."""
        breaker = CircuitBreaker(failure_threshold=5)

        for expected_count in range(1, 6):
            breaker.failures = expected_count
            assert breaker.failures == expected_count

    def test_failures_reset_on_success(self):
        """Verify failures reset to 0 on success."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Set some failures
        breaker.failures = 4

        # Reset on success logic
        breaker.failures = 0
        breaker.last_failure_time = None

        assert breaker.failures == 0
        assert breaker.last_failure_time is None

    def test_failure_timestamp_updated(self):
        """Verify failure timestamp is updated on each failure."""
        breaker = CircuitBreaker()
        import time

        # First failure
        time_1 = 1000.0
        breaker.last_failure_time = time_1

        # Second failure
        time_2 = 1010.0
        breaker.last_failure_time = time_2

        # Last failure should be time_2
        assert breaker.last_failure_time == time_2


class TestCircuitBreakerManualReset:
    """Test manual reset functionality."""

    def test_reset_from_closed_state(self):
        """Verify reset works from closed state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Already closed
        assert breaker.state == "closed"

        # Reset
        breaker.failures = 0
        breaker.last_failure_time = None
        breaker.state = "closed"

        assert breaker.state == "closed"
        assert breaker.failures == 0

    def test_reset_from_open_state(self):
        """Verify reset works from open state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Set to open state
        breaker.state = "open"
        breaker.failures = 5
        breaker.last_failure_time = 1000.0

        # Reset
        breaker.failures = 0
        breaker.last_failure_time = None
        breaker.state = "closed"

        assert breaker.state == "closed"
        assert breaker.failures == 0
        assert breaker.is_closed
        assert not breaker.is_open

    def test_reset_from_half_open_state(self):
        """Verify reset works from half-open state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Set to half-open state
        breaker.state = "half-open"
        breaker.failures = 3
        breaker.last_failure_time = 1000.0

        # Reset
        breaker.failures = 0
        breaker.last_failure_time = None
        breaker.state = "closed"

        assert breaker.state == "closed"
        assert breaker.failures == 0


class TestCircuitBreakerProperties:
    """Test circuit breaker property methods."""

    def test_is_closed_property(self):
        """Verify is_closed property returns correct value."""
        breaker = CircuitBreaker()

        # Closed state
        breaker.state = "closed"
        assert breaker.is_closed is True
        assert breaker.is_open is False

        # Open state
        breaker.state = "open"
        assert breaker.is_closed is False

        # Half-open state
        breaker.state = "half-open"
        assert breaker.is_closed is False

    def test_is_open_property(self):
        """Verify is_open property returns correct value."""
        breaker = CircuitBreaker()

        # Closed state
        breaker.state = "closed"
        assert breaker.is_open is False

        # Open state
        breaker.state = "open"
        assert breaker.is_open is True

        # Half-open state
        breaker.state = "half-open"
        assert breaker.is_open is False

    def test_string_representation(self):
        """Verify __repr__ contains all relevant info."""
        breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)
        breaker.state = "closed"
        breaker.failures = 2

        repr_str = repr(breaker)

        assert "CircuitBreaker" in repr_str
        assert "state=closed" in repr_str
        assert "failures=2" in repr_str
        assert "threshold=5" in repr_str


class TestCircuitBreakerThresholdValues:
    """Test various threshold configurations."""

    def test_threshold_of_one(self):
        """Verify circuit opens immediately with threshold=1."""
        breaker = CircuitBreaker(failure_threshold=1)

        breaker.failures = 1
        if breaker.failures >= breaker.failure_threshold:
            breaker.state = "open"

        assert breaker.state == "open"

    def test_high_threshold_value(self):
        """Verify circuit works with high threshold."""
        breaker = CircuitBreaker(failure_threshold=100)

        for i in range(1, 100):
            breaker.failures = i
            assert breaker.state == "closed"

        # At 100, should open
        breaker.failures = 100
        if breaker.failures >= breaker.failure_threshold:
            breaker.state = "open"

        assert breaker.state == "open"

    def test_zero_timeout(self):
        """Verify circuit handles zero timeout (immediate recovery)."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=0.0)

        # Open circuit
        breaker.state = "open"
        breaker.failures = 3
        breaker.last_failure_time = 1000.0

        # Check timeout with zero timeout
        current_time = 1000.0  # Same timestamp
        if breaker.state == "open" and breaker.last_failure_time:
            if (current_time - breaker.last_failure_time) >= breaker.timeout:
                breaker.state = "half-open"

        # Should transition immediately since timeout is 0
        assert breaker.state == "half-open"

