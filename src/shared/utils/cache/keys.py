"""Cache key building utilities."""
import hashlib
import logging
from typing import List, Optional


logger = logging.getLogger(__name__)


def build_cache_key(namespace: str, identifier: str, *parts: str) -> str:
    """Build cache key with namespace and optional parts.
    
    Args:
        namespace: Namespace for grouping (e.g., "llm", "fetcher", "user")
        identifier: Unique identifier for the cached item
        *parts: Optional additional parts for the key
    
    Returns:
        Colon-separated cache key (e.g., "llm:embedding:abc123")
    
    Example:
        build_cache_key("llm", "embedding", "abc123")
        # Returns: "llm:embedding:abc123"
        
        build_cache_key("fetcher", "arxiv", "cs.LG", "123")
        # Returns: "fetcher:arxiv:cs.LG:123"
    """
    # Validate inputs
    if not namespace:
        raise ValueError("namespace is required")
    if not identifier:
        raise ValueError("identifier is required")
    
    # Build parts list
    parts_list = [namespace, identifier] + [p for p in parts if p]
    
    # Filter out empty parts
    parts_list = [p for p in parts_list if p]
    
    if not parts_list:
        raise ValueError("At least one part (namespace or identifier) must be non-empty")
    
    # Join with colons
    key = ":".join(parts_list)
    
    logger.debug(f"Built cache key: {key}", extra={"key": key, "parts_count": len(parts_list)})
    
    return key


def build_hashed_cache_key(
    namespace: str,
    identifier: str,
    *parts: str,
    hash_length: int = 16,
) -> str:
    """Build cache key with hashed identifier for long strings.
    
    Args:
        namespace: Namespace for grouping
        identifier: Identifier to hash (can be long)
        *parts: Optional additional parts
        hash_length: Number of hex characters to use (default: 16)
    
    Returns:
        Cache key with hashed identifier (e.g., "llm:embedding:a1b2c3d4")
    
    Example:
        # Long identifier becomes short hash
        build_hashed_cache_key("llm", "embedding", "very_long_text_content")
        # Returns: "llm:embedding:a1b2c3d4e5f6g7h8"
    """
    # Validate inputs
    if not namespace:
        raise ValueError("namespace is required")
    if not identifier:
        raise ValueError("identifier is required")
    if hash_length < 8:
        raise ValueError("hash_length must be at least 8")
    if hash_length > 32:
        raise ValueError("hash_length must be at most 32")
    
    # Hash the identifier
    identifier_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:hash_length]
    
    # Build parts list
    parts_list = [namespace, identifier_hash] + [p for p in parts if p]
    
    # Filter out empty parts
    parts_list = [p for p in parts_list if p]
    
    if not parts_list:
        raise ValueError("At least one part (namespace or identifier) must be non-empty")
    
    # Join with colons
    key = ":".join(parts_list)
    
    logger.debug(
        f"Built hashed cache key: {key}",
        extra={"key": key, "identifier_hash": identifier_hash, "parts_count": len(parts_list)},
    )
    
    return key


def build_versioned_cache_key(
    namespace: str,
    identifier: str,
    version: int = 1,
    *parts: str,
) -> str:
    """Build cache key with version for easy invalidation.
    
    Args:
        namespace: Namespace for grouping
        identifier: Unique identifier
        version: Version number (increment to invalidate old keys)
        *parts: Optional additional parts
    
    Returns:
        Cache key with version (e.g., "config:llm:1")
    
    Example:
        # Version 1
        build_versioned_cache_key("config", "llm", version=1)
        # Returns: "config:llm:1"
        
        # Version 2 (invalidates version 1)
        build_versioned_cache_key("config", "llm", version=2)
        # Returns: "config:llm:2" (old key becomes stale)
    """
    # Validate inputs
    if not namespace:
        raise ValueError("namespace is required")
    if not identifier:
        raise ValueError("identifier is required")
    if version < 1:
        raise ValueError("version must be at least 1")
    
    # Build parts list
    parts_list = [namespace, identifier, str(version)] + [p for p in parts if p]
    
    # Filter out empty parts
    parts_list = [p for p in parts_list if p]
    
    if not parts_list:
        raise ValueError("At least one part must be non-empty")
    
    # Join with colons
    key = ":".join(parts_list)
    
    logger.debug(
        f"Built versioned cache key: {key}",
        extra={"key": key, "version": version, "parts_count": len(parts_list)},
    )
    
    return key


def validate_cache_key(key: str, max_length: int = 250) -> bool:
    """Validate cache key length and format.
    
    Args:
        key: Cache key to validate
        max_length: Maximum allowed key length (default: 250 bytes)
    
    Returns:
        True if valid, False otherwise
    
    Raises:
        ValueError: If key is invalid
    """
    if not key:
        raise ValueError("Cache key cannot be empty")
    
    if not isinstance(key, str):
        raise ValueError(f"Cache key must be string, got {type(key)}")
    
    if len(key) == 0:
        raise ValueError("Cache key cannot be empty")
    
    # Check length (Redis key length limit)
    if len(key.encode("utf-8")) > max_length:
        raise ValueError(
            f"Cache key too long: {len(key)} bytes (max: {max_length}). "
            f"Use hashed keys for long identifiers."
        )
    
    # Check for invalid characters
    invalid_chars = ['\n', '\r', ' ', '\t']
    for char in invalid_chars:
        if char in key:
            raise ValueError(f"Cache key contains invalid character: {repr(char)}")
    
    return True


def parse_cache_key(key: str) -> dict:
    """Parse cache key into components.
    
    Args:
        key: Cache key to parse
    
    Returns:
        Dict with parts:
            - namespace: Key namespace
            - identifier: Identifier
            - version: Version number (if present)
            - parts: List of additional parts
    """
    parts = key.split(":")
    
    if len(parts) < 2:
        raise ValueError(f"Invalid cache key format: {key}")
    
    result = {
        "namespace": parts[0],
        "identifier": parts[1] if len(parts) > 1 else None,
        "raw_key": key,
    }
    
    # Check for version
    if len(parts) > 2 and parts[2].isdigit():
        result["version"] = int(parts[2])
    elif len(parts) > 2:
        result["parts"] = parts[2:]
    
    return result

