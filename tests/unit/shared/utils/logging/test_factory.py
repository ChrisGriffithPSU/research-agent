"""Unit tests for logger factory utilities."""

from __future__ import annotations

import logging

from src.shared.utils.logging.factory import configure_logging, disable_logging, get_logger


def test_configure_logging_and_get_logger() -> None:
    configure_logging(service_name="test-service", level=logging.INFO, enable_console=False)
    logger = get_logger("tests.logger")
    assert logger.name == "tests.logger"


def test_disable_logging_replaces_handlers() -> None:
    disable_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
