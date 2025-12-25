"""RabbitMQ configuration and connection URL management."""
import logging
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class MessagingConfig(BaseSettings):
    """RabbitMQ configuration with connection and queue settings.

    Settings are loaded from environment variables with sensible defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RabbitMQ connection parameters
    host: str = Field(
        default="localhost",
        description="RabbitMQ host address"
    )
    port: int = Field(
        default=5672,
        description="RabbitMQ AMQP port"
    )
    user: str = Field(
        default="guest",
        description="RabbitMQ username"
    )
    password: str = Field(
        default="guest",
        description="RabbitMQ password"
    )
    virtual_host: str = Field(
        default="/",
        description="RabbitMQ virtual host"
    )

    # Connection settings
    heartbeat: int = Field(
        default=60,
        description="Heartbeat interval in seconds"
    )
    connection_timeout: int = Field(
        default=30,
        description="Connection timeout in seconds"
    )
    blocked_connection_timeout: int = Field(
        default=30,
        description="Blocked connection timeout in seconds"
    )

    # Queue configuration
    queue_max_length: int = Field(
        default=10000,
        description="Default maximum queue length (0 for unlimited)"
    )
    queue_message_ttl: Optional[int] = Field(
        default=86400000,  # 24 hours in milliseconds
        description="Default message TTL in milliseconds (None for no expiration)"
    )

    # Retry configuration
    publish_retry_max_attempts: int = Field(
        default=3,
        description="Max retry attempts for publishing"
    )
    publish_retry_base_delay: float = Field(
        default=1.0,
        description="Base delay for retry backoff in seconds"
    )
    publish_retry_max_delay: float = Field(
        default=60.0,
        description="Maximum delay for retry backoff in seconds"
    )

    # Circuit breaker configuration
    circuit_breaker_failure_threshold: int = Field(
        default=3,
        description="Number of failures before circuit opens"
    )
    circuit_breaker_timeout: float = Field(
        default=60.0,
        description="Circuit breaker timeout in seconds before half-open"
    )

    # Consumer configuration
    consumer_prefetch_count: int = Field(
        default=10,
        description="Number of messages to prefetch (QoS)"
    )

    @property
    def connection_url(self) -> str:
        """Construct AMQP connection URL."""
        # Strip leading slash from virtual_host to avoid double slashes in URL
        vhost = self.virtual_host.lstrip("/") if self.virtual_host != "/" else ""
        return (
            f"amqp://{self.user}:{self.password}@{self.host}:{self.port}"
            f"/{vhost}"
        )

    @field_validator("queue_max_length")
    @classmethod
    def validate_queue_max_length(cls, v: int) -> int:
        """Validate queue max length is non-negative."""
        if v < 0:
            raise ValueError("queue_max_length must be >= 0")
        return v

    @field_validator("queue_message_ttl")
    @classmethod
    def validate_queue_message_ttl(cls, v: Optional[int]) -> Optional[int]:
        """Validate queue message TTL is positive if set."""
        if v is not None and v <= 0:
            raise ValueError("queue_message_ttl must be > 0")
        return v


# Global configuration instance (loaded from environment)
messaging_config = MessagingConfig()

