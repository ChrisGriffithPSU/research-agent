"""Cache manager for Kaggle notebooks.

Provides caching layer for notebooks and search results with TTL support.
"""
import json
import logging
from typing import Optional, Dict, Any, List

from src.shared.interfaces import ICacheBackend
from src.services.fetchers.kaggle.config import KaggleFetcherConfig
from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookMetadata,
    NotebookContent,
    ParsedNotebook,
)
from src.services.fetchers.kaggle.exceptions import (
    CacheError,
    CacheConnectionError,
)
from src.shared.utils.cache.keys import CacheKeyBuilder


logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager for Kaggle notebooks and search results.

    Features:
    - TTL-based cache invalidation (configurable)
    - Separate caches for metadata, content, and search results
    - JSON serialization for complex objects
    - Cache hit/miss tracking

    All dependencies are injected through the constructor.

    Example:
        # Production use with Redis
        cache = RedisCacheBackend(url="redis://localhost:6379/0")
        manager = CacheManager(
            cache_backend=cache,
            config=config,
        )
        await manager.initialize()

        # Testing use with in-memory cache
        from src.shared.testing.mocks import InMemoryCacheBackend
        cache = InMemoryCacheBackend()
        manager = CacheManager(cache_backend=cache, config=config)

        # Use cache manager
        metadata = await manager.get_or_download_metadata(notebook_path, download_fn)

    Attributes:
        cache_backend: Cache backend implementation (ICacheBackend)
        config: Kaggle fetcher configuration
        key_builder: Cache key builder for consistent key format
    """

    def __init__(
        self,
        cache_backend: Optional[ICacheBackend] = None,
        config: Optional[KaggleFetcherConfig] = None,
    ):
        """Initialize cache manager.

        Args:
            cache_backend: Cache backend implementation (ICacheBackend)
            config: Kaggle fetcher configuration
        """
        self._cache = cache_backend
        self.config = config or KaggleFetcherConfig()
        self.key_builder = CacheKeyBuilder(prefix="kaggle")

        # Statistics
        self._hits = 0
        self._misses = 0
        self._errors = 0

    async def initialize(self) -> None:
        """Initialize cache connection."""
        if self._cache is None:
            logger.warning("No cache backend provided, caching disabled")
            return

        try:
            await self._cache.close()
            logger.info("CacheManager initialized")
        except Exception as e:
            raise CacheConnectionError(
                message=f"Failed to initialize cache: {e}",
                original=e,
            )

    async def close(self) -> None:
        """Close cache connection."""
        if self._cache:
            await self._cache.close()
        logger.info("CacheManager closed")

    def is_available(self) -> bool:
        """Check if cache is available."""
        return self._cache is not None

    # ==================== Notebook Metadata Caching ====================

    async def get_notebook_metadata(
        self,
        notebook_path: str,
    ) -> Optional[NotebookMetadata]:
        """Get cached notebook metadata.

        Args:
            notebook_path: Kaggle notebook path

        Returns:
            NotebookMetadata if cached, None otherwise
        """
        if not self.is_available():
            return None

        try:
            key = self.key_builder.for_notebook("metadata", notebook_path)
            cached = await self._cache.get(key)

            if cached:
                self._hits += 1
                return NotebookMetadata(**json.loads(cached))

            self._misses += 1
            return None

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache get failed for metadata: {e}")
            return None

    async def set_notebook_metadata(
        self,
        notebook_path: str,
        metadata: NotebookMetadata,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache notebook metadata.

        Args:
            notebook_path: Kaggle notebook path
            metadata: Notebook metadata to cache
            ttl_seconds: TTL in seconds (default from config)
        """
        if not self.is_available():
            return

        try:
            key = self.key_builder.for_notebook("metadata", notebook_path)
            ttl = ttl_seconds or self.config.ttl_search_seconds

            await self._cache.set(
                key,
                metadata.model_dump_json().encode("utf-8"),
                ttl_seconds=ttl,
            )

            logger.debug(f"Cached metadata for: {notebook_path}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache set failed for metadata: {e}")

    # ==================== Notebook Content Caching ====================

    async def get_notebook_content(
        self,
        notebook_path: str,
    ) -> Optional[NotebookContent]:
        """Get cached notebook content.

        Args:
            notebook_path: Kaggle notebook path

        Returns:
            NotebookContent if cached, None otherwise
        """
        if not self.is_available():
            return None

        try:
            key = self.key_builder.for_notebook("content", notebook_path)
            cached = await self._cache.get(key)

            if cached:
                self._hits += 1
                return NotebookContent(**json.loads(cached))

            self._misses += 1
            return None

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache get failed for content: {e}")
            return None

    async def set_notebook_content(
        self,
        notebook_path: str,
        content: NotebookContent,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache notebook content.

        Args:
            notebook_path: Kaggle notebook path
            content: Notebook content to cache
            ttl_seconds: TTL in seconds (default from config)
        """
        if not self.is_available():
            return

        try:
            key = self.key_builder.for_notebook("content", notebook_path)
            ttl = ttl_seconds or self.config.ttl_notebook_seconds

            await self._cache.set(
                key,
                content.model_dump_json().encode("utf-8"),
                ttl_seconds=ttl,
            )

            logger.debug(f"Cached content for: {notebook_path}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache set failed for content: {e}")

    async def get_or_download_content(
        self,
        notebook_path: str,
        download_fn,
    ) -> NotebookContent:
        """Get cached content or download if not cached.

        Args:
            notebook_path: Kaggle notebook path
            download_fn: Async function to download notebook

        Returns:
            NotebookContent (from cache or downloaded)
        """
        # Try cache first
        cached = await self.get_notebook_content(notebook_path)
        if cached:
            return cached

        # Download and cache
        content = await download_fn(notebook_path)
        await self.set_notebook_content(notebook_path, content)

        return content

    # ==================== Parsed Notebook Caching ====================

    async def get_parsed_notebook(
        self,
        notebook_path: str,
    ) -> Optional[ParsedNotebook]:
        """Get cached parsed notebook.

        Args:
            notebook_path: Kaggle notebook path

        Returns:
            ParsedNotebook if cached, None otherwise
        """
        if not self.is_available():
            return None

        try:
            key = self.key_builder.for_notebook("parsed", notebook_path)
            cached = await self._cache.get(key)

            if cached:
                self._hits += 1
                return ParsedNotebook(**json.loads(cached))

            self._misses += 1
            return None

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache get failed for parsed: {e}")
            return None

    async def set_parsed_notebook(
        self,
        notebook_path: str,
        parsed: ParsedNotebook,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache parsed notebook.

        Args:
            notebook_path: Kaggle notebook path
            parsed: ParsedNotebook to cache
            ttl_seconds: TTL in seconds (default from config)
        """
        if not self.is_available():
            return

        try:
            key = self.key_builder.for_notebook("parsed", notebook_path)
            ttl = ttl_seconds or self.config.ttl_notebook_seconds

            await self._cache.set(
                key,
                parsed.model_dump_json().encode("utf-8"),
                ttl_seconds=ttl,
            )

            logger.debug(f"Cached parsed notebook for: {notebook_path}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache set failed for parsed: {e}")

    # ==================== Search Result Caching ====================

    async def get_search_results(
        self,
        query: str,
    ) -> Optional[List[NotebookMetadata]]:
        """Get cached search results.

        Args:
            query: Search query

        Returns:
            List of NotebookMetadata if cached, None otherwise
        """
        if not self.is_available():
            return None

        try:
            key = self.key_builder.for_search(query)
            cached = await self._cache.get(key)

            if cached:
                self._hits += 1
                data = json.loads(cached)
                return [NotebookMetadata(**item) for item in data]

            self._misses += 1
            return None

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache get failed for search: {e}")
            return None

    async def set_search_results(
        self,
        query: str,
        results: List[NotebookMetadata],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache search results.

        Args:
            query: Search query
            results: List of NotebookMetadata to cache
            ttl_seconds: TTL in seconds (default from config)
        """
        if not self.is_available():
            return

        try:
            key = self.key_builder.for_search(query)
            ttl = ttl_seconds or self.config.ttl_search_seconds

            data = [item.model_dump() for item in results]
            await self._cache.set(
                key,
                json.dumps(data).encode("utf-8"),
                ttl_seconds=ttl,
            )

            logger.debug(f"Cached search results for: {query}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache set failed for search: {e}")

    # ==================== Cache Invalidation ====================

    async def invalidate_notebook(
        self,
        notebook_path: str,
    ) -> None:
        """Invalidate all cached data for a notebook.

        Args:
            notebook_path: Kaggle notebook path
        """
        if not self.is_available():
            return

        try:
            # Invalidate all notebook-related caches
            keys = [
                self.key_builder.for_notebook("metadata", notebook_path),
                self.key_builder.for_notebook("content", notebook_path),
                self.key_builder.for_notebook("parsed", notebook_path),
            ]

            for key in keys:
                await self._cache.delete(key)

            logger.debug(f"Invalidated cache for: {notebook_path}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache invalidation failed: {e}")

    async def invalidate_search(
        self,
        query: str,
    ) -> None:
        """Invalidate cached search results for a query.

        Args:
            query: Search query
        """
        if not self.is_available():
            return

        try:
            key = self.key_builder.for_search(query)
            await self._cache.delete(key)

            logger.debug(f"Invalidated search cache for: {query}")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache invalidation failed: {e}")

    async def clear_all(self) -> None:
        """Clear all Kaggle-related caches."""
        if not self.is_available():
            return

        try:
            pattern = self.key_builder.with_prefix("kaggle:*")
            await self._cache.delete_pattern(pattern)

            logger.info("Cleared all Kaggle caches")

        except Exception as e:
            self._errors += 1
            logger.warning(f"Cache clear failed: {e}")

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hit/miss/error counts and rates
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "total_requests": total,
            "hit_rate": hit_rate,
            "available": self.is_available(),
        }

    async def health_check(self) -> bool:
        """Check if cache is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self.is_available():
            return False

        try:
            # Simple health check
            key = self.key_builder.for_search("health_check")
            await self._cache.set(key, b"health", ttl_seconds=1)
            result = await self._cache.get(key)
            await self._cache.delete(key)
            return result is not None
        except Exception as e:
            logger.warning(f"Cache health check failed: {e}")
            return False


__all__ = [
    "CacheManager",
]

