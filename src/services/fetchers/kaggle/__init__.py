"""Kaggle fetcher plugin for ML research discovery.

Discovers and extracts notebooks from Kaggle for ML research purposes.
Supports competition-based, tag-based, and query-based discovery strategies.

Example:
    # Production use
    from src.services.fetchers.kaggle import KaggleFetcherFactory

    fetcher = KaggleFetcherFactory.create_full(
        config=config,
        cache_backend=cache,
        message_publisher=publisher,
    )
    await fetcher.initialize()

    results = await fetcher.run_discovery(
        strategies=["competition", "tag", "query"],
    )

    # Testing use
    from src.services.fetchers.kaggle import KaggleFetcherFactory

    fetcher = KaggleFetcherFactory.create_for_testing()
    results = await fetcher.run_discovery()
"""

# Version
__version__ = "1.0.0"

# Schema exports
from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookSource,
    CellType,
    NotebookMetadata,
    Output,
    CodeCell,
    MarkdownCell,
    CodeAnalysis,
    NotebookContent,
    ParsedNotebook,
    CompetitionMetadata,
)

from src.services.fetchers.kaggle.schemas.messages import (
    KaggleDiscoveredMessage,
    KaggleDiscoveryBatch,
)

# Interface exports
from src.services.fetchers.kaggle.interfaces import (
    IKaggleAPI,
    INotebookParser,
)

# Config exports
from src.services.fetchers.kaggle.config import (
    KaggleFetcherConfig,
    get_config,
    set_config,
    load_config_from_dict,
    load_config_from_file,
)

# Exception exports
from src.services.fetchers.kaggle.exceptions import (
    KaggleFetcherError,
    KaggleAPIError,
    RateLimitError,
    APITimeoutError,
    NotebookDownloadError,
    NotebookParseError,
    CacheError,
    CacheKeyError,
    CacheConnectionError,
    MessagePublishingError,
    CircuitOpenError,
    ValidationError,
    ConfigurationError,
)

# Service exports
from src.services.fetchers.kaggle.services import (
    KaggleAPIClient,
    DefaultRateLimiter,
    NotebookParser,
    CacheManager,
    KaggleMessagePublisher,
    KaggleFetcher,
    KaggleFetcherFactory,
    DiscoveryState,
)

# Factory shortcut
from src.services.fetchers.kaggle.services.fetcher import KaggleFetcherFactory

__all__ = [
    # Version
    "__version__",
    # Schemas
    "NotebookSource",
    "CellType",
    "NotebookMetadata",
    "Output",
    "CodeCell",
    "MarkdownCell",
    "CodeAnalysis",
    "NotebookContent",
    "ParsedNotebook",
    "CompetitionMetadata",
    # Messages
    "KaggleDiscoveredMessage",
    "KaggleDiscoveryBatch",
    # Interfaces
    "IKaggleAPI",
    "INotebookParser",
    # Config
    "KaggleFetcherConfig",
    "get_config",
    "set_config",
    "load_config_from_dict",
    "load_config_from_file",
    # Exceptions
    "KaggleFetcherError",
    "KaggleAPIError",
    "RateLimitError",
    "APITimeoutError",
    "NotebookDownloadError",
    "NotebookParseError",
    "CacheError",
    "CacheKeyError",
    "CacheConnectionError",
    "MessagePublishingError",
    "CircuitOpenError",
    "ValidationError",
    "ConfigurationError",
    # Services
    "KaggleAPIClient",
    "DefaultRateLimiter",
    "NotebookParser",
    "CacheManager",
    "KaggleMessagePublisher",
    "KaggleFetcher",
    "KaggleFetcherFactory",
    "DiscoveryState",
]

