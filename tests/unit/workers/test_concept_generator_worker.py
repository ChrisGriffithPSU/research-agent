"""Unit tests for concept generator worker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.concept_generator.worker import ConceptGeneratorWorker
from src.workers.shared.message_schemas import ConceptGenerationRequest
from tests.helpers.fakes import DummyConsumer, DummyLLMClient, DummyPublisher


def _concept_payload() -> str:
    return json.dumps(
        {
            "concept_objects": [
                {
                    "concept_id": "c1",
                    "concept_name": "Regime Switch",
                    "origin_domain": "control",
                    "concept_summary": "state transitions",
                    "core_problem_it_solves": "nonstationarity",
                    "system_abstraction": {},
                    "invariant_structures": [],
                    "assumptions": [],
                    "regime_behavior": {},
                    "failure_modes": [],
                    "cross_domain_analogies": [],
                    "research_hooks": [],
                    "evidence_quality": {},
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_process_generates_concepts_and_publishes_result(tmp_path: Path) -> None:
    worker = ConceptGeneratorWorker(
        llm_client=DummyLLMClient(_concept_payload()),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
    )

    req = ConceptGenerationRequest(
        paper_id="p1",
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        full_text="Body",
        categories=["cs.LG"],
    )
    await worker.process(req)

    assert (tmp_path / "p1" / "concepts" / "concepts.json").exists()
    published = worker.publisher.published  # type: ignore[attr-defined]
    assert len(published) == 1
    assert published[0]["routing_key"] == "concepts.generated"
    assert published[0]["message"]["paper_id"] == "p1"


def test_prepare_llm_input_truncates_long_text() -> None:
    worker = ConceptGeneratorWorker(
        llm_client=DummyLLMClient(_concept_payload()),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
    )
    req = ConceptGenerationRequest(
        paper_id="p1",
        title="Paper",
        abstract="Abstract",
        full_text="x" * 20000,
    )
    payload = worker._prepare_llm_input(req)
    assert "[...truncated]" in payload
