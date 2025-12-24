"""Cache service - main cache interface."""
import functools
import logging
from typing import Any, Callable, Dict, List, Optional

from src.shared.utils.cache.connection import RedisConnection
from src.shared.utils.cache.keys import (
    build_cache_key,
    build_hashed_cache_key,
    validate_cache_key,
)
from src.shared.utils.cache.serializers import JSONSerializer, Serializer, get_serializer


logger = logging.getLogger(__name__)


class CacheService:
    """High-level cache service orchestrating Redis operations.
    
    Provides:
    - Simple get/set/delete operations
    - Pattern-based key deletion
    - Batch operations (get_many)
    - Metrics collection
    - Serialization/deserialization
    
    Example:
        cache = CacheService(redis_url="redis://localhost:6379/0")
        await cache.initialize()
        
        # Set value
        await cache.set_cached("key", {"data": "value"}, ttl=3600)
        
        # Get value
        value = await cache.get_cached("key")
        
        # Delete
        await cache.delete("key")
        
        # Get metrics
        stats = cache.get_stats()
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        pool_size: int = 10,
        serializer: Optional[Serializer] = None,
    ):
        """Initialize cache service.
        
        Args:
            redis_url: Redis connection URL
            password: Optional Redis password
            pool_size: Connection pool size
            serializer: Serializer for cache values (default: JSONSerializer)
        """
        self.redis_url = redis_url
        self.password = password
        self.pool_size = pool_size
        self.serializer = serializer or JSONSerializer()
        
        # Initialize connection and metrics
        self.connection = RedisConnection(
            redis_url=redis_url,
            password=password,
            pool_size=pool_size,
        )
        from src.shared.utils.cache.metrics import CacheMetrics
        self.metrics = CacheMetrics()
        
        logger.info(
            f"CacheService initialized",
            extra={
                "redis_url": redis_url,
                "pool_size": pool_size,
                "serializer_type": type(self.serializer).__name__,
            },
        )
    
    async def initialize(self) -> None:
        """Initialize Redis connection pool.
        
        Must be called before using cache operations.
        """
        logger.info("Initializing CacheService")
        await self.connection.initialize()
        logger.info("CacheService initialized successfully")
    
    async def get_cached(self, cache_key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            cache_key: Cache key to retrieve
        
        Returns:
            Cached value or None if not found
        
        Example:
            value = await cache.get_cached("user:123:preferences")
            if value is None:
                print("Not cached")
        """
        # Validate key
        validate_cache_key(cache_key)
        
        try:
            # Placeholder for actual Redis get
            # In production:
            # connection = await self.connection.get_connection()
            # data = await connection.get(cache_key)
            # await self.connection._pool.release(connection)
            # 
            # if data is None:
            #     self.metrics.record_miss(cache_key)
            #     return None
            # 
            # value = self.serializer.deserialize(data)
            # self.metrics.record_hit(cache_key)
            # return value
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache get failed for key {cache_key}: {e}",
                extra={"cache_key": cache_key, "error": str(e)},
                exc_info=True,
            )
            self.metrics.record_miss(cache_key)
            return None
    
    async def set_cached(
        self,
        cache_key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Set value in cache.
        
        Args:
            cache_key: Cache key to store
            value: Value to cache
            ttl: Time-to-live in seconds (None = no expiration)
        
        Example:
            await cache.set_cached("user:123:preferences", {"theme": "dark"}, ttl=3600)
        """
        # Validate key
        validate_cache_key(cache_key)
        
        # Skip None values
        if value is None:
            logger.debug(f"Skipping cache set for None value: {cache_key}")
            return
        
        try:
            # Serialize value
            serialized = self.serializer.serialize(value)
            
            # Placeholder for actual Redis set
            # In production:
            # connection = await self.connection.get_connection()
            # await connection.set(cache_key, serialized, ex=ttl)
            # await self.connection._pool.release(connection)
            # 
            # self.metrics.record_size(len(serialized))
            # logger.debug(
            #     f"Set cache key: {cache_key}, TTL: {ttl}, Size: {len(serialized)}"
            # )
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache set failed for key {cache_key}: {e}",
                extra={"cache_key": cache_key, "error": str(e)},
                exc_info=True,
            )
            raise
    
    async def delete(self, cache_key: str) -> None:
        """Delete value from cache.
        
        Args:
            cache_key: Cache key to delete
        
        Example:
            await cache.delete("user:123:preferences")
        """
        validate_cache_key(cache_key)
        
        try:
            # Placeholder for actual Redis delete
            # In production:
            # connection = await self.connection.get_connection()
            # await connection.delete(cache_key)
            # await self.connection._pool.release(connection)
            # 
            # logger.debug(f"Deleted cache key: {cache_key}")
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache delete failed for key {cache_key}: {e}",
                extra={"cache_key": cache_key, "error": str(e)},
                exc_info=True,
            )
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern.
        
        Args:
            pattern: Key pattern (e.g., "cache:llm:*")
        
        Example:
            await cache.delete_pattern("cache:llm:*")  # Invalidates all LLM cache
        """
        try:
            # Placeholder for actual Redis scan/delete
            # In production:
            # connection = await self.connection.get_connection()
            # keys = await connection.keys(pattern)
            # if keys:
            #     await connection.delete(*keys)
            # await self.connection._pool.release(connection)
            # 
            # logger.info(f"Deleted {len(keys)} keys matching pattern: {pattern}")
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache delete pattern failed for {pattern}: {e}",
                extra={"pattern": pattern, "error": str(e)},
                exc_info=True,
            )
    
    async def get_many(self, cache_keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache efficiently.
        
        Args:
            cache_keys: List of cache keys
        
        Returns:
            Dict of key -> value (missing keys not included)
        
        Example:
            values = await cache.get_many([
                "user:123:preferences",
                "user:456:preferences",
                "config:llm",
            ])
        """
        if not cache_keys:
            return {}
        
        # Remove duplicates
        unique_keys = list(set(cache_keys))
        
        logger.debug(f"Getting {len(unique_keys)} cache keys")
        
        results = {}
        
        try:
            # Placeholder for actual Redis MGET
            # In production:
            # connection = await self.connection.get_connection()
            # values = await connection.mget(unique_keys)
            # await self.connection._pool.release(connection)
            # 
            # for key, data in zip(unique_keys, values):
            #     if data is not None:
            #         results[key] = self.serializer.deserialize(data)
            #         self.metrics.record_hit(key)
            #     else:
            #         self.metrics.record_miss(key)
            # 
            # return results
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache get_many failed: {e}",
                extra={
                    "keys_count": len(cache_keys),
                    "error": str(e),
                },
                exc_info=True,
            )
            # Return empty dict on error
            return {}
    
    async def exists(self, cache_key: str) -> bool:
        """Check if key exists in cache.
        
        Args:
            cache_key: Cache key to check
        
        Returns:
            True if key exists, False otherwise
        """
        validate_cache_key(cache_key)
        
        try:
            # Placeholder for actual Redis EXISTS
            # In production:
            # connection = await self.connection.get_connection()
            # exists = await connection.exists(cache_key)
            # await self.connection._pool.release(connection)
            # return bool(exists)
            raise NotImplementedError("Redis client not installed")
        
        except Exception as e:
            logger.error(
                f"Cache exists check failed for {cache_key}: {e}",
                extra={"cache_key": cache_key, "error": str(e)},
                exc_info=True,
            )
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with metrics from MetricsTracker
        """
        return self.metrics.get_stats()
    
    async def close(self) -> None:
        """Close cache service and Redis connection."""
        logger.info("Closing CacheService")
        await self.connection.close()
        logger.info("CacheService closed")
    
    def _attach_to_decorators(self, decorator: Callable) -> None:
        """Attach cache service instance to decorated function.
        
        This allows decorators to access the cache service.
        """
        @functools.wraps(decorator)
        def wrapper(*args, **kwargs):
            # Store cache service in function attributes for decorator access
            wrapper._cache_service = self
            return decorator(*args, **kwargs)
        
        return wrapper


def get_cache_service(
    redis_url: str = "redis://localhost:6379/0",
    password: Optional[str] = None,
    pool_size: int = 10,
    serializer_type: str = "json",
) -> CacheService:
    """Factory function to create and initialize cache service.
    
    Args:
        redis_url: Redis connection URL
        password: Optional Redis password
        pool_size: Connection pool size
        serializer_type: Type of serializer ("json", "pickle", "string")
    
    Returns:
        Initialized CacheService instance
    
    Example:
        # Create and initialize
        cache = get_cache_service(redis_url="redis://localhost:6379/0")
        await cache.initialize()
        
        # Attach to decorators
        @cached(ttl=3600, namespace="llm")
        async def my_function():
            # Now has access to cache via decorator
            pass
    """
    # Create cache service
    cache = CacheService(
        redis_url=redis_url,
        password=password,
        pool_size=pool_size,
        serializer=get_serializer(serializer_type),
    )
    
    return cache

