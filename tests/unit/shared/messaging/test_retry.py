"""Unit tests for messaging retry strategies."""

import pytest

from src.shared.messaging.exceptions import ConnectionError, PermanentError, TemporaryError
from src.shared.messaging.retry import (
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    NoRetryStrategy,
)


@pytest.mark.asyncio
async def test_exponential_retry_retries_temporary_errors() -> None:
    strategy = ExponentialBackoffStrategy(max_attempts=3)
    should_retry = await strategy.should_retry(0, TemporaryError("temp"))
    assert should_retry is True


@pytest.mark.asyncio
async def test_exponential_retry_never_retries_permanent_errors() -> None:
    strategy = ExponentialBackoffStrategy(max_attempts=3)
    should_retry = await strategy.should_retry(0, PermanentError("perm"))
    assert should_retry is False


@pytest.mark.asyncio
async def test_exponential_retry_does_not_retry_connection_error() -> None:
    strategy = ExponentialBackoffStrategy(max_attempts=3)
    should_retry = await strategy.should_retry(0, ConnectionError("offline"))
    assert should_retry is False


def test_exponential_backoff_returns_bounded_jittered_value() -> None:
    strategy = ExponentialBackoffStrategy(base_delay=2.0, max_delay=4.0)
    delay = strategy.get_backoff(3)
    # Base gets capped at 4.0, then jitter +-20% => [3.2, 4.8]
    assert 3.2 <= delay <= 4.8


def test_linear_backoff_increments_until_cap() -> None:
    strategy = LinearBackoffStrategy(base_delay=1.0, increment=2.0, max_delay=6.0)
    assert strategy.get_backoff(0) == 1.0
    assert strategy.get_backoff(1) == 3.0
    assert strategy.get_backoff(5) == 6.0


@pytest.mark.asyncio
async def test_no_retry_strategy_always_false() -> None:
    strategy = NoRetryStrategy()
    assert await strategy.should_retry(0, Exception("x")) is False
