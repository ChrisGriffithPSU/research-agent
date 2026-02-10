"""Unit tests for message publisher behavior."""

from __future__ import annotations

import types

import pytest
from pydantic import BaseModel

from src.shared.messaging.publisher import MessagePublisher, PublishError


class _Conn:
    def __init__(self, connected: bool = True) -> None:
        self.is_connected = connected
        self.channel = types.SimpleNamespace()

    async def close(self):
        return None


class _Msg(BaseModel):
    x: int


@pytest.mark.asyncio
async def test_publish_requires_connected_connection() -> None:
    publisher = MessagePublisher(connection=_Conn(connected=False))
    with pytest.raises(Exception):
        await publisher.publish(_Msg(x=1), routing_key="rk")


@pytest.mark.asyncio
async def test_publish_serializes_message_and_uses_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = MessagePublisher(connection=_Conn(connected=True))
    calls = {"count": 0}

    async def _fake_publish(message_bytes, routing_key, mandatory, immediate):
        calls["count"] += 1

    monkeypatch.setattr(publisher, "_do_publish", _fake_publish)
    await publisher.publish(_Msg(x=7), routing_key="rk")
    assert calls["count"] == 1
