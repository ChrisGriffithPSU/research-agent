"""Message publisher for Kaggle fetcher.

Uses injectable message publisher for testability.
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any

from src.shared.interfaces import IMessagePublisher
from src.services.fetchers.kaggle.config import KaggleFetcherConfig
from src.services.fetchers.kaggle.schemas.notebook import ParsedNotebook, NotebookMetadata
from src.services.fetchers.kaggle.schemas.messages import KaggleDiscoveredMessage
from src.services.fetchers.kaggle.exceptions import MessagePublishingError


logger = logging.getLogger(__name__)


class KaggleMessagePublisher:
    """Publisher for Kaggle notebook messages with injectable dependencies.

    Publishes to:
    - kaggle.discovered: Parsed notebooks with full content

    All dependencies are injected through the constructor.

    Example:
        # Production use with real publisher
        from src.shared.messaging.publisher import MessagePublisher
        from src.shared.messaging.connection import RabbitMQConnection

        connection = RabbitMQConnection(connection_string="amqp://localhost:5672/")
        publisher = MessagePublisher(connection=connection)

        kaggle_publisher = KaggleMessagePublisher(
            message_publisher=publisher,
            config=config,
        )

        # Testing use with mocks
        from src.shared.testing.mocks import MockMessagePublisher

        kaggle_publisher = KaggleMessagePublisher(
            message_publisher=MockMessagePublisher(),
            config=config,
        )

        # Use publisher
        await kaggle_publisher.publish_discovered(notebooks=[parsed_notebook])

    Attributes:
        message_publisher: IMessagePublisher for actual publishing
        config: Kaggle fetcher configuration
        _initialized: Whether the service has been initialized
    """

    def __init__(
        self,
        message_publisher: Optional[IMessagePublisher] = None,
        config: Optional[KaggleFetcherConfig] = None,
    ):
        """Initialize message publisher.

        Args:
            message_publisher: IMessagePublisher for actual publishing
            config: Kaggle fetcher configuration
        """
        self._publisher = message_publisher
        self.config = config or KaggleFetcherConfig()
        self._initialized = False

        # Queue name from config
        self.discovered_queue = self.config.discovered_queue

        # Statistics
        self._published_count = 0
        self._error_count = 0

    async def initialize(self) -> None:
        """Initialize publisher connection."""
        if self._initialized:
            return

        if self._publisher is None:
            logger.warning("No message publisher provided, publishing disabled")
            return

        self._initialized = True
        logger.info(
            f"KaggleMessagePublisher initialized, queue: {self.discovered_queue}"
        )

    async def publish_discovered(
        self,
        notebooks: List[ParsedNotebook],
        correlation_id: Optional[str] = None,
    ) -> int:
        """Publish discovered notebooks to kaggle.discovered queue.

        Args:
            notebooks: List of parsed notebooks to publish
            correlation_id: Optional correlation ID for tracing

        Returns:
            Number of notebooks published successfully

        Raises:
            MessagePublishingError: If publishing fails
        """
        if not self._initialized:
            await self.initialize()

        if not notebooks:
            return 0

        if self._publisher is None:
            logger.warning("No message publisher, skipping publish")
            return 0

        published = 0

        for notebook in notebooks:
            try:
                message = self._build_discovered_message(notebook, correlation_id)

                await self._publisher.publish(
                    message=message,
                    routing_key=self.discovered_queue,
                )

                published += 1
                self._published_count += 1

                logger.debug(f"Published discovered notebook: {notebook.notebook_path}")

            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Failed to publish discovered notebook {notebook.notebook_path}: {e}"
                )
                continue

        logger.info(
            f"Published {published}/{len(notebooks)} notebooks to {self.discovered_queue}"
        )
        return published

    async def publish_metadata(
        self,
        notebooks: List[NotebookMetadata],
        correlation_id: Optional[str] = None,
    ) -> int:
        """Publish notebook metadata without full content.

        Args:
            notebooks: List of notebook metadata to publish
            correlation_id: Optional correlation ID for tracing

        Returns:
            Number of notebooks published successfully
        """
        if not self._initialized:
            await self.initialize()

        if not notebooks:
            return 0

        if self._publisher is None:
            logger.warning("No message publisher, skipping publish")
            return 0

        published = 0

        for notebook in notebooks:
            try:
                # Create minimal message with metadata only
                message = self._build_metadata_message(notebook, correlation_id)

                await self._publisher.publish(
                    message=message,
                    routing_key=self.discovered_queue,
                )

                published += 1
                self._published_count += 1

                logger.debug(f"Published metadata for: {notebook.notebook_id}")

            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Failed to publish metadata {notebook.notebook_id}: {e}"
                )
                continue

        return published

    async def publish_batch_discovered(
        self,
        notebooks: List[ParsedNotebook],
        correlation_id: Optional[str] = None,
        batch_size: int = 10,
    ) -> int:
        """Publish notebooks in batches.

        Args:
            notebooks: List of parsed notebooks
            correlation_id: Optional correlation ID
            batch_size: Notebooks per batch

        Returns:
            Total notebooks published
        """
        total_published = 0

        for i in range(0, len(notebooks), batch_size):
            batch = notebooks[i:i + batch_size]
            batch_id = f"{correlation_id}_batch_{i//batch_size}" if correlation_id else None

            try:
                published = await self.publish_discovered(batch, batch_id)
                total_published += published

                # Small delay between batches
                if i + batch_size < len(notebooks):
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to publish batch {i//batch_size}: {e}")
                continue

        return total_published

    def _build_discovered_message(
        self,
        notebook: ParsedNotebook,
        correlation_id: Optional[str] = None,
    ) -> KaggleDiscoveredMessage:
        """Build discovered message from parsed notebook.

        Args:
            notebook: ParsedNotebook with structured content
            correlation_id: Optional correlation ID

        Returns:
            KaggleDiscoveredMessage
        """
        return KaggleDiscoveredMessage(
            correlation_id=correlation_id or notebook.notebook_path,
            notebook_id=notebook.notebook_path,
            notebook_path=notebook.notebook_path,
            title=notebook.title,
            authors=notebook.authors,
            competition_slug=notebook.competition_slug,
            tags=notebook.tags,
            votes=notebook.votes,
            total_views=0,  # Not available in parsed notebook
            notebook_content=notebook,
            source=notebook.metadata.get("source", "unknown"),
            source_query=notebook.metadata.get("source_query", ""),
        )

    def _build_metadata_message(
        self,
        metadata: NotebookMetadata,
        correlation_id: Optional[str] = None,
    ) -> KaggleDiscoveredMessage:
        """Build discovered message from metadata only.

        Args:
            metadata: NotebookMetadata
            correlation_id: Optional correlation ID

        Returns:
            KaggleDiscoveredMessage with empty content
        """
        return KaggleDiscoveredMessage(
            correlation_id=correlation_id or metadata.notebook_id,
            notebook_id=metadata.notebook_id,
            notebook_path=metadata.notebook_path,
            title=metadata.title,
            authors=metadata.authors,
            competition_slug=metadata.competition_slug,
            tags=metadata.tags,
            votes=metadata.votes,
            total_views=metadata.total_views,
            notebook_content=None,  # Not included in metadata-only publish
            source=metadata.source,
            source_query=metadata.source_query,
        )

    async def health_check(self) -> bool:
        """Check if publisher is healthy."""
        if not self._initialized or self._publisher is None:
            return False

        try:
            return await self._publisher.health_check()
        except Exception as e:
            logger.warning(f"Publisher health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close publisher connection."""
        self._initialized = False
        if self._publisher:
            await self._publisher.close()
        logger.info("KaggleMessagePublisher closed")

    def get_stats(self) -> Dict[str, Any]:
        """Get publisher statistics."""
        total = self._published_count + self._error_count
        success_rate = (
            self._published_count / total
            if total > 0 else 0
        )

        return {
            "published_count": self._published_count,
            "error_count": self._error_count,
            "success_rate": success_rate,
            "queues": {
                "discovered": self.discovered_queue,
            },
        }

    @property
    def publisher(self) -> Optional[IMessagePublisher]:
        """Get the underlying publisher (for testing)."""
        return self._publisher

    def __repr__(self) -> str:
        return (
            f"KaggleMessagePublisher("
            f"published={self._published_count}, "
            f"errors={self._error_count})"
        )


__all__ = [
    "KaggleMessagePublisher",
]

