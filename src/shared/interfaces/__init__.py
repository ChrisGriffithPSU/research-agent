"""Abstract interfaces for shared infrastructure.

Allows dependency injection for testability and flexibility.
All concrete implementations must honor these contracts.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime


# ==================== Cache Interfaces ====================

class IRedisConnection(Protocol):
    """Protocol for Redis connection."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the connection."""
        ...
    
    @abstractmethod
    async def get_connection(self) -> Any:
        """Get a connection from the pool.
        
        Returns:
            Redis client instance
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection pool."""
        ...
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected to Redis.
        
        Returns:
            True if connected, False otherwise
        """
        ...


class ISerializer(Protocol):
    """Protocol for cache value serialization."""
    
    @abstractmethod
    def serialize(self, value: Any) -> bytes:
        """Serialize a value to bytes.
        
        Args:
            value: Value to serialize
            
        Returns:
            Serialized bytes
        """
        ...
    
    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to a value.
        
        Args:
            data: Serialized bytes
            
        Returns:
            Deserialized value
        """
        ...


class ICacheBackend(Protocol):
    """Protocol for cache operations.
    
    This is the primary interface for cache operations.
    Implementations: RedisCache, InMemoryCache, etc.
    """
    
    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached bytes or None if not found
        """
        ...
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Optional TTL in seconds
        """
        ...
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key from cache.
        
        Args:
            key: Cache key to delete
        """
        ...
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache.
        
        Args:
            key: Cache key to check
            
        Returns:
            True if key exists, False otherwise
        """
        ...
    
    @abstractmethod
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Get multiple values from cache.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dict of key -> value (missing keys not included)
        """
        ...
    
    @abstractmethod
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern.
        
        Args:
            pattern: Key pattern (e.g., "cache:llm:*")
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the cache backend."""
        ...



# ==================== LLM Interfaces ====================

class ILLMClient(Protocol):
    """Protocol for individual LLM client operations."""
    
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        **kwargs,
    ) -> 'LLMResponse':
        """Complete a prompt.
        
        Args:
            prompt: User prompt
            model: Model name
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            system: System prompt
            **kwargs: Additional provider-specific args
            
        Returns:
            LLMResponse with generated content
        """
        ...
    
    @abstractmethod
    async def generate_embedding(self, text: str, model: str, **kwargs) -> List[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            model: Embedding model name
            **kwargs: Additional args
            
        Returns:
            List of embedding values
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        ...
    
    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """Get list of available models.
        
        Returns:
            List of model names
        """
        ...


class LLMResponse:
    """Response from LLM completion.
    
    Attributes:
        content: Generated text content
        model: Model used for generation
        provider: Provider name (e.g., "openai", "anthropic")
        usage: Token usage information
        cost: Cost of the request in dollars
    """
    
    def __init__(
        self,
        content: str,
        model: str,
        provider: str,
        usage: Optional[Dict[str, int]] = None,
        cost: Optional[float] = None,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.cost = cost
    
    def __repr__(self) -> str:
        return f"LLMResponse(content={self.content[:50]}..., model={self.model}, provider={self.provider})"


class ILLMRouter(Protocol):
    """Protocol for LLM routing and failover.
    
    Routes requests to appropriate providers based on task type.
    Handles failover and load balancing.
    """
    
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """Complete a prompt using appropriate provider.
        
        Args:
            prompt: User prompt
            task_type: Type of task (extraction, synthesis, etc.)
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            force_provider: Override routing with specific provider
            **kwargs: Additional args
            
        Returns:
            LLMResponse from selected provider
        """
        ...
    
    @abstractmethod
    async def generate_embedding(
        self,
        text: str,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> List[float]:
        """Generate embedding using appropriate provider.
        
        Args:
            text: Text to embed
            force_provider: Override routing
            **kwargs: Additional args
            
        Returns:
            List of embedding values
        """
        ...
    
    @abstractmethod
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers.
        
        Returns:
            Dict mapping provider name to health status
        """
        ...
    
    @abstractmethod
    def add_provider(self, name: str, client: ILLMClient) -> None:
        """Add a provider after initialization.
        
        Args:
            name: Provider name
            client: ILLMClient implementation
        """
        ...
    
    @abstractmethod
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary.
        
        Returns:
            Dict with cost information by provider
        """
        ...


# ==================== Messaging Interfaces ====================

class IMessageConnection(Protocol):
    """Protocol for message broker connection.
    
    Handles connection lifecycle and channel management.
    """
    
    @abstractmethod
    async def connect(self) -> None:
        """Connect to the message broker."""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        ...
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected to broker.
        
        Returns:
            True if connected, False otherwise
        """
        ...
    
    @property
    @abstractmethod
    def channel(self) -> Any:
        """Get the broker channel.
        
        Returns:
            Broker-specific channel object
        """
        ...


class IRetryStrategy(Protocol):
    """Protocol for retry strategies."""
    
    @abstractmethod
    async def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if should retry after an error.
        
        Args:
            attempt: Current attempt number (1-based)
            error: The error that occurred
            
        Returns:
            True if should retry, False otherwise
        """
        ...
    
    @abstractmethod
    def get_backoff(self, attempt: int) -> float:
        """Get backoff delay for an attempt.
        
        Args:
            attempt: Current attempt number
            
        Returns:
            Delay in seconds before next retry
        """
        ...


class ICircuitBreaker(Protocol):
    """Protocol for circuit breaker pattern.
    
    Prevents cascading failures by stopping requests to failing services.
    """
    
    @abstractmethod
    async def call(self, func, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitOpenError: If circuit is open
        """
        ...
    
    @abstractmethod
    def is_open(self) -> bool:
        """Check if circuit is open.
        
        Returns:
            True if circuit is open (requests blocked)
        """
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        ...


class IRateLimiter(Protocol):
    """Protocol for rate limiting.
    
    Controls the rate of requests to external services.
    """
    
    @abstractmethod
    async def acquire(self) -> None:
        """Acquire permission to make a request.
        
        Blocks if rate limit is exceeded.
        """
        ...
    
    @abstractmethod
    async def get_delay(self) -> float:
        """Get the delay until next request is allowed.
        
        Returns:
            Delay in seconds (0 if available now)
        """
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset rate limiter state."""
        ...


class IMessagePublisher(Protocol):
    """Protocol for message publishing.
    
    Publishes messages to a message broker.
    """
    
    @abstractmethod
    async def publish(
        self,
        message: Any,
        routing_key: str,
        mandatory: bool = False,
        immediate: bool = False,
    ) -> None:
        """Publish a message.
        
        Args:
            message: Message to publish
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the publisher."""
        ...


class IMessageConsumer(Protocol):
    """Protocol for message consuming."""
    
    @abstractmethod
    async def consume(
        self,
        queue: str,
        callback: callable,
        **kwargs,
    ) -> None:
        """Start consuming messages from a queue.
        
        Args:
            queue: Queue name
            callback: Callback function for messages
            **kwargs: Additional consumer options
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the consumer."""
        ...



# ==================== Database Interfaces ====================

class IDatabaseEngine(Protocol):
    """Protocol for database engine."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the database engine."""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the database engine."""
        ...
    
    @abstractmethod
    def get_session_factory(self):
        """Get the session factory.
        
        Returns:
            Session factory callable
        """
        ...



class IDatabaseSession(Protocol):
    """Protocol for database session."""
    
    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction."""
        ...
    
    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close the session."""
        ...
    
    @abstractmethod
    def add(self, obj: Any) -> None:
        """Add an object to the session."""
        ...
    
    @abstractmethod
    async def execute(self, query: Any, **kwargs) -> Any:
        """Execute a query."""
        ...
    
    @abstractmethod
    async def scalar(self, query: Any, **kwargs) -> Any:
        """Execute a scalar query."""
        ...



# ==================== HTTP Client Interfaces ====================

class IHTTPClient(Protocol):
    """Protocol for HTTP client operations."""
    
    @abstractmethod
    async def get(self, url: str, **kwargs) -> 'HTTPResponse':
        """Perform GET request.
        
        Args:
            url: URL to request
            **kwargs: Additional request options
            
        Returns:
            HTTPResponse
        """
        ...
    
    @abstractmethod
    async def post(self, url: str, **kwargs) -> 'HTTPResponse':
        """Perform POST request."""
        ...
    
    @abstractmethod
    async def put(self, url: str, **kwargs) -> 'HTTPResponse':
        """Perform PUT request."""
        ...
    
    @abstractmethod
    async def delete(self, url: str, **kwargs) -> 'HTTPResponse':
        """Perform DELETE request."""
        ...
    
    @abstractmethod
    async def aclose(self) -> None:
        """Close the client."""
        ...


class HTTPResponse:
    """HTTP response wrapper.
    
    Attributes:
        status_code: HTTP status code
        content: Response content as bytes
        headers: Response headers
    """
    
    def __init__(
        self,
        status_code: int,
        content: bytes,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
    
    @property
    def text(self) -> str:
        """Get content as text."""
        return self.content.decode('utf-8')
    
    def json(self) -> Any:
        """Parse content as JSON."""
        import json
        return json.loads(self.content)
    
    def raise_for_status(self) -> None:
        """Raise error if status code indicates failure."""
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code}: {self.text[:200]}", status_code=self.status_code)


class HTTPError(Exception):
    """HTTP error exception."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ==================== Export ====================

__all__ = [
    # Cache
    "IRedisConnection",
    "ISerializer",
    "ICacheBackend",
    # LLM
    "ILLMClient",
    "LLMResponse",
    "ILLMRouter",
    # Messaging
    "IMessageConnection",
    "IRetryStrategy",
    "ICircuitBreaker",
    "IRateLimiter",
    "IMessagePublisher",
    "IMessageConsumer",
    # Database
    "IDatabaseEngine",
    "IDatabaseSession",
    # HTTP
    "IHTTPClient",
    "HTTPResponse",
    "HTTPError",
]

