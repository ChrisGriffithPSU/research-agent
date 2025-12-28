"""Message consumer for RabbitMQ."""
import asyncio
import functools
import json
import logging
import time
from typing import Callable, Dict, Optional

import aio_pika

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.retry import IRetryStrategy
from src.shared.messaging.schemas import BaseMessage, QueueName
from src.shared.messaging.metrics import get_metrics
from src.shared.messaging.exceptions import (
    PermanentError,
    TemporaryError,
    ConsumeError,
    ChannelError,
    ChannelClosedError,
    ConnectionClosedError,
    ResourceLockedError,
    PreconditionFailedError,
)

logger = logging.getLogger(__name__)


class MessageConsumer:
    """RabbitMQ message consumer with handler management.

    Features:
    - Async message handlers
    - QoS (prefetch count)
    - Manual ack/nack control
    - Automatic DLQ routing on permanent errors
    - Retry on transient errors
    - Metrics collection
    - Graceful shutdown
    """

    # Message type mapping for deserialization
    _MESSAGE_TYPES: Dict[QueueName, type] = {}

    def __init__(
        self,
        connection: RabbitMQConnection,
        retry_strategy: Optional[IRetryStrategy] = None,
        prefetch_count: int = 10,
    ):
        """Initialize message consumer.

        Args:
            connection: RabbitMQ connection
            retry_strategy: Strategy for retry logic
            prefetch_count: QoS prefetch count (messages per consumer)
        """
        self._connection = connection
        self._retry_strategy = retry_strategy
        self._prefetch_count = prefetch_count
        self._handlers: Dict[QueueName, Callable] = {}
        self._metrics = get_metrics()
        self._consuming = False
        self._shutdown_requested = False
        self._message_type_mapping = self._build_message_type_mapping()

    def _build_message_type_mapping(self) -> Dict[QueueName, type]:
        """Build mapping from queue to message type.

        Returns:
            Dict mapping QueueName to corresponding Pydantic model
        """
        from src.shared.messaging.schemas import (
            SourceMessage,
            DeduplicatedContentMessage,
            ExtractedInsightsMessage,
            DigestReadyMessage,
            FeedbackMessage,
            TrainingTriggerMessage,
        )

        return {
            QueueName.CONTENT_DISCOVERED: SourceMessage,
            QueueName.CONTENT_DEDUPLICATED: DeduplicatedContentMessage,
            QueueName.INSIGHTS_EXTRACTED: ExtractedInsightsMessage,
            QueueName.DIGEST_READY: DigestReadyMessage,
            QueueName.FEEDBACK_SUBMITTED: FeedbackMessage,
            QueueName.TRAINING_TRIGGER: TrainingTriggerMessage,
        }

    def subscribe(
        self,
        queue_name: QueueName,
        handler: Callable[[BaseMessage], None],
    ) -> None:
        """Register handler for a queue.

        Args:
            queue_name: Queue to consume from
            handler: Async function to handle messages

        Raises:
            ValueError: If handler is not async
            ValueError: If queue doesn't have a message type
        """
        # Validate handler is async
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError("Handler must be an async function")

        # Check message type exists for queue
        if queue_name not in self._message_type_mapping:
            raise ValueError(f"No message type defined for queue {queue_name.value}")

        self._handlers[queue_name] = handler
        logger.info(f"Registered handler for queue: {queue_name.value}")

    async def start(self) -> None:
        """Start consuming messages from subscribed queues.

        Blocks until shutdown is requested.
        """
        if self._consuming:
            logger.warning("Consumer already running")
            return

        if not self._handlers:
            logger.warning("No handlers registered, nothing to consume")
            return

        if not self._connection.is_connected:
            from src.shared.messaging.exceptions import ConnectionError
            raise ConnectionError("Not connected to RabbitMQ")

        self._consuming = True
        self._shutdown_requested = False

        # Configure QoS (prefetch)
        channel = self._connection.channel
        await channel.set_qos(prefetch_count=self._prefetch_count)

        # Setup consumer for each queue
        for queue_name in self._handlers.keys():
            await channel.basic_consume(
                queue=queue_name.value,
                consumer_callback=self._create_callback(queue_name),
            )

        logger.info(
            f"Started consuming from {len(self._handlers)} queue(s): "
            f"{', '.join([q.value for q in self._handlers.keys()])}"
        )

        # Wait for shutdown
        while not self._shutdown_requested:
            await asyncio.sleep(0.1)

        # Clean shutdown
        await self._stop()

    async def stop(self, graceful: bool = True, timeout: float = 30.0) -> None:
        """Stop consuming messages.

        Args:
            graceful: Wait for current messages to finish
            timeout: Maximum time to wait for graceful shutdown
        """
        if not self._consuming:
            return

        self._shutdown_requested = True
        logger.info("Stopping consumer...")

        if graceful:
            # Wait for in-flight messages to complete
            logger.debug(f"Waiting {timeout}s for graceful shutdown")
            await asyncio.sleep(timeout)

        # Cancel all consumers
        try:
            channel = self._connection.channel
            await channel.cancel()
            logger.info("Consumers cancelled")
        except Exception as e:
            logger.error(f"Error cancelling consumers: {e}")

        self._consuming = False
        logger.info("Consumer stopped")

    def _create_callback(
        self,
        queue_name: QueueName,
    ) -> Callable:
        """Create callback wrapper for queue.

        Adds:
        - Deserialization
        - Metrics collection
        - Error handling (transient vs permanent)
        - Ack/nack logic

        Args:
            queue_name: Queue to create callback for

        Returns:
            Async callback function
        """
        message_type = self._message_type_mapping[queue_name]

        async def callback(
            message: aio_pika.IncomingMessage,
            channel: aio_pika.RobustChannel,
        ):
            # Start timer
            start_time = time.time()

            try:
                # Deserialize message
                data = json.loads(message.body.decode("utf-8"))
                validated_message = message_type.model_validate(data)

                # Call handler with decorator for metrics
                handler = self._handlers[queue_name]
                await self._call_handler_with_metrics(
                    handler, validated_message, queue_name, start_time
                )

                # Success - ack message
                await message.ack()
                self._metrics.record_message_acked(queue_name.value)

                latency_ms = (time.time() - start_time) * 1000
                self._metrics.record_time(
                    f"consumed.{queue_name.value}",
                    latency_ms,
                )

            except json.JSONDecodeError as e:
                # Invalid JSON - permanent error, send to DLQ
                await self._handle_permanent_error(
                    message, queue_name, "invalid_json", e
                )

            except ValueError as e:
                # Pydantic validation error - permanent, send to DLQ
                await self._handle_permanent_error(
                    message, queue_name, "validation_error", e
                )

            except PermanentError as e:
                # Explicit permanent error - send to DLQ
                await self._handle_permanent_error(
                    message, queue_name, "permanent_error", e
                )

            except TemporaryError as e:
                # Transient error - nack with requeue
                logger.warning(
                    f"Temporary error processing message from {queue_name.value}: {e}"
                )
                await message.nack(requeue=True)
                self._metrics.record_message_nacked(queue_name.value, requeued=True)

            except aio_pika.exceptions.ChannelClosed as e:
                # Channel closed by broker - classify by reply code
                await self._handle_channel_closed(
                    message, queue_name, e
                )

            except aio_pika.exceptions.ConnectionClosed as e:
                # Connection closed by broker
                logger.error(
                    f"Connection closed while processing message from {queue_name.value}: {e}"
                )
                # Don't requeue - connection is down
                await message.nack(requeue=False)
                self._metrics.record_message_nacked(queue_name.value, requeued=False)
                self._metrics.record_dlq_message(queue_name.value, "connection_closed")

            except Exception as e:
                # Unknown error - treat as transient, requeue
                logger.warning(
                    f"Unknown error processing message from {queue_name.value}: {e}"
                )
                await message.nack(requeue=True)
                self._metrics.record_message_nacked(queue_name.value, requeued=True)

        return callback

    async def _call_handler_with_metrics(
        self,
        handler: Callable[[BaseMessage], None],
        message: BaseMessage,
        queue_name: QueueName,
        start_time: float,
    ) -> None:
        """Call handler with metrics collection.

        Args:
            handler: Handler function
            message: Validated message
            queue_name: Queue name
            start_time: Start timestamp
        """
        correlation_id = message.correlation_id
        logger.info(
            f"Processing message {correlation_id} from {queue_name.value}"
        )

        try:
            await handler(message)
            self._metrics.record_message_consumed(queue_name.value)

        except Exception as e:
            # Handler exception - will be caught by callback
            raise

    async def _handle_permanent_error(
        self,
        message: aio_pika.IncomingMessage,
        queue_name: QueueName,
        reason: str,
        error: Exception,
    ) -> None:
        """Handle permanent error (send to DLQ).

        Args:
            message: Incoming message
            queue_name: Queue where error occurred
            reason: Error reason for logging
            error: Exception that occurred
        """
        logger.error(
            f"Permanent error ({reason}) for message from {queue_name.value}: {error}"
        )

        # Send to DLQ (nack without requeue)
        await message.nack(requeue=False)
        self._metrics.record_message_nacked(queue_name.value, requeued=False)
        self._metrics.record_dlq_message(queue_name.value, reason)

    async def _handle_channel_closed(
        self,
        message: aio_pika.IncomingMessage,
        queue_name: QueueName,
        error: aio_pika.exceptions.ChannelClosed,
    ) -> None:
        """Handle channel closed by broker.

        Classifies errors by AMQP reply code and routes appropriately.

        Args:
            message: Incoming message
            queue_name: Queue where error occurred
            error: ChannelClosed exception with reply_code and reply_text
        """
        reply_code = error.reply_code
        reply_text = error.reply_text

        logger.error(
            f"Channel closed for queue {queue_name.value}: "
            f"[{reply_code}] {reply_text}"
        )

        # Classify by reply code
        if reply_code == 405:  # RESOURCE_LOCKED
            # Another consumer is processing - requeue
            logger.warning(f"Queue {queue_name.value} locked, requeuing message")
            await message.nack(requeue=True)
            self._metrics.record_message_nacked(queue_name.value, requeued=True)
            self._metrics.record_error(queue_name.value, "resource_locked")

        elif reply_code == 406:  # PRECONDITION_FAILED
            # Queue declaration mismatch - don't requeue
            logger.error(
                f"Precondition failed for queue {queue_name.value}: {reply_text}"
            )
            await message.nack(requeue=False)
            self._metrics.record_message_nacked(queue_name.value, requeued=False)
            self._metrics.record_dlq_message(queue_name.value, "precondition_failed")

        elif reply_code == 404:  # NOT_FOUND
            # Queue doesn't exist - don't requeue
            logger.error(f"Queue {queue_name.value} not found: {reply_text}")
            await message.nack(requeue=False)
            self._metrics.record_message_nacked(queue_name.value, requeued=False)
            self._metrics.record_dlq_message(queue_name.value, "queue_not_found")

        elif reply_code == 403:  # ACCESS_REFUSED
            # Permission denied - don't requeue
            logger.error(f"Access denied for queue {queue_name.value}: {reply_text}")
            await message.nack(requeue=False)
            self._metrics.record_message_nacked(queue_name.value, requeued=False)
            self._metrics.record_dlq_message(queue_name.value, "access_denied")

        elif reply_code >= 500:
            # Broker error - might be transient, requeue
            logger.warning(
                f"Broker error [{reply_code}] for queue {queue_name.value}, requeuing: {reply_text}"
            )
            await message.nack(requeue=True)
            self._metrics.record_message_nacked(queue_name.value, requeued=True)
            self._metrics.record_error(queue_name.value, f"broker_error_{reply_code}")

        else:
            # Unknown error - don't requeue, send to DLQ
            logger.error(
                f"Unknown channel error [{reply_code}] for queue {queue_name.value}: {reply_text}"
            )
            await message.nack(requeue=False)
            self._metrics.record_message_nacked(queue_name.value, requeued=False)
            self._metrics.record_dlq_message(queue_name.value, f"channel_error_{reply_code}")

    async def health_check(self) -> bool:
        """Check if consumer is healthy.

        Returns:
            True if connected and consuming, False otherwise
        """
        try:
            is_connected = self._connection.is_connected
            is_consuming = self._consuming and not self._shutdown_requested

            return is_connected and is_consuming

        except Exception as e:
            logger.error(f"Consumer health check failed: {e}")
            return False

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"MessageConsumer(handlers={len(self._handlers)}, "
            f"consuming={self._consuming}, "
            f"prefetch={self._prefetch_count})"
        )


def message_handler(
    queue_name: QueueName,
):
    """Decorator for message handlers with cross-cutting concerns.

    Adds:
    - Metrics collection (processing time, success/failure)
    - Error logging
    - Correlation ID logging

    Args:
        queue_name: Queue to monitor

    Usage:
        @message_handler(QueueName.CONTENT_DISCOVERED)
        async def handle_message(message: SourceMessage):
            # Process message
            pass
    """

    def decorator(handler_func):
        @functools.wraps(handler_func)
        async def wrapper(message: BaseMessage):
            metrics = get_metrics()

            # Get queue name from handler name (if possible)
            # This is a simple approach - could be enhanced with context
            start_time = time.time()

            logger.info(
                f"Handler started: {handler_func.__name__} "
                f"(correlation_id={message.correlation_id})"
            )

            try:
                # Call actual handler
                result = await handler_func(message)

                # Record success metrics
                latency_ms = (time.time() - start_time) * 1000
                metrics.record_time(
                    f"handler.{handler_func.__name__}",
                    latency_ms,
                )

                logger.info(
                    f"Handler completed: {handler_func.__name__} "
                    f"(latency={latency_ms:.2f}ms)"
                )

                return result

            except Exception as e:
                # Record error metrics
                metrics.record_error(
                    queue_name.value if queue_name else "unknown",
                    type(e).__name__,
                )

                logger.error(
                    f"Handler failed: {handler_func.__name__} "
                    f"(error={type(e).__name__}): {e}"
                )

                # Re-raise for callback to handle ack/nack
                raise

        return wrapper

    return decorator

