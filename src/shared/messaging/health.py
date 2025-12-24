"""Health check functionality for messaging."""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Literal

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.schemas import QueueName
from src.shared.messaging.exceptions import ConnectionError
from src.shared.messaging.metrics import get_metrics

logger = logging.getLogger(__name__)


class HealthStatus:
    """Health check result."""

    def __init__(
        self,
        status: Literal["healthy", "unhealthy", "degraded"],
        timestamp: datetime,
        checks: Dict[str, str],
        metrics: Dict[str, any],
    ):
        """Initialize health status.

        Args:
            status: Overall health status
            timestamp: When check was performed
            checks: Individual check results
            metrics: Queue and performance metrics
        """
        self.status = status
        self.timestamp = timestamp
        self.checks = checks
        self.metrics = metrics


async def check_messaging_health(
    connection: RabbitMQConnection,
    queues: List[QueueName] = None,
) -> HealthStatus:
    """Check RabbitMQ health and queue status.

    Args:
        connection: RabbitMQ connection to check
        queues: List of queues to check (all if None)

    Returns:
        HealthStatus with overall status, checks, and metrics
    """
    # Default to all queues
    if queues is None:
        queues = list(QueueName)

    health = HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
        checks={},
        metrics={},
    )

    metrics = get_metrics()

    # Check 1: Connection status
    try:
        is_connected = connection.is_connected
        health.checks["connection"] = "ok" if is_connected else "failed"
        health.metrics["connection.status"] = "connected" if is_connected else "disconnected"

        if not is_connected:
            health.status = "unhealthy"
            logger.warning("Messaging health check: connection failed")
        else:
            logger.debug("Messaging health check: connection OK")
    except Exception as e:
        health.checks["connection"] = f"failed: {e}"
        health.status = "unhealthy"
        health.metrics["connection.status"] = "error"
        logger.error(f"Messaging health check: connection error: {e}")

    # Only check queues if connection is healthy
    if is_connected:
        # Check 2: Queue depths and DLQ counts
        try:
            from src.shared.messaging.queue_setup import QueueSetup

            queue_setup = QueueSetup(connection)
            queue_depths = await queue_setup.get_queue_depths()

            health.metrics["queues"] = queue_depths

            # Check for degraded state (>80% capacity)
            from src.shared.messaging.config import messaging_config
            warning_threshold = messaging_config.queue_max_length * 0.8

            for queue_name, depth in queue_depths.items():
                if depth >= 0:  # Valid queue (not error)
                    if depth >= warning_threshold:
                        health.checks[f"{queue_name}.depth"] = "warning"
                        health.status = "degraded"
                        logger.warning(
                            f"Queue {queue_name} depth {depth} exceeds "
                            f"warning threshold {warning_threshold}"
                        )
                    else:
                        health.checks[f"{queue_name}.depth"] = "ok"

            logger.debug(f"Queue depths: {queue_depths}")

        except Exception as e:
            health.checks["queues"] = f"failed: {e}"
            health.status = "unhealthy"
            logger.error(f"Messaging health check: queue error: {e}")

    # Check 3: Metrics summary
    try:
        metrics_summary = metrics.get_summary()
        health.metrics["metrics"] = metrics_summary

        # Check for high error rates
        total_published = metrics.get_counter("total_messages.published", 0)
        total_errors = metrics.get_counter("total_errors", 0)

        if total_published > 0:
            error_rate = total_errors / total_published
            health.metrics["error_rate"] = error_rate

            # Degraded if error rate > 10%
            if error_rate > 0.1:
                health.checks["error_rate"] = "warning"
                if health.status == "healthy":
                    health.status = "degraded"
                logger.warning(f"High error rate: {error_rate:.1%}")
            else:
                health.checks["error_rate"] = "ok"

    except Exception as e:
        health.checks["metrics"] = f"failed: {e}"
        logger.error(f"Messaging health check: metrics error: {e}")

    # Check 4: DLQ messages
    try:
        for queue in queues:
            if queue.value.endswith(".dlq"):
                dlq_depth = health.metrics["queues"].get(queue.value, -1)

                if dlq_depth > 0:
                    health.checks[f"{queue.value}.count"] = f"{dlq_depth} messages"

                    # Degraded if DLQ has messages
                    if health.status == "healthy":
                        health.status = "degraded"
                    logger.warning(f"DLQ {queue.value} has {dlq_depth} messages")

    except Exception as e:
        logger.debug(f"Could not check DLQs: {e}")

    # Log overall status
    logger.info(
        f"Messaging health check: status={health.status}, "
        f"checks={len(health.checks)}, "
        f"timestamp={health.timestamp.isoformat()}"
    )

    return health


async def quick_check(connection: RabbitMQConnection) -> bool:
    """Quick check if messaging connection works.

    Args:
        connection: RabbitMQ connection to check

    Returns:
        True if connection successful, False otherwise
    """
    try:
        # Just check if connected
        is_connected = connection.is_connected
        logger.debug(f"Quick messaging health check: {is_connected}")
        return is_connected
    except Exception:
        logger.debug("Quick messaging health check: failed")
        return False

