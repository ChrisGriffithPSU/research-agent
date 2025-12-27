"""Mock implementations for testing without external services.

All mocks honor the interface contracts defined in src.shared.interfaces.
Use these for unit tests and integration tests that need to run fast.
"""
import asyncio
import fnmatch
import json
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta


# ==================== Cache Mocks ====================

class InMemoryCacheBackend:
    """In-memory cache backend for testing.
    
    Stores values in a dictionary. No Redis connection required.
    Perfect for unit tests and CI/CD pipelines.
    
    Example:
        cache = InMemoryCacheBackend()
        await cache.set("key", b"value", ttl=3600)
        result = await cache.get("key")  # b"value"
    """
    
    def __init__(self):
        self._storage: Dict[str, tuple[bytes, Optional[int]]] = {}
        self._expiry: Dict[str, datetime] = {}
    
    async def initialize(self) -> None:
        """No initialization needed for in-memory cache."""
        pass
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get value from memory cache."""
        now = datetime.utcnow()
        
        # Check if expired
        if key in self._expiry and self._expiry[key] < now:
            del self._storage[key]
            del self._expiry[key]
            return None
        
        if key in self._storage:
            return self._storage[key][0]
        return None
    
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set value in memory cache."""
        self._storage[key] = (value, ttl_seconds)
        
        if ttl_seconds:
            self._expiry[key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        elif key in self._expiry:
            del self._expiry[key]
    
    async def delete(self, key: str) -> None:
        """Delete value from memory cache."""
        self._storage.pop(key, None)
        self._expiry.pop(key, None)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists (and not expired)."""
        now = datetime.utcnow()
        
        if key in self._expiry and self._expiry[key] < now:
            del self._storage[key]
            del self._expiry[key]
            return False
        
        return key in self._storage
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Get multiple values from memory cache."""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete keys matching pattern (simple glob matching)."""
        keys_to_delete = [k for k in self._storage if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            await self.delete(key)
    
    async def close(self) -> None:
        """Clear all data."""
        self._storage.clear()
        self._expiry.clear()
    
    def clear(self) -> None:
        """Clear all data (synchronous)."""
        self._storage.clear()
        self._expiry.clear()
    
    def __len__(self) -> int:
        """Return number of items in cache."""
        return len(self._storage)


class DictCacheBackend:
    """Simple dict-based cache for testing.
    
    Simpler than InMemoryCacheBackend - no expiry, no TTL support.
    Use when you just need basic caching behavior.
    """
    
    def __init__(self):
        self._data: Dict[str, bytes] = {}
    
    async def get(self, key: str) -> Optional[bytes]:
        return self._data.get(key)
    
    async def set(self, key: str, value: bytes, ttl_seconds: Optional[int] = None) -> None:
        self._data[key] = value
    
    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
    
    async def exists(self, key: str) -> bool:
        return key in self._data
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        return {k: v for k, v in self._data.items() if k in keys}
    
    async def delete_pattern(self, pattern: str) -> None:
        keys_to_delete = [k for k in self._data if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            del self._data[key]
    
    async def close(self) -> None:
        self._data.clear()


# ==================== LLM Mocks ====================

class MockLLMClient:
    """Mock LLM client for testing.
    
    Returns predefined responses without calling external APIs.
    
    Example:
        client = MockLLMClient(
            responses={
                ("claude-sonnet-4", hash("test prompt") % 1000): 
                    "Mock response content"
            }
        )
        response = await client.complete(
            prompt="test prompt",
            model="claude-sonnet-4"
        )
    """
    
    def __init__(
        self,
        name: str = "mock",
        responses: Optional[Dict[tuple, str]] = None,
        embeddings: Optional[Dict[str, List[float]]] = None,
    ):
        """Initialize mock client.
        
        Args:
            name: Provider name for responses
            responses: Dict of (model, prompt_hash) -> response content
            embeddings: Dict of text -> embedding vector
        """
        self._name = name
        self._responses = responses or {}
        self._embeddings = embeddings or {}
        self._call_count = 0
        self._health = True
        self._available_models = ["mock-model-1", "mock-model-2"]
    
    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        **kwargs,
    ) -> 'MockLLMResponse':
        """Return mock response."""
        from src.shared.interfaces import LLMResponse
        
        self._call_count += 1
        
        # Look up response by model and prompt hash
        key = (model, hash(prompt) % 1000)
        content = self._responses.get(key, f"Mock response for: {prompt[:50]}")
        
        return MockLLMResponse(
            content=content,
            model=model,
            provider=self._name,
            usage={"prompt_tokens": 10, "completion_tokens": len(content.split())},
            cost=0.001,
        )
    
    async def generate_embedding(self, text: str, model: str, **kwargs) -> List[float]:
        """Return mock embedding."""
        self._call_count += 1
        
        if text in self._embeddings:
            return self._embeddings[text]
        
        # Return consistent mock embedding
        return [0.1] * 10
    
    async def health_check(self) -> bool:
        """Return mock health status."""
        return self._health
    
    async def get_available_models(self) -> List[str]:
        """Return mock available models."""
        return self._available_models
    
    def set_health(self, healthy: bool) -> None:
        """Set health status for testing."""
        self._health = healthy
    
    def get_call_count(self) -> int:
        """Get number of calls made."""
        return self._call_count
    
    def reset_call_count(self) -> None:
        """Reset call count."""
        self._call_count = 0


class MockLLMResponse:
    """Mock LLM response for testing."""
    
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


class MockLLMRouter:
    """Mock LLM router for testing.
    
    Uses MockLLMClient for all requests.
    
    Example:
        router = MockLLMRouter(
            providers={
                "anthropic": MockLLMClient(name="anthropic"),
                "ollama": MockLLMClient(name="ollama"),
            }
        )
        response = await router.complete(
            prompt="test",
            task_type="extraction"
        )
    """
    
    def __init__(
        self,
        providers: Optional[Dict[str, MockLLMClient]] = None,
        routing_map: Optional[Dict[str, List[str]]] = None,
    ):
        """Initialize mock router.
        
        Args:
            providers: Dict of provider name -> MockLLMClient
            routing_map: TaskType -> list of provider names (priority order)
        """
        self._providers = providers or {
            "anthropic": MockLLMClient(name="anthropic"),
            "openai": MockLLMClient(name="openai"),
            "ollama": MockLLMClient(name="ollama"),
        }
        self._routing_map = routing_map or {
            "extraction": ["anthropic", "ollama"],
            "synthesis": ["anthropic", "ollama"],
            "categorization": ["anthropic", "ollama"],
            "query_generation": ["ollama", "anthropic"],
            "embedding": ["openai", "ollama"],
        }
        self._cost_tracker: Dict[str, float] = {p: 0.0 for p in self._providers}
    
    async def complete(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> MockLLMResponse:
        """Route to mock provider."""
        from src.shared.interfaces import LLMResponse
        
        if force_provider:
            provider_order = [force_provider]
        else:
            provider_order = self._routing_map.get(task_type, ["anthropic"])
        
        for provider_name in provider_order:
            provider = self._providers.get(provider_name)
            if provider:
                response = await provider.complete(
                    prompt=prompt,
                    model=f"{provider_name}-model",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                self._cost_tracker[provider_name] += response.cost or 0
                return response
        
        raise RuntimeError("No providers available")
    
    async def generate_embedding(
        self,
        text: str,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> List[float]:
        """Generate mock embedding."""
        provider_name = force_provider or "openai"
        provider = self._providers.get(provider_name)
        if provider:
            return await provider.generate_embedding(text=text, model="embedding-model")
        raise RuntimeError("No providers available")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check mock provider health."""
        return {name: await p.health_check() for name, p in self._providers.items()}
    
    def add_provider(self, name: str, client: MockLLMClient) -> None:
        """Add a provider after initialization."""
        self._providers[name] = client
        self._cost_tracker[name] = 0.0
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary."""
        return {
            "by_provider": dict(self._cost_tracker),
            "total": sum(self._cost_tracker.values()),
        }
    
    def get_provider(self, name: str) -> Optional[MockLLMClient]:
        """Get a provider by name."""
        return self._providers.get(name)


# ==================== Messaging Mocks ====================

class MockMessageChannel:
    """Mock message channel for testing.
    
    Records published messages for verification.
    """
    
    def __init__(self):
        self._published: List[Dict[str, Any]] = []
    
    async def publish(
        self,
        body: bytes,
        routing_key: str,
        mandatory: bool = False,
        immediate: bool = False,
        properties: Any = None,
    ) -> None:
        """Record published message."""
        self._published.append({
            "body": body,
            "routing_key": routing_key,
            "mandatory": mandatory,
            "immediate": immediate,
            "properties": properties,
        })
    
    async def set_confirm_delivery(self) -> None:
        """Mock publisher confirms."""
        pass
    
    def get_published(self) -> List[Dict[str, Any]]:
        """Get all published messages."""
        return list(self._published)
    
    def clear(self) -> None:
        """Clear published messages."""
        self._published.clear()


class MockMessageConnection:
    """Mock message connection for testing.
    
    Stores published messages in memory.
    
    Example:
        connection = MockMessageConnection()
        await connection.connect()
        channel = connection.channel
        await channel.publish(b"message", routing_key="test.queue")
        messages = connection.get_published_messages()
    """
    
    def __init__(self):
        self._connected = False
        self._channel = MockMessageChannel()
    
    async def connect(self) -> None:
        """Mock connect."""
        self._connected = True
    
    async def close(self) -> None:
        """Mock close."""
        self._connected = False
    
    async def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected
    
    @property
    def channel(self) -> MockMessageChannel:
        """Return mock channel."""
        return self._channel
    
    def get_published_messages(self) -> List[Dict[str, Any]]:
        """Get all published messages (for testing assertions)."""
        return self._channel.get_published()
    
    def clear_published(self) -> None:
        """Clear published messages."""
        self._channel.clear()


class MockMessagePublisher:
    """Mock message publisher for testing.
    
    Stores messages in memory for verification.
    
    Example:
        publisher = MockMessagePublisher()
        await publisher.publish(MyMessage(), routing_key="test.queue")
        published = publisher.get_published()
    """
    
    def __init__(self, connection: Optional[MockMessageConnection] = None):
        """Initialize mock publisher."""
        self._connection = connection or MockMessageConnection()
        self._published: List[Dict[str, Any]] = []
    
    async def publish(
        self,
        message: Any,
        routing_key: str,
        mandatory: bool = False,
        immediate: bool = False,
    ) -> None:
        """Store message (don't actually publish)."""
        self._published.append({
            "message": message,
            "routing_key": routing_key,
            "mandatory": mandatory,
            "immediate": immediate,
        })
    
    async def health_check(self) -> bool:
        """Mock health check."""
        return True
    
    async def close(self) -> None:
        """Mock close."""
        pass
    
    def get_published(self) -> List[Dict[str, Any]]:
        """Get published messages for assertion."""
        return list(self._published)
    
    def clear(self) -> None:
        """Clear published messages."""
        self._published.clear()
    
    @property
    def connection(self) -> MockMessageConnection:
        """Get the underlying connection."""
        return self._connection


class MockRetryStrategy:
    """Mock retry strategy for testing.
    
    Allows fine-grained control over retry behavior.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        fail_after: Optional[int] = None,
    ):
        """Initialize mock strategy.
        
        Args:
            max_retries: Maximum retries allowed
            backoff_base: Base delay for exponential backoff
            fail_after: Fail after this many attempts (None = never)
        """
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._fail_after = fail_after
        self._attempts: List[Dict[str, Any]] = []
    
    async def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if should retry."""
        self._attempts.append({"attempt": attempt, "error": error})
        
        if self._fail_after is not None and attempt >= self._fail_after:
            return False
        
        return attempt < self._max_retries
    
    def get_backoff(self, attempt: int) -> float:
        """Get backoff delay."""
        return self._backoff_base * (2 ** (attempt - 1))
    
    def get_attempts(self) -> List[Dict[str, Any]]:
        """Get all recorded attempts."""
        return list(self._attempts)
    
    def reset(self) -> None:
        """Reset recorded attempts."""
        self._attempts.clear()


class MockCircuitBreaker:
    """Mock circuit breaker for testing.
    
    Allows fine-grained control over circuit state.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        initial_state: str = "closed",
    ):
        """Initialize mock circuit breaker.
        
        Args:
            failure_threshold: Failures before opening
            timeout: Time before half-open
            initial_state: Initial state (closed, open, half-open)
        """
        self._failure_threshold = failure_threshold
        self._timeout = timeout
        self._state = initial_state
        self._failure_count = 0
        self._calls: List[Dict[str, Any]] = []
    
    async def call(self, func, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        self._calls.append({"args": args, "kwargs": kwargs, "state": self._state})
        
        if self._state == "open":
            raise CircuitOpenError("Circuit is open")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Handle successful call."""
        if self._state == "half-open":
            self._state = "closed"
            self._failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failure_count += 1
        if self._state == "closed" and self._failure_count >= self._failure_threshold:
            self._state = "open"
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._state == "open"
    
    def is_closed(self) -> bool:
        """Check if circuit is closed."""
        return self._state == "closed"
    
    def is_half_open(self) -> bool:
        """Check if circuit is half-open."""
        return self._state == "half-open"
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = "closed"
        self._failure_count = 0
    
    def open(self) -> None:
        """Force circuit open."""
        self._state = "open"
    
    def half_open(self) -> None:
        """Force circuit half-open."""
        self._state = "half-open"
    
    def get_calls(self) -> List[Dict[str, Any]]:
        """Get all recorded calls."""
        return list(self._calls)
    
    def get_failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# ==================== HTTP Mocks ====================

class MockHTTPResponse:
    """Mock HTTP response."""
    
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
        return self.content.decode('utf-8')
    
    def json(self) -> Any:
        return json.loads(self.content)
    
    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code}: {self.text[:200]}", self.status_code)


class HTTPError(Exception):
    """HTTP error exception."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class MockHTTPClient:
    """Mock HTTP client for testing.
    
    Returns predefined responses without making actual HTTP calls.
    
    Example:
        client = MockHTTPClient(
            responses={
                "https://api.example.com/data": MockHTTPResponse(
                    status_code=200,
                    content=b'{"key": "value"}'
                )
            }
        )
        response = await client.get("https://api.example.com/data")
    """
    
    def __init__(self, responses: Optional[Dict[str, MockHTTPResponse]] = None):
        """Initialize mock HTTP client.
        
        Args:
            responses: Dict of URL -> MockHTTPResponse
        """
        self._responses = responses or {}
        self._calls: List[Dict[str, Any]] = []
    
    async def get(self, url: str, **kwargs) -> MockHTTPResponse:
        """Return mock GET response."""
        self._calls.append({"method": "GET", "url": url, "kwargs": kwargs})
        return self._get_response(url)
    
    async def post(self, url: str, **kwargs) -> MockHTTPResponse:
        """Return mock POST response."""
        self._calls.append({"method": "POST", "url": url, "kwargs": kwargs})
        return self._get_response(url)
    
    async def put(self, url: str, **kwargs) -> MockHTTPResponse:
        """Return mock PUT response."""
        self._calls.append({"method": "PUT", "url": url, "kwargs": kwargs})
        return self._get_response(url)
    
    async def delete(self, url: str, **kwargs) -> MockHTTPResponse:
        """Return mock DELETE response."""
        self._calls.append({"method": "DELETE", "url": url, "kwargs": kwargs})
        return self._get_response(url)
    
    def _get_response(self, url: str) -> MockHTTPResponse:
        """Get response for URL."""
        if url in self._responses:
            return self._responses[url]
        
        return MockHTTPResponse(
            status_code=404,
            content=b'{"error": "Not found"}',
            headers={"content-type": "application/json"},
        )
    
    async def aclose(self) -> None:
        """Mock close."""
        pass
    
    def get_calls(self) -> List[Dict[str, Any]]:
        """Get all calls made (for testing assertions)."""
        return list(self._calls)
    
    def clear_calls(self) -> None:
        """Clear recorded calls."""
        self._calls.clear()
    
    def add_response(self, url: str, response: MockHTTPResponse) -> None:
        """Add a response after initialization."""
        self._responses[url] = response


# ==================== Database Mocks ====================

class MockDatabaseSession:
    """Mock database session for testing.
    
    Stores objects in memory.
    
    Example:
        session = MockDatabaseSession()
        session.add(User(name="test"))
        await session.commit()
    """
    
    def __init__(self):
        self._objects: List[Any] = []
        self._committed = False
        self._rolled_back = False
    
    async def commit(self) -> None:
        """Mock commit."""
        self._committed = True
    
    async def rollback(self) -> None:
        """Mock rollback."""
        self._rolled_back = True
    
    async def close(self) -> None:
        """Mock close."""
        pass
    
    def add(self, obj: Any) -> None:
        """Add object to session."""
        self._objects.append(obj)
    
    async def execute(self, query: Any, **kwargs) -> Any:
        """Mock execute."""
        return MockResult(self._objects)
    
    async def scalar(self, query: Any, **kwargs) -> Any:
        """Mock scalar."""
        if self._objects:
            return self._objects[0]
        return None
    
    def get_objects(self) -> List[Any]:
        """Get all objects in session."""
        return list(self._objects)
    
    def is_committed(self) -> bool:
        """Check if committed."""
        return self._committed
    
    def is_rolled_back(self) -> bool:
        """Check if rolled back."""
        return self._rolled_back


class MockResult:
    """Mock query result."""
    
    def __init__(self, objects: List[Any]):
        self._objects = objects
    
    def all(self) -> List[Any]:
        """Get all results."""
        return list(self._objects)
    
    def first(self) -> Any:
        """Get first result."""
        return self._objects[0] if self._objects else None
    
    def scalars(self) -> 'MockScalarResult':
        """Return scalar results."""
        return MockScalarResult(self._objects)


class MockScalarResult:
    """Mock scalar result."""
    
    def __init__(self, objects: List[Any]):
        self._objects = objects
    
    def all(self) -> List[Any]:
        return [self._scalar(o) for o in self._objects]
    
    def first(self) -> Any:
        return self._scalar(self._objects[0]) if self._objects else None
    
    def _scalar(self, obj: Any) -> Any:
        """Extract scalar value."""
        if hasattr(obj, '__scalar__'):
            return obj.__scalar__()
        return obj


# ==================== Factory for Test Dependencies ====================

class TestDependencyFactory:
    """Factory for creating test dependencies.
    
    Provides pre-configured mock implementations for common services.
    
    Example:
        from src.shared.testing.mocks import TestDependencyFactory
        
        @pytest.fixture
        def cache():
            return TestDependencyFactory.create_cache()
        
        @pytest.fixture
        def llm_router():
            return TestDependencyFactory.create_llm_router()
        
        @pytest.fixture
        def publisher():
            return TestDependencyFactory.create_publisher()
    """
    
    # Cache factories
    @staticmethod
    def create_cache() -> InMemoryCacheBackend:
        """Create in-memory cache for testing."""
        return InMemoryCacheBackend()
    
    @staticmethod
    def create_dict_cache() -> DictCacheBackend:
        """Create dict-based cache for testing."""
        return DictCacheBackend()
    
    # LLM factories
    @staticmethod
    def create_llm_router(
        responses: Optional[Dict[tuple, str]] = None,
        providers: Optional[Dict[str, MockLLMClient]] = None,
    ) -> MockLLMRouter:
        """Create mock LLM router for testing."""
        if providers is None:
            providers = {
                "anthropic": MockLLMClient(name="anthropic", responses=responses),
                "openai": MockLLMClient(name="openai", responses=responses),
                "ollama": MockLLMClient(name="ollama", responses=responses),
            }
        return MockLLMRouter(providers=providers)
    
    @staticmethod
    def create_llm_client(
        name: str = "test",
        responses: Optional[Dict[tuple, str]] = None,
    ) -> MockLLMClient:
        """Create mock LLM client for testing."""
        return MockLLMClient(name=name, responses=responses)
    
    # Messaging factories
    @staticmethod
    def create_publisher() -> MockMessagePublisher:
        """Create mock message publisher for testing."""
        return MockMessagePublisher()
    
    @staticmethod
    def create_connection() -> MockMessageConnection:
        """Create mock message connection for testing."""
        return MockMessageConnection()
    
    @staticmethod
    def create_retry_strategy(
        max_retries: int = 3,
        fail_after: Optional[int] = None,
    ) -> MockRetryStrategy:
        """Create mock retry strategy for testing."""
        return MockRetryStrategy(max_retries=max_retries, fail_after=fail_after)
    
    @staticmethod
    def create_circuit_breaker(
        failure_threshold: int = 5,
        initial_state: str = "closed",
    ) -> MockCircuitBreaker:
        """Create mock circuit breaker for testing."""
        return MockCircuitBreaker(
            failure_threshold=failure_threshold,
            initial_state=initial_state,
        )
    
    # HTTP factories
    @staticmethod
    def create_http_client(
        responses: Optional[Dict[str, MockHTTPResponse]] = None,
    ) -> MockHTTPClient:
        """Create mock HTTP client for testing."""
        return MockHTTPClient(responses=responses)
    
    # Database factories
    @staticmethod
    def create_session() -> MockDatabaseSession:
        """Create mock database session for testing."""
        return MockDatabaseSession()


# ==================== Async Utilities ====================

async def async_return(value):
    """Helper to return a value from async context."""
    return value


async def async_raises(exception: Exception):
    """Helper to raise an exception from async context."""
    raise exception


# ==================== Export ====================

__all__ = [
    # Cache
    "InMemoryCacheBackend",
    "DictCacheBackend",
    # LLM
    "MockLLMClient",
    "MockLLMResponse",
    "MockLLMRouter",
    # Messaging
    "MockMessageChannel",
    "MockMessageConnection",
    "MockMessagePublisher",
    "MockRetryStrategy",
    "MockCircuitBreaker",
    "CircuitOpenError",
    # HTTP
    "MockHTTPResponse",
    "MockHTTPClient",
    "HTTPError",
    # Database
    "MockDatabaseSession",
    "MockResult",
    # Factory
    "TestDependencyFactory",
    # Utilities
    "async_return",
    "async_raises",
]

