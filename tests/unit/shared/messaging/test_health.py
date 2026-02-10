"""Unit tests for messaging health helpers."""

from __future__ import annotations

import types

import pytest

from src.shared.messaging.health import check_messaging_health, quick_check


class _Conn:
    def __init__(self, is_connected: bool) -> None:
        self.is_connected = is_connected


@pytest.mark.asyncio
async def test_quick_check_reflects_connection_property() -> None:
    assert await quick_check(_Conn(True)) is True
    assert await quick_check(_Conn(False)) is False


@pytest.mark.asyncio
async def test_check_messaging_health_reports_healthy_with_empty_queues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _QueueSetup:
        def __init__(self, _conn: object) -> None:
            pass

        async def get_queue_depths(self) -> dict[str, int]:
            return {"content.discovered": 0}

    class _Metrics:
        def get_summary(self) -> dict[str, object]:
            return {"ok": True}

        def get_counter(self, name: str, default: int = 0) -> int:
            return 0

    import src.shared.messaging.queue_setup as queue_setup_module
    import src.shared.messaging.health as health_module

    monkeypatch.setattr(queue_setup_module, "QueueSetup", _QueueSetup)
    monkeypatch.setattr(health_module, "get_metrics", lambda: _Metrics())

    health = await check_messaging_health(_Conn(True), queues=[])
    assert str(health.status) == "healthy"
    assert health.checks["connection"] == "ok"
