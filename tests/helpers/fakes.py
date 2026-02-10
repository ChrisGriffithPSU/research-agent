"""Reusable test doubles for worker and pipeline tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class DummyConsumer:
    """Minimal consumer test double matching worker expectations."""

    def __init__(self) -> None:
        self.subscriptions: list[tuple[object, object]] = []
        self.started = False
        self.stopped = False

    def subscribe(
        self, queue: object, callback: object, message_type: object | None = None
    ) -> None:
        self.subscriptions.append((queue, callback))

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class DummyPublisher:
    """Records all published messages in-memory."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, message: Any, routing_key: str, **kwargs: Any) -> None:
        payload = message
        if hasattr(message, "model_dump"):
            payload = message.model_dump(mode="json")
        elif hasattr(message, "model_dump_json"):
            payload = json.loads(message.model_dump_json())
        elif isinstance(message, str):
            try:
                payload = json.loads(message)
            except Exception:
                payload = message

        self.published.append(
            {
                "routing_key": routing_key,
                "message": payload,
                "raw_message": message,
            }
        )


class DummyLLMResponse:
    """Simple LLM response object with `.content`."""

    def __init__(self, content: str) -> None:
        self.content = content


class DummyLLMClient:
    """Configurable async LLM stub for worker tests."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> DummyLLMResponse:
        self.calls.append(kwargs)
        return DummyLLMResponse(self._content)

    async def health_check(self) -> bool:
        return True


@dataclass(slots=True)
class FakeParsedContent:
    """Parsed content payload returned by fake PDF processor."""

    text_content: str
    metadata: dict[str, Any]
    tables: list[dict[str, Any]]
    equations: list[str]
    figure_captions: list[dict[str, str]]


class FakePDFProcessor:
    """Fake async PDF processor used for parser worker tests."""

    def __init__(self, parsed: FakeParsedContent) -> None:
        self.parsed = parsed
        self.calls: list[tuple[str, str]] = []

    async def extract(self, pdf_url: str, paper_id: str) -> FakeParsedContent:
        self.calls.append((pdf_url, paper_id))
        return self.parsed
