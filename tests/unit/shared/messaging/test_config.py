"""Unit tests for messaging configuration."""

from src.shared.messaging.config import MessagingConfig


def test_connection_url_uses_all_connection_parts() -> None:
    cfg = MessagingConfig(host="mq", port=5673, user="u", password="p", virtual_host="/v1")
    assert cfg.connection_url == "amqp://u:p@mq:5673/v1"


def test_connection_url_for_root_vhost_ends_with_single_slash() -> None:
    cfg = MessagingConfig(virtual_host="/")
    assert cfg.connection_url.endswith("/")


def test_invalid_negative_queue_max_length_raises() -> None:
    try:
        MessagingConfig(queue_max_length=-1)
    except ValueError as exc:
        assert "queue_max_length" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative queue_max_length")
