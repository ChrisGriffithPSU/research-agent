"""Unit tests for worker message contracts."""

from __future__ import annotations

from src.workers.shared.message_schemas import (
    ConceptGenerationRequest,
    ConceptsGenerated,
    NotificationRequest,
    PaperTriageDecision,
    PaperTriageRequest,
    PlanGenerated,
)


def test_paper_triage_request_has_defaults_and_serialized_datetime() -> None:
    msg = PaperTriageRequest(
        paper_id="p1",
        title="title",
        abstract="abs",
        arxiv_url="https://arxiv.org/abs/p1",
        pdf_url="https://arxiv.org/pdf/p1.pdf",
    )
    payload = msg.model_dump(mode="json")
    assert payload["attempt"] == 0
    assert isinstance(payload["created_at"], str)


def test_concept_generation_request_accepts_optional_categories() -> None:
    msg = ConceptGenerationRequest(
        paper_id="p1",
        title="t",
        abstract="a",
        full_text="body",
        categories=["cs.LG"],
    )
    assert msg.categories == ["cs.LG"]


def test_notification_request_contract() -> None:
    msg = NotificationRequest(status="INFO", title="x", message="y")
    assert msg.experiment_id is None
    assert msg.recommendation is None


def test_plan_generated_contract() -> None:
    msg = PlanGenerated(paper_id="p1", plan_json_path="runs/p1/plan.json", experiment_count=3)
    assert msg.paper_id == "p1"
    assert msg.experiment_count == 3


def test_triage_decision_confidence_bounds() -> None:
    ok = PaperTriageDecision(paper_id="p", decision="REJECT_PAPER", confidence=0.0)
    assert ok.confidence == 0.0
    try:
        PaperTriageDecision(paper_id="p", decision="REQUEST_FULL_TEXT", confidence=1.2)
    except Exception as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("Expected validation error for confidence > 1")
