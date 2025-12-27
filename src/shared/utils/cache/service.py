"""Refactored cache service with dependency injection.

This module provides a clean separation between cache interface and implementation.
All dependencies are injected through the constructor for testability.
"""
import logging
from typing import Any, Dict, List, Optional

from src.shared.interfaces import (
    ICacheBackend,
    ISerializer,
)
from src.shared.utils.cache.keys import validate_cache_key


logger = logging.getLogger(__name__)


class DefaultJSONSerializer:
    """Default JSON serializer for cache values.
    
    Handles basic Python types that are JSON-serializable.
    """
    
    def serialize(self, value: Any) -> bytes:
        """Serialize value to JSON bytes."""
        return json.dumps(value, default=str).encode('utf-8')
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize JSON bytes to value."""
        return json.loads(data.decode('utf-8'))


# Import json for serializer
import json


class CacheService:
    """High-level cache service with injectable dependencies.
    
    This is the main cache interface used by the application.
    All dependencies are injected through the constructor.
    
    Example:
        # Production use with Redis
        backend = RedisCacheBackend(redis_url="redis://localhost:6379/0")
        cache = CacheService(cache_backend=backend)
        await cache.initialize()
        
        # Testing use with in-memory cache
        from src.shared.testing.mocks import InMemoryCacheBackend
        cache = CacheService(cache_backend=InMemoryCacheBackend())
        
        # Use cache
        await cache.set_cached("key", {"data": "value"}, ttl=3600)
        value = await cache.get_cached("key")
    
    Attributes:
        _backend: Cache backend implementation (ICacheBackend)
        _serializer: Serializer for values (ISerializer)
        _initialized: Whether the service has been initialized
    """
    
    def __init__(
        self,
        cache_backend: ICacheBackend,
        serializer: Optional[ISerializer] = None,
    ):
        """Initialize cache service.
        
        Args:
            cache_backend: Cache backend implementation (Redis, memory, etc.)
            serializer: Serializer for cache values (optional, default JSON)
        """
        self._backend = cache_backend
        self._serializer = serializer or DefaultJSONSerializer()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the cache backend.
        
        Calls initialize on the backend if it has that method.
        """
        if hasattr(self._backend, 'initialize'):
            await self._backend.initialize()
        self._initialized = True
        logger.info("CacheService initialized")
    
    async def get_cached(self, cache_key: str) -> Optional[Any]:
        """Get a value from cache.
        
        Args:
            cache_key: Cache key to retrieve
            
        Returns:
            Cached value or None if not found
        """
        validate_cache_key(cache_key)
        
        try:
            data = await self._backend.get(cache_key)
            
            if data is None:
                logger.debug(f"Cache miss: {cache_key}")
                return None
            
            value = self._serializer.deserialize(data)
            logger.debug(f"Cache hit: {cache_key}")
            return value
            
        except Exception as e:
            logger.error(f"Cache get failed for key {cache_key}: {e}", exc_info=True)
            return None
    
    async def set_cached(
        self,
        cache_key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Set a value in cache.
        
        Args:
            cache_key: Cache key to store
            value: Value to cache
            ttl: Time-to-live in seconds (None = no expiration)
        """
        validate_cache_key(cache_key)
        
        if value is None:
            logger.debug(f"Skipping cache set for None value: {cache_key}")
            return
        
        try:
            serialized = self._serializer.serialize(value)
            await self._backend.set(cache_key, serialized, ttl_seconds=ttl)
            logger.debug(f"Set cache key: {cache_key}, TTL: {ttl}")
            
        except Exception as e:
            logger.error(f"Cache set failed for key {cache_key}: {e}", exc_info=True)
            raise
    
    async def delete(self, cache_key: str) -> None:
        """Delete a value from cache.
        
        Args:
            cache_key: Cache key to delete
        """
        validate_cache_key(cache_key)
        
        try:
            await self._backend.delete(cache_key)
            logger.debug(f"Deleted cache key: {cache_key}")
            
        except Exception as e:
            logger.error(f"Cache delete failed for key {cache_key}: {e}", exc_info=True)
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern.
        
        Args:
            pattern: Key pattern (e.g., "cache:llm:*")
        """
        try:
            await self._backend.delete_pattern(pattern)
            logger.info(f"Deleted keys matching pattern: {pattern}")
            
        except Exception as e:
            logger.error(f"Cache delete pattern failed for {pattern}: {e}", exc_info=True)
    
    async def get_many(self, cache_keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache.
        
        Args:
            cache_keys: List of cache keys
            
        Returns:
            Dict of key -> value (missing keys not included)
        """
        if not cache_keys:
            return {}
        
        try:
            results = await self._backend.get_many(cache_keys)
            return {
                k: self._serializer.deserialize(v)
                for k, v in results.items()
            }
            
        except Exception as e:
            logger.error(f"Cache get_many failed: {e}", exc_info=True)
            return {}
    
    async def exists(self, cache_key: str) -> bool:
        """Check if a key exists in cache.
        
        Args:
            cache_key: Cache key to check
            
        Returns:
            True if key exists, False otherwise
        """
        validate_cache_key(cache_key)
        
        try:
            return await self._backend.exists(cache_key)
            
        except Exception as e:
            logger.error(f"Cache exists check failed for {cache_key}: {e}", exc_info=True)
            return False
    
    async def close(self) -> None:
        """Close cache service and backend connection."""
        await self._backend.close()
        self._initialized = False
        logger.info("CacheService closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with backend type information
        """
        return {
            "backend_type": type(self._backend).__name__,
            "initialized": self._initialized,
        }
    
    @property
    def backend(self) -> ICacheBackend:
        """Get the underlying backend (for testing)."""
        return self._backend


class CacheServiceFactory:
    """Factory for creating CacheService instances.
    
    Provides convenient methods for creating services with common configurations.
    """
    
    @staticmethod
    def create_redis(
        redis_url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        pool_size: int = 10,
    ) -> CacheService:
        """Create CacheService with Redis backend.
        
        Args:
            redis_url: Redis connection URL
            password: Optional Redis password
            pool_size: Connection pool size
            
        Returns:
            Configured CacheService with Redis backend
        """
        from src.shared.utils.cache.connection import RedisConnection
        
        connection = RedisConnection(
            redis_url=redis_url,
            password=password,
            pool_size=pool_size,
        )
        
        backend = RedisCacheBackend(connection=connection)
        
        return CacheService(cache_backend=backend)
    
    @staticmethod
    def create_in_memory() -> CacheService:
        """Create CacheService with in-memory backend.
        
        Useful for testing and development without Redis.
        
        Returns:
            CacheService with InMemoryCacheBackend
        """
        from src.shared.testing.mocks import InMemoryCacheBackend
        
        backend = InMemoryCacheBackend()
        
        return CacheService(cache_backend=backend)
    
    @staticmethod
    def create_from_backend(backend: ICacheBackend) -> CacheService:
        """Create CacheService from existing backend.
        
        Args:
            backend: ICacheBackend implementation
            
        Returns:
            CacheService wrapping the provided backend
        """
        return CacheService(cache_backend=backend)


class RedisCacheBackend:
    """Redis cache backend implementation.
    
    Wraps Redis connection for use with CacheService.
    
    Attributes:
        connection: Redis connection instance
    """
    
    def __init__(self, connection: 'RedisConnection'):
        """Initialize Redis backend.
        
        Args:
            connection: Redis connection instance
        """
        self.connection = connection
    
    async def initialize(self) -> None:
        """Initialize the Redis connection."""
        await self.connection.initialize()
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get value from Redis."""
        redis = await self.connection.get_connection()
        data = await redis.get(key)
        return data
    
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set value in Redis."""
        redis = await self.connection.get_connection()
        await redis.set(key, value, ex=ttl_seconds)
    
    async def delete(self, key: str) -> None:
        """Delete key from Redis."""
        redis = await self.connection.get_connection()
        await redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        redis = await self.connection.get_connection()
        return await redis.exists(key)
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Get multiple values from Redis."""
        if not keys:
            return {}
        
        redis = await self.connection.get_connection()
        values = await redis.mget(keys)
        
        result = {}
        for key, data in zip(keys, values):
            if data is not None:
                result[key] = data
        
        return result
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete keys matching pattern from Redis."""
        redis = await self.connection.get_connection()
        
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)
        
        if keys:
            await redis.delete(*keys)
    
    async def close(self) -> None:
        """Close the Redis connection."""
        await self.connection.close()
    
    async def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return await self.connection.is_connected()


# Remove the old global factory function
# The new pattern uses explicit dependency injection


__all__ = [
    "CacheService",
    "CacheServiceFactory",
    "RedisCacheBackend",
    "DefaultJSONSerializer",
]
