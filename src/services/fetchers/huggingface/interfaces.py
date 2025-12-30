"""Abstract interfaces for HuggingFace fetcher plugin.

Design Principles (from code-quality.mdc):
- Interface Segregation: Small, focused interfaces
- Dependency Inversion: Depend on abstractions, not concretions
- Clear Contracts: Document behavior, exceptions, and invariants
- Async Boundaries: Consistent async/await patterns throughout
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class IHuggingFaceAPI(ABC):
    """Interface for HuggingFace API client.
    
    What Changes Often:
        - HTTP client implementation
        - Retry strategy and backoff configuration
        - Rate limiting approach
    
    What Never Changes:
        - Search interface and parameters
        - Model info structure
        - Pagination contract
    
    Raises:
        - APIError: For HTTP errors from HuggingFace
        - RateLimitError: When rate limit is exceeded
        - ModelNotFoundError: When model doesn't exist
    """
    
    @abstractmethod
    async def search_models(
        self,
        query: str,
        task: Optional[str] = None,
        max_results: int = 20,
        sort_by: str = "downloads",
    ) -> List[Any]:
        """Search for models matching query.
        
        Args:
            query: Search query string
            task: Optional task filter (e.g., 'time-series-forecasting')
            max_results: Maximum results to return (default 20)
            sort_by: Sort field - 'downloads', 'likes', or 'lastModified'
            
        Returns:
            List of model metadata matching query
            
        Raises:
            APIError: If API request fails
            RateLimitError: If rate limit is exceeded
        """
        pass
    
    @abstractmethod
    async def get_model_info(
        self,
        model_id: str,
    ) -> Any:
        """Get detailed metadata for a specific model.
        
        Args:
            model_id: HuggingFace model ID (org/model-name)
            
        Returns:
            Model metadata
            
        Raises:
            APIError: If API request fails
            ModelNotFoundError: If model doesn't exist
        """
        pass
    
    @abstractmethod
    async def get_model_card(
        self,
        model_id: str,
    ) -> str:
        """Fetch raw model card content.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Raw markdown content of model card
            
        Raises:
            APIError: If API request fails
            ModelNotFoundError: If model doesn't exist
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if HuggingFace API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        pass


class IModelCardParser(ABC):
    """Interface for model card parsing.
    
    What Changes Often:
        - Parsing logic and section extraction rules
        - LLM formatting output structure
    
    What Never Changes:
        - Output format (ModelCardContent dataclass)
        - Parse interface
    """
    
    @abstractmethod
    def parse(
        self,
        model_id: str,
        card_content: str,
    ) -> Any:
        """Parse model card content into structured format.
        
        Args:
            model_id: HuggingFace model ID
            card_content: Raw markdown content
            
        Returns:
            ModelCardContent with parsed sections
            
        Raises:
            ModelCardParseError: If parsing fails
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if parser is healthy.
        
        Returns:
            True if parser is healthy, False otherwise
        """
        pass


class ICacheBackend(ABC):
    """Interface for caching layer.
    
    What Changes Often:
        - Cache implementation (Redis, disk, memory)
        - Serialization format
    
    What Never Changes:
        - Get/set/delete interface
        - TTL handling semantics
    """
    
    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        """Get cached value by key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached bytes or None if not found
        """
        pass
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set cached value with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (None for default)
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached value.
        
        Args:
            key: Cache key to delete
        """
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close cache connection and cleanup resources."""
        pass


class IHuggingFacePublisher(ABC):
    """Interface for message publishing.
    
    What Changes Often:
        - Queue implementation (RabbitMQ, Redis, etc.)
        - Message serialization format
    
    What Never Changes:
        - Publish interface
        - Message format contract
    """
    
    @abstractmethod
    async def publish_discovered(
        self,
        models: List[Any],
        correlation_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> int:
        """Publish discovered models to queue.
        
        Args:
            models: List of model metadata to publish
            correlation_id: Optional correlation ID for tracing
            query: Original search query
            
        Returns:
            Number of models published successfully
        """
        pass
    
    @abstractmethod
    async def publish_parse_request(
        self,
        model_id: str,
        correlation_id: str,
        original_correlation_id: str,
        priority: int = 5,
        relevance_score: Optional[float] = None,
        intelligence_notes: Optional[str] = None,
    ) -> None:
        """Publish a parse request for a model card.
        
        Args:
            model_id: Model ID to parse
            correlation_id: Correlation ID for this request
            original_correlation_id: Original discovery correlation ID
            priority: Parse priority (1-10)
            relevance_score: LLM-assigned relevance score
            intelligence_notes: Optional notes from intelligence layer
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close publisher connection and cleanup resources."""
        pass


class IHuggingFaceFetcher(ABC):
    """Main interface for HuggingFace fetcher.
    
    Orchestrates all components for model discovery.
    This is the ENTRY POINT for the fetcher subsystem.
    
    What Changes Often:
        - Discovery workflow orchestration
        - Caching strategy
    
    What Never Changes:
        - run_discovery interface and behavior
        - Health check interface
    """
    
    @abstractmethod
    async def run_discovery(
        self,
        queries: List[str],
        tasks: Optional[List[str]] = None,
    ) -> int:
        """Run model discovery for queries and/or tasks.
        
        This is the main entry point for discovery. It:
        1. Checks cache for cached results
        2. Falls back to API for cache misses
        3. Publishes results to message queue
        
        Args:
            queries: List of search queries
            tasks: Optional list of task filters
            
        Returns:
            Number of models discovered and published
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all components.
        
        Returns:
            Dict mapping component name to health status
        """
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize all components and establish connections."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Clean up all resources and close connections."""
        pass

