"""Message schemas and queue definitions for RabbitMQ messaging.

Defines the QueueName enum matching the actual pipeline queues and
a BaseMessage for cross-cutting messaging concerns.
"""

import enum
import logging
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer

logger = logging.getLogger(__name__)


class QueueName(str, enum.Enum):
    """Named queues in the research pipeline."""

    # Pipeline queues
    PAPER_FULLTEXT_REQUEST = "paper.fulltext.request"
    PAPER_PARSED = "paper.parsed"
    PAPER_CONCEPTS_REQUEST = "paper.concepts.request"
    CONCEPTS_GENERATED = "concepts.generated"
    PLAN_GENERATE_REQUEST = "plan.generate.request"
    PLAN_GENERATED = "plan.generated"
    CODE_EXECUTION_REQUEST = "code.execution.request"
    CODE_EXECUTION_RESULT = "code.execution.result"
    EXPERIMENT_EVALUATION_REQUEST = "experiment.evaluation.request"
    EXPERIMENT_EVALUATION_RESULT = "experiment.evaluation.result"
    NOTIFY_SEND = "notify.send"

    # Dead letter queues
    PAPER_FULLTEXT_DLQ = "paper.fulltext.dlq"
    PAPER_CONCEPTS_DLQ = "paper.concepts.dlq"
    PLAN_GENERATE_DLQ = "plan.generate.dlq"
    CODE_EXECUTION_DLQ = "code.execution.dlq"
    EXPERIMENT_EVALUATION_DLQ = "experiment.evaluation.dlq"


class BaseMessage(BaseModel):
    """Base message with common metadata.

    All message types inherit from this class to ensure
    consistent correlation tracking and timestamps.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=False,
        use_enum_values=False,
    )

    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID to trace message through pipeline",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when message was created",
    )
    retry_count: int = Field(
        default=0,
        description="Number of times message has been retried",
    )

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime, _info):
        """Serialize datetime to ISO format string."""
        return dt.isoformat()
