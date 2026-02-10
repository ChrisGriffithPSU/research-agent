"""E2E in-process test for paper ingestion worker chain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.concept_generator.worker import ConceptGeneratorWorker
from src.workers.paper_triage.worker import PaperTriageWorker
from src.workers.pdf_parser.worker import PDFParserWorker
from src.workers.shared.message_schemas import (
    ConceptGenerationRequest,
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


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_end_to_end_paper_to_concepts_flow(tmp_path: Path) -> None:
    triage = PaperTriageWorker(
        llm_client=DummyLLMClient(
            json.dumps(
                {
                    "decision": "REQUEST_FULL_TEXT",
                    "confidence_0_to_1": 0.9,
                    "primary_reasoning": {},
                }
            )
        ),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
    )
    parser = PDFParserWorker(
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path / "artifacts")),
        pdf_processor=FakePDFProcessor(
            FakeParsedContent(
                text_content="Introduction\nResult",
                metadata={"title": "P"},
                tables=[],
                equations=[],
                figure_captions=[],
            )
        ),  # type: ignore[arg-type]
    )
    concept = ConceptGeneratorWorker(
        llm_client=DummyLLMClient(
            json.dumps(
                {
                    "concept_objects": [
                        {
                            "concept_id": "c1",
                            "concept_name": "signal",
                            "origin_domain": "math",
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
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path / "artifacts")),
    )

    req = PaperTriageRequest(
        paper_id="p1",
        title="Paper",
        abstract="A",
        arxiv_url="u",
        pdf_url="p",
    )
    await triage.process(req)
    fulltext = FullTextRequest.model_validate(
        next(
            x["message"]
            for x in triage.publisher.published
            if x["routing_key"] == "paper.fulltext.request"
        )  # type: ignore[attr-defined]
    )
    await parser.process(fulltext)
    concept_request = ConceptGenerationRequest.model_validate(
        next(
            x["message"]
            for x in parser.publisher.published
            if x["routing_key"] == "paper.concepts.request"
        )  # type: ignore[attr-defined]
    )
    await concept.process(concept_request)

    assert any(x["routing_key"] == "concepts.generated" for x in concept.publisher.published)  # type: ignore[attr-defined]
