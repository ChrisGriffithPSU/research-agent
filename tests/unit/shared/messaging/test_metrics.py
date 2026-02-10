"""Unit tests for messaging metrics."""

from src.shared.messaging.metrics import MessagingMetrics, get_metrics, reset_metrics


def test_counter_gauge_and_timer_recording() -> None:
    metrics = MessagingMetrics()
    metrics.increment("a")
    metrics.increment("a", 2)
    metrics.decrement("a")
    metrics.set_gauge("g", 3.14)
    metrics.record_time("t", 100.0)
    metrics.record_time("t", 200.0)

    assert metrics.get_counter("a") == 2
    assert metrics.get_gauge("g") == 3.14
    stats = metrics.get_timer_stats("t")
    assert stats["count"] == 2
    assert stats["min"] == 100.0
    assert stats["max"] == 200.0


def test_error_summary_and_global_reset() -> None:
    reset_metrics()
    metrics = get_metrics()
    metrics.record_error("q1", "ValidationError")
    metrics.record_error("q1", "ValidationError")
    metrics.record_error("q1", "Timeout")
    summary = metrics.get_error_summary("q1")
    assert summary["ValidationError"] == 2
    assert summary["Timeout"] == 1

    reset_metrics()
    assert get_metrics().get_counter("total_errors.q1") == 0
