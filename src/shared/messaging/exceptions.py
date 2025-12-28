"""Messaging-related exceptions."""
from typing import Optional


class MessagingError(Exception):
    """Base exception for messaging errors."""

    def __init__(
        self,
        message: str,
        original: Optional[Exception] = None,
    ):
        self.message = message
        self.original = original
        if original:
            super().__init__(f"{message}: {original}")
        else:
            super().__init__(message)


class ConnectionError(MessagingError):
    """RabbitMQ connection failed or lost.

    Raised when:
    - Cannot connect to RabbitMQ
    - Connection is unexpectedly closed
    - Authentication fails
    """


class PublishError(MessagingError):
    """Failed to publish message after all retry attempts.

    Raised when:
    - Publisher confirms fail after retries
    - Exchange does not exist
    - Message rejected by broker
    """


class ConsumeError(MessagingError):
    """Failed to consume or process message.

    Raised when:
    - Cannot start consumer
    - Queue does not exist
    - Consumer channel closes unexpectedly
    """


class MessageValidationError(MessagingError):
    """Message failed Pydantic validation.

    Raised when:
    - Message is missing required fields
    - Message has invalid data types
    - Message schema version mismatch
    """


class QueueError(MessagingError):
    """Queue-related operation failed.

    Raised when:
    - Cannot declare queue
    - Cannot bind queue to exchange
    - Queue configuration is invalid
    """


class CircuitBreakerOpenError(MessagingError):
    """Circuit breaker is open, preventing operations.

    Raised when:
    - Circuit breaker has opened due to repeated failures
    - Operation blocked until timeout
    """


class ChannelError(MessagingError):
    """Base exception for channel-level errors.

    Raised when:
    - Channel operation fails
    - Channel is in invalid state
    """


class ChannelClosedError(ChannelError):
    """RabbitMQ broker closed the channel.

    Raised when:
    - Broker closes channel due to error
    - Channel reaches limit
    - Authentication issue with specific channel

    Attributes:
        reply_code: AMQP reply code from broker
        reply_text: AMQP reply text from broker
    """

    def __init__(
        self,
        message: str,
        reply_code: Optional[int] = None,
        reply_text: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(message, original=original)


class ConnectionClosedError(ConnectionError):
    """RabbitMQ broker closed the connection.

    Raised when:
    - Broker closes the connection
    - Connection times out
    - Network partition detected

    Attributes:
        reply_code: AMQP reply code from broker
        reply_text: AMQP reply text from broker
    """

    def __init__(
        self,
        message: str,
        reply_code: Optional[int] = None,
        reply_text: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(message, original=original)


class ResourceLockedError(MessagingError):
    """Resource is locked by another operation.

    Raised when:
    - Queue is exclusive to another connection
    - Message is being processed by another consumer
    - Cannot acquire lock on resource
    """


class PreconditionFailedError(MessagingError):
    """Broker rejected operation due to precondition failure.

    Raised when:
    - Queue declaration parameters don't match
    - Message TTL conflicts with queue settings
    - Dead letter exchange configuration invalid
    - Version conflict on conditional update
    """

    def __init__(
        self,
        message: str,
        condition: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.condition = condition
        super().__init__(message, original=original)


class ConfirmFailedError(MessagingError):
    """Publisher confirm failed.

    Raised when:
    - Broker rejects message (NACK)
    - Message not routed to any queue
    - Internal broker error during confirmation

    Attributes:
        delivery_tag: Delivery tag of failed message
        reply_code: AMQP reply code
        reply_text: AMQP reply text
    """

    def __init__(
        self,
        message: str,
        delivery_tag: Optional[int] = None,
        reply_code: Optional[int] = None,
        reply_text: Optional[str] = None,
        original: Optional[Exception] = None,
    ):
        self.delivery_tag = delivery_tag
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(message, original=original)


class PermanentError(Exception):
    """Base exception for permanent errors that should not be retried.

    Services should raise this or inherit from it when an error indicates
    a permanent failure (e.g., invalid message, missing resource).

    When a PermanentError is raised:
    - Publisher: Does not retry, raises PublishError
    - Consumer: Sends message to DLQ (does not requeue)
    """

    pass


class TemporaryError(Exception):
    """Base exception for temporary/transient errors that should be retried.

    Services should raise this or inherit from it when an error indicates
    a temporary failure (e.g., network timeout, temporary unavailable).

    When a TemporaryError is raised:
    - Publisher: Retries with backoff
    - Consumer: Nacks with requeue (will retry)
    """

    pass

