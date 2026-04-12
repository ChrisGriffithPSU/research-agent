"""Unit tests for message consumer subscription and validation behavior."""

from __future__ import annotations

import pytest

from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.schemas import QueueName
from src.workers.shared.message_schemas import PaperFullTextRequest


class _Conn:
    def __init__(self) -> None:
        self.is_connected = True
        self.channel = None


@pytest.mark.asyncio
async def test_subscribe_requires_async_handler() -> None:
    consumer = MessageConsumer(connection=_Conn())  # type: ignore[arg-type]

    def _sync_handler(_message):
        return None

    with pytest.raises(ValueError):
        consumer.subscribe(
            QueueName.PAPER_FULLTEXT_REQUEST,
            _sync_handler,
            message_type=PaperFullTextRequest,
        )


@pytest.mark.asyncio
async def test_start_no_handlers_returns_without_error() -> None:
    consumer = MessageConsumer(connection=_Conn())  # type: ignore[arg-type]
    await consumer.start()
