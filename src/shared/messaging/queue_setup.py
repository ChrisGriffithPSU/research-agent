"""Queue and exchange setup for RabbitMQ.

Declares the topic exchange, pipeline queues, dead-letter queues,
and bindings for the research pipeline.
"""

import logging

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.exceptions import QueueError
from src.shared.messaging.schemas import QueueName

logger = logging.getLogger(__name__)

# Exchange names
EXCHANGE_NAME = "researcher"
DLQ_EXCHANGE_NAME = "researcher.dlq"

# Alternate exchange for unroutable messages
ALTERNATE_EXCHANGE_NAME = "researcher.ae"
ALTERNATE_EXCHANGE_DLQ_NAME = "researcher.ae.dlq"

# Queue → routing key bindings for the pipeline
PIPELINE_BINDINGS: dict[QueueName, str] = {
    QueueName.PAPER_FULLTEXT_REQUEST: "paper.fulltext.request",
    QueueName.PAPER_PARSED: "paper.parsed",
    QueueName.PAPER_CONCEPTS_REQUEST: "paper.concepts.request",
    QueueName.CONCEPTS_GENERATED: "concepts.generated",
    QueueName.PLAN_GENERATE_REQUEST: "plan.generate.request",
    QueueName.PLAN_GENERATED: "plan.generated",
    QueueName.CODE_EXECUTION_REQUEST: "code.execution.request",
    QueueName.CODE_EXECUTION_RESULT: "code.execution.result",
    QueueName.EXPERIMENT_EVALUATION_REQUEST: "experiment.evaluation.request",
    QueueName.EXPERIMENT_EVALUATION_RESULT: "experiment.evaluation.result",
    QueueName.NOTIFY_SEND: "notify.send",
}

# Main queue → DLQ mapping
_DLQ_MAP: dict[QueueName, QueueName] = {
    QueueName.PAPER_FULLTEXT_REQUEST: QueueName.PAPER_FULLTEXT_DLQ,
    QueueName.PAPER_CONCEPTS_REQUEST: QueueName.PAPER_CONCEPTS_DLQ,
    QueueName.PLAN_GENERATE_REQUEST: QueueName.PLAN_GENERATE_DLQ,
    QueueName.CODE_EXECUTION_REQUEST: QueueName.CODE_EXECUTION_DLQ,
    QueueName.EXPERIMENT_EVALUATION_REQUEST: QueueName.EXPERIMENT_EVALUATION_DLQ,
}

# All DLQ enum values for declaration
_DLQ_QUEUES: list[QueueName] = [
    QueueName.PAPER_FULLTEXT_DLQ,
    QueueName.PAPER_CONCEPTS_DLQ,
    QueueName.PLAN_GENERATE_DLQ,
    QueueName.CODE_EXECUTION_DLQ,
    QueueName.EXPERIMENT_EVALUATION_DLQ,
]


class QueueSetup:
    """Queue and exchange declaration and configuration."""

    def __init__(self, connection: RabbitMQConnection):
        self._connection = connection

    async def setup_all_queues(self) -> None:
        """Declare all exchanges, queues, and bindings."""
        await self._declare_alternate_exchange()
        await self._declare_alternate_exchange_dlq()
        await self._declare_exchange()
        await self._declare_dlq_exchange()
        await self._declare_all_queues()
        await self._bind_all_queues()
        logger.info("All queues, exchanges, and bindings declared successfully")

    async def _declare_alternate_exchange(self) -> None:
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=ALTERNATE_EXCHANGE_NAME,
                type="direct",
                durable=True,
            )
        except Exception as e:
            raise QueueError(
                f"Failed to declare alternate exchange {ALTERNATE_EXCHANGE_NAME}", original=e
            ) from e

    async def _declare_alternate_exchange_dlq(self) -> None:
        channel = self._connection.channel
        try:
            await channel.declare_queue(
                name=ALTERNATE_EXCHANGE_DLQ_NAME,
                durable=True,
            )
        except Exception as e:
            raise QueueError(
                f"Failed to declare AE DLQ {ALTERNATE_EXCHANGE_DLQ_NAME}", original=e
            ) from e

    async def _declare_exchange(self) -> None:
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=EXCHANGE_NAME,
                type="topic",
                durable=True,
                arguments={
                    "x-alternate-exchange": ALTERNATE_EXCHANGE_NAME,
                },
            )
        except Exception as e:
            raise QueueError(f"Failed to declare exchange {EXCHANGE_NAME}", original=e) from e

    async def _declare_dlq_exchange(self) -> None:
        channel = self._connection.channel
        try:
            await channel.declare_exchange(
                name=DLQ_EXCHANGE_NAME,
                type="direct",
                durable=True,
            )
        except Exception as e:
            raise QueueError(
                f"Failed to declare DLQ exchange {DLQ_EXCHANGE_NAME}", original=e
            ) from e

    async def _declare_all_queues(self) -> None:
        """Declare all main pipeline queues and DLQs."""
        # Main queues with DLQ routing
        for queue_name in PIPELINE_BINDINGS:
            dlq = _DLQ_MAP.get(queue_name)
            arguments: dict = {}
            if dlq is not None:
                arguments["x-dead-letter-exchange"] = DLQ_EXCHANGE_NAME
                arguments["x-dead-letter-routing-key"] = dlq.value
            await self._declare_queue(queue_name.value, arguments)

        # DLQs (no DLQ-of-DLQ)
        for dlq_name in _DLQ_QUEUES:
            await self._declare_queue(dlq_name.value, {})

    async def _declare_queue(self, name: str, arguments: dict) -> None:
        channel = self._connection.channel
        try:
            await channel.declare_queue(
                name=name,
                durable=True,
                arguments=arguments,
            )
            logger.debug(f"Declared queue: {name}")
        except Exception as e:
            raise QueueError(f"Failed to declare queue {name}", original=e) from e

    async def _bind_all_queues(self) -> None:
        """Bind pipeline queues to topic exchange."""
        channel = self._connection.channel
        exchange = await channel.declare_exchange(name=EXCHANGE_NAME, passive=True)

        for queue_name, routing_key in PIPELINE_BINDINGS.items():
            queue = await channel.declare_queue(name=queue_name.value, passive=True)
            await queue.bind(exchange, routing_key=routing_key)
            logger.debug(f"Bound queue {queue_name.value} to {routing_key}")

        # Bind AE DLQ to AE
        ae_queue = await channel.declare_queue(name=ALTERNATE_EXCHANGE_DLQ_NAME, passive=True)
        ae_exchange = await channel.declare_exchange(name=ALTERNATE_EXCHANGE_NAME, passive=True)
        await ae_queue.bind(ae_exchange, routing_key="")

    async def get_queue_depths(self) -> dict[str, int]:
        """Get current message count for all queues."""
        depths: dict[str, int] = {}
        for queue_name in QueueName:
            try:
                info = await self._connection.get_queue_info(queue_name.value)
                if info:
                    depths[queue_name.value] = info["message_count"]
            except Exception as e:
                logger.warning(f"Failed to get depth for {queue_name.value}: {e}")
                depths[queue_name.value] = -1
        return depths
