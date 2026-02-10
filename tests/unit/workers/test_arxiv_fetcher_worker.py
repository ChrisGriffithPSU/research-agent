"""Unit tests for ArXiv fetcher worker core logic."""

from __future__ import annotations

import pytest

from src.services.fetchers.arxiv.schemas.paper import PaperMetadata
from src.workers.arxiv_fetcher.config import ArxivFetcherConfig
from src.workers.arxiv_fetcher.worker import ArxivFetcherWorker, FetcherDependencies


class _Api:
    def __init__(self, papers: list[PaperMetadata]) -> None:
        self._papers = papers

    async def fetch_by_categories(self, categories, max_per_category, days_back):
        return self._papers

    async def close(self) -> None:
        return None

    def get_stats(self):
        return {"request_count": 1}


class _Publisher:
    def __init__(self) -> None:
        self.published: list[tuple[object, str]] = []

    async def publish(self, message, routing_key):
        self.published.append((message, routing_key))


class _Repo:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.stored: list[str] = []

    async def exists(self, paper_id: str) -> bool:
        return paper_id in self.existing

    async def store_paper_id(self, paper_id: str) -> None:
        self.stored.append(paper_id)
        self.existing.add(paper_id)


def _paper(paper_id: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        abstract="A",
        arxiv_url=f"https://arxiv.org/abs/{paper_id}",
        pdf_url=f"https://arxiv.org/pdf/{paper_id}.pdf",
    )


@pytest.mark.asyncio
async def test_process_papers_deduplicates_batch_and_persists_new_ids() -> None:
    papers = [_paper("p1"), _paper("p1"), _paper("p2")]
    deps = FetcherDependencies(
        api_client=_Api(papers),
        publisher=_Publisher(),
        paper_repository=_Repo(existing={"p2"}),
        config=ArxivFetcherConfig(categories=["cs.LG"], max_results_per_category=5),
    )
    worker = ArxivFetcherWorker(deps)
    await worker._process_papers(papers)

    assert worker.state.processed_count == 3
    assert worker.state.duplicate_count >= 2
    assert len(deps.publisher.published) == 1
    assert deps.paper_repository.stored == ["p1"]
