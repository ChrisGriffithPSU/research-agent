"""Configuration for arXiv fetcher plugin.

All parameters are easily configurable with sensible defaults.
Integrates with existing config patterns from src/shared/utils/config/
"""
from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field


class ArxivFetcherConfig(BaseModel):
    """Configuration for arXiv fetcher (Two-Phase Architecture).
    
    Attributes:
        categories: arXiv categories to monitor
        discovered_queue: Queue for discovered papers (metadata only)
        parse_request_queue: Queue for parse requests (from intelligence layer)
        extracted_queue: Queue for fully extracted papers
        rate_limit_requests_per_second: Rate limit for arXiv API requests
        max_concurrent_categories: Maximum concurrent category fetches
        max_results_per_query: Max results per query (arXiv limit: 2000)
        default_results_per_query: Default results to fetch per query
        pdf_download_timeout: Timeout for PDF download in seconds
        pdf_parse_timeout: Timeout for PDF parsing in seconds
        max_pdf_size_mb: Max PDF size to process (MB)
        skip_papers_larger_than_mb: Skip PDFs larger than this size
        cache_enabled: Enable caching
        cache_backend: Cache backend: redis, disk, or hybrid
        redis_url: Redis connection URL
        disk_cache_dir: Directory for disk cache
        ttl_api_response_seconds: TTL for API response cache (1 hour)
        ttl_pdf_content_seconds: TTL for PDF content cache (24 hours)
        ttl_parsed_content_seconds: TTL for parsed content cache (48 hours)
        ttl_query_expansion_seconds: TTL for query expansion cache (5 minutes)
        llm_query_enabled: Enable LLM-based query expansion
        llm_provider: Primary LLM provider for query expansion
        llm_model: LLM model for query expansion
        llm_temperature: LLM temperature for query generation
        max_query_expansions: Maximum number of query variations to generate
        queue_name: Queue for publishing raw papers
        batch_size: Papers per batch when publishing
        publish_max_retries: Maximum retries for publish failures
        publish_retry_delay_seconds: Base delay for publish retries
        metrics_enabled: Enable metrics collection
        tracing_enabled: Enable distributed tracing
        log_level: Logging level
    """
    
    # ==================== Categories ====================
    categories: List[str] = Field(
        default=[
            # Machine Learning
            "cs.LG", "cs.AI", "cs.TF", "cs.CL", "cs.CV",
            "stat.ML", "stat.TH", "stat.ME", "stat.CO",
            # Quantitative Finance
            "q-fin.TR", "q-fin.CP", "q-fin.GN", "q-fin.MF", 
            "q-fin.PM", "q-fin.ST", "q-fin.RM",
            # Mathematics
            "math.ST", "math.PR", "math.DS", "math.OC",
            # Economics
            "econ.GN", "econ.TH",
        ],
        description="arXiv categories to monitor (all ML, finance, math relevant)"
    )
    
    # ==================== Queues ====================
    discovered_queue: str = Field(
        default="arxiv.discovered",
        description="Queue for discovered papers (metadata only)"
    )
    parse_request_queue: str = Field(
        default="arxiv.parse_request",
        description="Queue for parse requests (from intelligence layer)"
    )
    extracted_queue: str = Field(
        default="content.extracted",
        description="Queue for fully extracted papers"
    )
    
    # ==================== Rate Limiting ====================
    rate_limit_requests_per_second: float = Field(
        default=0.33,  # 1 request per 3 seconds
        description="Rate limit for arXiv API requests"
    )
    max_concurrent_categories: int = Field(
        default=3,
        description="Maximum concurrent category fetches"
    )
    
    # ==================== Pagination ====================
    max_results_per_query: int = Field(
        default=200,
        description="Max results per query (arXiv limit: 2000)"
    )
    default_results_per_query: int = Field(
        default=50,
        description="Default results to fetch per query"
    )
    
    # ==================== PDF Processing ====================
    pdf_download_timeout: int = Field(
        default=60,
        description="Timeout for PDF download in seconds"
    )
    pdf_parse_timeout: int = Field(
        default=120,
        description="Timeout for PDF parsing in seconds"
    )
    max_pdf_size_mb: int = Field(
        default=50,
        description="Max PDF size to process (MB)"
    )
    skip_papers_larger_than_mb: int = Field(
        default=100,
        description="Skip PDFs larger than this size"
    )
    
    # ==================== Caching ====================
    cache_enabled: bool = Field(
        default=True,
        description="Enable caching"
    )
    cache_backend: str = Field(
        default="redis",  # "redis", "disk", "hybrid"
        description="Cache backend: redis, disk, or hybrid"
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    disk_cache_dir: Optional[Path] = Field(
        default=Path("/data/arxiv_cache"),
        description="Directory for disk cache"
    )
    ttl_api_response_seconds: int = Field(
        default=3600,
        description="TTL for API response cache (1 hour)"
    )
    ttl_pdf_content_seconds: int = Field(
        default=86400,
        description="TTL for PDF content cache (24 hours)"
    )
    ttl_parsed_content_seconds: int = Field(
        default=172800,
        description="TTL for parsed content cache (48 hours)"
    )
    ttl_query_expansion_seconds: int = Field(
        default=300,
        description="TTL for query expansion cache (5 minutes)"
    )
    
    # ==================== LLM Query Processing ====================
    llm_query_enabled: bool = Field(
        default=True,
        description="Enable LLM-based query expansion"
    )
    llm_provider: str = Field(
        default="ollama",  # "ollama", "anthropic", "openai"
        description="Primary LLM provider for query expansion"
    )
    llm_model: str = Field(
        default="llama3.1:8b",
        description="LLM model for query expansion"
    )
    llm_temperature: float = Field(
        default=0.3,
        description="LLM temperature for query generation"
    )
    max_query_expansions: int = Field(
        default=5,
        description="Maximum number of query variations to generate"
    )
    
    # ==================== Queue Publishing ====================
    batch_size: int = Field(
        default=10,
        description="Papers per batch when publishing"
    )
    publish_max_retries: int = Field(
        default=5,
        description="Maximum retries for publish failures"
    )
    publish_retry_delay_seconds: float = Field(
        default=1.0,
        description="Base delay for publish retries"
    )
    
    # ==================== Observability ====================
    metrics_enabled: bool = Field(
        default=True,
        description="Enable metrics collection"
    )
    tracing_enabled: bool = Field(
        default=True,
        description="Enable distributed tracing"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    class Config:
        json_encoders = {
            Path: lambda v: str(v)
        }


# Global config instance
_config: Optional[ArxivFetcherConfig] = None


def get_config() -> ArxivFetcherConfig:
    """Get or create the global configuration instance.
    
    Returns:
        ArxivFetcherConfig instance with all settings
    """
    global _config
    if _config is None:
        _config = ArxivFetcherConfig()
    return _config


def set_config(config: ArxivFetcherConfig) -> None:
    """Set the global configuration instance.
    
    Args:
        config: ArxivFetcherConfig instance to use
    """
    global _config
    _config = config


def load_config_from_dict(config_dict: dict) -> ArxivFetcherConfig:
    """Load configuration from dictionary.
    
    Args:
        config_dict: Dictionary with configuration values
        
    Returns:
        ArxivFetcherConfig instance
    """
    return ArxivFetcherConfig(**config_dict)


def load_config_from_file(config_path: Path) -> ArxivFetcherConfig:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        ArxivFetcherConfig instance
    """
    import yaml
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    return ArxivFetcherConfig(**config_dict)

