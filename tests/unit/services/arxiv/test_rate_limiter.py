"""Unit tests for arXiv rate limiter."""

from __future__ import annotations

import pytest

from src.services.fetchers.arxiv.utils.rate_limiter import AdaptiveRateLimiter, RateLimiter


@pytest.mark.asyncio
async def test_try_acquire_consumes_available_token() -> None:
    limiter = RateLimiter(rate=10.0, capacity=1, initial_tokens=1)
    assert await limiter.try_acquire() is True
    assert await limiter.try_acquire() is False


@pytest.mark.asyncio
async def test_get_delay_positive_when_no_tokens() -> None:
    limiter = RateLimiter(rate=1.0, capacity=1, initial_tokens=0)
    delay = await limiter.get_delay()
    assert delay > 0


@pytest.mark.asyncio
async def test_adaptive_rate_limiter_reduces_rate_on_429() -> None:
    limiter = AdaptiveRateLimiter(base_rate=0.3, min_rate=0.1)
    before = limiter.current_rate
    await limiter.on_rate_limit(retry_after=3)
    assert limiter.current_rate <= before
