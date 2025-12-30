"""Message publisher for HuggingFace fetcher.

Design Principles (from code-quality.mdc):
- Dependency Inversion: Uses IMessagePublisher interface
- State Management: Mutable statistics separated from immutable config
- Graceful Degradation: Publisher failures don't crash the fetcher
- Observability: Structured logging at publish boundaries
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.shared.interfaces import IMessagePublisher
from src.services.fetchers.huggingface.config import HFetcherConfig
from src.services.fetchers.huggingface.schemas.model import ModelMetadata
from src.services.fetchers.huggingface.schemas.messages import (
    HuggingFaceDiscoveredMessage,
    HuggingFaceParseRequestMessage,
)
from src.services.fetchers.huggingface.exceptions import PublishError


logger = logging.getLogger(__name__)


@dataclass
class PublisherStats:
    """Mutable statistics for the publisher.
    
    Separated from immutable configuration to enable
    thread-safe updates and clear state management.
    """
    published_count: int = 0
    error_count: int = 0
    batch_count: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate publish success rate."""
        total = self.published_count + self.error_count
        return self.published_count / total if total > 0 else 0.0


class HuggingFaceMessagePublisher:
    """Publisher for HuggingFace model messages with injectable dependencies.
    
    Responsibilities:
    - Publish discovered models to message queue
    - Publish parse requests for model card parsing
    - Batch publishing for efficiency
    - Track statistics
    
    Immutable Dependencies:
    - config: Configuration (frozen)
    - _publisher: IMessagePublisher (injected)
    
    Mutable State:
    - _initialized: Initialization flag
    - stats: Publish/error statistics
    
    Publishes to:
    - huggingface.discovered: Models with metadata only
    - huggingface.parse_request: Parse requests from intelligence layer
    """
    
    def __init__(
        self,
        message_publisher: Optional[IMessagePublisher] = None,
        config: Optional[HFetcherConfig] = None,
    ):
        """Initialize message publisher.
        
        Args:
            message_publisher: IMessagePublisher for actual publishing
            config: Configuration (injected, frozen)
        """
        self._publisher = message_publisher
        self._config = config or HFetcherConfig()
        self._initialized: bool = False
        self._stats = PublisherStats()
        
        # Queue names from config
        self._discovered_queue = self._config.discovered_queue
        self._parse_request_queue = self._config.parse_request_queue
    
    async def initialize(self) -> None:
        """Initialize publisher connection.
        
        Side effects:
        - Initializes underlying publisher if provided
        """
        if self._initialized:
            return
        
        if self._publisher is None:
            logger.warning(
                "No message publisher provided. Publishing will be skipped.",
                extra={"event": "publisher_no_config"}
            )
            return
        
        await self._publisher.initialize()
        self._initialized = True
        
        logger.info(
            f"HuggingFaceMessagePublisher initialized, "
            f"queues: {self._discovered_queue}, {self._parse_request_queue}",
            extra={
                "event": "publisher_init",
                "discovered_queue": self._discovered_queue,
                "parse_request_queue": self._parse_request_queue,
            }
        )
    
    async def publish_discovered(
        self,
        models: List[ModelMetadata],
        correlation_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> int:
        """Publish discovered models to huggingface.discovered queue.
        
        Args:
            models: List of model metadata to publish
            correlation_id: Optional correlation ID for tracing
            query: Original search query
            
        Returns:
            Number of models published successfully
        """
        if not self._initialized:
            await self.initialize()
        
        if not models:
            logger.debug(
                "No models to publish",
                extra={"event": "publish_no_models"}
            )
            return 0
        
        if self._publisher is None:
            logger.warning(
                "No message publisher, skipping publish",
                extra={"event": "publisher_not_configured"}
            )
            return 0
        
        published = 0
        
        for model in models:
            try:
                message = HuggingFaceDiscoveredMessage(
                    correlation_id=correlation_id or model.model_id,
                    models=[model],
                    query=query or "",
                    task_filter=None,
                    total_count=1,
                )
                
                await self._publisher.publish(
                    message=message.model_dump(),
                    routing_key=self._discovered_queue,
                )
                
                published += 1
                self._stats.published_count += 1
                
                logger.debug(
                    f"Published discovered model: {model.model_id}",
                    extra={
                        "event": "model_published",
                        "model_id": model.model_id,
                        "correlation_id": correlation_id,
                    }
                )
                
            except Exception as e:
                self._stats.error_count += 1
                logger.error(
                    f"Failed to publish discovered model {model.model_id}: {e}",
                    extra={
                        "event": "publish_error",
                        "model_id": model.model_id,
                        "error": str(e),
                    }
                )
                continue
        
        logger.info(
            f"Published {published}/{len(models)} models to {self._discovered_queue}",
            extra={
                "event": "batch_published",
                "published": published,
                "total": len(models),
                "queue": self._discovered_queue,
            }
        )
        
        return published
    
    async def publish_parse_request(
        self,
        model_id: str,
        correlation_id: str,
        original_correlation_id: str,
        priority: int = 5,
        relevance_score: Optional[float] = None,
        intelligence_notes: Optional[str] = None,
    ) -> None:
        """Publish a parse request to huggingface.parse_request queue.
        
        Args:
            model_id: Model ID to parse
            correlation_id: Correlation ID for this request
            original_correlation_id: Original discovery correlation ID
            priority: Parse priority (1-10)
            relevance_score: LLM-assigned relevance score
            intelligence_notes: Optional notes from intelligence layer
        """
        if not self._initialized:
            await self.initialize()
        
        if self._publisher is None:
            logger.warning(
                "No message publisher, skipping publish",
                extra={"event": "publisher_not_configured"}
            )
            return
        
        try:
            message = HuggingFaceParseRequestMessage(
                correlation_id=correlation_id,
                original_correlation_id=original_correlation_id,
                model_id=model_id,
                priority=priority,
                relevance_score=relevance_score,
                intelligence_notes=intelligence_notes,
            )
            
            await self._publisher.publish(
                message=message.model_dump(),
                routing_key=self._parse_request_queue,
            )
            
            logger.info(
                f"Published parse request for {model_id} (priority: {priority})",
                extra={
                    "event": "parse_request_published",
                    "model_id": model_id,
                    "priority": priority,
                    "correlation_id": correlation_id,
                }
            )
            
        except Exception as e:
            self._stats.error_count += 1
            logger.error(
                f"Failed to publish parse request for {model_id}: {e}",
                extra={
                    "event": "parse_request_error",
                    "model_id": model_id,
                    "error": str(e),
                }
            )
            raise PublishError(
                message=f"Failed to publish parse request: {e}",
                queue_name=self._parse_request_queue,
                message_type="parse_request",
                correlation_id=correlation_id,
                original=e,
            )
    
    async def publish_batch_discovered(
        self,
        models: List[ModelMetadata],
        correlation_id: Optional[str] = None,
        query: Optional[str] = None,
        batch_size: int = 10,
    ) -> int:
        """Publish models in batches.
        
        Args:
            models: List of model metadata
            correlation_id: Optional correlation ID
            query: Original search query
            batch_size: Models per batch
            
        Returns:
            Total models published
        """
        total_published = 0
        self._stats.batch_count += 1
        
        for i in range(0, len(models), batch_size):
            batch = models[i:i + batch_size]
            batch_id = (
                f"{correlation_id}_batch_{i//batch_size}"
                if correlation_id else None
            )
            
            try:
                published = await self.publish_discovered(
                    batch, batch_id, query
                )
                total_published += published
                
                # Small delay between batches to avoid overwhelming queue
                if i + batch_size < len(models):
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(
                    f"Failed to publish batch {i//batch_size}: {e}",
                    extra={
                        "event": "batch_error",
                        "batch_index": i // batch_size,
                        "error": str(e),
                    }
                )
                continue
        
        return total_published
    
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._initialized or self._publisher is None:
            return False
        
        try:
            return await self._publisher.health_check()
        except Exception as e:
            logger.warning(
                f"Publisher health check failed: {e}",
                extra={"event": "health_check_failed", "error": str(e)}
            )
            return False
    
    async def close(self) -> None:
        """Close publisher connection.
        
        Side effects:
        - Sets initialized to False
        - Closes underlying publisher
        """
        self._initialized = False
        if self._publisher:
            await self._publisher.close()
        
        logger.info(
            "HuggingFaceMessagePublisher closed",
            extra={"event": "publisher_close"}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get publisher statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "published_count": self._stats.published_count,
            "error_count": self._stats.error_count,
            "batch_count": self._stats.batch_count,
            "success_rate": self._stats.success_rate,
            "queues": {
                "discovered": self._discovered_queue,
                "parse_request": self._parse_request_queue,
            },
        }
    
    @property
    def publisher(self) -> Optional[IMessagePublisher]:
        """Get the underlying publisher (for testing)."""
        return self._publisher
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"HuggingFaceMessagePublisher("
            f"published={stats['published_count']}, "
            f"errors={stats['error_count']}, "
            f"success_rate={stats['success_rate']:.2%})"
        )

