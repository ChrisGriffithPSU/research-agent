"""Unit tests for shared circuit breaker utilities."""

from __future__ import annotations

import asyncio

import pytest

from src.shared.exceptions import CircuitOpenError
from src.shared.utils.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_circuit_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=60)

    async def _fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    with pytest.raises(RuntimeError):
        await breaker.call(_fail)

    assert breaker.get_state() == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await breaker.call(lambda: "never")


@pytest.mark.asyncio
async def test_half_open_closes_after_success_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=1, timeout_seconds=0, success_threshold=2)

    async def _fail() -> None:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.get_state() == CircuitState.OPEN

    # Force timeout transition.
    await asyncio.sleep(0.01)
    assert await breaker.call(lambda: "ok") == "ok"
    assert breaker.get_state() == CircuitState.HALF_OPEN
    assert await breaker.call(lambda: "ok") == "ok"
    assert breaker.get_state() == CircuitState.CLOSED
