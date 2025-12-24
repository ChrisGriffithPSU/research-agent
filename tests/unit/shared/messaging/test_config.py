"""Unit tests for MessagingConfig."""
import pytest
from src.shared.messaging.config import MessagingConfig


def test_messaging_config_defaults():
    """Should use sensible defaults."""
    config = MessagingConfig()

    assert config.host == "localhost"
    assert config.port == 5672
    assert config.user == "guest"
    assert config.password == "guest"
    assert config.virtual_host == "/"
    assert config.heartbeat == 60
    assert config.connection_timeout == 30
    assert config.queue_max_length == 10000
    assert config.queue_message_ttl == 86400000


def test_messaging_config_connection_url():
    """Should construct correct AMQP connection URL."""
    config = MessagingConfig(
        host="test-host",
        port=5673,
        user="testuser",
        password="testpass",
        virtual_host="/testvhost",
    )

    url = config.connection_url
    assert url == "amqp://testuser:testpass@test-host:5673/testvhost"


def test_messaging_config_queue_max_length_validation():
    """Should reject negative queue_max_length."""
    with pytest.raises(ValueError, match="queue_max_length must be >= 0"):
        MessagingConfig(queue_max_length=-1)

    # Zero should be valid
    config = MessagingConfig(queue_max_length=0)
    assert config.queue_max_length == 0


def test_messaging_config_ttl_validation():
    """Should reject non-positive TTL."""
    with pytest.raises(ValueError, match="queue_message_ttl must be > 0"):
        MessagingConfig(queue_message_ttl=-1)

    # None should be valid (no TTL)
    config = MessagingConfig(queue_message_ttl=None)
    assert config.queue_message_ttl is None


def test_messaging_config_positive_ttl():
    """Should accept positive TTL."""
    config = MessagingConfig(queue_message_ttl=3600000)
    assert config.queue_message_ttl == 3600000

