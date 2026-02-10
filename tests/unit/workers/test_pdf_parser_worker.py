"""Unit tests for PDF parser worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.pdf_parser.worker import PDFParserWorker
from src.workers.shared.message_schemas import FullTextRequest
from tests.helpers.fakes import DummyConsumer, DummyPublisher, FakePDFProcessor, FakeParsedContent


@pytest.mark.asyncio
async def test_process_stores_artifacts_and_publishes_followup_messages(tmp_path: Path) -> None:
    parsed = FakeParsedContent(
        text_content="Introduction\nBody",
        metadata={"title": "Parsed Title"},
        tables=[{"a": 1}],
        equations=["x=y"],
        figure_captions=[],
    )
    worker = PDFParserWorker(
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
        pdf_processor=FakePDFProcessor(parsed),  # type: ignore[arg-type]
    )

    msg = FullTextRequest(paper_id="p1", pdf_url="https://arxiv.org/pdf/p1.pdf")
    await worker.process(msg)

    assert (tmp_path / "p1" / "parsed" / "full_text.txt").exists()
    assert (tmp_path / "p1" / "parsed" / "tables.json").exists()
    assert (tmp_path / "p1" / "parsed" / "equations.txt").exists()

    published = worker.publisher.published  # type: ignore[attr-defined]
    assert [p["routing_key"] for p in published] == ["paper.parsed", "paper.concepts.request"]
