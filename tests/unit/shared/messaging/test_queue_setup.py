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
        if queue_name == QueueName.PAPER_PARSED.value:
            raise RuntimeError("boom")
        if queue_name in self.depths:
            return {"message_count": self.depths[queue_name], "consumer_count": 1}
        return None


@pytest.mark.asyncio
async def test_declare_queue_adds_dead_letter_routing() -> None:
    conn = _Conn()
    setup = QueueSetup(conn)  # type: ignore[arg-type]
    dlq = QueueName.PAPER_FULLTEXT_DLQ
    await setup._declare_queue(
        QueueName.PAPER_FULLTEXT_REQUEST.value,
        {"x-dead-letter-exchange": DLQ_EXCHANGE_NAME, "x-dead-letter-routing-key": dlq.value},
    )
    _, args = conn.channel.declared_queues[-1]
    assert args["x-dead-letter-exchange"] == DLQ_EXCHANGE_NAME
    assert args["x-dead-letter-routing-key"] == dlq.value


@pytest.mark.asyncio
async def test_get_queue_depths_handles_lookup_errors() -> None:
    conn = _Conn()
    conn.depths[QueueName.PAPER_FULLTEXT_REQUEST.value] = 5
    setup = QueueSetup(conn)  # type: ignore[arg-type]
    depths = await setup.get_queue_depths()
    assert depths[QueueName.PAPER_FULLTEXT_REQUEST.value] == 5
    assert depths[QueueName.PAPER_PARSED.value] == -1
