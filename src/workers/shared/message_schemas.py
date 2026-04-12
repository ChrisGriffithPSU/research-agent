"""Message schemas for quant research pipeline.

Defines JSON contracts for Pub/Sub messaging between workers.
All messages include correlation tracking and timestamps.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer


class BaseMessage(BaseModel):
    """Base message with common metadata."""

    work_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique ID for this work unit"
    )
    parent_work_id: str | None = Field(
        default=None, description="ID of parent work unit for tracing"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
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


class PaperFullTextRequest(BaseMessage):
    """Request to fetch and parse full PDF.

    Published by: ArXiv Fetcher
    Consumed by: PDF Parser
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Paper authors")
    abstract: str = Field(..., description="Paper abstract")
    categories: list[str] = Field(default_factory=list, description="ArXiv categories")
    arxiv_url: str = Field(..., description="ArXiv abstract page URL")
    pdf_url: str = Field(..., description="Direct PDF URL")
    submitted_date: str | None = Field(None, description="Submission date")


class ConceptGenerationRequest(BaseMessage):
    """Request to generate concepts from a parsed paper.

    Published by: PDF Parser
    Consumed by: Concept Generator Agent
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: list[str] = Field(default_factory=list, description="Paper authors")
    full_text: str = Field(..., description="Full extracted text")
    sections: list[dict[str, str]] = Field(
        default_factory=list, description="Text sections with headings"
    )
    categories: list[str] = Field(default_factory=list, description="ArXiv categories")
    artifact_refs: list[str] = Field(default_factory=list, description="Paths to stored artifacts")


# ==================== Concept Generation Messages ====================


class ConceptObject(BaseModel):
    """Single concept object extracted from paper."""

    concept_id: str = Field(..., description="Unique concept ID")
    concept_name: str = Field(..., description="Human-readable name")
    origin_domain: str = Field(..., description="Original domain of concept")
    concept_summary: str = Field(..., description="Brief summary")
    core_problem_it_solves: str = Field(..., description="Core problem addressed")
    system_abstraction: dict[str, Any] = Field(
        default_factory=dict, description="System abstraction details"
    )
    invariant_structures: list[dict[str, str]] = Field(
        default_factory=list, description="Identified invariant structures"
    )
    assumptions: list[str] = Field(default_factory=list, description="Key assumptions")
    regime_behavior: dict[str, Any] = Field(
        default_factory=dict, description="Behavior across regimes"
    )
    failure_modes: list[dict[str, Any]] = Field(
        default_factory=list, description="Potential failure modes"
    )
    cross_domain_analogies: list[dict[str, str]] = Field(
        default_factory=list, description="Cross-domain analogies"
    )
    research_hooks: list[dict[str, Any]] = Field(
        default_factory=list, description="Falsifiable research questions"
    )
    evidence_quality: dict[str, Any] = Field(
        default_factory=dict, description="Quality assessment of evidence"
    )


class ConceptsGenerated(BaseMessage):
    """Generated concept objects.

    Published by: Concept Generator Agent
    Consumed by: Experiment Exploder Agent
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    concept_objects: list[ConceptObject] = Field(
        default_factory=list, description="Extracted concept objects"
    )
    concepts_json_path: str = Field(..., description="Path to stored concepts.json")
    artifact_refs: list[str] = Field(default_factory=list, description="Paths to all artifacts")
    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata about generation")


class PlanGenerated(BaseMessage):
    """Experiment plan generated from concept objects.

    Published by: Experiment Exploder Agent
    Consumed by: Code Executor
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    plan_json_path: str = Field(..., description="Path to generated plan JSON")
    batch_id: str | None = Field(None, description="Optional batch identifier")
    experiment_count: int = Field(default=0, description="Total experiments generated")


# ==================== Code Execution Messages ====================


class CodeExecutionRequest(BaseMessage):
    """Request to execute an experiment via LLM-generated code.

    Published by: Experiment Exploder
    Consumed by: Code Executor
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    experiment_id: str = Field(..., description="Experiment ID from plan")
    experiment_name: str = Field(..., description="Human-readable experiment name")
    experiment_goal: str = Field(..., description="What the experiment should test")
    hypothesis_id: str = Field(..., description="Hypothesis being tested")
    experiment_spec: dict[str, Any] = Field(
        default_factory=dict, description="Full experiment specification from plan"
    )
    plan_json_path: str = Field(..., description="Path to the experiment plan JSON")
    max_fix_iterations: int = Field(
        default=5, description="Maximum LLM fix iterations before escalation"
    )


class CodeExecutionResult(BaseMessage):
    """Result of a code execution attempt.

    Published by: Code Executor
    Consumed by: Experiment Evaluator
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    experiment_id: str = Field(..., description="Experiment ID")
    hypothesis_id: str = Field(..., description="Hypothesis being tested")
    status: Literal["success", "failed", "escalated"] = Field(..., description="Execution status")
    code_path: str | None = Field(None, description="Path to generated code file")
    stdout: str | None = Field(None, description="Captured stdout")
    stderr: str | None = Field(None, description="Captured stderr")
    exit_code: int | None = Field(None, description="Process exit code")
    result_data: dict[str, Any] | None = Field(
        None, description="Parsed execution results (metrics, outputs)"
    )
    fix_iterations: int = Field(default=0, description="Number of LLM fix iterations attempted")
    fix_history: list[dict[str, str]] = Field(
        default_factory=list, description="History of fix attempts (code_summary + error)"
    )
    artifact_refs: list[str] = Field(default_factory=list, description="Paths to artifacts")


# ==================== Experiment Evaluation Messages ====================


class ExperimentEvaluationRequest(BaseMessage):
    """Request to evaluate experiment results.

    Published by: Code Executor
    Consumed by: Experiment Evaluator
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    experiment_id: str = Field(..., description="Experiment ID")
    hypothesis_id: str = Field(..., description="Hypothesis being tested")
    execution_status: Literal["success", "failed", "escalated"] = Field(
        ..., description="Execution status from code executor"
    )
    execution_result: dict[str, Any] | None = Field(None, description="Result data from execution")
    stdout: str | None = Field(None, description="Execution stdout")
    stderr: str | None = Field(None, description="Execution stderr")


class ExperimentEvaluationResult(BaseMessage):
    """Evaluation decision for an experiment.

    Published by: Experiment Evaluator
    """

    paper_id: str = Field(..., description="ArXiv paper ID")
    experiment_id: str = Field(..., description="Experiment ID")
    hypothesis_id: str = Field(..., description="Hypothesis being tested")
    recommendation: Literal["PROMOTE", "KILL", "INVESTIGATE", "RETRY"] = Field(
        ..., description="What to do with this experiment"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the recommendation")
    reasoning: str = Field(..., description="Why this recommendation was made")
    key_findings: list[str] = Field(
        default_factory=list, description="Key findings from the experiment"
    )
    next_steps: list[str] = Field(default_factory=list, description="Recommended next actions")
    artifact_refs: list[str] = Field(default_factory=list, description="Paths to artifacts")


# ==================== Notification Messages ====================


class NotificationRequest(BaseMessage):
    """Request to send notification.

    Published by: Various agents on completion/failure
    Consumed by: Notifier worker
    """

    experiment_id: str | None = Field(None, description="Experiment ID if applicable")
    paper_id: str | None = Field(None, description="Paper ID if applicable")
    status: Literal["SUCCESS", "FAILED", "NEEDS_HUMAN", "INFO"] = Field(
        ..., description="Status to report"
    )
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Main message content")
    artifact_refs: list[str] = Field(default_factory=list, description="Links to artifacts")
    recommendation: str | None = Field(None, description="PROMOTE/KILL/INVESTIGATE/NONE")
