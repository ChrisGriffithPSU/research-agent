"""Refactored cache manager for arXiv fetcher.

Uses dependency injection for testability.
"""
import json
import hashlib
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime

from src.shared.interfaces import ICacheBackend
from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.exceptions import CacheError, CacheConnectionError


logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager for arXiv fetcher with injectable backend.
    
    Provides caching for:
    - API responses (TTL: 1 hour)
    - Query expansions (TTL: 5 minutes)
    - Parsed content (TTL: 48 hours)
    
    All dependencies are injected through the constructor.
    
    Example:
        # Production use with Redis
        from src.shared.utils.cache.service import CacheService, RedisCacheBackend
        from src.shared.utils.cache.connection import RedisConnection
        
        connection = RedisConnection(redis_url="redis://localhost:6379/0")
        backend = RedisCacheBackend(connection=connection)
        cache = CacheService(cache_backend=backend)
        
        manager = CacheManager(
            cache_backend=backend,  # Inject the backend
            config=config,
        )
        await manager.initialize()
        
        # Testing use with in-memory cache
        from src.shared.testing.mocks import InMemoryCacheBackend
        
        manager = CacheManager(
            cache_backend=InMemoryCacheBackend(),
            config=config,
        )
    
    Attributes:
        config: ArXiv fetcher configuration
        cache: Cache backend implementation (ICacheBackend)
        _initialized: Whether the service has been initialized
    """
    
    # Cache key prefixes
    ARXIV_API_CACHE = "arxiv:api"
    ARXIV_PARSED_CACHE = "arxiv:parsed"
    ARXIV_QUERY_CACHE = "arxiv:query"
    
    def __init__(
        self,
        cache_backend: Optional[ICacheBackend] = None,
        config: Optional[ArxivFetcherConfig] = None,
    ):
        """Initialize cache manager.
        
        Args:
            cache_backend: Cache backend implementation (ICacheBackend)
            config: ArXiv fetcher configuration
        """
        self.config = config or ArxivFetcherConfig()
        self.cache = cache_backend
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize cache connection.
        
        Raises:
            CacheConnectionError: If cache connection fails
        """
        if self._initialized:
            return
        
        if self.cache is None:
            raise CacheConnectionError(
                "No cache backend provided. "
                "Inject a cache backend (e.g., InMemoryCacheBackend) for testing."
            )
        
        try:
            if hasattr(self.cache, 'initialize'):
                await self.cache.initialize()
            self._initialized = True
            logger.info("CacheManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            raise CacheConnectionError(
                message=f"Failed to initialize cache: {e}",
                original=e,
            )
    
    # ==================== Key Building ====================
    
    def _build_api_key(self, query: str, **params) -> str:
        """Build cache key for API responses."""
        key_data = f"{query}:{sorted(params.items())}"
        return self._hash_key(self.ARXIV_API_CACHE, key_data)
    
    def _build_parsed_key(self, paper_id: str) -> str:
        """Build cache key for parsed content."""
        return f"{self.ARXIV_PARSED_CACHE}:{paper_id}"
    
    def _build_query_key(self, query: str) -> str:
        """Build cache key for query expansions."""
        return self._hash_key(self.ARXIV_QUERY_CACHE, query)
    
    def _hash_key(self, prefix: str, key_data: str) -> str:
        """Create a hashed cache key."""
        hash_value = hashlib.md5(key_data.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_value}"
    
    # ==================== API Response Caching ====================
    
    async def get_api_response(self, query: str, **params) -> Optional[Dict[str, Any]]:
        """Get cached API response.
        
        Args:
            query: Search query
            **params: Additional parameters
            
        Returns:
            Cached response dict or None if not found
        """
        if not self._initialized or self.cache is None:
            return None
        
        try:
            key = self._build_api_key(query, **params)
            cached = await self.cache.get(key)
            
            if cached:
                logger.debug(f"API cache hit: {query[:50]}...")
                return json.loads(cached.decode('utf-8'))
            
            logger.debug(f"API cache miss: {query[:50]}...")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get API cache: {e}")
            return None
    
    async def set_api_response(
        self,
        query: str,
        response: Dict[str, Any],
        **params,
    ) -> None:
        """Cache API response."""
        if not self._initialized or self.cache is None:
            return
        
        try:
            key = self._build_api_key(query, **params)
            serialized = json.dumps(response, default=str).encode('utf-8')
            await self.cache.set(
                key,
                serialized,
                ttl_seconds=self.config.ttl_api_response_seconds,
            )
            logger.debug(f"Cached API response: {query[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to cache API response: {e}")
    
    # ==================== Parsed Content Caching ====================
    
    async def get_parsed_content(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """Get cached parsed content."""
        if not self._initialized or self.cache is None:
            return None
        
        try:
            key = self._build_parsed_key(paper_id)
            cached = await self.cache.get(key)
            
            if cached:
                logger.debug(f"Parsed content cache hit: {paper_id}")
                return json.loads(cached.decode('utf-8'))
            
            logger.debug(f"Parsed content cache miss: {paper_id}")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get parsed content cache: {e}")
            return None
    
    async def set_parsed_content(
        self,
        paper_id: str,
        content: Dict[str, Any],
    ) -> None:
        """Cache parsed content."""
        if not self._initialized or self.cache is None:
            return
        
        try:
            key = self._build_parsed_key(paper_id)
            serialized = json.dumps(content, default=str).encode('utf-8')
            await self.cache.set(
                key,
                serialized,
                ttl_seconds=self.config.ttl_parsed_content_seconds,
            )
            logger.debug(f"Cached parsed content: {paper_id}")
            
        except Exception as e:
            logger.warning(f"Failed to cache parsed content: {e}")
    
    # ==================== Query Expansion Caching ====================
    
    async def get_query_expansion(self, query: str) -> Optional[List[str]]:
        """Get cached query expansions."""
        if not self._initialized or self.cache is None:
            return None
        
        try:
            key = self._build_query_key(query)
            cached = await self.cache.get(key)
            
            if cached:
                logger.debug(f"Query expansion cache hit: {query[:50]}...")
                return json.loads(cached.decode('utf-8'))
            
            logger.debug(f"Query expansion cache miss: {query[:50]}...")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get query expansion cache: {e}")
            return None
    
    async def set_query_expansion(
        self,
        query: str,
        expansions: List[str],
    ) -> None:
        """Cache query expansions."""
        if not self._initialized or self.cache is None:
            return
        
        try:
            key = self._build_query_key(query)
            serialized = json.dumps(expansions).encode('utf-8')
            await self.cache.set(
                key,
                serialized,
                ttl_seconds=self.config.ttl_query_expansion_seconds,
            )
            logger.debug(f"Cached query expansion: {query[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to cache query expansion: {e}")
    
    # ==================== Batch Operations ====================
    
    async def get_many_parsed(
        self,
        paper_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Get multiple parsed content items."""
        if not self._initialized or self.cache is None:
            return {}
        
        try:
            keys = [self._build_parsed_key(pid) for pid in paper_ids]
            cached = await self.cache.get_many(keys)
            
            result = {}
            for key, value in cached.items():
                # Extract paper_id from key
                paper_id = key.split(":")[-1]
                try:
                    result[paper_id] = json.loads(value.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            
            logger.debug(f"get_many_parsed: {len(result)}/{len(paper_ids)} hits")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to get many parsed content: {e}")
            return {}
    
    # ==================== Utility Methods ====================
    
    async def invalidate_paper(self, paper_id: str) -> None:
        """Invalidate all cached data for a paper."""
        if not self._initialized or self.cache is None:
            return
        
        try:
            parsed_key = self._build_parsed_key(paper_id)
            await self.cache.delete(parsed_key)
            logger.info(f"Invalidated cache for paper: {paper_id}")
            
        except Exception as e:
            logger.warning(f"Failed to invalidate paper cache: {e}")
    
    async def invalidate_api_cache(self, pattern: str) -> None:
        """Invalidate API cache entries matching pattern."""
        if not self._initialized or self.cache is None:
            return
        
        try:
            full_pattern = f"{self.ARXIV_API_CACHE}:{pattern}"
            await self.cache.delete_pattern(full_pattern)
            logger.info(f"Invalidated API cache matching: {pattern}")
            
        except Exception as e:
            logger.warning(f"Failed to invalidate API cache: {e}")
    
    async def health_check(self) -> bool:
        """Check if cache is healthy.
        
        Returns:
            True if cache is healthy, False otherwise
        """
        if not self._initialized or self.cache is None:
            return False
        
        try:
            return await self.cache.exists("health_check_key") or True
        except Exception as e:
            logger.warning(f"Cache health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close cache connection."""
        if self.cache is not None:
            await self.cache.close()
            self._initialized = False
            logger.info("CacheManager closed")
    
    @property
    def is_initialized(self) -> bool:
        """Check if cache manager is initialized."""
        return self._initialized
    
    @property
    def backend(self) -> Optional[ICacheBackend]:
        """Get the underlying backend (for testing)."""
        return self.cache
    
    def __repr__(self) -> str:
        return (
            f"CacheManager("
            f"initialized={self._initialized}, "
            f"backend={type(self.cache).__name__ if self.cache else None})"
        )
