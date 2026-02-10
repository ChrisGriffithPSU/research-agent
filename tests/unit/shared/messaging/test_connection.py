"""Unit tests for RabbitMQ connection management."""

from __future__ import annotations

import asyncio
import types

import pytest

import src.shared.messaging.connection as connection_module
from src.shared.messaging.config import MessagingConfig
from src.shared.messaging.connection import RabbitMQConnection, get_connection
from src.shared.messaging.exceptions import ConnectionError


class _FakeQueueInfo:
    def __init__(self, messages: int = 0, consumers: int = 0) -> None:
        self.declaration_result = types.SimpleNamespace(
            message_count=messages,
            consumer_count=consumers,
        )


class _FakeChannel:
    def __init__(self) -> None:
        self.is_closed = False
        self.confirm_selected = False

    async def close(self) -> None:
        self.is_closed = True

    async def confirm_select(self) -> None:
        self.confirm_selected = True

    async def declare_queue(self, name: str, passive: bool = True):
        if name == "missing":
            raise RuntimeError("not found")
        return _FakeQueueInfo(messages=3, consumers=1)


class _FakeRobustConnection:
    def __init__(self) -> None:
        self.is_closed = False
        self._channel = _FakeChannel()
        self.closed = asyncio.Future()

    async def channel(self):
        return self._channel

    async def close(self):
        self.is_closed = True


@pytest.mark.asyncio
async def test_connect_and_close_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRobustConnection()

    async def _connect_robust(*args, **kwargs):
        return fake

    async def _monitor(self):
        return None

    monkeypatch.setattr(connection_module.aio_pika, "connect_robust", _connect_robust)
    monkeypatch.setattr(RabbitMQConnection, "_monitor_connection", _monitor)

    conn = RabbitMQConnection(MessagingConfig(host="localhost", port=5672, user="u", password="p"))
    await conn.connect()
    assert conn.is_connected is True
    assert conn.channel is fake._channel

    await conn.close()
    assert conn.is_connected is False


@pytest.mark.asyncio
async def test_connect_raises_connection_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(connection_module.aio_pika, "connect_robust", _boom)
    conn = RabbitMQConnection(MessagingConfig())
    with pytest.raises(ConnectionError):
        await conn.connect()


@pytest.mark.asyncio
async def test_get_queue_info_returns_message_and_consumer_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRobustConnection()

    async def _connect_robust(*args, **kwargs):
        return fake

    async def _monitor(self):
        return None

    monkeypatch.setattr(connection_module.aio_pika, "connect_robust", _connect_robust)
    monkeypatch.setattr(RabbitMQConnection, "_monitor_connection", _monitor)

    conn = RabbitMQConnection(MessagingConfig())
    await conn.connect()
    info = await conn.get_queue_info("content.discovered")
    assert info == {"message_count": 3, "consumer_count": 1}


@pytest.mark.asyncio
async def test_get_connection_is_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    connection_module._global_connection = None
    cfg = MessagingConfig(host="h", port=5672, user="u", password="p")
    a = await get_connection(cfg)
    b = await get_connection(cfg)
    assert a is b
