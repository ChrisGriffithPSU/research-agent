"""Configuration for HuggingFace fetcher plugin.

All parameters are easily configurable with sensible defaults.
Integrates with existing config patterns from src/shared/utils/config/
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class HFetcherConfig(BaseModel):
    """Configuration for HuggingFace fetcher.

    Attributes:
        # Discovery
        default_results_per_query: Max models per query search
        trending_models_count: Number of trending models to fetch
        max_concurrent_searches: Maximum concurrent search operations

        # Rate Limiting
        rate_limit_requests_per_second: Rate limit for HF API requests
        rate_limit_retries: Maximum retries for rate limit errors
        rate_limit_delay_seconds: Delay when rate limited

        # Caching
        ttl_model_seconds: TTL for model metadata cache
        ttl_search_seconds: TTL for search results
        cache_enabled: Enable caching

        # Resilience
        max_retries: Maximum retries for failed operations
        base_delay_seconds: Base delay for exponential backoff
        max_delay_seconds: Maximum delay for exponential backoff

        # Publishing
        discovered_queue: Queue for discovered models
        parse_request_queue: Queue for parse requests
        publish_batch_size: Models per batch when publishing
        publish_max_retries: Maximum retries for publish failures

        # Observability
        log_level: Logging level
        metrics_enabled: Enable metrics collection
        correlation_id_header: Header name for correlation ID
    """

    # ==================== Discovery ====================
    default_results_per_query: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max models per query search"
    )
    trending_models_count: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of trending models to fetch"
    )
    max_concurrent_searches: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent search operations"
    )

    # ==================== Rate Limiting ====================
    rate_limit_requests_per_second: float = Field(
        default=2.0,
        description="Rate limit for HuggingFace API requests (2 per second)"
    )
    rate_limit_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retries for rate limit errors"
    )
    rate_limit_delay_seconds: float = Field(
        default=1.0,
        description="Delay when rate limited (seconds)"
    )

    # ==================== Caching ====================
    ttl_model_seconds: int = Field(
        default=86400,
        description="TTL for model metadata cache (24 hours)"
    )
    ttl_search_seconds: int = Field(
        default=3600,
        description="TTL for search results (1 hour)"
    )
    cache_enabled: bool = Field(
        default=True,
        description="Enable caching"
    )

    # ==================== Resilience ====================
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retries for failed operations"
    )
    base_delay_seconds: float = Field(
        default=1.0,
        description="Base delay for exponential backoff"
    )
    max_delay_seconds: float = Field(
        default=60.0,
        description="Maximum delay for exponential backoff"
    )

    # ==================== Publishing ====================
    discovered_queue: str = Field(
        default="huggingface.discovered",
        description="Queue for discovered models"
    )
    parse_request_queue: str = Field(
        default="huggingface.parse_request",
        description="Queue for parse requests"
    )
    publish_batch_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Models per batch when publishing"
    )
    publish_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retries for publish failures"
    )

    # ==================== Observability ====================
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    metrics_enabled: bool = Field(
        default=True,
        description="Enable metrics collection"
    )
    correlation_id_header: str = Field(
        default="X-Correlation-ID",
        description="Header name for correlation ID"
    )

    class Config:
        json_encoders = {}


# Global config instance
_config: Optional[HFetcherConfig] = None


def get_config() -> HFetcherConfig:
    """Get or create the global configuration instance.

    Returns:
        HFetcherConfig instance with all settings
    """
    global _config
    if _config is None:
        _config = HFetcherConfig()
    return _config


def set_config(config: HFetcherConfig) -> None:
    """Set the global configuration instance.

    Args:
        config: HFetcherConfig instance to use
    """
    global _config
    _config = config


def load_config_from_dict(config_dict: dict) -> HFetcherConfig:
    """Load configuration from dictionary.

    Args:
        config_dict: Dictionary with configuration values

    Returns:
        HFetcherConfig instance
    """
    return HFetcherConfig(**config_dict)


def load_config_from_file(config_path: str) -> HFetcherConfig:
    """Load configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        HFetcherConfig instance
    """
    import yaml
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    return HFetcherConfig(**config_dict)


__all__ = [
    "HFetcherConfig",
    "get_config",
    "set_config",
    "load_config_from_dict",
    "load_config_from_file",
]

