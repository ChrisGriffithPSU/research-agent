"""HuggingFace fetcher for model discovery.

Provides components for searching HuggingFace models, parsing model cards,
and publishing results to message queues.

Example Usage:
    from src.services.fetchers.huggingface import HuggingFaceFetcher
    
    # Create and initialize fetcher
    fetcher = HuggingFaceFetcher()
    await fetcher.initialize()
    
    # Run discovery
    count = await fetcher.run_discovery(
        queries=["time series forecasting", "LSTM stock"],
        tasks=["time-series-forecasting"],
    )
    
    # Search for a specific model
    result = await fetcher.search_single("transformer")
    
    # Get model with parsed card
    model_data = await fetcher.get_model_with_card("meta-llama/Llama-3-8B")
    
    await fetcher.close()

Modules:
    schemas: Data classes for models, model cards, and messages
    services: Service implementations (API client, cache, parser, publisher, fetcher)
    interfaces: Abstract interfaces for dependency injection
    exceptions: Domain-specific exceptions
    config: Configuration classes
"""
from src.services.fetchers.huggingface.config import (
    HFetcherConfig,
    get_config,
    set_config,
    load_config_from_dict,
    load_config_from_file,
)
from src.services.fetchers.huggingface.exceptions import (
    HuggingFaceError,
    APIError,
    RateLimitError,
    ModelNotFoundError,
    ModelCardParseError,
    CacheError,
    PublishError,
    HealthCheckError,
)
from src.services.fetchers.huggingface.interfaces import (
    IHuggingFaceAPI,
    IModelCardParser,
    ICacheBackend,
    IHuggingFacePublisher,
    IHuggingFaceFetcher,
)
from src.services.fetchers.huggingface.schemas.model import (
    ModelSource,
    TaskTag,
    ModelMetadata,
    ModelCardMetadata,
    ModelCardContent,
)
from src.services.fetchers.huggingface.schemas.messages import (
    HuggingFaceDiscoveredMessage,
    HuggingFaceParseRequestMessage,
)
from src.services.fetchers.huggingface.services import (
    HuggingFaceAPIClient,
    CacheManager,
    HuggingFaceFetcher,
    Parser,
    HuggingFaceMessagePublisher,
)

__all__ = [
    # Configuration
    "HFetcherConfig",
    "get_config",
    "set_config",
    "load_config_from_dict",
    "load_config_from_file",
    # Exceptions
    "HuggingFaceError",
    "APIError",
    "RateLimitError",
    "ModelNotFoundError",
    "ModelCardParseError",
    "CacheError",
    "PublishError",
    "HealthCheckError",
    # Interfaces
    "IHuggingFaceAPI",
    "IModelCardParser",
    "ICacheBackend",
    "IHuggingFacePublisher",
    "IHuggingFaceFetcher",
    # Schemas
    "ModelSource",
    "TaskTag",
    "ModelMetadata",
    "ModelCardMetadata",
    "ModelCardContent",
    "HuggingFaceDiscoveredMessage",
    "HuggingFaceParseRequestMessage",
    # Services
    "HuggingFaceAPIClient",
    "CacheManager",
    "HuggingFaceFetcher",
    "Parser",
    "HuggingFaceMessagePublisher",
]

