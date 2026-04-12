"""Unit tests for worker message contracts."""

from __future__ import annotations

from src.workers.shared.message_schemas import (
    ConceptsGenerated,
    NotificationRequest,
    PaperFullTextRequest,
    ParsedPaper,
    PlanGenerated,
    CodeExecutionRequest,
    CodeExecutionResult,
    ExperimentEvaluationRequest,
    ExperimentEvaluationResult,
)


def test_paper_fulltext_request_has_defaults_and_serialized_datetime() -> None:
    msg = PaperFullTextRequest(
        paper_id="p1",
        title="title",
        abstract="abs",
        arxiv_url="https://arxiv.org/abs/p1",
        pdf_url="https://arxiv.org/pdf/p1.pdf",
    )
    payload = msg.model_dump(mode="json")
    assert payload["attempt"] == 0
    assert isinstance(payload["created_at"], str)


def test_parsed_paper_has_defaults() -> None:
    msg = ParsedPaper(
        paper_id="p1",
        title="t",
        abstract="a",
        full_text="body",
    )
    assert msg.sections == []
    assert msg.categories == []


def test_notification_request_contract() -> None:
    msg = NotificationRequest(status="INFO", title="x", message="y")
    assert msg.experiment_id is None
    assert msg.recommendation is None


def test_plan_generated_contract() -> None:
    msg = PlanGenerated(paper_id="p1", plan_json_path="runs/p1/plan.json", experiment_count=3)
    assert msg.paper_id == "p1"
    assert msg.experiment_count == 3


def test_code_execution_request_defaults() -> None:
    msg = CodeExecutionRequest(
        paper_id="p1",
        experiment_id="e1",
        experiment_name="test experiment",
        experiment_goal="test goal",
        hypothesis_id="h1",
        plan_json_path="/path/to/plan.json",
    )
    assert msg.max_fix_iterations == 5
    assert msg.priority == 5


def test_code_execution_result_contract() -> None:
    msg = CodeExecutionResult(
        paper_id="p1",
        experiment_id="e1",
        hypothesis_id="h1",
        status="success",
        stdout="ok",
        exit_code=0,
    )
    assert msg.fix_iterations == 0
    assert msg.fix_history == []


def test_experiment_evaluation_request_contract() -> None:
    msg = ExperimentEvaluationRequest(
        paper_id="p1",
        experiment_id="e1",
        hypothesis_id="h1",
        execution_status="success",
    )
    assert msg.stdout is None


def test_experiment_evaluation_result_recommendation_values() -> None:
    for rec in ("PROMOTE", "KILL", "INVESTIGATE", "RETRY"):
        msg = ExperimentEvaluationResult(
            paper_id="p1",
            experiment_id="e1",
            hypothesis_id="h1",
            recommendation=rec,  # type: ignore[arg-type]
            confidence=0.8,
            reasoning="test",
        )
        assert msg.recommendation == rec
