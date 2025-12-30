"""Cache manager for HuggingFace fetcher.

Design Principles (from code-quality.mdc):
- Graceful Degradation: Cache failures don't crash the application
- State Management: Mutable state (connection, stats) separated from immutable config
- Defensive Programming: Validate inputs, handle edge cases
- Observability: Structured logging at decision points
"""
import hashlib
import json
import logging
from typing import Optional, Any, Dict
from dataclasses import dataclass
from datetime import datetime

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from ..config import HFetcherConfig
from ..exceptions import CacheError
from ..interfaces import ICacheBackend


logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Mutable statistics for the cache manager.
    
    Separated from immutable configuration to enable
    thread-safe updates and clear state management.
    """
    hit_count: int = 0
    miss_count: int = 0
    error_count: int = 0
    set_count: int = 0
    delete_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class CacheManager(ICacheBackend):
    """Redis-based cache manager for HuggingFace data.
    
    Responsibilities:
    - Manage Redis connection pool
    - Implement cache-aside pattern
    - Handle serialization/deserialization
    - Graceful degradation on cache failures
    
    Immutable Dependencies:
    - config: Configuration (frozen)
    
    Mutable State:
    - pool: Redis connection pool
    - client: Redis client instance
    - _initialized: Initialization flag
    - stats: Cache statistics
    """
    
    def __init__(
        self,
        config: Optional[HFetcherConfig] = None,
    ):
        """Initialize the cache manager.
        
        Args:
            config: Configuration (injected, frozen)
        """
        self._config = config or HFetcherConfig()
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._prefix = "hf:"
        self._initialized: bool = False
        self._stats = CacheStats()
    
    async def initialize(self) -> None:
        """Initialize Redis connection pool.
        
        Side effects:
        - Creates connection pool
        - Tests connection with ping
        """
        if self._initialized:
            return
        
        try:
            self._pool = ConnectionPool.from_url(
                self._config.redis_url,
                max_connections=10,
                decode_responses=False,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            
            self._initialized = True
            logger.info(
                f"CacheManager initialized with Redis: {self._config.redis_url}",
                extra={"event": "cache_init", "redis_url": self._config.redis_url}
            )
            
        except Exception as e:
            logger.warning(
                f"Failed to initialize cache, will operate without caching: {e}",
                extra={
                    "event": "cache_init_failed",
                    "redis_url": self._config.redis_url,
                    "error": str(e),
                }
            )
            # Don't raise - cache is optional
    
    def _ensure_initialized(self) -> None:
        """Ensure the cache is initialized.
        
        Raises:
            CacheError: If cache not initialized and no fallback
        """
        if not self._initialized:
            raise CacheError(
                message="CacheManager not initialized. Call initialize() first.",
                operation="initialize",
            )
    
    def _make_key(self, key_type: str, *args: Any) -> str:
        """Generate a cache key.
        
        Args:
            key_type: Type of data (search, model_info, model_card)
            *args: Key components
            
        Returns:
            Full cache key with prefix
        """
        # Create a deterministic string from args
        key_parts = [str(arg) for arg in args if arg]
        key_str = ":".join(key_parts)
        
        # Hash long keys to avoid Redis limits
        if len(key_str) > 200:
            key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:32]
            key_str = key_hash
        
        return f"{self._prefix}{key_type}:{key_str}"
    
    def _make_search_key(
        self,
        query: str,
        task: Optional[str] = None,
        max_results: int = 20,
    ) -> str:
        """Generate cache key for search results.
        
        Args:
            query: Search query
            task: Optional task filter
            max_results: Maximum results
            
        Returns:
            Cache key
        """
        return self._make_key("search", query, task, max_results)
    
    def _make_model_info_key(self, model_id: str) -> str:
        """Generate cache key for model info.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Cache key
        """
        return self._make_key("info", model_id)
    
    def _make_model_card_key(self, model_id: str) -> str:
        """Generate cache key for model card.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Cache key
        """
        return self._make_key("card", model_id)
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value to bytes for caching.
        
        Args:
            value: Value to serialize
            
        Returns:
            Serialized bytes
        """
        if isinstance(value, bytes):
            return value
        return json.dumps(value, default=str).encode("utf-8")
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize cached bytes to value.
        
        Args:
            data: Cached bytes
            
        Returns:
            Deserialized value
        """
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Return raw bytes if not JSON
            return data
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get cached value by key.
        
        Graceful degradation: Returns None on cache errors.
        
        Args:
            key: Cache key
            
        Returns:
            Cached bytes or None if not found/error
        """
        if not self._initialized or not self._client:
            self._stats.miss_count += 1
            return None
        
        try:
            data = await self._client.get(key)
            
            if data:
                self._stats.hit_count += 1
                logger.debug(
                    f"Cache hit: {key}",
                    extra={"event": "cache_hit", "key": key}
                )
            else:
                self._stats.miss_count += 1
                logger.debug(
                    f"Cache miss: {key}",
                    extra={"event": "cache_miss", "key": key}
                )
            
            return data
            
        except Exception as e:
            self._stats.error_count += 1
            logger.warning(
                f"Cache get failed for {key}, continuing without cache: {e}",
                extra={
                    "event": "cache_get_error",
                    "key": key,
                    "error": str(e),
                }
            )
            return None
    
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set cached value with optional TTL.
        
        Graceful degradation: Silently ignores cache errors.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        if not self._initialized or not self._client:
            return
        
        try:
            # Use configured TTL if not specified
            ttl = ttl_seconds or self._config.ttl_api_response_seconds
            
            await self._client.setex(key, ttl, value)
            self._stats.set_count += 1
            
            logger.debug(
                f"Cached {key} with TTL={ttl}s",
                extra={"event": "cache_set", "key": key, "ttl": ttl}
            )
            
        except Exception as e:
            self._stats.error_count += 1
            logger.warning(
                f"Cache set failed for {key}, continuing without cache: {e}",
                extra={
                    "event": "cache_set_error",
                    "key": key,
                    "error": str(e),
                }
            )
    
    async def delete(self, key: str) -> None:
        """Delete cached value.
        
        Graceful degradation: Silently ignores cache errors.
        
        Args:
            key: Cache key to delete
        """
        if not self._initialized or not self._client:
            return
        
        try:
            await self._client.delete(key)
            self._stats.delete_count += 1
            
            logger.debug(
                f"Deleted cache: {key}",
                extra={"event": "cache_delete", "key": key}
            )
            
        except Exception as e:
            self._stats.error_count += 1
            logger.warning(
                f"Cache delete failed for {key}, continuing: {e}",
                extra={
                    "event": "cache_delete_error",
                    "key": key,
                    "error": str(e),
                }
            )
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.
        
        Graceful degradation: Returns False on cache errors.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self._initialized or not self._client:
            return False
        
        try:
            result = await self._client.exists(key)
            return result > 0
            
        except Exception as e:
            self._stats.error_count += 1
            logger.warning(
                f"Cache exists check failed for {key}, continuing: {e}",
                extra={
                    "event": "cache_exists_error",
                    "key": key,
                    "error": str(e),
                }
            )
            return False
    
    # Convenience methods for HuggingFace data types
    
    async def get_search_results(
        self,
        query: str,
        task: Optional[str] = None,
        max_results: int = 20,
    ) -> Optional[Any]:
        """Get cached search results.
        
        Args:
            query: Search query
            task: Optional task filter
            max_results: Maximum results
            
        Returns:
            Cached search results or None
        """
        key = self._make_search_key(query, task, max_results)
        data = await self.get(key)
        
        if data:
            return self._deserialize(data)
        return None
    
    async def set_search_results(
        self,
        query: str,
        results: Any,
        task: Optional[str] = None,
        max_results: int = 20,
    ) -> None:
        """Cache search results.
        
        Args:
            query: Search query
            results: Search results to cache
            task: Optional task filter
            max_results: Maximum results
        """
        key = self._make_search_key(query, task, max_results)
        ttl = self._config.ttl_search_result_seconds
        
        await self.set(key, self._serialize(results), ttl_seconds=ttl)
    
    async def get_model_info(self, model_id: str) -> Optional[Any]:
        """Get cached model info.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Cached model info or None
        """
        key = self._make_model_info_key(model_id)
        data = await self.get(key)
        
        if data:
            return self._deserialize(data)
        return None
    
    async def set_model_info(
        self,
        model_id: str,
        model_info: Any,
    ) -> None:
        """Cache model info.
        
        Args:
            model_id: HuggingFace model ID
            model_info: Model info to cache
        """
        key = self._make_model_info_key(model_id)
        ttl = self._config.ttl_api_response_seconds
        
        await self.set(key, self._serialize(model_info), ttl_seconds=ttl)
    
    async def get_model_card(self, model_id: str) -> Optional[str]:
        """Get cached model card content.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Cached model card content or None
        """
        key = self._make_model_card_key(model_id)
        data = await self.get(key)
        
        if data:
            # Decode as string
            return data.decode("utf-8") if isinstance(data, bytes) else data
        return None
    
    async def set_model_card(
        self,
        model_id: str,
        card_content: str,
    ) -> None:
        """Cache model card content.
        
        Args:
            model_id: HuggingFace model ID
            card_content: Model card content to cache
        """
        key = self._make_model_card_key(model_id)
        ttl = self._config.ttl_model_card_seconds
        
        await self.set(key, card_content.encode("utf-8"), ttl_seconds=ttl)
    
    async def health_check(self) -> bool:
        """Check if cache is healthy.
        
        Returns:
            True if cache is accessible, False otherwise
        """
        if not self._initialized or not self._client:
            return False
        
        try:
            await self._client.ping()
            return True
        except Exception as e:
            logger.warning(
                f"Cache health check failed: {e}",
                extra={"event": "cache_health_check_failed", "error": str(e)}
            )
            return False
    
    async def close(self) -> None:
        """Close cache connection.
        
        Side effects:
        - Sets initialized to False
        - Closes Redis client and pool
        """
        self._initialized = False
        
        if self._client:
            await self._client.close()
        
        if self._pool:
            await self._pool.disconnect()
        
        logger.info(
            "CacheManager closed",
            extra={"event": "cache_close"}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "hit_count": self._stats.hit_count,
            "miss_count": self._stats.miss_count,
            "error_count": self._stats.error_count,
            "set_count": self._stats.set_count,
            "delete_count": self._stats.delete_count,
            "hit_rate": self._stats.hit_rate,
            "initialized": self._initialized,
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"CacheManager("
            f"hits={stats['hit_count']}, "
            f"misses={stats['miss_count']}, "
            f"hit_rate={stats['hit_rate']:.2%})"
        )

