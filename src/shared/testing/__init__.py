"""Testing utilities and mocks for the application.

Provides mock implementations for external services to enable fast, isolated testing.
"""
from src.shared.testing.mocks import (
    CircuitOpenError,
    DictCacheBackend,
    HTTPError,
    # Cache
    InMemoryCacheBackend,
    MockCircuitBreaker,
    # Database
    MockDatabaseSession,
    MockHTTPClient,
    # HTTP
    MockHTTPResponse,
    # LLM
    MockLLMClient,
    MockLLMResponse,
    MockLLMRouter,
    # Messaging
    MockMessageChannel,
    MockMessageConnection,
    MockMessagePublisher,
    MockResult,
    MockRetryStrategy,
    # Factory
    TestDependencyFactory,
    async_raises,
    # Utilities
    async_return,
)

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

