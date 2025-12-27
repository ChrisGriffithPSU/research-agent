"""Cache infrastructure utilities."""

from src.shared.utils.cache.connection import RedisConnection  # noqa: F401
from src.shared.utils.cache.keys import (
    build_cache_key,
    build_hashed_cache_key,
    build_versioned_cache_key,
    parse_cache_key,
    validate_cache_key,
)  # noqa: F401
from src.shared.utils.cache.serializers import (
    JSONSerializer,
    PickleSerializer,
    Serializer,
    StringSerializer,
    get_serializer,
)  # noqa: F401
from src.shared.utils.cache.decorator import cached, cached_with_key  # noqa: F401
from src.shared.utils.cache.metrics import (
    CacheMetrics,
    MetricsTracker,
    SlidingWindowCacheMetrics,
    get_metrics,
)  # noqa: F401
from src.shared.utils.cache.service import CacheService, CacheServiceFactory  # noqa: F401

__all__ = [
    # Connection management
    "RedisConnection",
    # Serializers
    "Serializer",
    "JSONSerializer",
    "PickleSerializer",
    "StringSerializer",
    "get_serializer",
    # Key building
    "build_cache_key",
    "build_hashed_cache_key",
    "build_versioned_cache_key",
    "validate_cache_key",
    "parse_cache_key",
    # Metrics
    "CacheMetrics",
    "SlidingWindowCacheMetrics",
    "MetricsTracker",
    "get_metrics",
    # Decorators
    "cached",
    "cached_with_key",
    # Service
    "CacheService",
    "CacheServiceFactory",
]

