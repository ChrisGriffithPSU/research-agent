"""Main arXiv fetcher orchestrator with dependency injection.

Coordinates all components for paper discovery:
- Query expansion (LLM)
- API calls (arXiv API)
- Caching (Redis)
- Publishing (RabbitMQ)

All dependencies are injected through the constructor.
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from src.shared.interfaces import (
    ICacheBackend,
    IMessagePublisher,
    ILLMRouter,
)
from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import PaperMetadata, PaperSource
from src.services.fetchers.arxiv.services.cache_manager import CacheManager
from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
from src.services.fetchers.arxiv.services.publisher import ArxivMessagePublisher
from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor


logger = logging.getLogger(__name__)


class ArxivFetcher:
    """Main arXiv fetcher orchestrator with injectable dependencies.
    
    Coordinates all components for paper discovery:
    - Query expansion (LLM)
    - API calls (arXiv API)
    - Caching (optional)
    - Publishing (optional)
    
    All dependencies are injected through the constructor.
    No internal creation of external services.
    
    Example:
        # Production use with real dependencies
        fetcher = ArxivFetcher(
            config=config,
            cache=cache_backend,
            query_processor=query_processor,
            api_client=api_client,
            publisher=publisher,
            pdf_processor=pdf_processor,
        )
        await fetcher.initialize()
        
        # Testing use with mocks
        from src.shared.testing.mocks import (
            InMemoryCacheBackend,
            MockLLMRouter,
            MockMessagePublisher,
        )
        
        fetcher = ArxivFetcher(
            config=ArxivFetcherConfig(),
            cache=InMemoryCacheBackend(),
            query_processor=QueryProcessor(llm_router=MockLLMRouter()),
            api_client=ArxivAPIClient(),  # Uses mocks internally
            publisher=ArxivMessagePublisher(
                message_publisher=MockMessagePublisher()
            ),
        )
        
        # Use fetcher
        results = await fetcher.run_discovery(
            queries=["transformer attention"],
            categories=["cs.LG"],
        )
    
    Attributes:
        config: ArXiv fetcher configuration
        cache: Cache backend (ICacheBackend)
        query_processor: Query processor
        api_client: arXiv API client
        publisher: Message publisher
        pdf_processor: PDF processor
        _initialized: Whether the service has been initialized
    """
    
    def __init__(
        self,
        config: Optional[ArxivFetcherConfig] = None,
        cache: Optional[ICacheBackend] = None,
        query_processor: Optional[QueryProcessor] = None,
        api_client: Optional[ArxivAPIClient] = None,
        publisher: Optional[ArxivMessagePublisher] = None,
        pdf_processor: Optional[PDFProcessor] = None,
    ):
        """Initialize arXiv fetcher.
        
        Args:
            config: ArXiv fetcher configuration
            cache: Cache backend (ICacheBackend)
            query_processor: Query processor
            api_client: arXiv API client
            publisher: Message publisher
            pdf_processor: PDF processor
        """
        self.config = config or ArxivFetcherConfig()
        self.cache = cache
        self.query_processor = query_processor
        self.api_client = api_client
        self.publisher = publisher
        self.pdf_processor = pdf_processor
        
        self._initialized = False
        self._correlation_id = str(uuid4())
        
        # Statistics
        self._papers_discovered = 0
        self._papers_published = 0
        self._queries_processed = 0
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
        if self.api_client is None:
            raise ValueError(
                "api_client is required. "
                "Inject an ArxivAPIClient instance."
            )
        
        # Initialize components that have initialization methods
        if self.cache is not None:
            cache_manager = CacheManager(
                cache_backend=self.cache,
                config=self.config,
            )
            await cache_manager.initialize()
            self._cache_manager = cache_manager
        else:
            self._cache_manager = None
        
        if self.query_processor is not None:
            await self.query_processor.initialize()
        
        await self.api_client.initialize()
        
        if self.publisher is not None:
            await self.publisher.initialize()
        
        if self.pdf_processor is not None:
            pass  # PDFProcessor doesn't have async init
        
        self._initialized = True
        logger.info("ArxivFetcher initialized successfully")
    
    async def run_discovery(
        self,
        queries: List[str],
        categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run paper discovery for queries and/or categories.
        
        Args:
            queries: List of search queries
            categories: Optional list of categories to also monitor
            
        Returns:
            Dict with discovery results and statistics
        """
        if not self._initialized:
            await self.initialize()
        
        run_correlation_id = str(uuid4())
        start_time = datetime.utcnow()
        
        logger.info(
            f"Starting discovery run {run_correlation_id[:8]}... "
            f"with {len(queries)} queries"
        )
        
        all_papers = []
        
        # Process queries
        if queries:
            papers_from_queries = await self._process_queries(queries)
            all_papers.extend(papers_from_queries)
        
        # Fetch from categories
        if categories:
            papers_from_categories = await self._fetch_categories(categories)
            all_papers.extend(papers_from_categories)
        
        # Deduplicate papers
        unique_papers = self._deduplicate_papers(all_papers)
        
        # Publish to queue
        if unique_papers and self.publisher is not None:
            published = await self.publisher.publish_discovered(
                papers=unique_papers,
                correlation_id=run_correlation_id,
            )
            self._papers_published = published
        else:
            self._papers_published = 0
        
        self._papers_discovered = len(unique_papers)
        
        # Build results
        duration = (datetime.utcnow() - start_time).total_seconds()
        results = {
            "correlation_id": run_correlation_id,
            "papers_discovered": len(unique_papers),
            "papers_published": self._papers_published,
            "queries_processed": self._queries_processed,
            "categories_fetched": len(categories) if categories else 0,
            "duration_seconds": duration,
            "errors": self._errors[-10:],  # Last 10 errors
        }
        
        logger.info(
            f"Discovery run {run_correlation_id[:8]}... completed in {duration:.2f}s: "
            f"{len(unique_papers)} papers found, {self._papers_published} published"
        )
        
        return results
    
    async def _process_queries(self, queries: List[str]) -> List[PaperMetadata]:
        """Process queries and fetch papers."""
        all_papers = []
        
        for query in queries:
            try:
                # Expand query using LLM (if query processor available)
                if self.query_processor is not None:
                    expansion = await self.query_processor.expand_query(query)
                    self._queries_processed += 1
                    expanded_queries = expansion.expanded_queries
                else:
                    # No query processor, use original query
                    expanded_queries = [query]
                    self._queries_processed += 1
                
                # Execute searches
                for expanded_query in expanded_queries:
                    papers = await self.api_client.search(
                        query=expanded_query,
                        max_results=self.config.default_results_per_query,
                        sort_by=ArxivAPIClient.SORT_RELEVANCE,
                    )
                    
                    # Mark source
                    for paper in papers:
                        paper.source = PaperSource.QUERY
                        paper.source_query = query
                    
                    all_papers.extend(papers)
                    logger.debug(
                        f"Found {len(papers)} papers for expanded query: "
                        f"{expanded_query[:50]}..."
                    )
                
            except Exception as e:
                logger.error(f"Failed to process query '{query}': {e}")
                self._errors.append({
                    "query": query,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue
        
        return all_papers
    
    async def _fetch_categories(
        self,
        categories: List[str],
    ) -> List[PaperMetadata]:
        """Fetch papers from categories."""
        try:
            papers = await self.api_client.fetch_by_categories(
                categories=categories,
                max_per_category=self.config.default_results_per_query,
            )
            
            logger.info(f"Fetched {len(papers)} papers from {len(categories)} categories")
            return papers
            
        except Exception as e:
            logger.error(f"Failed to fetch categories: {e}")
            self._errors.append({
                "categories": categories,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })
            return []
    
    def _deduplicate_papers(
        self,
        papers: List[PaperMetadata],
    ) -> List[PaperMetadata]:
        """Remove duplicate papers by ID."""
        seen = set()
        unique = []
        
        for paper in papers:
            if paper.paper_id and paper.paper_id not in seen:
                seen.add(paper.paper_id)
                unique.append(paper)
        
        duplicates_removed = len(papers) - len(unique)
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate papers")
        
        return unique
    
    async def handle_parse_request(
        self,
        paper_id: str,
        pdf_url: str,
        correlation_id: str,
        original_correlation_id: str,
        **kwargs,
    ) -> None:
        """Handle on-demand parse request."""
        if not self._initialized:
            await self.initialize()
        
        if self.pdf_processor is None or self.publisher is None:
            logger.warning("PDF processor or publisher not available, skipping parse request")
            return
        
        try:
            # Extract content from PDF
            content = await self.pdf_processor.extract(
                pdf_url=pdf_url,
                paper_id=paper_id,
            )
            
            # Get paper metadata
            papers = await self.api_client.fetch_by_ids([paper_id])
            if not papers:
                logger.error(f"Paper not found: {paper_id}")
                return
            
            paper = papers[0]
            
            # Publish extracted content
            await self.publisher.publish_extracted(
                paper=paper,
                content=content,
                discovery_correlation_id=original_correlation_id,
                parse_correlation_id=correlation_id,
            )
            
            logger.info(f"Processed parse request for {paper_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle parse request for {paper_id}: {e}")
            self._errors.append({
                "paper_id": paper_id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all components."""
        health = {}
        
        if self._cache_manager:
            health["cache"] = await self._cache_manager.health_check()
        
        if self.query_processor:
            health["query_processor"] = await self.query_processor.health_check()
        
        if self.api_client:
            health["api_client"] = await self.api_client.health_check()
        
        if self.publisher:
            health["publisher"] = await self.publisher.health_check()
        
        if self.pdf_processor:
            health["pdf_processor"] = await self.pdf_processor.health_check()
        
        return health
    
    async def close(self) -> None:
        """Clean up all resources."""
        if self._cache_manager:
            await self._cache_manager.close()
        
        if self.api_client:
            await self.api_client.close()
        
        if self.publisher:
            await self.publisher.close()
        
        self._initialized = False
        logger.info("ArxivFetcher closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fetcher statistics."""
        stats = {
            "papers_discovered": self._papers_discovered,
            "papers_published": self._papers_published,
            "queries_processed": self._queries_processed,
            "errors_count": len(self._errors),
            "initialized": self._initialized,
        }
        
        # Add component stats
        if self.api_client:
            stats["api_client"] = self.api_client.get_stats()
        
        if self.publisher:
            stats["publisher"] = self.publisher.get_stats()
        
        if self.pdf_processor:
            stats["pdf_processor"] = self.pdf_processor.get_stats()
        
        return stats
    
    @property
    def is_initialized(self) -> bool:
        """Check if fetcher is initialized."""
        return self._initialized
    
    def __repr__(self) -> str:
        return (
            f"ArxivFetcher("
            f"initialized={self._initialized}, "
            f"discovered={self._papers_discovered}, "
            f"published={self._papers_published})"
        )


class ArxivFetcherFactory:
    """Factory for creating ArxivFetcher instances."""
    
    @staticmethod
    def create_full(
        config: Optional[ArxivFetcherConfig] = None,
        cache_backend: Optional[ICacheBackend] = None,
        llm_router: Optional[ILLMRouter] = None,
        message_publisher: Optional[IMessagePublisher] = None,
    ) -> ArxivFetcher:
        """Create ArxivFetcher with all dependencies.
        
        Args:
            config: ArXiv fetcher configuration
            cache_backend: Cache backend (ICacheBackend)
            llm_router: LLM router for query expansion
            message_publisher: Message publisher
            
        Returns:
            Configured ArxivFetcher instance
        """
        # Create cache manager
        if cache_backend is not None:
            cache_manager = CacheManager(
                cache_backend=cache_backend,
                config=config,
            )
        else:
            cache_manager = None
        
        # Create query processor
        query_processor = QueryProcessor(
            llm_router=llm_router,
            cache_manager=cache_manager,
            config=config,
        )
        
        # Create API client
        api_client = ArxivAPIClient(
            cache=cache_manager,
            config=config,
        )
        
        # Create arXiv publisher
        arxiv_publisher = ArxivMessagePublisher(
            message_publisher=message_publisher,
            config=config,
        )
        
        # Create fetcher
        return ArxivFetcher(
            config=config,
            cache=cache_backend,
            query_processor=query_processor,
            api_client=api_client,
            publisher=arxiv_publisher,
        )
    
    @staticmethod
    def create_for_testing() -> ArxivFetcher:
        """Create ArxivFetcher with all mocks for testing.
        
        Returns:
            ArxivFetcher with mock dependencies
        """
        from src.shared.testing.mocks import (
            InMemoryCacheBackend,
            MockLLMRouter,
            MockMessagePublisher,
        )
        
        cache_backend = InMemoryCacheBackend()
        llm_router = MockLLMRouter()
        message_publisher = MockMessagePublisher()
        
        return ArxivFetcherFactory.create_full(
            config=ArxivFetcherConfig(),
            cache_backend=cache_backend,
            llm_router=llm_router,
            message_publisher=message_publisher,
        )


__all__ = [
    "ArxivFetcher",
    "ArxivFetcherFactory",
]
