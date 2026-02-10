"""Unit tests for ArXiv config and schema models."""

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import PaperMetadata, PaperSource


def test_arxiv_config_defaults_are_sane() -> None:
    cfg = ArxivFetcherConfig()
    assert cfg.max_results_per_category > 0
    assert cfg.output_queue == "paper.triage.request"
    assert len(cfg.categories) > 0


def test_paper_metadata_hash_and_equality_uses_paper_id() -> None:
    a = PaperMetadata(paper_id="1234.1", title="A")
    b = PaperMetadata(paper_id="1234.1", title="B")
    c = PaperMetadata(paper_id="9999.9", title="C")
    assert a == b
    assert a != c
    assert len({a, b, c}) == 2


def test_paper_source_defaults_to_query() -> None:
    msg = PaperMetadata(paper_id="x", title="T")
    assert msg.source == PaperSource.QUERY
