"""ArXiv fetcher worker.

Fetches papers from hardcoded categories and publishes to triage queue.
No LLM-based query expansion - simple category-based fetching only.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Set

import httpx

from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
from src.services.fetchers.arxiv.schemas.paper import PaperMetadata
from src.workers.arxiv_fetcher.config import ArxivFetcherConfig, HARDCODED_CATEGORIES
from src.workers.shared.message_schemas import PaperTriageRequest
from src.shared.db.config import get_session_factory
from src.shared.messaging.connection import get_connection
from src.shared.messaging.publisher import MessagePublisher
from src.shared.repositories.paper_repository import PaperRepository


logger = logging.getLogger(__name__)


@dataclass
class FetcherDependencies:
    """Immutable dependencies for ArXiv fetcher.

    Separates configuration and external services from mutable state
    during fetching operations.
    """

    api_client: ArxivAPIClient
    publisher: MessagePublisher
    paper_repository: PaperRepository
    config: ArxivFetcherConfig


@dataclass
class FetcherState:
    """Mutable state during fetch operations."""

    processed_count: int = 0
    published_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    processed_ids: Optional[Set[str]] = None

    def __post_init__(self):
        if self.processed_ids is None:
            self.processed_ids = set()


class ArxivFetcherWorker:
    """Worker that fetches ArXiv papers and publishes to triage queue.

    Fetches from hardcoded categories only - no LLM-based query expansion.
    Implements duplicate detection to avoid processing same paper twice.

    Example:
        deps = await ArxivFetcherWorker.create_dependencies()
        worker = ArxivFetcherWorker(deps)
        await worker.run()
    """

    def __init__(self, dependencies: FetcherDependencies):
        """Initialize fetcher worker.

        Args:
            dependencies: Immutable dependencies (config, clients, etc.)
        """
        self.deps = dependencies
        self.state = FetcherState()

    @staticmethod
    async def create_dependencies(
        config: Optional[ArxivFetcherConfig] = None,
    ) -> FetcherDependencies:
        """Create default dependencies from environment.

        Args:
            config: Optional configuration (creates default if not provided)

        Returns:
            Configured dependencies
        """
        config = config or ArxivFetcherConfig()

        # Create HTTP client
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

        # Create API client
        api_client = ArxivAPIClient(
            http_client=http_client,
            config=config,
        )

        # Create message publisher
        connection = await get_connection()
        await connection.connect()
        publisher = MessagePublisher(connection)

        # Create paper repository for duplicate detection
        session_factory = get_session_factory()
        session = session_factory()
        paper_repository = PaperRepository(session)

        return FetcherDependencies(
            api_client=api_client,
            publisher=publisher,
            paper_repository=paper_repository,
            config=config,
        )

    async def run(self) -> None:
        """Run fetcher - fetch papers from all categories and publish.

        Fetches papers from each hardcoded category and publishes
        triage requests for new papers.
        """
        logger.info(f"Starting ArXiv fetch for {len(self.deps.config.categories)} categories")

        try:
            # Fetch papers from all categories
            papers = await self._fetch_all_categories()

            # Filter duplicates and publish new papers
            await self._process_papers(papers)

            logger.info(
                f"Fetch complete: {self.state.processed_count} processed, "
                f"{self.state.published_count} published, "
                f"{self.state.duplicate_count} duplicates, "
                f"{self.state.error_count} errors"
            )

        except Exception as e:
            logger.exception(f"Fetcher failed: {e}")
            raise
        finally:
            await self.deps.api_client.close()
            if hasattr(self.deps.paper_repository, "session"):
                await self.deps.paper_repository.session.close()

    async def _fetch_all_categories(self) -> List[PaperMetadata]:
        """Fetch papers from all configured categories.

        Uses semaphore to limit concurrent category fetches.

        Returns:
            List of all fetched papers
        """
        all_papers: List[PaperMetadata] = []
        semaphore = asyncio.Semaphore(self.deps.config.max_concurrent_categories)

        async def fetch_with_limit(category: str) -> List[PaperMetadata]:
            async with semaphore:
                return await self._fetch_category(category)

        # Fetch all categories concurrently with limit
        tasks = [fetch_with_limit(category) for category in self.deps.config.categories]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for category, result in zip(self.deps.config.categories, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch category {category}: {result}")
                self.state.error_count += 1
            else:
                all_papers.extend(result)

        return all_papers

    async def _fetch_category(self, category: str) -> List[PaperMetadata]:
        """Fetch papers from a single category.

        Args:
            category: ArXiv category code

        Returns:
            List of papers from this category
        """
        logger.debug(f"Fetching category: {category}")

        try:
            papers = await self.deps.api_client.fetch_by_categories(
                categories=[category],
                max_per_category=self.deps.config.max_results_per_category,
                days_back=self.deps.config.days_back,
            )

            logger.info(f"Fetched {len(papers)} papers from {category}")
            return papers

        except Exception as e:
            logger.error(f"Error fetching category {category}: {e}")
            raise

    async def _process_papers(self, papers: List[PaperMetadata]) -> None:
        """Process fetched papers - filter duplicates and publish.

        Args:
            papers: List of fetched papers
        """
        for paper in papers:
            self.state.processed_count += 1

            # Skip if already processed in this run
            if paper.paper_id in self.state.processed_ids:
                logger.debug(f"Skipping duplicate in batch: {paper.paper_id}")
                self.state.duplicate_count += 1
                continue

            self.state.processed_ids.add(paper.paper_id)

            # Check database for existing paper
            try:
                exists = await self.deps.paper_repository.exists(paper.paper_id)
                if exists:
                    logger.debug(f"Paper already exists: {paper.paper_id}")
                    self.state.duplicate_count += 1
                    continue
            except Exception as e:
                logger.warning(f"Failed to check duplicate: {e}")
                # Continue processing even if duplicate check fails

            # Publish triage request
            try:
                await self._publish_paper(paper)
                self.state.published_count += 1

                # Store in database to prevent future duplicates
                await self.deps.paper_repository.store_paper_id(paper.paper_id)

            except Exception as e:
                logger.error(f"Failed to publish paper {paper.paper_id}: {e}")
                self.state.error_count += 1

    async def _publish_paper(self, paper: PaperMetadata) -> None:
        """Publish paper triage request message.

        Args:
            paper: Paper metadata to publish
        """
        message = PaperTriageRequest(
            paper_id=paper.paper_id,
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            arxiv_url=paper.arxiv_url,
            pdf_url=paper.pdf_url,
            submitted_date=paper.submitted_date,
        )

        await self.deps.publisher.publish(
            message=message,
            routing_key=self.deps.config.output_queue,
        )

        logger.debug(f"Published triage request for: {paper.paper_id}")

    async def health_check(self) -> bool:
        """Check if fetcher is healthy.

        Returns:
            True if API is accessible
        """
        return await self.deps.api_client.health_check()

    def get_stats(self) -> dict:
        """Get fetcher statistics.

        Returns:
            Dict with processing statistics
        """
        return {
            "processed": self.state.processed_count,
            "published": self.state.published_count,
            "duplicates": self.state.duplicate_count,
            "errors": self.state.error_count,
            "api_stats": self.deps.api_client.get_stats(),
        }
