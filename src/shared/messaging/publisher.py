"""Message publisher for RabbitMQ."""
import asyncio
import logging
import json
from typing import Optional

import aio_pika

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.retry import IRetryStrategy, ExponentialBackoffStrategy
from src.shared.messaging.circuit_breaker import CircuitBreaker
from src.shared.messaging.schemas import BaseMessage
from src.shared.messaging.metrics import get_metrics
from src.shared.messaging.exceptions import PublishError, ConnectionError

logger = logging.getLogger(__name__)


class MessagePublisher:
    """RabbitMQ message publisher with retry and circuit breaker.

    Features:
    - Publisher confirms (wait for RabbitMQ acknowledgement)
    - Retry with exponential backoff
    - Circuit breaker protection
    - Automatic JSON serialization
    - Correlation ID tracking
    - Metrics collection
    """

    def __init__(
        self,
        connection: RabbitMQConnection,
        retry_strategy: Optional[IRetryStrategy] = None,
        use_circuit_breaker: bool = True,
    ):
        """Initialize message publisher.

        Args:
            connection: RabbitMQ connection
            retry_strategy: Retry strategy (uses ExponentialBackoff if not provided)
            use_circuit_breaker: Enable circuit breaker protection
        """
        self._connection = connection
        self._retry_strategy = retry_strategy or ExponentialBackoffStrategy()
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._metrics = get_metrics()

        if use_circuit_breaker:
            from src.shared.messaging.config import messaging_config
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=messaging_config.circuit_breaker_failure_threshold,
                timeout=messaging_config.circuit_breaker_timeout,
            )

    async def publish(
        self,
        message: BaseMessage,
        routing_key: str,
        mandatory: bool = False,
        immediate: bool = False,
    ) -> None:
        """Publish a message to RabbitMQ.

        Args:
            message: Pydantic message model (will be serialized to JSON)
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready

        Raises:
            PublishError: If publish fails after all retries
            ConnectionError: If not connected to RabbitMQ
        """
        if not self._connection.is_connected:
            raise ConnectionError(
                "Not connected to RabbitMQ. Call connection.connect() first."
            )

        # Serialize message to JSON
        try:
            message_json = message.model_dump_json()
            message_bytes = message_json.encode("utf-8")
        except Exception as e:
            logger.error(f"Failed to serialize message: {e}")
            raise PublishError(f"Message serialization failed", original=e) from e

        # Apply circuit breaker if enabled
        if self._circuit_breaker:
            try:
                await self._publish_with_retry(
                    message_bytes,
                    routing_key,
                    mandatory,
                    immediate,
                )
            except Exception as e:
                # Circuit breaker already handles retries
                self._metrics.record_error(routing_key, type(e).__name__)
                raise
        else:
            await self._publish_with_retry(
                message_bytes,
                routing_key,
                mandatory,
                immediate,
            )

    async def _publish_with_retry(
        self,
        message_bytes: bytes,
        routing_key: str,
        mandatory: bool,
        immediate: bool,
    ) -> None:
        """Publish message with retry logic.

        Args:
            message_bytes: Serialized message bytes
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready

        Raises:
            PublishError: If all retry attempts fail
        """
        attempt = 0
        last_error = None

        while True:
            try:
                # Use circuit breaker if enabled
                if self._circuit_breaker:
                    await self._circuit_breaker.call(
                        self._do_publish,
                        message_bytes,
                        routing_key,
                        mandatory,
                        immediate,
                    )
                else:
                    await self._do_publish(
                        message_bytes,
                        routing_key,
                        mandatory,
                        immediate,
                    )

                # Success - record metrics and return
                self._metrics.record_message_published(routing_key)
                logger.info(
                    f"Published message to {routing_key} "
                    f"(attempt {attempt + 1})"
                )
                return

            except Exception as e:
                last_error = e
                attempt += 1

                # Check if should retry
                should_retry = await self._retry_strategy.should_retry(attempt, e)

                if not should_retry:
                    # All retries exhausted or permanent error
                    self._metrics.record_error(routing_key, type(e).__name__)
                    logger.error(
                        f"Failed to publish to {routing_key} after {attempt} attempts: {e}"
                    )
                    raise PublishError(
                        f"Failed to publish to {routing_key} after {attempt} attempts",
                        original=e,
                    ) from e

                # Backoff and retry
                backoff = self._retry_strategy.get_backoff(attempt)
                logger.warning(
                    f"Publish attempt {attempt + 1} failed, retrying in {backoff:.2f}s: {e}"
                )

                await asyncio.sleep(backoff)

    async def _do_publish(
        self,
        message_bytes: bytes,
        routing_key: str,
        mandatory: bool,
        immediate: bool,
    ) -> None:
        """Perform actual publish to RabbitMQ.

        Args:
            message_bytes: Serialized message bytes
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready

        Raises:
            Exception: If publish fails (not caught here)
        """
        channel = self._connection.channel

        # Enable publisher confirms
        await channel.set_confirm_delivery()

        # Publish message
        from src.shared.messaging.queue_setup import EXCHANGE_NAME
        await channel.publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=message_bytes,
            mandatory=mandatory,
            immediate=immediate,
            properties=aio_pika.BasicProperties(
                delivery_mode=2,  # Persistent messages
                content_type="application/json",
            ),
        )

    async def health_check(self) -> bool:
        """Check if publisher is healthy.

        Returns:
            True if connected, False otherwise
        """
        try:
            is_connected = self._connection.is_connected

            if self._circuit_breaker and self._circuit_breaker.is_open:
                logger.warning("Circuit breaker is open, publisher unhealthy")
                return False

            return is_connected

        except Exception as e:
            logger.error(f"Publisher health check failed: {e}")
            return False

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker to closed state.

        Use this after RabbitMQ recovers from failure.
        """
        if self._circuit_breaker:
            self._circuit_breaker.reset()
            logger.info("Publisher circuit breaker reset")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"MessagePublisher(connected={self._connection.is_connected}, "
            f"circuit_breaker={'enabled' if self._circuit_breaker else 'disabled'})"
        )


# Global publisher singleton
_publisher_lock = asyncio.Lock()
_global_publisher: Optional[MessagePublisher] = None


async def get_publisher(
    connection: Optional[RabbitMQConnection] = None,
    retry_strategy: Optional[IRetryStrategy] = None,
) -> MessagePublisher:
    """Get or create global message publisher.

    Args:
        connection: RabbitMQ connection (uses global if not provided)
        retry_strategy: Retry strategy (uses default if not provided)

    Returns:
        Singleton MessagePublisher instance
    """
    global _global_publisher

    async with _publisher_lock:
        if _global_publisher is None:
            if connection is None:
                connection = RabbitMQConnection()
                await connection.connect()

            _global_publisher = MessagePublisher(
                connection=connection,
                retry_strategy=retry_strategy,
            )
            logger.debug("Global publisher instance created")

    return _global_publisher

