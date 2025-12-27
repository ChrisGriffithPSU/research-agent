"""Messaging infrastructure for RabbitMQ.

Provides:
- Configuration management (MessagingConfig)
- Connection management (RabbitMQConnection, get_connection)
- Message schemas (BaseMessage, SourceMessage, etc.)
- Publisher API (MessagePublisher, get_publisher)
- Consumer API (MessageConsumer, message_handler decorator)
- Retry strategies (ExponentialBackoffStrategy, etc.)
- Circuit breaker (CircuitBreaker, circuit_breaker decorator)
- Metrics tracking (MessagingMetrics, get_metrics)
- Health checks (check_messaging_health, quick_check)
- Queue setup (QueueSetup)
"""

# Configuration
from src.shared.messaging.config import MessagingConfig, messaging_config

# Exceptions
from src.shared.messaging.exceptions import (
    MessagingError,
    ConnectionError,
    PublishError,
    ConsumeError,
    MessageValidationError,
    QueueError,
    CircuitBreakerOpenError,
    PermanentError,
    TemporaryError,
)

# Schemas
from src.shared.messaging.schemas import (
    QueueName,
    BaseMessage,
    SourceMessage,
    DeduplicatedContentMessage,
    ExtractedInsightsMessage,
    DigestItem,
    DigestReadyMessage,
    FeedbackMessage,
    TrainingTriggerMessage,
)

# Core logic
from src.shared.messaging.retry import (
    IRetryStrategy,
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    NoRetryStrategy,
)

from src.shared.messaging.circuit_breaker import (
    CircuitBreaker,
    circuit_breaker,
)

from src.shared.messaging.metrics import (
    MessagingMetrics,
    get_metrics,
    reset_metrics,
)

# Infrastructure
from src.shared.messaging.connection import (
    RabbitMQConnection,
    get_connection,
    disconnect,
)

from src.shared.messaging.queue_setup import (
    QueueSetup,
    EXCHANGE_NAME,
    DLQ_EXCHANGE_NAME,
)

# Publisher/Consumer APIs
from src.shared.messaging.publisher import (
    MessagePublisher,
    MessagePublisherFactory,
    NullMessagePublisher,
)

from src.shared.messaging.consumer import (
    MessageConsumer,
    message_handler,
)

# Health checks
from src.shared.messaging.health import (
    HealthStatus,
    check_messaging_health,
    quick_check,
)

__all__ = [
    # Configuration
    "MessagingConfig",
    "messaging_config",
    # Exceptions
    "MessagingError",
    "ConnectionError",
    "PublishError",
    "ConsumeError",
    "MessageValidationError",
    "QueueError",
    "CircuitBreakerOpenError",
    "PermanentError",
    "TemporaryError",
    # Schemas
    "QueueName",
    "BaseMessage",
    "SourceMessage",
    "DeduplicatedContentMessage",
    "ExtractedInsightsMessage",
    "DigestItem",
    "DigestReadyMessage",
    "FeedbackMessage",
    "TrainingTriggerMessage",
    # Core logic
    "IRetryStrategy",
    "ExponentialBackoffStrategy",
    "LinearBackoffStrategy",
    "NoRetryStrategy",
    "CircuitBreaker",
    "circuit_breaker",
    # Metrics
    "MessagingMetrics",
    "get_metrics",
    "reset_metrics",
    # Infrastructure
    "RabbitMQConnection",
    "get_connection",
    "disconnect",
    "QueueSetup",
    "EXCHANGE_NAME",
    "DLQ_EXCHANGE_NAME",
    # Publisher/Consumer
    "MessagePublisher",
    "MessagePublisherFactory",
    "NullMessagePublisher",
    "MessageConsumer",
    "message_handler",
    # Health checks
    "HealthStatus",
    "check_messaging_health",
    "quick_check",
]

