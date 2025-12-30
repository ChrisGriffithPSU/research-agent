"""HuggingFace fetcher orchestration service.

Design Principles (from code-quality.mdc):
- State Management: Mutable statistics separated from immutable dependencies
- Orchestration Pattern: Coordinates API client, cache, parser, and publisher
- Observability: Correlation ID flows through all operations
- Error Handling: Fail fast with clear error messages
"""
import asyncio
import logging
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from src.services.fetchers.huggingface.config import HFetcherConfig
from src.services.fetchers.huggingface.exceptions import APIError
from src.services.fetchers.huggingface.interfaces import (
    IHuggingFaceAPI,
    IModelCardParser,
    ICacheBackend,
    IHuggingFacePublisher,
    IHuggingFaceFetcher,
)
from src.services.fetchers.huggingface.schemas.model import (
    ModelMetadata,
    ModelCardContent,
)


logger = logging.getLogger(__name__)


@dataclass
class FetcherStats:
    """Mutable statistics for the fetcher.
    
    Separated from immutable dependencies to enable
    thread-safe updates and clear state management.
    """
    total_queries: int = 0
    total_models: int = 0
    total_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    started_at: Optional[datetime] = None
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class HuggingFaceFetcher(IHuggingFaceFetcher):
    """Main fetcher service for HuggingFace model discovery.
    
    Responsibilities:
    - Orchestrate API client, cache manager, parser, and publisher
    - Implement discovery workflow: cache check -> API call -> publish
    - Generate and propagate correlation IDs for tracing
    - Collect and report statistics
    
    Immutable Dependencies (constructor parameters):
    - api_client: IHuggingFaceAPI implementation
    - cache_manager: ICacheBackend implementation
    - parser: IModelCardParser implementation
    - publisher: IHuggingFacePublisher implementation
    - config: Configuration (frozen)
    
    Mutable State:
    - _initialized: Initialization flag
    - stats: Fetcher statistics
    
    Example:
        # Production use with real dependencies
        from src.services.fetchers.huggingface import (
            HuggingFaceAPIClient,
            CacheManager,
            Parser,
            HuggingFaceMessagePublisher,
        )
        
        fetcher = HuggingFaceFetcher(
            api_client=HuggingFaceAPIClient(),
            cache_manager=CacheManager(),
            parser=Parser(),
            publisher=HuggingFaceMessagePublisher(),
        )
        
        await fetcher.initialize()
        count = await fetcher.run_discovery(
            queries=["time series forecasting", "LSTM stock prediction"],
            tasks=["time-series-forecasting"],
        )
        
        # Testing use with mocks
        from src.services.fetchers.huggingface import (
            MockAPI,
            MockCache,
            MockParser,
        )
        
        fetcher = HuggingFaceFetcher(
            api_client=MockAPI(),
            cache_manager=MockCache(),
            parser=MockParser(),
            publisher=MockPublisher(),
        )
    """
    
    def __init__(
        self,
        api_client: Optional[IHuggingFaceAPI] = None,
        cache_manager: Optional[ICacheBackend] = None,
        parser: Optional[IModelCardParser] = None,
        publisher: Optional[IHuggingFacePublisher] = None,
        config: Optional[HFetcherConfig] = None,
    ):
        """Initialize the fetcher with dependencies.
        
        Args:
            api_client: HuggingFace API client (injected)
            cache_manager: Cache manager (injected)
            parser: Model card parser (injected)
            publisher: Message publisher (injected)
            config: Configuration (injected, frozen)
        """
        from src.services.fetchers.huggingface.services.api_client import (
            HuggingFaceAPIClient,
        )
        from src.services.fetchers.huggingface.services.cache_manager import (
            CacheManager,
        )
        from src.services.fetchers.huggingface.services.parser import (
            Parser,
        )
        from src.services.fetchers.huggingface.services.publisher import (
            HuggingFaceMessagePublisher,
        )
        
        self._config = config or HFetcherConfig()
        self._api_client = api_client or HuggingFaceAPIClient(config=self._config)
        self._cache_manager = cache_manager or CacheManager(config=self._config)
        self._parser = parser or Parser()
        self._publisher = publisher or HuggingFaceMessagePublisher(config=self._config)
        self._initialized: bool = False
        self._stats = FetcherStats()
    
    async def initialize(self) -> None:
        """Initialize all components.
        
        Side effects:
        - Initializes API client
        - Initializes cache manager
        - Initializes publisher
        """
        if self._initialized:
            return
        
        await asyncio.gather(
            self._api_client.initialize(),
            self._cache_manager.initialize(),
            self._publisher.initialize(),
        )
        
        self._initialized = True
        self._stats.started_at = datetime.utcnow()
        
        logger.info(
            "HuggingFaceFetcher initialized",
            extra={"event": "fetcher_init"}
        )
    
    async def run_discovery(
        self,
        queries: List[str],
        tasks: Optional[List[str]] = None,
    ) -> int:
        """Run model discovery for queries and/or tasks.
        
        This is the MAIN ENTRY POINT for discovery. The workflow:
        1. Generate correlation ID for tracing
        2. For each query/task combination:
           a. Check cache for cached results
           b. If cache miss, call API
           c. Cache results
           d. Publish results
        3. Return total models published
        
        Args:
            queries: List of search queries
            tasks: Optional list of task filters
            
        Returns:
            Number of models discovered and published
        """
        if not self._initialized:
            await self.initialize()
        
        correlation_id = str(uuid.uuid4())
        total_published = 0
        
        logger.info(
            f"Starting discovery: {len(queries)} queries, "
            f"{len(tasks) if tasks else 0} task filters",
            extra={
                "event": "discovery_start",
                "correlation_id": correlation_id,
                "query_count": len(queries),
                "task_count": len(tasks) if tasks else 0,
            }
        )
        
        try:
            # Process queries with optional task filters
            for query in queries:
                if tasks:
                    # Search with each task filter
                    for task in tasks:
                        models = await self._search(
                            query=query,
                            task=task,
                            correlation_id=correlation_id,
                        )
                        published = await self._publish(
                            models=models,
                            correlation_id=correlation_id,
                            query=query,
                        )
                        total_published += published
                else:
                    # Search without task filter
                    models = await self._search(
                        query=query,
                        task=None,
                        correlation_id=correlation_id,
                    )
                    published = await self._publish(
                        models=models,
                        correlation_id=correlation_id,
                        query=query,
                    )
                    total_published += published
            
            self._stats.total_models = total_published
            
            logger.info(
                f"Discovery complete: {total_published} models published",
                extra={
                    "event": "discovery_complete",
                    "correlation_id": correlation_id,
                    "total_published": total_published,
                }
            )
            
            return total_published
            
        except Exception as e:
            self._stats.total_errors += 1
            logger.error(
                f"Discovery failed: {e}",
                extra={
                    "event": "discovery_error",
                    "correlation_id": correlation_id,
                    "error": str(e),
                }
            )
            raise
    
    async def _search(
        self,
        query: str,
        task: Optional[str],
        correlation_id: str,
    ) -> List[ModelMetadata]:
        """Execute search for models with caching.
        
        Responsibilities:
        - Check cache for cached results
        - Execute API search on cache miss
        - Cache results after successful search
        
        Args:
            query: Search query
            task: Optional task filter
            correlation_id: Correlation ID for tracing
            
        Returns:
            List of models found (empty if not found)
        """
        # Check cache first
        if self._config.cache_enabled:
            cached = await self._cache_manager.get_search_results(
                query=query,
                task=task,
                max_results=self._config.default_results_per_query,
            )
            
            if cached:
                self._stats.cache_hits += 1
                logger.info(
                    f"Cache hit for query: {query} (task={task})",
                    extra={
                        "event": "cache_hit",
                        "correlation_id": correlation_id,
                        "query": query,
                        "task": task,
                        "cached_count": len(cached),
                    }
                )
                return cached
            else:
                self._stats.cache_misses += 1
        
        # Execute API search
        try:
            models = await self._api_client.search_models(
                query=query,
                task=task,
                max_results=self._config.default_results_per_query,
                sort_by="downloads",
            )
            
            self._stats.total_queries += 1
            
        except APIError as e:
            self._stats.total_errors += 1
            logger.error(
                f"Search failed for '{query}': {e}",
                extra={
                    "event": "search_error",
                    "correlation_id": correlation_id,
                    "query": query,
                    "task": task,
                    "error": str(e),
                }
            )
            return []
        
        if not models:
            logger.info(
                f"No models found for query: {query}",
                extra={
                    "event": "no_models_found",
                    "correlation_id": correlation_id,
                    "query": query,
                    "task": task,
                }
            )
            return models
        
        # Cache results
        if self._config.cache_enabled:
            try:
                await self._cache_manager.set_search_results(
                    query=query,
                    results=models,
                    task=task,
                    max_results=self._config.default_results_per_query,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to cache search results: {e}",
                    extra={
                        "event": "cache_set_error",
                        "correlation_id": correlation_id,
                        "error": str(e),
                    }
                )
        
        return models
    
    async def _publish(
        self,
        models: List[ModelMetadata],
        correlation_id: str,
        query: str,
    ) -> int:
        """Publish discovered models to message queue.
        
        Responsibilities:
        - Validate models list is not empty
        - Publish models to discovered queue
        - Track publish statistics
        
        Args:
            models: List of model metadata to publish
            correlation_id: Correlation ID for tracing
            query: Original search query
            
        Returns:
            Number of models published successfully
        """
        if not models:
            logger.debug(
                "No models to publish",
                extra={
                    "event": "publish_no_models",
                    "correlation_id": correlation_id,
                }
            )
            return 0
        
        try:
            published = await self._publisher.publish_discovered(
                models=models,
                correlation_id=correlation_id,
                query=query,
            )
            return published
            
        except Exception as e:
            self._stats.total_errors += 1
            logger.error(
                f"Failed to publish results for '{query}': {e}",
                extra={
                    "event": "publish_error",
                    "correlation_id": correlation_id,
                    "query": query,
                    "model_count": len(models),
                    "error": str(e),
                }
            )
            return 0
    
    async def search_single(
        self,
        query: str,
        task: Optional[str] = None,
        parse_cards: bool = False,
    ) -> Dict[str, Any]:
        """Search for models and optionally parse model cards.
        
        Args:
            query: Search query
            task: Optional task filter
            parse_cards: Whether to parse model cards
            
        Returns:
            Dictionary with models and optional parsed content
        """
        if not self._initialized:
            await self.initialize()
        
        correlation_id = str(uuid.uuid4())
        
        # Search
        models = await self._api_client.search_models(
            query=query,
            task=task,
            max_results=self._config.default_results_per_query,
        )
        
        result = {
            "query": query,
            "task": task,
            "models": models,
            "model_count": len(models),
            "correlation_id": correlation_id,
        }
        
        # Optionally parse model cards
        if parse_cards and models:
            parsed_cards = []
            for model in models[:5]:  # Parse first 5 to avoid rate limits
                try:
                    card_content = await self._api_client.get_model_card(
                        model_id=model.model_id,
                    )
                    parsed = self._parser.parse(
                        model_id=model.model_id,
                        card_content=card_content,
                    )
                    parsed_cards.append(parsed)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse card for {model.model_id}: {e}",
                        extra={
                            "event": "card_parse_error",
                            "model_id": model.model_id,
                            "error": str(e),
                        }
                    )
                    continue
            
            result["parsed_cards"] = parsed_cards
        
        return result
    
    async def get_model_with_card(
        self,
        model_id: str,
        parse: bool = True,
    ) -> Dict[str, Any]:
        """Get model info and optionally parse model card.
        
        Args:
            model_id: HuggingFace model ID
            parse: Whether to parse model card
            
        Returns:
            Dictionary with model info and parsed content
        """
        if not self._initialized:
            await self.initialize()
        
        correlation_id = str(uuid.uuid4())
        
        # Check cache
        if self._config.cache_enabled:
            cached_info = await self._cache_manager.get_model_info(model_id)
            if cached_info:
                logger.info(
                    f"Cache hit for model info: {model_id}",
                    extra={
                        "event": "cache_hit",
                        "correlation_id": correlation_id,
                        "model_id": model_id,
                    }
                )
                result = {"model": cached_info}
                
                if parse:
                    cached_card = await self._cache_manager.get_model_card(model_id)
                    if cached_card:
                        result["parsed_card"] = self._parser.parse(
                            model_id=model_id,
                            card_content=cached_card,
                        )
                
                return result
        
        # Fetch model info
        model = await self._api_client.get_model_info(model_id)
        
        result = {
            "model": model,
            "correlation_id": correlation_id,
        }
        
        # Cache model info
        if self._config.cache_enabled:
            try:
                await self._cache_manager.set_model_info(model_id, model)
            except Exception as e:
                logger.warning(
                    f"Failed to cache model info: {e}",
                    extra={
                        "event": "cache_set_error",
                        "correlation_id": correlation_id,
                        "error": str(e),
                    }
                )
        
        # Optionally parse model card
        if parse:
            try:
                card_content = await self._api_client.get_model_card(model_id)
                
                if self._config.cache_enabled:
                    try:
                        await self._cache_manager.set_model_card(model_id, card_content)
                    except Exception as e:
                        logger.warning(
                            f"Failed to cache model card: {e}",
                            extra={
                                "event": "cache_set_error",
                                "correlation_id": correlation_id,
                                "error": str(e),
                            }
                        )
                
                parsed_card = self._parser.parse(
                    model_id=model_id,
                    card_content=card_content,
                )
                result["parsed_card"] = parsed_card
                
            except Exception as e:
                logger.warning(
                    f"Failed to get/parse model card: {e}",
                    extra={
                        "event": "card_error",
                        "correlation_id": correlation_id,
                        "model_id": model_id,
                        "error": str(e),
                    }
                )
                result["card_error"] = str(e)
        
        return result
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all components.
        
        Returns:
            Dict mapping component name to health status
        """
        return {
            "api_client": await self._api_client.health_check(),
            "cache_manager": await self._cache_manager.health_check(),
            "parser": self._parser.health_check(),
            "publisher": await self._publisher.health_check(),
        }
    
    async def close(self) -> None:
        """Clean up all resources.
        
        Side effects:
        - Sets initialized to False
        - Closes all component connections
        """
        await asyncio.gather(
            self._api_client.close(),
            self._cache_manager.close(),
            self._publisher.close(),
        )
        
        self._initialized = False
        
        logger.info(
            "HuggingFaceFetcher closed",
            extra={"event": "fetcher_close"}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fetcher statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_queries": self._stats.total_queries,
            "total_models": self._stats.total_models,
            "total_errors": self._stats.total_errors,
            "cache_hits": self._stats.cache_hits,
            "cache_misses": self._stats.cache_misses,
            "cache_hit_rate": self._stats.cache_hit_rate,
            "initialized": self._initialized,
            "started_at": (
                self._stats.started_at.isoformat()
                if self._stats.started_at else None
            ),
            "api_stats": self._api_client.get_stats(),
            "cache_stats": self._cache_manager.get_stats(),
            "publisher_stats": self._publisher.get_stats(),
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"HuggingFaceFetcher("
            f"queries={stats['total_queries']}, "
            f"models={stats['total_models']}, "
            f"errors={stats['total_errors']}, "
            f"cache_hit_rate={stats['cache_hit_rate']:.2%})"
        )

