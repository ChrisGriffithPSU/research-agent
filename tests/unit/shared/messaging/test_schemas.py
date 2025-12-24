"""Unit tests for message schemas."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from src.shared.messaging.schemas import (
    BaseMessage,
    SourceMessage,
    ExtractedInsightsMessage,
    QueueName,
)
from src.shared.models.source import SourceType


def test_base_message_generates_correlation_id():
    """Should auto-generate UUID correlation ID."""
    message = BaseMessage()

    assert message.correlation_id is not None
    assert len(message.correlation_id) == 36  # UUID format


def test_base_message_generates_timestamp():
    """Should auto-generate current timestamp."""
    message = BaseMessage()

    assert message.created_at is not None
    assert isinstance(message.created_at, datetime)
    # Should be recent (within last second)
    assert (datetime.now(timezone.utc) - message.created_at).total_seconds() < 1.0


def test_base_message_default_retry_count():
    """Should have default retry_count of 0."""
    message = BaseMessage()

    assert message.retry_count == 0


def test_base_message_accepts_custom_fields():
    """Should accept custom correlation_id, created_at, retry_count."""
    custom_uuid = "custom-uuid-123"
    custom_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    message = BaseMessage(
        correlation_id=custom_uuid,
        created_at=custom_time,
        retry_count=5,
    )

    assert message.correlation_id == custom_uuid
    assert message.created_at == custom_time
    assert message.retry_count == 5


def test_source_message_validates_correctly():
    """Should validate with required fields."""
    message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/2401.xxxxx",
        title="Test Paper",
        content="Abstract content",
    )

    assert message.source_type == SourceType.ARXIV
    assert message.url == "https://arxiv.org/abs/2401.xxxxx"
    assert message.title == "Test Paper"
    assert message.content == "Abstract content"
    assert message.metadata == {}


def test_source_message_rejects_empty_url():
    """Should reject empty URL."""
    with pytest.raises(ValueError, match="URL cannot be empty"):
        SourceMessage(
            source_type=SourceType.ARXIV,
            url="",
            title="Test",
            content="Content",
        )


def test_source_message_rejects_empty_title():
    """Should reject empty title."""
    with pytest.raises(ValueError, match="Title cannot be empty"):
        SourceMessage(
            source_type=SourceType.ARXIV,
            url="https://arxiv.org/abs/2401.xxxxx",
            title="",
            content="Content",
        )


def test_source_message_rejects_empty_content():
    """Should reject empty content."""
    with pytest.raises(ValueError, match="Content cannot be empty"):
        SourceMessage(
            source_type=SourceType.ARXIV,
            url="https://arxiv.org/abs/2401.xxxxx",
            title="Test",
            content="",
        )


def test_source_message_accepts_metadata():
    """Should accept custom metadata."""
    metadata = {"authors": ["Author 1", "Author 2"], "published": "2024-01-01"}

    message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/2401.xxxxx",
        title="Test Paper",
        content="Content",
        metadata=metadata,
    )

    assert message.metadata == metadata


def test_source_message_serializes_to_json():
    """Should serialize to JSON."""
    message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/2401.xxxxx",
        title="Test Paper",
        content="Content",
    )

    json_str = message.model_dump_json()

    assert '"source_type":"arxiv"' in json_str
    assert '"title":"Test Paper"' in json_str
    assert '"content":"Content"' in json_str


def test_source_message_deserializes_from_json():
    """Should deserialize from JSON."""
    json_str = '{"source_type":"arxiv","url":"https://arxiv.org/abs/2401.xxxxx","title":"Test Paper","content":"Content"}'

    message = SourceMessage.model_validate_json(json_str)

    assert message.source_type == SourceType.ARXIV
    assert message.url == "https://arxiv.org/abs/2401.xxxxx"
    assert message.title == "Test Paper"
    assert message.content == "Content"


def test_extracted_insights_message_validates_actionability_score():
    """Should validate actionability score between 0 and 1."""
    # Valid scores
    for score in [0.0, 0.5, 1.0]:
        message = ExtractedInsightsMessage(
            source_type=SourceType.ARXIV,
            source_url="https://arxiv.org/abs/2401.xxxxx",
            source_title="Test",
            key_insights="Insight",
            core_techniques=["Technique 1"],
            code_snippets=["code"],
            actionability_score=score,
        )
        assert message.actionability_score == score


def test_extracted_insights_message_rejects_negative_score():
    """Should reject negative actionability score."""
    with pytest.raises(ValueError, match="actionability_score must be between 0.0 and 1.0"):
        ExtractedInsightsMessage(
            source_type=SourceType.ARXIV,
            source_url="https://arxiv.org/abs/2401.xxxxx",
            source_title="Test",
            key_insights="Insight",
            core_techniques=["Technique 1"],
            code_snippets=["code"],
            actionability_score=-0.1,
        )


def test_extracted_insights_message_rejects_score_above_one():
    """Should reject actionability score > 1.0."""
    with pytest.raises(ValueError, match="actionability_score must be between 0.0 and 1.0"):
        ExtractedInsightsMessage(
            source_type=SourceType.ARXIV,
            source_url="https://arxiv.org/abs/2401.xxxxx",
            source_title="Test",
            key_insights="Insight",
            core_techniques=["Technique 1"],
            code_snippets=["code"],
            actionability_score=1.1,
        )


def test_queue_name_values():
    """Should have correct queue names."""
    assert QueueName.CONTENT_DISCOVERED.value == "content.discovered"
    assert QueueName.CONTENT_DEDUPLICATED.value == "content.deduplicated"
    assert QueueName.INSIGHTS_EXTRACTED.value == "insights.extracted"
    assert QueueName.DIGEST_READY.value == "digest.ready"
    assert QueueName.FEEDBACK_SUBMITTED.value == "feedback.submitted"
    assert QueueName.TRAINING_TRIGGER.value == "training.trigger"


def test_queue_name_dlq_values():
    """Should have correct DLQ names."""
    assert QueueName.CONTENT_DISCOVERED_DLQ.value == "content.discovered.dlq"
    assert QueueName.CONTENT_DEDUPLICATED_DLQ.value == "content.deduplicated.dlq"
    assert QueueName.INSIGHTS_EXTRACTED_DLQ.value == "insights.extracted.dlq"
    assert QueueName.DIGEST_READY_DLQ.value == "digest.ready.dlq"
    assert QueueName.FEEDBACK_SUBMITTED_DLQ.value == "feedback.submitted.dlq"
    assert QueueName.TRAINING_TRIGGER_DLQ.value == "training.trigger.dlq"

