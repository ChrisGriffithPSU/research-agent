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

