"""Unit tests for retry strategies."""
import pytest
import asyncio

from src.shared.messaging.retry import (
    IRetryStrategy,
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    NoRetryStrategy,
)
from src.shared.messaging.exceptions import PermanentError


def test_exponential_backoff_calculates_correctly():
    """Should calculate correct backoff values (with jitter tolerance)."""
    strategy = ExponentialBackoffStrategy(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
    )

    # base_delay * (2 ^ attempt) with ±20% jitter
    backoff_0 = strategy.get_backoff(0)  # 1 * 2^0 = 1.0 ± 0.2
    backoff_1 = strategy.get_backoff(1)  # 1 * 2^1 = 2.0 ± 0.4
    backoff_2 = strategy.get_backoff(2)  # 1 * 2^2 = 4.0 ± 0.8

    # Allow for ±20% jitter
    assert 0.8 <= backoff_0 <= 1.2
    assert 1.6 <= backoff_1 <= 2.4
    assert 3.2 <= backoff_2 <= 4.8


def test_exponential_backoff_caps_at_max():
    """Should cap backoff at max_delay (with jitter tolerance)."""
    strategy = ExponentialBackoffStrategy(
        max_attempts=10,
        base_delay=1.0,
        max_delay=10.0,
    )

    # 2^9 = 512, but capped at 10 ± 2 (20% jitter)
    backoff = strategy.get_backoff(9)
    assert backoff <= 12.0  # max_delay + jitter
    assert backoff >= 8.0   # max_delay - jitter


@pytest.mark.asyncio
async def test_exponential_backoff_should_retry_transient_errors():
    """Should retry on transient errors (not PermanentError)."""
    strategy = ExponentialBackoffStrategy(max_attempts=3)

    # Transient error - should retry
    assert await strategy.should_retry(attempt=0, error=RuntimeError("transient"))
    assert await strategy.should_retry(attempt=1, error=ValueError("another transient"))
    assert await strategy.should_retry(attempt=2, error=Exception("unknown"))

    # Permanent error - should not retry
    assert not await strategy.should_retry(
        attempt=0, error=PermanentError("permanent")
    )

    # PublishError - should not retry (permanent)
    from src.shared.messaging.exceptions import PublishError
    assert not await strategy.should_retry(
        attempt=0, error=PublishError("publish failed")
    )

    # ConnectionError - should not retry (permanent)
    from src.shared.messaging.exceptions import ConnectionError
    assert not await strategy.should_retry(
        attempt=0, error=ConnectionError("connection failed")
    )


@pytest.mark.asyncio
async def test_exponential_backoff_should_not_retry_after_max_attempts():
    """Should not retry after max attempts reached."""
    strategy = ExponentialBackoffStrategy(max_attempts=3)

    # Should retry below max (attempts 0, 1, 2)
    assert await strategy.should_retry(attempt=0, error=RuntimeError("transient"))
    assert await strategy.should_retry(attempt=1, error=RuntimeError("transient"))
    assert await strategy.should_retry(attempt=2, error=RuntimeError("transient"))

    # Should not retry at or above max (attempts 3+)
    assert not await strategy.should_retry(attempt=3, error=RuntimeError("transient"))
    assert not await strategy.should_retry(attempt=4, error=RuntimeError("transient"))


def test_linear_backoff_calculates_correctly():
    """Should calculate correct linear backoff values (with jitter tolerance for potential future changes)."""
    strategy = LinearBackoffStrategy(
        max_attempts=3,
        base_delay=1.0,
        increment=2.0,
        max_delay=100.0,
    )

    # base_delay + (increment * attempt)
    # Note: Linear backoff doesn't have jitter in current implementation,
    # but we use ranges for consistency and robustness
    backoff_0 = strategy.get_backoff(0)  # 1 + 2*0 = 1.0
    backoff_1 = strategy.get_backoff(1)  # 1 + 2*1 = 3.0
    backoff_2 = strategy.get_backoff(2)  # 1 + 2*2 = 5.0

    assert 0.95 <= backoff_0 <= 1.05  # Small tolerance for floating point
    assert 2.95 <= backoff_1 <= 3.05
    assert 4.95 <= backoff_2 <= 5.05


def test_linear_backoff_caps_at_max():
    """Should cap linear backoff at max_delay."""
    strategy = LinearBackoffStrategy(
        max_attempts=10,
        base_delay=1.0,
        increment=10.0,
        max_delay=20.0,
    )

    # 1 + 10*9 = 91, but capped at 20
    backoff = strategy.get_backoff(9)
    assert backoff <= 20.0
    assert backoff >= 19.0  # Small tolerance


@pytest.mark.asyncio
async def test_linear_backoff_should_retry_transient_errors():
    """Should retry on transient errors (not PermanentError)."""
    strategy = LinearBackoffStrategy(max_attempts=3)

    assert await strategy.should_retry(attempt=0, error=RuntimeError("transient"))
    assert not await strategy.should_retry(
        attempt=0, error=PermanentError("permanent")
    )


@pytest.mark.asyncio
async def test_no_retry_strategy_never_retries():
    """Should never retry with NoRetryStrategy."""
    strategy = NoRetryStrategy()

    # Never retry, regardless of error or attempt
    assert not await strategy.should_retry(attempt=0, error=RuntimeError("error"))
    assert not await strategy.should_retry(attempt=10, error=RuntimeError("error"))
    assert not await strategy.should_retry(
        attempt=0, error=PermanentError("permanent")
    )

    # Backoff is always 0
    assert strategy.get_backoff(0) == 0.0
    assert strategy.get_backoff(10) == 0.0


def test_retry_strategy_interface():
    """ExponentialBackoffStrategy implements IRetryStrategy."""
    strategy = ExponentialBackoffStrategy()
    assert isinstance(strategy, IRetryStrategy)

    # Can call abstract methods
    asyncio.get_event_loop().run_until_complete(
        strategy.should_retry(0, Exception("test"))
    )
    backoff = strategy.get_backoff(0)
    assert backoff >= 0
