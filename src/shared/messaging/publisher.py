"""Refactored message publisher with dependency injection.

Provides a clean interface for message publishing with injectable dependencies.
"""
import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from src.shared.testing.mocks import MockMessageConnection, MockMessagePublisher

from src.shared.interfaces import (
    IMessageConnection,
    IRetryStrategy,
    ICircuitBreaker,
    IMessagePublisher,
)
from src.shared.messaging.schemas import BaseMessage
from src.shared.messaging.retry import ExponentialBackoffStrategy
from src.shared.messaging.exceptions import ConnectionError as MessagingConnectionError


logger = logging.getLogger(__name__)


class MessagePublisher:
    """RabbitMQ message publisher with injectable dependencies.
    
    Publishes messages to a message broker with retry and circuit breaker support.
    All dependencies are injected through the constructor.
    
    Example:
        # Production use with real connection
        connection = RabbitMQConnection(connection_string="amqp://localhost:5672/")
        publisher = MessagePublisher(
            connection=connection,
            retry_strategy=ExponentialBackoffStrategy(max_retries=5),
            circuit_breaker=CircuitBreaker(failure_threshold=5),
        )
        await connection.connect()
        
        # Testing use with mocks
        from src.shared.testing.mocks import (
            MockMessageConnection,
            MockRetryStrategy,
            MockCircuitBreaker,
        )
        publisher = MessagePublisher(
            connection=MockMessageConnection(),
            retry_strategy=MockRetryStrategy(max_retries=3),
        )
        
        # Use publisher
        await publisher.publish(
            message=MyMessage(),
            routing_key="test.queue",
        )
    
    Attributes:
        _connection: Message broker connection (IMessageConnection)
        _retry_strategy: Strategy for retrying failed publishes
        _circuit_breaker: Circuit breaker for fault tolerance
    """
    
    def __init__(
        self,
        connection: IMessageConnection,
        retry_strategy: Optional[IRetryStrategy] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
    ):
        """Initialize message publisher.
        
        Args:
            connection: Message broker connection (RabbitMQ, in-memory, etc.)
            retry_strategy: Strategy for retrying failed publishes
            circuit_breaker: Circuit breaker for fault tolerance
        """
        self._connection = connection
        self._retry_strategy = retry_strategy or ExponentialBackoffStrategy()
        self._circuit_breaker = circuit_breaker
    
    async def publish(
        self,
        message: BaseMessage,
        routing_key: str,
        mandatory: bool = False,
        immediate: bool = False,
    ) -> None:
        """Publish a message to the broker.
        
        Args:
            message: Message to publish
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready
            
        Raises:
            ConnectionError: If not connected to broker
            PublishError: If publish fails after all retries
        """
        if not self._connection.is_connected:
            raise MessagingConnectionError("Not connected to message broker. Call connection.connect() first.")
        
        # Serialize message
        try:
            message_json = message.model_dump_json()
            message_bytes = message_json.encode("utf-8")
        except Exception as e:
            raise PublishError(f"Message serialization failed", original=e) from e
        
        # Publish with retry and circuit breaker
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
        """
        attempt = 0
        last_error = None
        
        while True:
            try:
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
                
                logger.info(f"Published message to {routing_key}")
                return
                
            except Exception as e:
                last_error = e
                attempt += 1
                
                # Check if should retry
                should_retry = await self._retry_strategy.should_retry(attempt, e)
                
                if not should_retry:
                    # All retries exhausted or permanent error
                    raise PublishError(
                        f"Failed to publish to {routing_key} after {attempt} attempts",
                        original=e,
                    ) from e
                
                # Backoff and retry
                backoff = self._retry_strategy.get_backoff(attempt)
                logger.warning(
                    f"Publish attempt {attempt} failed, retrying in {backoff:.2f}s: {e}"
                )
                
                await asyncio.sleep(backoff)
    
    async def _do_publish(
        self,
        message_bytes: bytes,
        routing_key: str,
        mandatory: bool,
        immediate: bool,
    ) -> None:
        """Perform actual publish to broker.
        
        Args:
            message_bytes: Serialized message bytes
            routing_key: Routing key for topic exchange
            mandatory: Fail if no queue is bound
            immediate: Fail if no consumer is ready
        """
        channel = self._connection.channel
        
        # Broker-specific publish logic
        # This is abstracted in the connection's channel
        await channel.publish(
            body=message_bytes,
            routing_key=routing_key,
            mandatory=mandatory,
            immediate=immediate,
        )
    
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if self._circuit_breaker and self._circuit_breaker.is_open():
                return False
            return self._connection.is_connected()
        except Exception:
            return False
    
    async def close(self) -> None:
        """Close publisher and connection."""
        await self._connection.close()
        logger.info("MessagePublisher closed")
    
    @property
    def connection(self) -> IMessageConnection:
        """Get the underlying connection (for testing)."""
        return self._connection
    
    @property
    def circuit_breaker(self) -> Optional[ICircuitBreaker]:
        """Get the circuit breaker (for testing)."""
        return self._circuit_breaker
    
    def __repr__(self) -> str:
        return (
            f"MessagePublisher(connected={self._connection.is_connected()}, "
            f"circuit_breaker={'enabled' if self._circuit_breaker else 'disabled'})"
        )


class MessagePublisherFactory:
    """Factory for creating MessagePublisher instances.
    
    Provides convenient methods for creating publishers with common configurations.
    """
    
    @staticmethod
    def create_rabbitmq(
        connection_string: str = "amqp://localhost:5672/",
        max_retries: int = 5,
        base_delay: float = 1.0,
        failure_threshold: int = 5,
        timeout: float = 60.0,
    ) -> MessagePublisher:
        """Create MessagePublisher with RabbitMQ connection.
        
        Args:
            connection_string: AMQP connection string
            max_retries: Maximum retry attempts
            base_delay: Base delay for exponential backoff
            failure_threshold: Circuit breaker failure threshold
            timeout: Circuit breaker timeout
            
        Returns:
            Configured MessagePublisher instance
        """
        from src.shared.messaging.connection import RabbitMQConnection
        from src.shared.messaging.circuit_breaker import CircuitBreaker
        
        connection = RabbitMQConnection(connection_string=connection_string)
        
        retry_strategy = ExponentialBackoffStrategy(
            max_retries=max_retries,
            base_delay=base_delay,
        )
        
        circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            timeout=timeout,
        )
        
        return MessagePublisher(
            connection=connection,
            retry_strategy=retry_strategy,
            circuit_breaker=circuit_breaker,
        )
    
    @staticmethod
    def create_null() -> 'NullMessagePublisher':
        """Create null publisher that does nothing.
        
        Useful for testing and development.
        
        Returns:
            NullMessagePublisher instance
        """
        return NullMessagePublisher()
    
    @staticmethod
    def create_mock(
        connection: Optional['MockMessageConnection'] = None,
    ) -> 'MockMessagePublisher':
        """Create mock publisher for testing.
        
        Args:
            connection: Optional mock connection
            
        Returns:
            MockMessagePublisher instance
        """
        from src.shared.testing.mocks import MockMessageConnection, MockMessagePublisher

        return MockMessagePublisher(connection=connection)


class NullMessagePublisher:
    """Null publisher that does nothing.
    
    Useful for testing and when message publishing is optional.
    
    Example:
        # Use in tests
        publisher = NullMessagePublisher()
        await publisher.publish(MyMessage(), routing_key="test")  # Does nothing
    """
    
    async def publish(
        self,
        message: Any,
        routing_key: str,
        **kwargs,
    ) -> None:
        """Do nothing."""
        pass
    
    async def health_check(self) -> bool:
        """Always healthy."""
        return True
    
    async def close(self) -> None:
        """Do nothing."""
        pass


class PublishError(Exception):
    """Raised when message publishing fails after all retries."""
    
    def __init__(self, message: str, original: Optional[Exception] = None):
        self.message = message
        self.original = original
        super().__init__(message)


__all__ = [
    "MessagePublisher",
    "MessagePublisherFactory",
    "NullMessagePublisher",
    "PublishError",
]
