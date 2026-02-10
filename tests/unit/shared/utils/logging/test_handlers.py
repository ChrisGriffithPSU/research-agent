"""Unit tests for logging handlers."""

from __future__ import annotations

import logging

from src.shared.utils.logging.handlers import MetricsHandler, NullHandler, SamplingHandler


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_null_handler_drops_messages() -> None:
    handler = NullHandler()
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
    handler.emit(record)  # no-op


def test_metrics_handler_counts_levels() -> None:
    handler = MetricsHandler()
    handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None))
    handler.emit(logging.LogRecord("x", logging.ERROR, __file__, 1, "msg", (), None))
    counts = handler.get_counts()
    assert counts["INFO"] == 1
    assert counts["ERROR"] == 1


def test_sampling_handler_always_emits_errors() -> None:
    collector = _Collector()
    handler = SamplingHandler(collector, debug_rate=0.0, info_rate=0.0, warning_rate=0.0)
    err_record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", (), None)
    handler.emit(err_record)
    assert len(collector.records) == 1
