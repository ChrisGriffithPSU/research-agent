"""Base class for workers.

Provides common functionality for all workers including:
- Message consumption
- Error handling with retry
- Structured logging
- Health checks
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore

logger = logging.getLogger(__name__)


class WorkerConfig(BaseModel):
    """Base configuration for workers."""

    queue_name: str
    dlq_name: str | None = None
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class BaseWorker(ABC):
    """Base class for all workers.

    Provides common infrastructure for message processing,
    error handling, and artifact storage.

    Example:
        class MyWorker(BaseWorker):
            async def process(self, message: MyMessage) -> None:
                # Process message
                result = await self._do_work(message)
                # Publish result
                await self.publish("output.queue", result)

        worker = MyWorker(config, llm_client, message_consumer)
        await worker.start()
    """

    def __init__(
        self,
        config: WorkerConfig,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: LocalArtifactStore | None = None,
    ):
        """Initialize base worker.

        Args:
            config: Worker configuration
            message_consumer: Message consumer for input queue
            message_publisher: Publisher for output messages
            artifact_store: Optional artifact storage
        """
        self.config = config
        self.consumer = message_consumer
        self.publisher = message_publisher
        self.artifact_store = artifact_store or LocalArtifactStore()
        self._running = False

    @abstractmethod
    async def process(self, message: Any) -> None:
        """Process a message.

        Must be implemented by subclasses.

        Args:
            message: Deserialized message
        """
        pass

    @abstractmethod
    def get_message_type(self) -> type[BaseModel]:
        """Get the expected message type.

        Returns:
            Pydantic model class for message validation
        """
        pass

    async def start(self) -> None:
        """Start the worker.

        Begins consuming messages from the configured queue.
        """
        self._running = True
        logger.info(f"Starting worker: {self.__class__.__name__}")

        # Register message handler with explicit message type for this worker.
        self.consumer.subscribe(
            self.config.queue_name,
            self._handle_message,
            message_type=self.get_message_type(),
        )

        # Start consuming
        await self.consumer.start()

    async def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        await self.consumer.stop()
        logger.info(f"Stopped worker: {self.__class__.__name__}")

    async def _handle_message(self, message: BaseModel) -> None:
        """Handle incoming message with error handling.

        Args:
            message: Deserialized message
        """
        try:
            await self.process(message)
        except Exception as e:
            logger.exception(f"Failed to process message: {e}")
            # Error handling is done by the consumer (ack/nack/dlq)
            raise

    async def publish(
        self,
        routing_key: str,
        message: BaseModel,
    ) -> None:
        """Publish a message.

        Args:
            routing_key: Target queue/topic
            message: Message to publish
        """
        await self.publisher.publish(
            message=message,
            routing_key=routing_key,
        )

    async def store_artifact(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        """Store an artifact.

        Args:
            key: Artifact key/path
            data: Binary data
            content_type: MIME type

        Returns:
            Path to stored artifact
        """
        return await self.artifact_store.store(key, data, content_type)

    async def delete_artifact(self, key: str) -> bool:
        """Delete an artifact.

        Args:
            key: Artifact key/path

        Returns:
            True if deleted, False if not found
        """
        return await self.artifact_store.delete(key)

    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._running

    async def health_check(self) -> bool:
        """Check worker health.

        Returns:
            True if healthy
        """
        return True
