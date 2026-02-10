"""In-process integration tests across worker stages with dummy data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.concept_generator.worker import ConceptGeneratorWorker
from src.workers.experiment_exploder.worker import ExperimentExploderWorker
from src.workers.paper_triage.worker import PaperTriageWorker
from src.workers.pdf_parser.worker import PDFParserWorker
from src.workers.shared.message_schemas import (
    ConceptGenerationRequest,
    ConceptsGenerated,
    FullTextRequest,
    PaperTriageRequest,
)
from tests.helpers.fakes import (
    DummyConsumer,
    DummyLLMClient,
    DummyPublisher,
    FakePDFProcessor,
    FakeParsedContent,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_triage_to_experiment_plan_flow(tmp_path: Path) -> None:
    # Stage 1: triage
    triage_worker = PaperTriageWorker(
        llm_client=DummyLLMClient(
            json.dumps(
                {
                    "decision": "REQUEST_FULL_TEXT",
                    "confidence_0_to_1": 0.95,
                    "primary_reasoning": {},
                    "cross_domain_opportunities": [],
                    "notes_for_concept_stage": [],
                }
            )
        ),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
    )
    triage_request = PaperTriageRequest(
        paper_id="p1",
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        categories=["cs.LG"],
        arxiv_url="https://arxiv.org/abs/p1",
        pdf_url="https://arxiv.org/pdf/p1.pdf",
    )
    await triage_worker.process(triage_request)
    fulltext_payload = next(
        p["message"]
        for p in triage_worker.publisher.published
        if p["routing_key"] == "paper.fulltext.request"  # type: ignore[attr-defined]
    )

    # Stage 2: pdf parse
    parser_worker = PDFParserWorker(
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
        pdf_processor=FakePDFProcessor(
            FakeParsedContent(
                text_content="Introduction\nResult",
                metadata={"title": "Paper"},
                tables=[],
                equations=[],
                figure_captions=[],
            )
        ),  # type: ignore[arg-type]
    )
    await parser_worker.process(FullTextRequest.model_validate(fulltext_payload))
    concept_req_payload = next(
        p["message"]
        for p in parser_worker.publisher.published
        if p["routing_key"] == "paper.concepts.request"  # type: ignore[attr-defined]
    )

    # Stage 3: concept generation
    concept_worker = ConceptGeneratorWorker(
        llm_client=DummyLLMClient(
            json.dumps(
                {
                    "concept_objects": [
                        {
                            "concept_id": "c1",
                            "concept_name": "Regime",
                            "origin_domain": "control",
                            "concept_summary": "summary",
                            "core_problem_it_solves": "problem",
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
        ),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
    )
    await concept_worker.process(ConceptGenerationRequest.model_validate(concept_req_payload))
    concepts_payload = concept_worker.publisher.published[0]["message"]  # type: ignore[attr-defined]

    # Stage 4: experiment plan generation
    exploder_worker = ExperimentExploderWorker(
        llm_client=DummyLLMClient(
            json.dumps(
                {
                    "batch_id": "b1",
                    "experiment_packages": [{"id": "e1"}],
                    "meta": {"produced_total_experiments": 1},
                }
            )
        ),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
    )
    await exploder_worker.process(ConceptsGenerated.model_validate(concepts_payload))

    routing_keys = [x["routing_key"] for x in exploder_worker.publisher.published]  # type: ignore[attr-defined]
    assert routing_keys == ["notify.send", "plan.generated"]
