"""Testing utilities and mocks for the application.

Provides mock implementations for external services to enable fast, isolated testing.
"""
from src.shared.testing.mocks import (
    # Cache
    InMemoryCacheBackend,
    DictCacheBackend,
    # LLM
    MockLLMClient,
    MockLLMResponse,
    MockLLMRouter,
    # Messaging
    MockMessageChannel,
    MockMessageConnection,
    MockMessagePublisher,
    MockRetryStrategy,
    MockCircuitBreaker,
    CircuitOpenError,
    # HTTP
    MockHTTPResponse,
    MockHTTPClient,
    HTTPError,
    # Database
    MockDatabaseSession,
    MockResult,
    # Factory
    TestDependencyFactory,
    # Utilities
    async_return,
    async_raises,
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

