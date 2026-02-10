"""Unit tests for paper triage worker."""

from __future__ import annotations

import json

import pytest

from src.workers.paper_triage.worker import PaperTriageWorker
from src.workers.shared.message_schemas import PaperTriageRequest
from tests.helpers.fakes import DummyConsumer, DummyLLMClient, DummyPublisher


def _build_request() -> PaperTriageRequest:
    return PaperTriageRequest(
        work_id="w1",
        paper_id="p1",
        title="T",
        authors=["A"],
        abstract="Abstract",
        categories=["cs.LG"],
        arxiv_url="https://arxiv.org/abs/p1",
        pdf_url="https://arxiv.org/pdf/p1.pdf",
    )


@pytest.mark.asyncio
async def test_process_publishes_decision_and_fulltext_request_for_positive_triage() -> None:
    llm_payload = json.dumps(
        {
            "decision": "REQUEST_FULL_TEXT",
            "confidence_0_to_1": 0.9,
            "primary_reasoning": {"system_modeled": "relevant"},
            "cross_domain_opportunities": [],
            "notes_for_concept_stage": ["note"],
        }
    )
    worker = PaperTriageWorker(
        llm_client=DummyLLMClient(llm_payload),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
    )

    await worker.process(_build_request())
    published = worker.publisher.published  # type: ignore[attr-defined]
    assert len(published) == 2
    assert published[0]["routing_key"] == "paper.triage.decision"
    assert published[1]["routing_key"] == "paper.fulltext.request"


@pytest.mark.asyncio
async def test_process_only_publishes_decision_for_rejected_paper() -> None:
    llm_payload = json.dumps(
        {
            "decision": "REJECT_PAPER",
            "confidence_0_to_1": 0.8,
            "primary_reasoning": {},
        }
    )
    worker = PaperTriageWorker(
        llm_client=DummyLLMClient(llm_payload),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
    )

    await worker.process(_build_request())
    published = worker.publisher.published  # type: ignore[attr-defined]
    assert len(published) == 1
    assert published[0]["routing_key"] == "paper.triage.decision"
