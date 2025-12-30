"""Main Kaggle fetcher orchestrator with dependency injection.

Coordinates all components for notebook discovery:
- API calls (Kaggle API)
- Caching (Redis)
- Parsing (Notebook parser)
- Publishing (RabbitMQ)

All dependencies are injected through the constructor.
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4
from enum import Enum

from src.shared.interfaces import (
    ICacheBackend,
    IMessagePublisher,
    IRateLimiter,
    ICircuitBreaker,
)
from src.services.fetchers.kaggle.config import KaggleFetcherConfig
from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookMetadata,
    ParsedNotebook,
    NotebookSource,
)
from src.services.fetchers.kaggle.interfaces import IKaggleAPI, INotebookParser
from src.services.fetchers.kaggle.services.api_client import KaggleAPIClient
from src.services.fetchers.kaggle.services.parser import NotebookParser
from src.services.fetchers.kaggle.services.cache_manager import CacheManager
from src.services.fetchers.kaggle.services.publisher import KaggleMessagePublisher
from src.services.fetchers.kaggle.exceptions import (
    KaggleFetcherError,
    CircuitOpenError,
)


logger = logging.getLogger(__name__)


class DiscoveryState(Enum):
    """State machine states for discovery workflow."""
    INITIAL = "initial"
    DISCOVERING = "discovering"
    DOWNLOADING = "downloading"
    PARSING = "parsing"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class KaggleFetcher:
    """Main Kaggle fetcher orchestrator with injectable dependencies.

    Coordinates all components for notebook discovery:
    - API calls (Kaggle API)
    - Caching (Redis)
    - Parsing (Notebook parser)
    - Publishing (RabbitMQ)

    All dependencies are injected through the constructor.
    No internal creation of external services.

    Example:
        # Production use with real dependencies
        fetcher = KaggleFetcher(
            config=config,
            cache=cache_backend,
            api=api_client,
            parser=parser,
            publisher=publisher,
        )
        await fetcher.initialize()

        # Testing use with mocks
        from src.shared.testing.mocks import (
            InMemoryCacheBackend,
            MockMessagePublisher,
        )
        from src.services.fetchers.kaggle.services.api_client import KaggleAPIClient
        from src.services.fetchers.kaggle.services.parser import NotebookParser

        fetcher = KaggleFetcher(
            config=KaggleFetcherConfig(),
            cache=InMemoryCacheBackend(),
            api=KaggleAPIClient(),  # Uses mocks internally
            parser=NotebookParser(),
            publisher=KaggleMessagePublisher(
                message_publisher=MockMessagePublisher()
            ),
        )

        # Use fetcher
        results = await fetcher.run_discovery(
            strategies=["competition", "tag", "query"],
        )

    Attributes:
        config: Kaggle fetcher configuration
        api: Kaggle API client (IKaggleAPI)
        parser: Notebook parser (INotebookParser)
        cache: Cache manager (CacheManager)
        publisher: Message publisher (KaggleMessagePublisher)
        _initialized: Whether the service has been initialized
    """

    def __init__(
        self,
        config: Optional[KaggleFetcherConfig] = None,
        cache: Optional[ICacheBackend] = None,
        api: Optional[IKaggleAPI] = None,
        parser: Optional[INotebookParser] = None,
        publisher: Optional[KaggleMessagePublisher] = None,
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
    ):
        """Initialize Kaggle fetcher.

        Args:
            config: Kaggle fetcher configuration
            cache: Cache backend (ICacheBackend)
            api: Kaggle API client (IKaggleAPI)
            parser: Notebook parser (INotebookParser)
            publisher: Message publisher (KaggleMessagePublisher)
            rate_limiter: Rate limiter (IRateLimiter)
            circuit_breaker: Circuit breaker (ICircuitBreaker)
        """
        self.config = config or KaggleFetcherConfig()
        self._api = api
        self._parser = parser
        self._publisher = publisher
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker

        # Initialize cache manager
        self._cache_manager = None
        if cache is not None:
            self._cache_manager = CacheManager(
                cache_backend=cache,
                config=self.config,
            )

        # Internal state
        self._initialized = False
        self._state = DiscoveryState.INITIAL
        self._correlation_id = str(uuid4())

        # Statistics
        self._notebooks_discovered = 0
        self._notebooks_downloaded = 0
        self._notebooks_published = 0
        self._errors: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        """Initialize all components.

        Validates that required dependencies are set.
        No auto-creation of dependencies - they must be injected.

        Raises:
            ValueError: If required dependencies are missing
        """
        if self._initialized:
            return

        # Validate required dependencies
        if self._api is None:
            raise ValueError(
                "api is required. "
                "Inject an IKaggleAPI implementation (e.g., KaggleAPIClient)."
            )

        # Initialize API client
        await self._api.initialize()

        # Initialize parser
        if self._parser is None:
            self._parser = NotebookParser(config=self.config)

        # Initialize cache manager
        if self._cache_manager is not None:
            await self._cache_manager.initialize()

        # Initialize publisher
        if self._publisher is not None:
            await self._publisher.initialize()

        self._initialized = True
        logger.info("KaggleFetcher initialized successfully")

    async def close(self) -> None:
        """Clean up all resources."""
        if self._api:
            await self._api.close()

        if self._cache_manager:
            await self._cache_manager.close()

        if self._publisher:
            await self._publisher.close()

        self._initialized = False
        self._state = DiscoveryState.INITIAL
        logger.info("KaggleFetcher closed")

    async def run_discovery(
        self,
        strategies: List[str] = ["competition", "tag", "query"],
        queries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run notebook discovery using specified strategies.

        Args:
            strategies: Discovery strategies to use (competition, tag, query)
            queries: Optional list of queries for query-based search

        Returns:
            Dict with discovery results and statistics
        """
        if not self._initialized:
            await self.initialize()

        run_correlation_id = str(uuid4())
        start_time = datetime.utcnow()

        logger.info(
            f"Starting discovery run {run_correlation_id[:8]}... "
            f"with strategies: {strategies}"
        )

        self._state = DiscoveryState.DISCOVERING
        all_metadata: List[NotebookMetadata] = []

        try:
            # Strategy 1: Competition-based discovery
            if "competition" in strategies:
                competition_notebooks = await self._discover_by_competition()
                all_metadata.extend(competition_notebooks)

            # Strategy 2: Tag-based discovery
            if "tag" in strategies:
                tag_notebooks = await self._discover_by_tags()
                all_metadata.extend(tag_notebooks)

            # Strategy 3: Query-based discovery
            if "query" in strategies and queries:
                query_notebooks = await self._discover_by_queries(queries)
                all_metadata.extend(query_notebooks)

            # Deduplicate notebooks
            unique_metadata = self._deduplicate_notebooks(all_metadata)
            self._notebooks_discovered = len(unique_metadata)

            # Download and parse notebooks
            self._state = DiscoveryState.DOWNLOADING
            parsed_notebooks = await self._download_and_parse(unique_metadata)

            # Publish notebooks
            self._state = DiscoveryState.PUBLISHING
            published = await self._publish_notebooks(parsed_notebooks)
            self._notebooks_published = published

            self._state = DiscoveryState.COMPLETED

        except CircuitOpenError as e:
            self._state = DiscoveryState.FAILED
            self._errors.append({
                "error": str(e),
                "type": "circuit_breaker",
                "timestamp": datetime.utcnow().isoformat(),
            })
            logger.error(f"Circuit breaker open: {e}")

        except Exception as e:
            self._state = DiscoveryState.FAILED
            self._errors.append({
                "error": str(e),
                "type": "unknown",
                "timestamp": datetime.utcnow().isoformat(),
            })
            logger.error(f"Discovery failed: {e}")

        # Build results
        duration = (datetime.utcnow() - start_time).total_seconds()
        results = {
            "correlation_id": run_correlation_id,
            "notebooks_discovered": self._notebooks_discovered,
            "notebooks_downloaded": self._notebooks_downloaded,
            "notebooks_published": self._notebooks_published,
            "duration_seconds": duration,
            "state": self._state.value,
            "errors": self._errors[-10:],  # Last 10 errors
        }

        logger.info(
            f"Discovery run {run_correlation_id[:8]}... completed in {duration:.2f}s: "
            f"{self._notebooks_discovered} found, {self._notebooks_published} published"
        )

        return results

    async def _discover_by_competition(self) -> List[NotebookMetadata]:
        """Discover notebooks from competitions.

        Returns:
            List of notebook metadata from competitions
        """
        notebooks = []

        # For now, use hardcoded list of relevant competitions
        # In a full implementation, this could be LLM-driven
        competitions = [
            "titanic",
            "house-prices-advanced-regression-techniques",
            "digit-recognizer",
            "commonlitreadabilityprize",
            "feedback-prize-effectiveness",
        ]

        for competition in competitions:
            try:
                competition_notebooks = await self._api.get_competition_notebooks(
                    competition_slug=competition,
                    max_notebooks=self.config.max_notebooks_per_competition,
                )
                notebooks.extend(competition_notebooks)
                logger.debug(
                    f"Found {len(competition_notebooks)} notebooks "
                    f"from competition: {competition}"
                )

            except Exception as e:
                logger.warning(f"Failed to get notebooks for {competition}: {e}")
                self._errors.append({
                    "competition": competition,
                    "error": str(e),
                    "type": "competition_discovery",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

        return notebooks

    async def _discover_by_tags(self) -> List[NotebookMetadata]:
        """Discover notebooks by tags.

        Returns:
            List of notebook metadata from tag searches
        """
        notebooks = []

        for tag in self.config.tags:
            try:
                tag_notebooks = await self._api.search_notebooks(
                    query=f"tag:{tag}",
                    max_results=self.config.max_notebooks_per_tag,
                    sort_by=self.config.sort_by,
                )
                notebooks.extend(tag_notebooks)
                logger.debug(
                    f"Found {len(tag_notebooks)} notebooks for tag: {tag}"
                )

            except Exception as e:
                logger.warning(f"Failed to search tag {tag}: {e}")
                self._errors.append({
                    "tag": tag,
                    "error": str(e),
                    "type": "tag_discovery",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

        return notebooks

    async def _discover_by_queries(
        self,
        queries: List[str],
    ) -> List[NotebookMetadata]:
        """Discover notebooks by custom queries.

        Args:
            queries: List of search queries

        Returns:
            List of notebook metadata from query searches
        """
        notebooks = []

        for query in queries:
            try:
                query_notebooks = await self._api.search_notebooks(
                    query=query,
                    max_results=self.config.max_notebooks_per_query,
                    sort_by=self.config.sort_by,
                )
                notebooks.extend(query_notebooks)
                logger.debug(
                    f"Found {len(query_notebooks)} notebooks for query: {query}"
                )

            except Exception as e:
                logger.warning(f"Failed to search query {query}: {e}")
                self._errors.append({
                    "query": query,
                    "error": str(e),
                    "type": "query_discovery",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

        return notebooks

    async def _download_and_parse(
        self,
        metadata_list: List[NotebookMetadata],
    ) -> List[ParsedNotebook]:
        """Download and parse notebooks from metadata.

        Args:
            metadata_list: List of notebook metadata

        Returns:
            List of parsed notebooks
        """
        parsed_notebooks = []

        for metadata in metadata_list:
            try:
                # Check cache first
                if self._cache_manager:
                    cached = await self._cache_manager.get_parsed_notebook(
                        metadata.notebook_path
                    )
                    if cached:
                        parsed_notebooks.append(cached)
                        self._notebooks_downloaded += 1
                        continue

                # Download notebook content
                content = await self._api.download_notebook(metadata.notebook_path)

                # Parse notebook
                parsed = await self._parser.parse(
                    content.model_dump(),
                    metadata.notebook_path,
                )

                # Enrich with metadata
                parsed.title = metadata.title
                parsed.authors = metadata.authors
                parsed.competition_slug = metadata.competition_slug
                parsed.tags = metadata.tags
                parsed.votes = metadata.votes

                # Cache parsed notebook
                if self._cache_manager:
                    await self._cache_manager.set_parsed_notebook(
                        metadata.notebook_path,
                        parsed,
                    )

                parsed_notebooks.append(parsed)
                self._notebooks_downloaded += 1

                logger.debug(f"Downloaded and parsed: {metadata.notebook_id}")

            except Exception as e:
                logger.warning(f"Failed to download/parse {metadata.notebook_id}: {e}")
                self._errors.append({
                    "notebook_id": metadata.notebook_id,
                    "error": str(e),
                    "type": "download_parse",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

        return parsed_notebooks

    async def _publish_notebooks(
        self,
        notebooks: List[ParsedNotebook],
    ) -> int:
        """Publish parsed notebooks to message queue.

        Args:
            notebooks: List of parsed notebooks

        Returns:
            Number of notebooks published
        """
        if not notebooks or self._publisher is None:
            return 0

        return await self._publisher.publish_batch_discovered(
            notebooks=notebooks,
            batch_size=self.config.batch_size,
        )

    def _deduplicate_notebooks(
        self,
        notebooks: List[NotebookMetadata],
    ) -> List[NotebookMetadata]:
        """Remove duplicate notebooks by ID.

        Args:
            notebooks: List of notebook metadata

        Returns:
            List of unique notebooks
        """
        seen = set()
        unique = []

        for notebook in notebooks:
            if notebook.notebook_id and notebook.notebook_id not in seen:
                seen.add(notebook.notebook_id)
                unique.append(notebook)

        duplicates_removed = len(notebooks) - len(unique)
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate notebooks")

        return unique

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all components.

        Returns:
            Dict mapping component name to health status
        """
        health = {}

        if self._api:
            health["api"] = await self._api.health_check()

        if self._cache_manager:
            health["cache"] = await self._cache_manager.health_check()

        if self._publisher:
            health["publisher"] = await self._publisher.health_check()

        return health

    def get_stats(self) -> Dict[str, Any]:
        """Get fetcher statistics."""
        stats = {
            "notebooks_discovered": self._notebooks_discovered,
            "notebooks_downloaded": self._notebooks_downloaded,
            "notebooks_published": self._notebooks_published,
            "errors_count": len(self._errors),
            "state": self._state.value,
            "initialized": self._initialized,
        }

        # Add component stats
        if self._api:
            stats["api"] = self._api.get_stats()

        if self._cache_manager:
            stats["cache"] = self._cache_manager.get_stats()

        if self._publisher:
            stats["publisher"] = self._publisher.get_stats()

        return stats

    @property
    def is_initialized(self) -> bool:
        """Check if fetcher is initialized."""
        return self._initialized

    @property
    def state(self) -> DiscoveryState:
        """Get current state."""
        return self._state

    def __repr__(self) -> str:
        return (
            f"KaggleFetcher("
            f"initialized={self._initialized}, "
            f"state={self._state.value}, "
            f"discovered={self._notebooks_discovered}, "
            f"published={self._notebooks_published})"
        )


class KaggleFetcherFactory:
    """Factory for creating KaggleFetcher instances."""

    @staticmethod
    def create_full(
        config: Optional[KaggleFetcherConfig] = None,
        cache_backend: Optional[ICacheBackend] = None,
        message_publisher: Optional[IMessagePublisher] = None,
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
    ) -> KaggleFetcher:
        """Create KaggleFetcher with all dependencies.

        Args:
            config: Kaggle fetcher configuration
            cache_backend: Cache backend (ICacheBackend)
            message_publisher: Message publisher
            rate_limiter: Rate limiter (IRateLimiter)
            circuit_breaker: Circuit breaker (ICircuitBreaker)

        Returns:
            Configured KaggleFetcher instance
        """
        # Create API client
        api = KaggleAPIClient(
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            config=config,
        )

        # Create parser
        parser = NotebookParser(config=config)

        # Create cache manager
        cache_manager = None
        if cache_backend is not None:
            cache_manager = CacheManager(
                cache_backend=cache_backend,
                config=config,
            )

        # Create publisher
        publisher = KaggleMessagePublisher(
            message_publisher=message_publisher,
            config=config,
        )

        # Create fetcher
        return KaggleFetcher(
            config=config,
            cache=cache_backend,
            api=api,
            parser=parser,
            publisher=publisher,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
        )

    @staticmethod
    def create_for_testing() -> KaggleFetcher:
        """Create KaggleFetcher with all mocks for testing.

        Returns:
            KaggleFetcher with mock dependencies
        """
        from src.shared.testing.mocks import (
            InMemoryCacheBackend,
            MockMessagePublisher,
        )

        cache_backend = InMemoryCacheBackend()
        message_publisher = MockMessagePublisher()

        return KaggleFetcherFactory.create_full(
            config=KaggleFetcherConfig(),
            cache_backend=cache_backend,
            message_publisher=message_publisher,
        )


__all__ = [
    "KaggleFetcher",
    "KaggleFetcherFactory",
    "DiscoveryState",
]

