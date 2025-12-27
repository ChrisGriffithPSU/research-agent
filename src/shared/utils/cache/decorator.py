"""Cache decorator for automatic function result caching."""
import functools
import hashlib
import inspect
import logging
from typing import Any, Callable, Optional

from src.shared.utils.cache.keys import build_cache_key, build_hashed_cache_key
from src.shared.utils.cache.serializers import JSONSerializer, Serializer


logger = logging.getLogger(__name__)

# Default serializer
_default_serializer = JSONSerializer()


def cached(
    ttl: int = 300,
    key_builder: Optional[Callable] = None,
    namespace: Optional[str] = None,
    serializer: Optional[Serializer] = None,
    skip_none: bool = False,
):
    """Decorator for caching function results.
    
    Args:
        ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        key_builder: Function to build cache key. If None, uses function args.
        namespace: Namespace for key (optional, uses function name if not provided)
        serializer: Serializer instance (default: JSONSerializer)
        skip_none: If True, don't cache None results (default: False)
    
    Example:
        @cached(ttl=3600, namespace="llm")
        async def fetch_paper_data(paper_id: str):
            # Result cached for 1 hour
            return await fetch_from_api(paper_id)
        
        @cached(ttl=60, namespace="user")
        async def get_user_preferences(user_id: int):
            # Result cached for 1 minute
            return await fetch_preferences(user_id)
    """
    def decorator(func: Callable):
        # Determine namespace
        if namespace is None:
            namespace = func.__name__
        
        # Determine serializer
        final_serializer = serializer or _default_serializer
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache instance from function attributes (set by CacheService)
            cache_service = getattr(wrapper, '_cache_service', None)
            if cache_service is None:
                logger.warning(
                    f"Cache not initialized for {func.__name__}. "
                    f"Decorator used without CacheService."
                )
                return await func(*args, **kwargs)
            
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _build_key_from_args(args, kwargs, namespace, func)
            
            # Try to get from cache
            try:
                cached_value = await cache_service.get_cached(cache_key)
                
                if cached_value is not None:
                    logger.debug(
                        f"Cache hit for {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "namespace": namespace,
                            "ttl": ttl,
                        },
                    )
                    return cached_value
                
                # Cache miss, call function
                logger.debug(
                    f"Cache miss for {func.__name__}",
                    extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "namespace": namespace,
                            "ttl": ttl,
                        },
                    )
                
                result = await func(*args, **kwargs)
                
                # Skip caching None if configured
                if skip_none and result is None:
                    return result
                
                # Cache the result
                try:
                    serialized = final_serializer.serialize(result)
                    
                    await cache_service.set_cached(
                        cache_key=cache_key,
                        value=serialized,
                        ttl=ttl,
                    )
                    
                    logger.debug(
                        f"Cached result for {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "namespace": namespace,
                            "ttl": ttl,
                            "value_size": len(serialized),
                        },
                    )
                
                except Exception as e:
                    logger.error(
                        f"Failed to cache result for {func.__name__}: {e}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    # Still return result even if caching fails
                    return result
            
            except Exception as e:
                logger.error(
                    f"Cache error in {func.__name__}: {e}",
                    extra={
                        "function": func.__name__,
                        "cache_key": cache_key,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                return await func(*args, **kwargs)
        
        return wrapper


def _build_key_from_args(args: tuple, kwargs: dict, namespace: str, func: Callable) -> str:
    """Build cache key from function arguments.
    
    Args:
        args: Positional arguments
        kwargs: Keyword arguments
        namespace: Cache namespace
        func: Function being decorated
    
    Returns:
        Cache key string
    """
    # Get function signature
    sig = inspect.signature(func)
    
    # Determine which args to use for key
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()
    
    # Build key parts
    parts = [namespace]
    
    # Add positional args (excluding first if it's 'self')
    for i, (name, value) in enumerate(bound_args.arguments.items()):
        if i == 0 and name == 'self':
            # Skip 'self' for methods
            continue
        parts.append(f"{name}={value}")
    
    # Add keyword args
    for name, value in bound_args.kwargs.items():
        parts.append(f"{name}={value}")
    
    # Hash if too long
    key_str = ":".join(parts)
    if len(key_str) > 50:
        key_str = build_hashed_cache_key(namespace, key_str)
    
    return key_str


def cached_with_key(
    cache_key: str,
    ttl: int = 300,
    serializer: Optional[Serializer] = None,
    skip_none: bool = False,
):
    """Decorator with explicit cache key.
    
    Args:
        cache_key: Exact cache key to use (bypasses key_builder)
        ttl: Time-to-live in seconds
        serializer: Serializer instance (default: JSONSerializer)
        skip_none: If True, don't cache None results
    
    Example:
        @cached_with_key("config:llm", ttl=600)
        async def get_llm_config():
            # Always uses same key, updates in 10 min
            return await fetch_config()
    """
    def decorator(func: Callable):
        final_serializer = serializer or _default_serializer
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache instance from function attributes
            cache_service = getattr(wrapper, '_cache_service', None)
            if cache_service is None:
                logger.warning(
                    f"Cache not initialized for {func.__name__}. "
                    f"Decorator used without CacheService."
                )
                return await func(*args, **kwargs)
            
            # Use explicit key
            try:
                cached_value = await cache_service.get_cached(cache_key)
                
                if cached_value is not None:
                    logger.debug(
                        f"Cache hit for {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "ttl": ttl,
                        },
                    )
                    return cached_value
                
                # Cache miss, call function
                logger.debug(
                    f"Cache miss for {func.__name__}",
                    extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "ttl": ttl,
                        },
                    )
                
                result = await func(*args, **kwargs)
                
                # Skip caching None if configured
                if skip_none and result is None:
                    return result
                
                # Cache the result
                try:
                    serialized = final_serializer.serialize(result)
                    
                    await cache_service.set_cached(
                        cache_key=cache_key,
                        value=serialized,
                        ttl=ttl,
                    )
                    
                    logger.debug(
                        f"Cached result for {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "ttl": ttl,
                            "value_size": len(serialized),
                        },
                    )
                
                except Exception as e:
                    logger.error(
                        f"Failed to cache result for {func.__name__}: {e}",
                        extra={
                            "function": func.__name__,
                            "cache_key": cache_key,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    # Still return result even if caching fails
                    return result
            
            except Exception as e:
                logger.error(
                    f"Cache error in {func.__name__}: {e}",
                    extra={
                        "function": func.__name__,
                        "cache_key": cache_key,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                return await func(*args, **kwargs)
        
        return wrapper

