"""Unit tests for Slack notifier worker."""

from __future__ import annotations

from src.workers.notifier.slack_worker import SlackNotifierWorker
from src.workers.shared.message_schemas import NotificationRequest
from tests.helpers.fakes import DummyConsumer, DummyPublisher


def _worker() -> SlackNotifierWorker:
    return SlackNotifierWorker(
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        webhook_url=None,
        bot_token=None,
        channel="#test",
    )


def test_format_message_contains_key_sections() -> None:
    worker = _worker()
    msg = NotificationRequest(
        status="INFO",
        title="Run Complete",
        message="Body",
        metrics={"sharpe": 1.2},
        artifact_refs=["runs/x/summary.json"],
        recommendation="INVESTIGATE",
    )
    payload = worker._format_message(msg)
    assert payload["channel"] == "#test"
    assert "Run Complete" in payload["blocks"][0]["text"]["text"]
    assert "sharpe" in payload["text"]
