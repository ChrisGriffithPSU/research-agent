"""Message schemas for quant research pipeline.

Defines JSON contracts for Pub/Sub messaging between workers.
All messages include correlation tracking and timestamps.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer


class BaseMessage(BaseModel):
    """Base message with common metadata."""

    work_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique ID for this work unit"
    )
    parent_work_id: Optional[str] = Field(
        default=None, description="ID of parent work unit for tracing"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when message was created",
    )
    attempt: int = Field(default=0, description="Current attempt number")
    max_attempts: int = Field(default=3, description="Maximum retry attempts")
    priority: int = Field(
        default=5, ge=1, le=10, description="Priority level (1-10, lower is higher priority)"
    )

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format."""
        return dt.isoformat()


# ==================== Paper Ingestion Messages ====================


class PaperTriageRequest(BaseMessage):
    """Request to triage a paper based on abstract.

    Published by: ArXiv Fetcher
    Consumed by: Paper Triage Agent
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(default_factory=list, description="Paper authors")
    abstract: str = Field(..., description="Paper abstract")
    categories: List[str] = Field(default_factory=list, description="ArXiv categories")
    arxiv_url: str = Field(..., description="ArXiv abstract page URL")
    pdf_url: str = Field(..., description="Direct PDF URL")
    submitted_date: Optional[str] = Field(None, description="Submission date")


class PaperTriageDecision(BaseMessage):
    """Decision from paper triage.

    Published by: Paper Triage Agent
    Consumed by: Full Text Request handler or rejection logger
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    decision: Literal["REQUEST_FULL_TEXT", "REJECT_PAPER"] = Field(
        ..., description="Triage decision"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: Dict[str, Any] = Field(
        default_factory=dict, description="Structured reasoning from triage"
    )
    cross_domain_opportunities: List[Dict[str, str]] = Field(
        default_factory=list, description="Identified cross-domain opportunities"
    )
    notes_for_concept_stage: List[str] = Field(
        default_factory=list, description="Notes for downstream concept generation"
    )


class FullTextRequest(BaseMessage):
    """Request to fetch and parse full PDF.

    Published by: Paper Triage Agent (on REQUEST_FULL_TEXT)
    Consumed by: PDF Parser
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    pdf_url: str = Field(..., description="Direct PDF URL")
    triage_decision: Dict[str, Any] = Field(
        default_factory=dict, description="Original triage decision for context"
    )


class ParsedPaper(BaseMessage):
    """Parsed paper content.

    Published by: PDF Parser
    Consumed by: Concept Generator Agent
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: List[str] = Field(default_factory=list, description="Paper authors")
    full_text: str = Field(..., description="Full extracted text")
    sections: List[Dict[str, str]] = Field(
        default_factory=list, description="Text sections with headings"
    )
    artifact_refs: List[str] = Field(default_factory=list, description="Paths to stored artifacts")


# ==================== Concept Generation Messages ====================


class ConceptGenerationRequest(BaseMessage):
    """Request to generate concept objects.

    Published by: PDF Parser
    Consumed by: Concept Generator Agent
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: List[str] = Field(default_factory=list, description="Paper authors")
    full_text: str = Field(..., description="Full paper text")
    sections: List[Dict[str, str]] = Field(default_factory=list, description="Text sections")
    categories: List[str] = Field(default_factory=list, description="Paper categories")
    triage_context: Dict[str, Any] = Field(
        default_factory=dict, description="Context from triage stage"
    )
    artifact_refs: List[str] = Field(default_factory=list, description="Paths to stored artifacts")


class ConceptObject(BaseModel):
    """Single concept object extracted from paper."""

    concept_id: str = Field(..., description="Unique concept ID")
    concept_name: str = Field(..., description="Human-readable name")
    origin_domain: str = Field(..., description="Original domain of concept")
    concept_summary: str = Field(..., description="Brief summary")
    core_problem_it_solves: str = Field(..., description="Core problem addressed")
    system_abstraction: Dict[str, Any] = Field(
        default_factory=dict, description="System abstraction details"
    )
    invariant_structures: List[Dict[str, str]] = Field(
        default_factory=list, description="Identified invariant structures"
    )
    assumptions: List[str] = Field(default_factory=list, description="Key assumptions")
    regime_behavior: Dict[str, Any] = Field(
        default_factory=dict, description="Behavior across regimes"
    )
    failure_modes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Potential failure modes"
    )
    cross_domain_analogies: List[Dict[str, str]] = Field(
        default_factory=list, description="Cross-domain analogies"
    )
    research_hooks: List[Dict[str, Any]] = Field(
        default_factory=list, description="Falsifiable research questions"
    )
    evidence_quality: Dict[str, Any] = Field(
        default_factory=dict, description="Quality assessment of evidence"
    )


class ConceptsGenerated(BaseMessage):
    """Generated concept objects.

    Published by: Concept Generator Agent
    Consumed by: Experiment Exploder Agent (future)
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    concept_objects: List[ConceptObject] = Field(
        default_factory=list, description="Extracted concept objects"
    )
    concepts_json_path: str = Field(..., description="Path to stored concepts.json")
    artifact_refs: List[str] = Field(default_factory=list, description="Paths to all artifacts")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Metadata about generation")


class PlanGenerated(BaseMessage):
    """Experiment plan generated from concept objects.

    Published by: Experiment Exploder Agent
    Consumed by: downstream experiment execution workers
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    plan_json_path: str = Field(..., description="Path to generated plan JSON")
    batch_id: Optional[str] = Field(None, description="Optional batch identifier")
    experiment_count: int = Field(default=0, description="Total experiments generated")


# ==================== Notification Messages ====================


class NotificationRequest(BaseMessage):
    """Request to send notification.

    Published by: Various agents on completion/failure
    Consumed by: Notifier worker
    """

    experiment_id: Optional[str] = Field(None, description="Experiment ID if applicable")
    paper_id: Optional[str] = Field(None, description="Paper ID if applicable")
    status: Literal["SUCCESS", "FAILED", "NEEDS_HUMAN", "INFO"] = Field(
        ..., description="Status to report"
    )
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Main message content")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Key metrics")
    regime_breakdown: List[Dict[str, Any]] = Field(
        default_factory=list, description="Regime breakdown table"
    )
    plots: List[str] = Field(default_factory=list, description="Paths to plot images")
    artifact_refs: List[str] = Field(default_factory=list, description="Links to artifacts")
    crossed_threshold: bool = Field(default=False, description="Whether thresholds were crossed")
    recommendation: Optional[str] = Field(None, description="PROMOTE/KILL/INVESTIGATE/NONE")


# ==================== Dead Letter Queue Messages ====================


class FailedMessage(BaseMessage):
    """Message that failed processing.

    Published to: Dead letter queue
    """

    original_message: Dict[str, Any] = Field(..., description="Original message that failed")
    error_type: str = Field(..., description="Type of error")
    error_message: str = Field(..., description="Error message")
    error_traceback: Optional[str] = Field(None, description="Full traceback")
    failed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When failure occurred"
    )

    @field_serializer("failed_at")
    def serialize_failed_at(self, dt: datetime) -> str:
        """Serialize datetime to ISO format."""
        return dt.isoformat()
