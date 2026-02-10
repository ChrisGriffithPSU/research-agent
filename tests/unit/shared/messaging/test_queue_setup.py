"""Unit tests for RabbitMQ queue setup routines."""

from __future__ import annotations

import pytest

from src.shared.messaging.queue_setup import DLQ_EXCHANGE_NAME, QueueSetup
from src.shared.messaging.schemas import QueueName


class _FakeExchange:
    pass


class _FakeQueue:
    def __init__(self, name: str) -> None:
        self.name = name
        self.bindings: list[tuple[object, str]] = []

    async def bind(self, exchange: object, routing_key: str) -> None:
        self.bindings.append((exchange, routing_key))


class _FakeChannel:
    def __init__(self) -> None:
        self.declared_queues: list[tuple[str, dict]] = []
        self.declared_exchanges: list[tuple[str, dict]] = []
        self.queues: dict[str, _FakeQueue] = {}

    async def declare_queue(
        self, name: str, durable: bool = True, arguments=None, passive: bool = False
    ):
        if passive and name in self.queues:
            return self.queues[name]
        queue = self.queues.get(name, _FakeQueue(name))
        self.queues[name] = queue
        self.declared_queues.append((name, arguments or {}))
        return queue

    async def declare_exchange(self, name: str, **kwargs):
        self.declared_exchanges.append((name, kwargs))
        return _FakeExchange()


class _Conn:
    def __init__(self) -> None:
        self.channel = _FakeChannel()
        self.depths: dict[str, int] = {}

    async def get_queue_info(self, queue_name: str):
        if queue_name == QueueName.DIGEST_READY.value:
            raise RuntimeError("boom")
        if queue_name in self.depths:
            return {"message_count": self.depths[queue_name], "consumer_count": 1}
        return None


def test_get_dlq_name_maps_all_main_queues() -> None:
    setup = QueueSetup(_Conn())  # type: ignore[arg-type]
    assert setup._get_dlq_name(QueueName.CONTENT_DISCOVERED) == QueueName.CONTENT_DISCOVERED_DLQ
    assert setup._get_dlq_name(QueueName.TRAINING_TRIGGER) == QueueName.TRAINING_TRIGGER_DLQ


@pytest.mark.asyncio
async def test_declare_queue_adds_dead_letter_and_limits() -> None:
    conn = _Conn()
    setup = QueueSetup(conn)  # type: ignore[arg-type]
    await setup._declare_queue(
        QueueName.CONTENT_DISCOVERED,
        {"max_length": 100, "ttl": 2000, "routing_key": "content.discovered"},
    )
    _, args = conn.channel.declared_queues[-1]
    assert args["x-dead-letter-exchange"] == DLQ_EXCHANGE_NAME
    assert args["x-dead-letter-routing-key"] == QueueName.CONTENT_DISCOVERED_DLQ.value
    assert args["x-message-ttl"] == 2000
    assert args["x-max-length"] == 100


@pytest.mark.asyncio
async def test_get_queue_depths_handles_lookup_errors() -> None:
    conn = _Conn()
    conn.depths[QueueName.CONTENT_DISCOVERED.value] = 5
    setup = QueueSetup(conn)  # type: ignore[arg-type]
    depths = await setup.get_queue_depths()
    assert depths[QueueName.CONTENT_DISCOVERED.value] == 5
    assert depths[QueueName.DIGEST_READY.value] == -1
