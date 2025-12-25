"""RabbitMQ connection management."""
import asyncio
import logging
from typing import Optional, Dict

import aio_pika

from src.shared.messaging.config import MessagingConfig
from src.shared.messaging.exceptions import ConnectionError

logger = logging.getLogger(__name__)


class RabbitMQConnection:
    """RabbitMQ connection with async support.

    Uses singleton pattern - one connection per service.
    Provides channels for publishers and consumers.
    """

    _instance: Optional["RabbitMQConnection"] = None
    _config: Optional[MessagingConfig] = None

    def __init__(self, config: MessagingConfig):
        """Initialize RabbitMQ connection.

        Args:
            config: Messaging configuration
        """
        self._config = config
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None
        self._is_connected = False
        self._reconnect_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish connection to RabbitMQ.

        Raises:
            ConnectionError: If connection fails
        """
        if self._is_connected:
            logger.debug("Already connected to RabbitMQ")
            return

        logger.info(
            f"Connecting to RabbitMQ at {self._config.host}:{self._config.port}..."
        )

        try:
            url = self._config.connection_url
            self._connection = await aio_pika.connect_robust(
                url,
                heartbeat=self._config.heartbeat,
                connection_timeout=self._config.connection_timeout,
                blocked_connection_timeout=self._config.blocked_connection_timeout,
            )

            self._channel = await self._connection.channel()
            self._is_connected = True

            logger.info(
                f"Connected to RabbitMQ at {self._config.host}:{self._config.port}"
            )

            # Start reconnection task (aio-pika handles auto-reconnect)
            self._reconnect_task = asyncio.create_task(
                self._monitor_connection()
            )

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._is_connected = False
            raise ConnectionError(
                f"Failed to connect to RabbitMQ at {self._config.host}:{self._config.port}",
                original=e,
            ) from e

    async def close(self) -> None:
        """Close connection gracefully.

        Closes channel and connection, cancels monitoring task.
        """
        if not self._is_connected:
            logger.debug("Not connected, nothing to close")
            return

        logger.info("Closing RabbitMQ connection...")

        # Cancel reconnection task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Close channel
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
            logger.debug("RabbitMQ channel closed")

        # Close connection
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.debug("RabbitMQ connection closed")

        self._is_connected = False
        logger.info("RabbitMQ connection closed")

    async def _monitor_connection(self) -> None:
        """Monitor connection and log status changes."""
        if self._connection is None:
            return

        try:
            # Wait for connection close event
            await self._connection.closed

            if self._is_connected:
                logger.warning("RabbitMQ connection closed unexpectedly")
                self._is_connected = False

        except asyncio.CancelledError:
            # Task cancelled during close()
            pass
        except Exception as e:
            logger.error(f"Error monitoring RabbitMQ connection: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._is_connected and self._connection is not None

    @property
    def channel(self) -> aio_pika.RobustChannel:
        """Get channel for operations.

        Raises:
            ConnectionError: If not connected
        """
        if not self._is_connected or self._channel is None:
            raise ConnectionError(
                "Not connected to RabbitMQ. Call connect() first."
            )

        if self._channel.is_closed:
            raise ConnectionError("Channel is closed")

        return self._channel

    async def get_queue_info(self, queue_name: str) -> Optional[Dict[str, int]]:
        """Get information about a queue.

        Args:
            queue_name: Name of queue

        Returns:
            Queue info dict with message_count, consumer_count, etc.
            None if queue doesn't exist
        """
        try:
            channel = self.channel
            queue_info = await channel.declare_queue(
                name=queue_name,
                passive=True,  # Don't create, just check
            )
            return {
                "message_count": queue_info.method.message_count,
                "consumer_count": queue_info.method.consumer_count,
            }
        except aio_pika.exceptions.ChannelClosedByBroker as e:
            if e.reply_code == 404:  # NOT_FOUND
                logger.debug(f"Queue {queue_name} does not exist")
                return None
            raise
        except Exception as e:
            logger.error(f"Error getting queue info for {queue_name}: {e}")
            raise

    async def purge_queue(self, queue_name: str) -> int:
        """Purge all messages from a queue.

        Args:
            queue_name: Name of queue

        Returns:
            Number of messages purged

        Raises:
            ConnectionError: If purge fails
        """
        try:
            channel = self.channel
            result = await channel.queue_purge(queue=queue_name)
            logger.info(f"Purged {result.method.message_count} messages from {queue_name}")
            return result.method.message_count
        except Exception as e:
            logger.error(f"Error purging queue {queue_name}: {e}")
            raise ConnectionError(f"Failed to purge queue {queue_name}", original=e) from e

    def __repr__(self) -> str:
        """String representation."""
        return f"RabbitMQConnection(connected={self._is_connected}, host={self._config.host})"


# Global connection singleton
_connection_lock = asyncio.Lock()
_global_connection: Optional[RabbitMQConnection] = None


async def get_connection(config: Optional[MessagingConfig] = None) -> RabbitMQConnection:
    """Get or create global RabbitMQ connection.

    Args:
        config: Messaging configuration (uses global if not provided)

    Returns:
        Singleton RabbitMQConnection instance

    Raises:
        ConnectionError: If connection fails
    """
    global _global_connection

    async with _connection_lock:
        if _global_connection is None:
            if config is None:
                from src.shared.messaging.config import messaging_config
                config = messaging_config

            _global_connection = RabbitMQConnection(config)
            logger.debug("Global RabbitMQ connection created")

    return _global_connection


async def disconnect() -> None:
    """Close global connection.

    Call this during service shutdown.
    """
    global _global_connection

    async with _connection_lock:
        if _global_connection is not None:
            await _global_connection.close()
            _global_connection = None
            logger.info("Global RabbitMQ connection closed")

