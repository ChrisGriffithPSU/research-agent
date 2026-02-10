"""Unit tests for shared retry decorator utilities."""

from __future__ import annotations

import pytest

from src.shared.utils.retry import calculate_backoff, retry


def test_calculate_backoff_respects_cap() -> None:
    value = calculate_backoff(
        attempt=10, base_seconds=1.0, factor=2.0, max_seconds=5.0, jitter_percent=0.0
    )
    assert value == 5.0


@pytest.mark.asyncio
async def test_retry_decorator_eventually_succeeds() -> None:
    state = {"count": 0}

    @retry(max_attempts=3, backoff_base=0.0, jitter_percent=0.0)
    async def flaky() -> str:
        state["count"] += 1
        if state["count"] < 3:
            raise RuntimeError("retry")
        return "ok"

    assert await flaky() == "ok"
    assert state["count"] == 3
