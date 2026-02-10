"""Unit tests for async logging context helpers."""

from __future__ import annotations

import pytest

from src.shared.utils.logging.context import get_context, get_correlation_id, log_context


@pytest.mark.asyncio
async def test_log_context_sets_and_restores_values() -> None:
    original = get_context()
    async with log_context(correlation_id="cid-1", operation_name="op-1"):
        assert get_correlation_id() == "cid-1"
        scoped = get_context()
        assert scoped["operation_name"] == "op-1"
    restored = get_context()
    assert restored["correlation_id"] == original["correlation_id"]
