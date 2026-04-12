"""Unit tests for BaseWorker behavior."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import PaperFullTextRequest
from tests.helpers.fakes import DummyConsumer, DummyPublisher


class _OutMessage(BaseModel):
    value: str


class _Worker(BaseWorker):
    async def process(self, message: Any) -> None:
        await self.publish("out.queue", _OutMessage(value="ok"))

    def get_message_type(self):
        return PaperFullTextRequest


@pytest.mark.asyncio
async def test_start_registers_consumer_subscription_and_sets_running() -> None:
    consumer = DummyConsumer()
    publisher = DummyPublisher()
    worker = _Worker(
        config=WorkerConfig(queue_name="paper.fulltext.request"),
        message_consumer=consumer,  # type: ignore[arg-type]
        message_publisher=publisher,  # type: ignore[arg-type]
    )

    await worker.start()
    assert worker.is_running() is True
    assert consumer.started is True
    assert len(consumer.subscriptions) == 1


@pytest.mark.asyncio
async def test_handle_message_calls_process_and_publishes() -> None:
    consumer = DummyConsumer()
    publisher = DummyPublisher()
    worker = _Worker(
        config=WorkerConfig(queue_name="paper.fulltext.request"),
        message_consumer=consumer,  # type: ignore[arg-type]
        message_publisher=publisher,  # type: ignore[arg-type]
    )

    msg = PaperFullTextRequest(
        paper_id="p1",
        title="t",
        abstract="a",
        arxiv_url="u",
        pdf_url="p",
    )
    await worker._handle_message(msg)
    assert publisher.published[0]["routing_key"] == "out.queue"
    assert publisher.published[0]["message"]["value"] == "ok"


@pytest.mark.asyncio
async def test_stop_clears_running_and_stops_consumer() -> None:
    consumer = DummyConsumer()
    publisher = DummyPublisher()
    worker = _Worker(
        config=WorkerConfig(queue_name="paper.fulltext.request"),
        message_consumer=consumer,  # type: ignore[arg-type]
        message_publisher=publisher,  # type: ignore[arg-type]
    )

    await worker.start()
    await worker.stop()
    assert worker.is_running() is False
    assert consumer.stopped is True
