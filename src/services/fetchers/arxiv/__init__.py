"""arXiv Fetcher Plugin.

A comprehensive arXiv paper discovery and extraction system.

Two-Phase Architecture:
1. Discovery: Query arXiv API, publish metadata to arxiv.discovered queue
2. Extraction: On-demand PDF parsing when intelligence layer approves paper

Components:
- ArxivFetcher: Main orchestrator for paper discovery
- ArxivAPIClient: arXiv API integration with rate limiting
- QueryProcessor: LLM-based query expansion for fuzzy matching
- CacheManager: Redis caching for API responses and parsed content
- ArxivMessagePublisher: Message publishing to RabbitMQ
- PDFProcessor: PDF content extraction using docling

Usage:
    from src.services.fetchers.arxiv import ArxivFetcher
    
    fetcher = ArxivFetcher()
    await fetcher.initialize()
    
    results = await fetcher.run_discovery(
        queries=["transformer time series forecasting"],
        categories=["cs.LG", "stat.ML"],
    )
    
    await fetcher.close()
"""
from src.services.fetchers.arxiv.config import (
    ArxivFetcherConfig,
    get_config,
    load_config_from_dict,
    load_config_from_file,
)
from src.services.fetchers.arxiv.interfaces import (
    PaperMetadata,
    ParsedContent,
    QueryExpansion,
    IArxivAPI,
    IPDFParser,
    ICacheBackend,
    IMessagePublisher,
    IQueryProcessor,
    IRateLimiter,
    IArxivFetcher,
)
from src.services.fetchers.arxiv.schemas.paper import (
    PaperMetadata,
    ParsedContent,
    QueryExpansion,
    TableData,
    FigureData,
)
from src.services.fetchers.arxiv.schemas.messages import (
    ArxivDiscoveredMessage,
    ArxivParseRequestMessage,
    ArxivExtractedMessage,
    ArxivDiscoveryBatch,
)
from src.services.fetchers.arxiv.services import (
    ArxivFetcher,
    ArxivAPIClient,
    QueryProcessor,
    CacheManager,
    ArxivMessagePublisher,
    PDFProcessor,
)
from src.services.fetchers.arxiv.utils import (
    RateLimiter,
    AdaptiveRateLimiter,
)

__version__ = "1.0.0"

__all__ = [
    # Configuration
    "ArxivFetcherConfig",
    "get_config",
    "load_config_from_dict",
    "load_config_from_file",
    # Interfaces
    "PaperMetadata",
    "ParsedContent",
    "QueryExpansion",
    "IArxivAPI",
    "IPDFParser",
    "ICacheBackend",
    "IMessagePublisher",
    "IQueryProcessor",
    "IRateLimiter",
    "IArxivFetcher",
    # Schemas
    "TableData",
    "FigureData",
    "ArxivDiscoveredMessage",
    "ArxivParseRequestMessage",
    "ArxivExtractedMessage",
    "ArxivDiscoveryBatch",
    # Services
    "ArxivFetcher",
    "ArxivAPIClient",
    "QueryProcessor",
    "CacheManager",
    "ArxivMessagePublisher",
    "PDFProcessor",
    # Utilities
    "RateLimiter",
    "AdaptiveRateLimiter",
]

