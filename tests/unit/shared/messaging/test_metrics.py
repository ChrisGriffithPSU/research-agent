"""Unit tests for messaging metrics."""
import pytest
import time

from src.shared.messaging.metrics import (
    MessagingMetrics,
    get_metrics,
    reset_metrics,
)


def test_metrics_initialization():
    """Should initialize with empty metrics."""
    metrics = MessagingMetrics()

    summary = metrics.get_summary()

    assert len(summary["counters"]) == 0
    assert len(summary["gauges"]) == 0
    assert len(summary["timers"]) == 0
    assert len(summary["errors"]) == 0


def test_metrics_increment():
    """Should increment counter."""
    metrics = MessagingMetrics()

    metrics.increment("test.counter", value=5)
    assert metrics.get_counter("test.counter") == 5

    metrics.increment("test.counter", value=3)
    assert metrics.get_counter("test.counter") == 8


def test_metrics_decrement():
    """Should decrement counter."""
    metrics = MessagingMetrics()

    metrics.increment("test.counter", value=10)
    metrics.decrement("test.counter", value=3)

    assert metrics.get_counter("test.counter") == 7


def test_metrics_set_gauge():
    """Should set gauge value."""
    metrics = MessagingMetrics()

    metrics.set_gauge("test.gauge", 42.5)
    assert metrics.get_gauge("test.gauge") == 42.5

    # Overwrites previous value
    metrics.set_gauge("test.gauge", 99.9)
    assert metrics.get_gauge("test.gauge") == 99.9


def test_metrics_record_time():
    """Should record timer durations."""
    metrics = MessagingMetrics()

    # Record some durations
    metrics.record_time("test.timer", 100.0)
    metrics.record_time("test.timer", 200.0)
    metrics.record_time("test.timer", 50.0)

    stats = metrics.get_timer_stats("test.timer")

    assert stats["count"] == 3
    assert stats["min"] == 50.0
    assert stats["max"] == 200.0
    assert stats["avg"] == 116.67  # (100+200+50)/3


def test_metrics_timer_stats_percentiles():
    """Should calculate percentiles correctly."""
    metrics = MessagingMetrics()

    # Record durations: 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
    for duration in range(10, 110, 10):
        metrics.record_time("test.timer", float(duration))

    stats = metrics.get_timer_stats("test.timer")

    # p50 should be ~60
    assert 59 <= stats["p50"] <= 61
    # p95 should be ~95
    assert 94 <= stats["p95"] <= 96
    # p99 should be ~99
    assert 98 <= stats["p99"] <= 100


def test_metrics_timer_keeps_recent():
    """Should only keep last 1000 samples."""
    metrics = MessagingMetrics()

    # Record 1500 samples
    for i in range(1500):
        metrics.record_time("test.timer", float(i))

    stats = metrics.get_timer_stats("test.timer")

    # Should only have last 1000
    assert stats["count"] == 1000
    # Min should be 500 (1500 - 1000)
    assert stats["min"] == 500.0
    # Max should be 1499 (last sample)
    assert stats["max"] == 1499.0


def test_metrics_record_error():
    """Should record errors by queue and type."""
    metrics = MessagingMetrics()

    metrics.record_error("content.discovered", "ValidationError")
    metrics.record_error("content.discovered", "ValidationError")
    metrics.record_error("content.discovered", "ProcessingError")

    summary = metrics.get_error_summary("content.discovered")

    assert "ValidationError" in summary
    assert summary["ValidationError"] == 2
    assert "ProcessingError" in summary
    assert summary["ProcessingError"] == 1


def test_metrics_record_message_published():
    """Should record published messages."""
    metrics = MessagingMetrics()

    metrics.record_message_published("content.discovered")
    metrics.record_message_published("insights.extracted")

    assert metrics.get_counter("messages.published.content.discovered") == 1
    assert metrics.get_counter("messages.published.insights.extracted") == 1


def test_metrics_record_message_consumed():
    """Should record consumed messages."""
    metrics = MessagingMetrics()

    metrics.record_message_consumed("content.discovered")
    metrics.record_message_consumed("content.discovered")

    assert metrics.get_counter("messages.consumed.content.discovered") == 2


def test_metrics_record_message_acked():
    """Should record acked messages."""
    metrics = MessagingMetrics()

    metrics.record_message_acked("content.discovered")

    assert metrics.get_counter("messages.acked.content.discovered") == 1


def test_metrics_record_message_nacked_requeued():
    """Should record nacked requeued messages."""
    metrics = MessagingMetrics()

    metrics.record_message_nacked("content.discovered", requeued=True)
    metrics.record_message_nacked("content.discovered", requeued=True)

    assert metrics.get_counter("messages.nacked.content.discovered.requeued") == 2


def test_metrics_record_message_nacked_dlq():
    """Should record nacked DLQ messages."""
    metrics = MessagingMetrics()

    metrics.record_message_nacked("content.discovered", requeued=False)
    metrics.record_message_nacked("insights.extracted", requeued=False)

    assert metrics.get_counter("messages.nacked.content.discovered.dlq") == 1
    assert metrics.get_counter("messages.nacked.insights.extracted.dlq") == 1


def test_metrics_record_dlq_message():
    """Should record DLQ messages."""
    metrics = MessagingMetrics()

    metrics.record_dlq_message("content.discovered", "validation_error")
    metrics.record_dlq_message("content.discovered", "permanent_error")

    assert metrics.get_counter("dlq.messages.content.discovered") == 2
    assert metrics.get_counter("dlq.content.discovered.validation_error") == 1
    assert metrics.get_counter("dlq.content.discovered.permanent_error") == 1


def test_metrics_get_summary():
    """Should return complete summary."""
    metrics = MessagingMetrics()

    # Add some data
    metrics.increment("test.counter", value=10)
    metrics.set_gauge("test.gauge", 42.0)
    metrics.record_time("test.timer", 100.0)
    metrics.record_error("test.queue", "TestError")

    summary = metrics.get_summary()

    assert "counters" in summary
    assert "gauges" in summary
    assert "timers" in summary
    assert "errors" in summary
    assert "timestamp" in summary

    assert summary["counters"]["test.counter"] == 10
    assert summary["gauges"]["test.gauge"] == 42.0
    assert summary["timers"]["test.timer"]["count"] == 1


def test_metrics_reset_all():
    """Should reset all metrics."""
    metrics = MessagingMetrics()

    # Add some data
    metrics.increment("test.counter", value=10)
    metrics.set_gauge("test.gauge", 42.0)
    metrics.record_time("test.timer", 100.0)

    # Reset all
    metrics.reset()

    summary = metrics.get_summary()

    assert len(summary["counters"]) == 0
    assert len(summary["gauges"]) == 0
    assert len(summary["timers"]) == 0
    assert len(summary["errors"]) == 0


def test_metrics_reset_specific():
    """Should reset specific metric."""
    metrics = MessagingMetrics()

    # Add data to multiple metrics
    metrics.increment("counter1", value=10)
    metrics.increment("counter2", value=20)
    metrics.set_gauge("gauge1", 42.0)

    # Reset specific counter
    metrics.reset("counter1")

    assert metrics.get_counter("counter1") == 0
    assert metrics.get_counter("counter2") == 20
    assert metrics.get_gauge("gauge1") == 42.0


def test_global_metrics_singleton():
    """Should return singleton instance."""
    metrics1 = get_metrics()
    metrics2 = get_metrics()

    # Should be same instance
    assert metrics1 is metrics2


def test_global_metrics_reset():
    """Should reset global metrics."""
    metrics = get_metrics()

    # Add some data
    metrics.increment("test.counter", value=10)

    # Reset via global function
    reset_metrics()

    # Global instance should be cleared
    assert metrics.get_counter("test.counter") == 0

