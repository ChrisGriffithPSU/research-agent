"""Queue and exchange setup for RabbitMQ."""
import logging
from typing import Dict

import aio_pika

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.schemas import QueueName
from src.shared.messaging.exceptions import QueueError

logger = logging.getLogger(__name__)


# Exchange and DLQ exchange names
EXCHANGE_NAME = "researcher"
DLQ_EXCHANGE_NAME = "researcher.dlq"

# Alternate exchange for unroutable messages
ALTERNATE_EXCHANGE_NAME = "researcher.ae"
ALTERNATE_EXCHANGE_DLQ_NAME = "researcher.ae.dlq"


class QueueSetup:
    """Queue and exchange declaration and configuration.

    Declares:
    - Topic exchange for routing
    - Main queues (6 queues for pipeline)
    - Dead letter queues (one per main queue)
    - Bindings between queues and exchange
    """

    def __init__(self, connection: RabbitMQConnection):
        """Initialize queue setup.

        Args:
            connection: RabbitMQ connection
        """
        self._connection = connection

    async def setup_all_queues(self) -> None:
        """Declare all queues, exchanges, and bindings.

        This should be called once during service startup.
        """
        await self._declare_alternate_exchange()
        await self._declare_alternate_exchange_dlq()
        await self._declare_exchange()
        await self._declare_dlq_exchange()
        await self._declare_all_queues()
        await self._bind_all_queues()

        logger.info("All queues, exchanges, and bindings declared successfully")

    async def _declare_alternate_exchange(self) -> None:
        """Declare alternate exchange for unroutable messages.

        The alternate exchange receives messages that cannot be routed
        to any queue. Messages are then forwarded to the AE DLQ.
        """
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=ALTERNATE_EXCHANGE_NAME,
                type="direct",
                durable=True,
            )
            logger.info(f"Declared alternate exchange: {ALTERNATE_EXCHANGE_NAME}")
        except Exception as e:
            logger.error(f"Failed to declare alternate exchange {ALTERNATE_EXCHANGE_NAME}: {e}")
            raise QueueError(f"Failed to declare alternate exchange {ALTERNATE_EXCHANGE_NAME}", original=e) from e

    async def _declare_alternate_exchange_dlq(self) -> None:
        """Declare DLQ for the alternate exchange.

        This queue receives all messages that cannot be routed to any
        main queue. Messages here indicate a routing configuration issue.
        """
        channel = self._connection.channel
        try:
            await channel.declare_queue(
                name=ALTERNATE_EXCHANGE_DLQ_NAME,
                durable=True,
            )
            logger.info(f"Declared alternate exchange DLQ: {ALTERNATE_EXCHANGE_DLQ_NAME}")
        except Exception as e:
            logger.error(f"Failed to declare AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME}: {e}")
            raise QueueError(f"Failed to declare AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME}", original=e) from e

    async def _declare_exchange(self) -> None:
        """Declare topic exchange with alternate exchange for unroutable messages."""
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=EXCHANGE_NAME,
                type="topic",  # Topic exchange for flexible routing
                durable=True,  # Persist across RabbitMQ restarts
                arguments={
                    # Configure alternate exchange for unroutable messages
                    "x-alternate-exchange": ALTERNATE_EXCHANGE_NAME,
                },
            )
            logger.info(f"Declared topic exchange: {EXCHANGE_NAME} with AE: {ALTERNATE_EXCHANGE_NAME}")
        except Exception as e:
            logger.error(f"Failed to declare exchange {EXCHANGE_NAME}: {e}")
            raise QueueError(f"Failed to declare exchange {EXCHANGE_NAME}", original=e) from e

    async def _declare_dlq_exchange(self) -> None:
        """Declare dead letter exchange."""
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=DLQ_EXCHANGE_NAME,
                type="direct",
                durable=True,
            )
            logger.info(f"Declared DLQ exchange: {DLQ_EXCHANGE_NAME}")
        except Exception as e:
            logger.error(f"Failed to declare DLQ exchange {DLQ_EXCHANGE_NAME}: {e}")
            raise QueueError(f"Failed to declare DLQ exchange {DLQ_EXCHANGE_NAME}", original=e) from e

    async def _declare_all_queues(self) -> None:
        """Declare all main queues and DLQs."""
        from src.shared.messaging.config import messaging_config

        # Queue configurations
        queue_configs = {
            # Main pipeline queues
            QueueName.CONTENT_DISCOVERED: {
                "max_length": messaging_config.queue_max_length,
                "ttl": messaging_config.queue_message_ttl,
                "routing_key": "content.discovered",
            },
            QueueName.CONTENT_DEDUPLICATED: {
                "max_length": messaging_config.queue_max_length,
                "ttl": messaging_config.queue_message_ttl,
                "routing_key": "content.deduplicated",
            },
            QueueName.INSIGHTS_EXTRACTED: {
                "max_length": 5000,  # Smaller for insights (LLM processed)
                "ttl": messaging_config.queue_message_ttl,
                "routing_key": "insights.extracted",
            },
            QueueName.DIGEST_READY: {
                "max_length": 100,  # Small for digest items (final stage)
                "ttl": messaging_config.queue_message_ttl,
                "routing_key": "digest.ready",
            },
            QueueName.FEEDBACK_SUBMITTED: {
                "max_length": messaging_config.queue_max_length,
                "ttl": None,  # No expiration - feedback is important
                "routing_key": "feedback.submitted",
            },
            QueueName.TRAINING_TRIGGER: {
                "max_length": 10,  # Very small - triggers are rare
                "ttl": messaging_config.queue_message_ttl,
                "routing_key": "training.trigger",
            },

            # DLQs
            QueueName.CONTENT_DISCOVERED_DLQ: {
                "max_length": None,  # DLQs don't limit
                "ttl": None,  # DLQs persist for manual inspection
                "routing_key": None,  # DLQs don't need routing
                "is_dlq": True,
            },
            QueueName.CONTENT_DEDUPLICATED_DLQ: {
                "max_length": None,
                "ttl": None,
                "routing_key": None,
                "is_dlq": True,
            },
            QueueName.INSIGHTS_EXTRACTED_DLQ: {
                "max_length": None,
                "ttl": None,
                "routing_key": None,
                "is_dlq": True,
            },
            QueueName.DIGEST_READY_DLQ: {
                "max_length": None,
                "ttl": None,
                "routing_key": None,
                "is_dlq": True,
            },
            QueueName.FEEDBACK_SUBMITTED_DLQ: {
                "max_length": None,
                "ttl": None,
                "routing_key": None,
                "is_dlq": True,
            },
            QueueName.TRAINING_TRIGGER_DLQ: {
                "max_length": None,
                "ttl": None,
                "routing_key": None,
                "is_dlq": True,
            },
        }

        # Declare each queue
        for queue_name, config in queue_configs.items():
            await self._declare_queue(queue_name, config)

    async def _declare_queue(self, queue_name: QueueName, config: Dict) -> None:
        """Declare a single queue with DLQ configuration.

        Args:
            queue_name: Queue enum value
            config: Queue configuration dict
        """
        channel = self._connection.channel

        # Build queue arguments
        arguments = {}

        # Add DLQ routing for main queues (not DLQs themselves)
        if not config.get("is_dlq", False):
            dlq_name = self._get_dlq_name(queue_name)
            arguments["x-dead-letter-exchange"] = DLQ_EXCHANGE_NAME
            arguments["x-dead-letter-routing-key"] = dlq_name.value

        # Add message TTL if set
        if config.get("ttl") is not None:
            arguments["x-message-ttl"] = config["ttl"]

        # Add max length if set
        if config.get("max_length") is not None:
            arguments["x-max-length"] = config["max_length"]
            arguments["x-overflow"] = "drop-head"  # Drop oldest when full

        try:
            await channel.declare_queue(
                name=queue_name.value,
                durable=True,  # Persist across RabbitMQ restarts
                arguments=arguments,
            )
            logger.debug(f"Declared queue: {queue_name.value} with args: {arguments}")
        except Exception as e:
            logger.error(f"Failed to declare queue {queue_name.value}: {e}")
            raise QueueError(f"Failed to declare queue {queue_name.value}", original=e) from e

    async def _bind_all_queues(self) -> None:
        """Bind main queues to topic exchange and AE DLQ to AE."""
        from src.shared.messaging.config import messaging_config

        # Queue to routing key mappings
        bindings = {
            QueueName.CONTENT_DISCOVERED: "content.discovered",
            QueueName.CONTENT_DEDUPLICATED: "content.deduplicated",
            QueueName.INSIGHTS_EXTRACTED: "insights.extracted",
            QueueName.DIGEST_READY: "digest.ready",
            QueueName.FEEDBACK_SUBMITTED: "feedback.submitted",
            QueueName.TRAINING_TRIGGER: "training.trigger",
        }

        # Bind each main queue (not DLQs)
        for queue_name, routing_key in bindings.items():
            await self._bind_queue(queue_name, routing_key)

        # Bind AE DLQ to AE (catch-all for unroutable messages)
        await self._bind_ae_dlq()

    async def _bind_queue(self, queue_name: QueueName, routing_key: str) -> None:
        """Bind a queue to the topic exchange.

        Args:
            queue_name: Queue to bind
            routing_key: Routing key pattern
        """
        channel = self._connection.channel

        try:
            # Get existing queue (passive=True means don't create, just get)
            queue = await channel.declare_queue(
                name=queue_name.value,
                passive=True,
            )
            # Get existing exchange
            exchange = await channel.declare_exchange(
                name=EXCHANGE_NAME,
                passive=True,
            )
            # Bind queue to exchange with routing key
            await queue.bind(exchange, routing_key=routing_key)
            logger.debug(f"Bound queue {queue_name.value} to {routing_key}")
        except Exception as e:
            logger.error(
                f"Failed to bind queue {queue_name.value} to {routing_key}: {e}"
            )
            raise QueueError(
                f"Failed to bind queue {queue_name.value} to {routing_key}",
                original=e,
            ) from e

    async def _bind_ae_dlq(self) -> None:
        """Bind AE DLQ queue to alternate exchange.

        This queue receives all messages that cannot be routed to any
        main queue. Messages here indicate a routing configuration issue.
        """
        channel = self._connection.channel
        try:
            # Get existing queue
            queue = await channel.declare_queue(
                name=ALTERNATE_EXCHANGE_DLQ_NAME,
                passive=True,
            )
            # Get existing exchange
            exchange = await channel.declare_exchange(
                name=ALTERNATE_EXCHANGE_NAME,
                passive=True,
            )
            # Bind queue to exchange (all messages go to DLQ)
            await queue.bind(exchange, routing_key="")
            logger.debug(f"Bound AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME} to {ALTERNATE_EXCHANGE_NAME}")
        except Exception as e:
            logger.error(
                f"Failed to bind AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME}: {e}"
            )
            raise QueueError(
                f"Failed to bind AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME}",
                original=e,
            ) from e

    def _get_dlq_name(self, queue_name: QueueName) -> QueueName:
        """Get the DLQ name for a main queue.

        Args:
            queue_name: Main queue name

        Returns:
            Corresponding DLQ queue name
        """
        dlq_map = {
            QueueName.CONTENT_DISCOVERED: QueueName.CONTENT_DISCOVERED_DLQ,
            QueueName.CONTENT_DEDUPLICATED: QueueName.CONTENT_DEDUPLICATED_DLQ,
            QueueName.INSIGHTS_EXTRACTED: QueueName.INSIGHTS_EXTRACTED_DLQ,
            QueueName.DIGEST_READY: QueueName.DIGEST_READY_DLQ,
            QueueName.FEEDBACK_SUBMITTED: QueueName.FEEDBACK_SUBMITTED_DLQ,
            QueueName.TRAINING_TRIGGER: QueueName.TRAINING_TRIGGER_DLQ,
        }

        return dlq_map.get(queue_name)

    async def get_queue_depths(self) -> Dict[str, int]:
        """Get current message count for all queues.

        Returns:
            Dict mapping queue name to message count
        """
        depths = {}

        for queue_name in QueueName:
            try:
                info = await self._connection.get_queue_info(queue_name.value)
                if info:
                    depths[queue_name.value] = info["message_count"]
            except Exception as e:
                logger.warning(f"Failed to get depth for {queue_name.value}: {e}")
                depths[queue_name.value] = -1  # Error indicator

        return depths

    async def check_queues_exist(self) -> Dict[str, bool]:
        """Check if queues exist.

        Returns:
            Dict mapping queue name to existence status
        """
        existence = {}

        for queue_name in QueueName:
            try:
                info = await self._connection.get_queue_info(queue_name.value)
                existence[queue_name.value] = info is not None
            except Exception as e:
                logger.warning(f"Error checking {queue_name.value}: {e}")
                existence[queue_name.value] = False

        return existence

