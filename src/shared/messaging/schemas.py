"""Message schemas for RabbitMQ messaging."""
import enum
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from src.shared.models.source import SourceType

logger = logging.getLogger(__name__)


class QueueName(str, enum.Enum):
    """Named queues in the system."""

    # Main pipeline queues
    CONTENT_DISCOVERED = "content.discovered"
    CONTENT_DEDUPLICATED = "content.deduplicated"
    INSIGHTS_EXTRACTED = "insights.extracted"
    DIGEST_READY = "digest.ready"

    # Feedback loop queues
    FEEDBACK_SUBMITTED = "feedback.submitted"
    TRAINING_TRIGGER = "training.trigger"

    # Dead letter queues (per-queue DLQs)
    CONTENT_DISCOVERED_DLQ = "content.discovered.dlq"
    CONTENT_DEDUPLICATED_DLQ = "content.deduplicated.dlq"
    INSIGHTS_EXTRACTED_DLQ = "insights.extracted.dlq"
    DIGEST_READY_DLQ = "digest.ready.dlq"
    FEEDBACK_SUBMITTED_DLQ = "feedback.submitted.dlq"
    TRAINING_TRIGGER_DLQ = "training.trigger.dlq"


class BaseMessage(BaseModel):
    """Base message with common metadata.

    All message types inherit from this class to ensure
    consistent correlation tracking and timestamps.
    """

    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID to trace message through pipeline"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when message was created"
    )
    retry_count: int = Field(
        default=0,
        description="Number of times message has been retried"
    )

    class Config:
        """Pydantic config for JSON serialization."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class SourceMessage(BaseMessage):
    """Message from fetchers with raw content.

    Published to: content.discovered queue
    Consumed by: Deduplication Service
    """

    source_type: SourceType = Field(
        ...,  # Required
        description="Type of content source (arxiv, kaggle, etc.)"
    )
    url: str = Field(
        ...,  # Required
        max_length=2048,
        description="Source URL"
    )
    title: str = Field(
        ...,  # Required
        max_length=512,
        description="Content title"
    )
    content: str = Field(
        ...,  # Required
        description="Full content (abstract, summary, description, etc.)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional source-specific metadata"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL is not empty."""
        if not v or not v.strip():
            raise ValueError("URL cannot be empty")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not empty."""
        if not v or not v.strip():
            raise ValueError("Content cannot be empty")
        return v


class DeduplicatedContentMessage(BaseMessage):
    """Message after deduplication check.

    Published to: content.deduplicated queue
    Consumed by: Extraction Service
    """

    source_type: SourceType = Field(..., description="Type of content source")
    url: str = Field(..., max_length=2048, description="Source URL")
    title: str = Field(..., max_length=512, description="Content title")
    content: str = Field(..., description="Full content")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # Reference to original discovered message
    original_correlation_id: str = Field(
        ..., description="Correlation ID from original SourceMessage"
    )


class ExtractedInsightsMessage(BaseMessage):
    """Message with LLM-extracted insights.

    Published to: insights.extracted queue
    Consumed by: Synthesis Service
    """

    source_type: SourceType = Field(..., description="Type of content source")
    source_url: str = Field(..., max_length=2048, description="Source URL")
    source_title: str = Field(..., max_length=512, description="Source title")

    # Extracted insights
    key_insights: str = Field(
        ..., description="Key methodology and technique insights"
    )
    core_techniques: List[str] = Field(
        default_factory=list, description="Core algorithms and techniques"
    )
    code_snippets: List[str] = Field(
        default_factory=list, description="Code or pseudocode snippets"
    )
    actionability_score: float = Field(
        ..., ge=0.0, le=1.0, description="How actionable for research (0-1)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional extraction metadata"
    )

    # Reference chain
    original_correlation_id: str = Field(
        ..., description="Original SourceMessage correlation ID"
    )
    deduplicated_correlation_id: str = Field(
        ..., description="DeduplicatedContentMessage correlation ID"
    )

    @field_validator("actionability_score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        """Validate actionability score is in range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("actionability_score must be between 0.0 and 1.0")
        return v


class DigestItem(BaseModel):
    """Single item in digest."""

    source_type: SourceType = Field(..., description="Source of item")
    source_url: str = Field(..., max_length=2048, description="Source URL")
    source_title: str = Field(..., max_length=512, description="Source title")

    # Categorized insights
    key_insights: str = Field(..., description="Key insights")
    core_techniques: List[str] = Field(
        default_factory=list, description="Techniques used"
    )
    code_snippets: List[str] = Field(
        default_factory=list, description="Code snippets"
    )

    # Synthesis output
    category: str = Field(..., max_length=100, description="Assigned category")
    application_ideas: List[str] = Field(
        ..., min_length=1, description="How to apply in research"
    )

    relevance_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Personalized relevance score"
    )


class DigestReadyMessage(BaseMessage):
    """Message with synthesized digest ready for generation.

    Published to: digest.ready queue
    Consumed by: Digest Generation Service
    """

    digest_items: List[DigestItem] = Field(
        ..., min_length=1, description="Items in digest"
    )
    item_count: int = Field(
        ..., ge=1, description="Number of items in digest"
    )

    # Synthesis metadata
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When digest was synthesized"
    )
    categories: List[str] = Field(
        default_factory=list, description="Categories present in digest"
    )

    # Reference chain
    insight_correlation_ids: List[str] = Field(
        default_factory=list,
        description="Correlation IDs of ExtractedInsightsMessages"
    )

    @field_validator("item_count")
    @classmethod
    def validate_item_count(cls, v: int, info) -> int:
        """Validate item_count matches digest_items length."""
        items = info.data.get("digest_items", [])
        if len(items) != v:
            raise ValueError("item_count must match digest_items length")
        return v


class FeedbackMessage(BaseMessage):
    """Message with user feedback on digest item.

    Published to: feedback.submitted queue
    Consumed by: Learning Service
    """

    item_id: str = Field(..., description="Digest item ID")
    correlation_id: Optional[str] = Field(
        default=None, description="Original digest item correlation ID"
    )

    rating: int = Field(
        ..., ge=1, le=5, description="User rating (1-5 stars)"
    )
    implemented: bool = Field(
        ..., description="Whether user implemented this idea"
    )
    notes: Optional[str] = Field(
        default=None, description="User notes on implementation"
    )

    # Context
    category: Optional[str] = Field(
        default=None, description="Category of item"
    )
    source_type: Optional[SourceType] = Field(
        default=None, description="Source type of item"
    )

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Validate rating is 1-5."""
        if not 1 <= v <= 5:
            raise ValueError("rating must be between 1 and 5")
        return v


class TrainingTriggerMessage(BaseMessage):
    """Message to trigger model retraining.

    Published to: training.trigger queue
    Consumed by: Learning Service
    """

    trigger_reason: str = Field(
        ..., description="Why training was triggered (threshold_reached, manual, scheduled)"
    )
    feedback_count: int = Field(
        ..., ge=0, description="Number of feedback items collected"
    )
    model_version: Optional[str] = Field(
        default=None, description="Current model version being replaced"
    )

    # Training metadata
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When training was triggered"
    )
    feedback_correlation_ids: List[str] = Field(
        default_factory=list,
        description="Correlation IDs of FeedbackMessages"
    )

