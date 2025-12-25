"""Redis connection manager with pooling."""
import logging
from typing import Optional

try:
    from redis.asyncio import Redis, ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore
    ConnectionPool = None  # type: ignore

from src.shared.exceptions.cache import CacheConnectionError


logger = logging.getLogger(__name__)


class RedisConnection:
    """Redis connection manager with pooling.
    
    Manages Redis connection pool for efficient async operations.
    Supports password authentication and configurable pool size.
    
    Args:
        redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        password: Optional password for authentication
        pool_size: Number of connections in pool (default: 10)
        socket_timeout: Socket timeout in seconds (default: 5)
        socket_connect_timeout: Connection timeout in seconds (default: 5)
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        pool_size: int = 10,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
    ):
        """Initialize Redis connection.
        
        Args:
            redis_url: Redis connection URL
            password: Optional password
            pool_size: Pool size
            socket_timeout: Socket timeout
            socket_connect_timeout: Connection timeout
        """
        self.redis_url = redis_url
        self.password = password
        self.pool_size = pool_size
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        
        # Redis pool and client
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None

        if not REDIS_AVAILABLE:
            logger.warning(
                "Redis library not installed. Install with: pip install redis[hiredis]"
            )

        logger.debug(
            f"RedisConnection initialized (redis_available={REDIS_AVAILABLE})",
            extra={
                "redis_url": redis_url,
                "pool_size": pool_size,
                "has_password": password is not None,
                "redis_available": REDIS_AVAILABLE,
            },
        )
    
    async def get_connection(self) -> Redis:
        """Get Redis client from pool.

        Returns:
            Redis client instance

        Raises:
            CacheConnectionError: If connection not available
        """
        if not REDIS_AVAILABLE:
            raise CacheConnectionError(
                "Redis library not installed. Install with: pip install redis[hiredis]"
            )

        if self._redis is None:
            raise CacheConnectionError(
                "Redis not initialized. Call initialize() first."
            )

        return self._redis
    
    async def initialize(self) -> None:
        """Initialize Redis connection pool.

        This must be called before using get_connection().

        Raises:
            CacheConnectionError: If Redis unavailable or connection fails
        """
        if not REDIS_AVAILABLE:
            raise CacheConnectionError(
                "Redis library not installed. Install with: pip install redis[hiredis]"
            )

        logger.info("Initializing Redis connection pool")

        try:
            # Create connection pool
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                password=self.password,
                max_connections=self.pool_size,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=False,  # Let serializer handle decoding
            )

            # Create Redis client with pool
            self._redis = Redis(connection_pool=self._pool)

            # Test connection
            await self._redis.ping()

            logger.info(
                "Redis connection pool initialized successfully",
                extra={"pool_size": self.pool_size, "redis_url": self.redis_url},
            )

        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}", exc_info=True)
            raise CacheConnectionError(
                f"Failed to connect to Redis at {self.redis_url}: {e}"
            ) from e
    
    async def ping(self) -> bool:
        """Check if Redis connection is healthy.

        Returns:
            True if Redis responds to PING, False otherwise
        """
        if not REDIS_AVAILABLE or self._redis is None:
            return False

        try:
            result = await self._redis.ping()
            return bool(result)
        except Exception as e:
            logger.error(f"Redis ping failed: {e}", exc_info=True)
            return False
    
    async def close(self) -> None:
        """Close all connections in pool.

        Call this when shutting down the application.
        """
        if self._redis is None:
            return

        logger.info("Closing Redis connection pool")

        try:
            # Close Redis client (which closes pool)
            await self._redis.aclose()
            self._redis = None
            self._pool = None

            logger.info("Redis connection pool closed")

        except Exception as e:
            logger.error(f"Error closing Redis pool: {e}", exc_info=True)
    
    def get_pool_info(self) -> dict:
        """Get information about connection pool.
        
        Returns:
            Dict with pool statistics
        """
        if self._pool is None:
            return {
                "initialized": False,
                "redis_url": self.redis_url,
                "pool_size": self.pool_size,
            }
        
        # Placeholder for actual pool info
        # In production, would use self._pool.get_connected_count(), etc.
        return {
            "initialized": True,
            "redis_url": self.redis_url,
            "pool_size": self.pool_size,
        }

