"""Unit tests for messaging schema contracts."""

from src.shared.messaging.schemas import QueueName, BaseMessage


def test_queue_name_contains_pipeline_values() -> None:
    assert QueueName.PAPER_FULLTEXT_REQUEST.value == "paper.fulltext.request"
    assert QueueName.PAPER_CONCEPTS_REQUEST.value == "paper.concepts.request"
    assert QueueName.CODE_EXECUTION_REQUEST.value == "code.execution.request"
    assert QueueName.EXPERIMENT_EVALUATION_REQUEST.value == "experiment.evaluation.request"
    assert QueueName.NOTIFY_SEND.value == "notify.send"


def test_base_message_has_correlation_id_and_timestamp() -> None:
    msg = BaseMessage()
    assert msg.correlation_id is not None
    assert msg.retry_count == 0
    payload = msg.model_dump(mode="json")
    assert isinstance(payload["created_at"], str)
