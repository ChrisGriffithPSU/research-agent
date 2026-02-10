"""Unit tests for structured JSON formatter."""

from __future__ import annotations

import json
import logging

from src.shared.utils.logging.formatters import StructuredJSONFormatter


def test_formatter_outputs_json_with_expected_fields() -> None:
    formatter = StructuredJSONFormatter(service_name="svc")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    rendered = formatter.format(record)
    payload = json.loads(rendered)
    assert payload["service_name"] == "svc"
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
