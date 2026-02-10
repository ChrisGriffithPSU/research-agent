"""Unit tests for messaging schema contracts."""

from src.shared.messaging.schemas import QueueName, SourceMessage
from src.shared.models.source import SourceType


def test_queue_name_contains_expected_content_pipeline_values() -> None:
    assert QueueName.CONTENT_DISCOVERED.value == "content.discovered"
    assert QueueName.DIGEST_READY.value == "digest.ready"


def test_source_message_requires_non_empty_core_fields() -> None:
    msg = SourceMessage(source_type=SourceType.ARXIV, url="https://x", title="t", content="c")
    payload = msg.model_dump(mode="json")
    assert payload["source_type"] in {"arxiv", SourceType.ARXIV}

    try:
        SourceMessage(source_type=SourceType.ARXIV, url="", title="x", content="y")
    except Exception as exc:
        assert "URL cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected validation error for empty URL")
