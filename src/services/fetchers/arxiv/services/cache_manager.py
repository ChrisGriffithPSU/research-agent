"""Cache manager for arXiv fetcher.

Integrates with existing CacheService from src/shared/utils/cache/
Provides caching for API responses, parsed content, and query expansions.
"""
import json
import hashlib
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime

from src.shared.utils.cache.service import CacheService, get_cache_service
from src.shared.utils.cache.keys import build_cache_key, build_hashed_cache_key
from src.shared.utils.cache.serializers import JSONSerializer

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.exceptions import CacheError, CacheConnectionError


logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager for arXiv fetcher.
    
    Integrates with existing CacheService from src/shared/utils/cache/
    Provides caching for:
    - API responses (TTL: 1 hour)
    - Query expansions (TTL: 5 minutes)
    - Parsed content (TTL: 48 hours)
    
    Attributes:
        config: ArXiv fetcher configuration
        cache: CacheService instance
        namespace_prefix: Prefix for all cache keys
    """
    
    # Cache key prefixes (using existing namespace pattern)
    ARXIV_API_CACHE = "arxiv:api"
    ARXIV_PARSED_CACHE = "arxiv:parsed"
    ARXIV_QUERY_CACHE = "arxiv:query"
    
    def __init__(
        self,
        config: Optional[ArxivFetcherConfig] = None,
        cache: Optional[CacheService] = None,
    ):
        """Initialize cache manager.
        
        Args:
            config: ArXiv fetcher configuration (uses default if not provided)
            cache: CacheService instance (creates one if not provided)
        """
        self.config = config or ArxivFetcherConfig()
        self.cache = cache
        self._initialized = False
        
        # Initialize serializers
        self._json_serializer = JSONSerializer()
    
    async def initialize(self) -> None:
        """Initialize cache connection.
        
        Raises:
            CacheConnectionError: If cache connection fails
        """
        if self._initialized:
            return
            
        try:
            if self.cache is None:
                self.cache = get_cache_service(
                    redis_url=self.config.redis_url,
                    serializer_type="json",
                )
            
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
        """Build cache key for API responses.
        
        Args:
            query: Search query
            **params: Additional parameters
            
        Returns:
            Cache key string
        """
        key_data = f"{query}:{sorted(params.items())}"
        return build_hashed_cache_key(self.ARXIV_API_CACHE, key_data, hash_length=16)
    
    def _build_parsed_key(self, paper_id: str) -> str:
        """Build cache key for parsed content.
        
        Args:
            paper_id: arXiv ID
            
        Returns:
            Cache key string
        """
        return build_cache_key(self.ARXIV_PARSED_CACHE, paper_id)
    
    def _build_query_key(self, query: str) -> str:
        """Build cache key for query expansions.
        
        Args:
            query: Original query
            
        Returns:
            Cache key string
        """
        return build_hashed_cache_key(self.ARXIV_QUERY_CACHE, query, hash_length=12)
    
    # ==================== API Response Caching ====================
    
    async def get_api_response(self, query: str, **params) -> Optional[Dict[str, Any]]:
        """Get cached API response.
        
        Args:
            query: Search query
            **params: Additional parameters
            
        Returns:
            Cached response dict or None if not found
        """
        if not self._initialized:
            return None
            
        try:
            key = self._build_api_key(query, **params)
            cached = await self.cache.get_cached(key)
            
            if cached:
                logger.debug(f"API cache hit: {query[:50]}...")
                return cached
            
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
        """Cache API response.
        
        Args:
            query: Search query
            response: API response to cache
            **params: Additional parameters
        """
        if not self._initialized:
            return
            
        try:
            key = self._build_api_key(query, **params)
            await self.cache.set_cached(
                key,
                response,
                ttl=self.config.ttl_api_response_seconds,
            )
            logger.debug(f"Cached API response: {query[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to cache API response: {e}")
    
    # ==================== Parsed Content Caching ====================
    
    async def get_parsed_content(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """Get cached parsed content.
        
        Args:
            paper_id: arXiv ID
            
        Returns:
            Cached parsed content dict or None if not found
        """
        if not self._initialized:
            return None
            
        try:
            key = self._build_parsed_key(paper_id)
            cached = await self.cache.get_cached(key)
            
            if cached:
                logger.debug(f"Parsed content cache hit: {paper_id}")
                return cached
            
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
        """Cache parsed content.
        
        Args:
            paper_id: arXiv ID
            content: Parsed content to cache
        """
        if not self._initialized:
            return
            
        try:
            key = self._build_parsed_key(paper_id)
            await self.cache.set_cached(
                key,
                content,
                ttl=self.config.ttl_parsed_content_seconds,
            )
            logger.debug(f"Cached parsed content: {paper_id}")
            
        except Exception as e:
            logger.warning(f"Failed to cache parsed content: {e}")
    
    # ==================== Query Expansion Caching ====================
    
    async def get_query_expansion(self, query: str) -> Optional[List[str]]:
        """Get cached query expansions.
        
        Args:
            query: Original query
            
        Returns:
            Cached expansions list or None if not found
        """
        if not self._initialized:
            return None
            
        try:
            key = self._build_query_key(query)
            cached = await self.cache.get_cached(key)
            
            if cached:
                logger.debug(f"Query expansion cache hit: {query[:50]}...")
                return cached
            
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
        """Cache query expansions.
        
        Args:
            query: Original query
            expansions: Expanded queries to cache
        """
        if not self._initialized:
            return
            
        try:
            key = self._build_query_key(query)
            await self.cache.set_cached(
                key,
                expansions,
                ttl=self.config.ttl_query_expansion_seconds,
            )
            logger.debug(f"Cached query expansion: {query[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to cache query expansion: {e}")
    
    # ==================== Batch Operations ====================
    
    async def get_many_parsed(
        self,
        paper_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Get multiple parsed content items.
        
        Args:
            paper_ids: List of arXiv IDs
            
        Returns:
            Dict mapping paper_id to cached content
        """
        if not self._initialized:
            return {}
            
        try:
            keys = [self._build_parsed_key(pid) for pid in paper_ids]
            paper_id_map = {self._build_parsed_key(pid): pid for pid in paper_ids}
            
            cached = await self.cache.get_many(keys)
            
            result = {}
            for key, value in cached.items():
                paper_id = paper_id_map.get(key)
                if paper_id:
                    result[paper_id] = value
            
            logger.debug(
                f"get_many_parsed: {len(result)}/{len(paper_ids)} hits"
            )
            return result
            
        except Exception as e:
            logger.warning(f"Failed to get many parsed content: {e}")
            return {}
    
    # ==================== Utility Methods ====================
    
    async def invalidate_paper(self, paper_id: str) -> None:
        """Invalidate all cached data for a paper.
        
        Args:
            paper_id: arXiv ID to invalidate
        """
        if not self._initialized:
            return
            
        try:
            # Invalidate parsed content
            parsed_key = self._build_parsed_key(paper_id)
            await self.cache.delete(parsed_key)
            logger.info(f"Invalidated cache for paper: {paper_id}")
            
        except Exception as e:
            logger.warning(f"Failed to invalidate paper cache: {e}")
    
    async def invalidate_api_cache(self, pattern: str) -> None:
        """Invalidate API cache entries matching pattern.
        
        Args:
            pattern: Pattern to match (e.g., "transformer*")
        """
        if not self._initialized:
            return
            
        try:
            full_pattern = f"{self.ARXIV_API_CACHE}:{pattern}"
            await self.cache.delete_pattern(full_pattern)
            logger.info(f"Invalidated API cache matching: {pattern}")
            
        except Exception as e:
            logger.warning(f"Failed to invalidate API cache: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with cache metrics
        """
        if self.cache is None:
            return {"status": "not_initialized"}
            
        try:
            return self.cache.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> bool:
        """Check if cache is healthy.
        
        Returns:
            True if cache is healthy, False otherwise
        """
        if not self._initialized or self.cache is None:
            return False
            
        try:
            return await self.cache.connection.ping()
        except Exception as e:
            logger.warning(f"Cache health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close cache connection."""
        if self.cache is not None:
            await self.cache.close()
            self._initialized = False
            logger.info("CacheManager closed")
    
    def __repr__(self) -> str:
        return (
            f"CacheManager("
            f"initialized={self._initialized}, "
            f"backend={self.config.cache_backend})"
        )

