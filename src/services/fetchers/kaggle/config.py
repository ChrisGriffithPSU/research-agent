"""Configuration for Kaggle fetcher plugin.

All parameters are easily configurable with sensible defaults.
Integrates with existing config patterns from src/shared/utils/config/
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class KaggleFetcherConfig(BaseModel):
    """Configuration for Kaggle fetcher.

    Attributes:
        # Discovery
        tags: List of tags to search for notebooks
        max_notebooks_per_competition: Max notebooks to fetch per competition
        max_notebooks_per_tag: Max notebooks per tag search
        max_notebooks_per_query: Max notebooks per query search
        sort_by: Sort field (voteCount, dateCreated, scoreDescending)
        min_votes: Minimum votes to include notebook

        # Caching
        ttl_notebook_seconds: TTL for notebook cache (default: 86400 = 24h)
        ttl_search_seconds: TTL for search results (default: 86400)
        cache_enabled: Enable caching

        # Rate Limiting
        rate_limit_requests_per_second: Rate limit for Kaggle API requests

        # Resilience
        circuit_breaker_failure_threshold: Failures before opening circuit
        circuit_breaker_timeout_seconds: Timeout before retrying
        max_retries: Maximum retries for failed operations
        base_delay_seconds: Base delay for exponential backoff

        # Publishing
        discovered_queue: Queue for discovered notebooks
        batch_size: Notebooks per batch when publishing
        publish_max_retries: Maximum publish retries
        publish_retry_delay_seconds: Base delay for publish retries

        # Parsing
        ast_depth: AST parsing depth (0=no AST, 1=imports+functions, 2=full)
        extract_outputs: Whether to extract cell outputs

        # Observability
        log_level: Logging level
        metrics_enabled: Enable metrics collection
    """

    # ==================== Discovery ====================
    tags: List[str] = Field(
        default=[
            "time-series",
            "forecasting",
            "feature-engineering",
            "stock-prediction",
            "quantitative-finance",
            "machine-learning",
        ],
        description="Tags to search for notebooks"
    )
    max_notebooks_per_competition: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Max notebooks to fetch per competition"
    )
    max_notebooks_per_tag: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max notebooks per tag search"
    )
    max_notebooks_per_query: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max notebooks per query search"
    )
    sort_by: str = Field(
        default="voteCount",
        description="Sort field: voteCount, dateCreated, scoreDescending"
    )
    min_votes: int = Field(
        default=0,
        ge=0,
        description="Minimum votes to include notebook"
    )

    # ==================== Caching ====================
    ttl_notebook_seconds: int = Field(
        default=86400,
        description="TTL for notebook cache (24 hours)"
    )
    ttl_search_seconds: int = Field(
        default=86400,
        description="TTL for search results (24 hours)"
    )
    cache_enabled: bool = Field(
        default=True,
        description="Enable caching"
    )

    # ==================== Rate Limiting ====================
    rate_limit_requests_per_second: float = Field(
        default=1.0,
        description="Rate limit for Kaggle API requests (1 per second)"
    )

    # ==================== Resilience ====================
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Failures before opening circuit"
    )
    circuit_breaker_timeout_seconds: int = Field(
        default=60,
        description="Timeout before retrying (seconds)"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum retries for failed operations"
    )
    base_delay_seconds: float = Field(
        default=1.0,
        description="Base delay for exponential backoff"
    )

    # ==================== Publishing ====================
    discovered_queue: str = Field(
        default="kaggle.discovered",
        description="Queue for discovered notebooks"
    )
    batch_size: int = Field(
        default=10,
        description="Notebooks per batch when publishing"
    )
    publish_max_retries: int = Field(
        default=5,
        description="Maximum retries for publish failures"
    )
    publish_retry_delay_seconds: float = Field(
        default=1.0,
        description="Base delay for publish retries"
    )

    # ==================== Parsing ====================
    ast_depth: int = Field(
        default=2,
        ge=0,
        le=2,
        description="AST parsing depth: 0=no AST, 1=imports+functions, 2=full"
    )
    extract_outputs: bool = Field(
        default=True,
        description="Whether to extract cell outputs"
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

    class Config:
        json_encoders = {}


# Global config instance
_config: Optional[KaggleFetcherConfig] = None


def get_config() -> KaggleFetcherConfig:
    """Get or create the global configuration instance.

    Returns:
        KaggleFetcherConfig instance with all settings
    """
    global _config
    if _config is None:
        _config = KaggleFetcherConfig()
    return _config


def set_config(config: KaggleFetcherConfig) -> None:
    """Set the global configuration instance.

    Args:
        config: KaggleFetcherConfig instance to use
    """
    global _config
    _config = config


def load_config_from_dict(config_dict: dict) -> KaggleFetcherConfig:
    """Load configuration from dictionary.

    Args:
        config_dict: Dictionary with configuration values

    Returns:
        KaggleFetcherConfig instance
    """
    return KaggleFetcherConfig(**config_dict)


def load_config_from_file(config_path: str) -> KaggleFetcherConfig:
    """Load configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        KaggleFetcherConfig instance
    """
    import yaml
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    return KaggleFetcherConfig(**config_dict)


__all__ = [
    "KaggleFetcherConfig",
    "get_config",
    "set_config",
    "load_config_from_dict",
    "load_config_from_file",
]

