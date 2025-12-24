"""Shared utilities module."""

from src.shared.utils import error_response  # noqa: F401
from src.shared.utils import retry  # noqa: F401
from src.shared.utils import circuit_breaker  # noqa: F401

__all__ = [
    # Error handling utilities
    "error_response",
    "ExceptionHandlerMiddleware",
    # Retry utilities
    "retry",
    "calculate_backoff",
    "CircuitOpenError",
    # Circuit breaker utilities
    "circuit_breaker",
    "CircuitBreaker",
    "CircuitState",
    # Configuration utilities
    "configure_logging",
    "get_logger",
    "disable_logging",
    "find_config_path",
    "ConfigLocator",
    "YAMLLoader",
    "EnvSubstitutor",
    "ConfigMerger",
    "ListMergeStrategy",
    "deep_merge",
    "ConfigLoader",
    "load_config",
    # Database helpers
    "db_transaction",
    "query_timeout",
    "BatchInsertMixin",
    "batch_create",
    "batch_create_or_ignore",
    "BatchUpsertMixin",
    "batch_upsert",
    "UpsertMixin",
    "upsert",
    "EnhancedVectorSearchMixin",
    "vector_similarity_search_filtered",
    "vector_similarity_search_paginated",
    # Logging utilities
    "configure_logging",
    "get_logger",
    "disable_logging",
    "get_correlation_id",
    "get_request_id",
    "get_service_name",
    "get_operation_name",
    "get_context",
    "log_context",
    "correlation_id_generator",
    "async_correlation_id_generator",
    "StructuredJSONFormatter",
    "SamplingHandler",
    "NullHandler",
    "MetricsHandler",
    "SlidingWindowSamplingHandler",
    "RotatingFileHandler",
    # Cache utilities
    "RedisConnection",
    "Serializer",
    "JSONSerializer",
    "PickleSerializer",
    "StringSerializer",
    "get_serializer",
    "build_cache_key",
    "build_hashed_cache_key",
    "build_versioned_cache_key",
    "validate_cache_key",
    "parse_cache_key",
    "CacheMetrics",
    "SlidingWindowCacheMetrics",
    "MetricsTracker",
    "get_metrics",
    "cached",
    "cached_with_key",
    "CacheService",
    "get_cache_service",
]

