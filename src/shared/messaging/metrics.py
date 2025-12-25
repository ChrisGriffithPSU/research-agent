"""Metrics tracking for messaging operations."""
import logging
import time
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MessagingMetrics:
    """Track messaging metrics for observability.

    Thread-safe metrics collection for:
    - Counters (message counts, error counts)
    - Timers (latency, processing time)
    - Gauges (queue depth, connection status)
    """

    def __init__(self):
        """Initialize metrics storage."""
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._gauges: Dict[str, float] = {}
        self._errors: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def increment(self, metric_name: str, value: int = 1) -> None:
        """Increment a counter metric.

        Args:
            metric_name: Name of metric (e.g., "messages.published")
            value: Amount to increment (default 1)
        """
        with self._lock:
            self._counters[metric_name] += value

    def decrement(self, metric_name: str, value: int = 1) -> None:
        """Decrement a counter metric.

        Args:
            metric_name: Name of metric (e.g., "messages.in_queue")
            value: Amount to decrement (default 1)
        """
        with self._lock:
            self._counters[metric_name] -= value

    def set_gauge(self, metric_name: str, value: float) -> None:
        """Set a gauge metric (instantaneous value).

        Args:
            metric_name: Name of metric (e.g., "queue.depth")
            value: Current gauge value
        """
        with self._lock:
            self._gauges[metric_name] = value

    def record_time(self, metric_name: str, duration_ms: float) -> None:
        """Record a duration in milliseconds.

        Args:
            metric_name: Name of metric (e.g., "message.processing_time")
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            self._timers[metric_name].append(duration_ms)

            # Keep only last 1000 samples to prevent unbounded growth
            if len(self._timers[metric_name]) > 1000:
                self._timers[metric_name] = self._timers[metric_name][-1000:]

    def record_error(self, queue: str, error_type: str) -> None:
        """Record an error occurrence.

        Args:
            queue: Queue where error occurred
            error_type: Type of error (e.g., "ValidationError", "PublishError")
        """
        with self._lock:
            metric_name = f"errors.{queue}"
            self._errors[metric_name][error_type] += 1
            # Also increment total error counter
            self._counters[f"total_errors.{queue}"] += 1

    def record_message_published(self, queue: str) -> None:
        """Record a message published to queue.

        Args:
            queue: Queue name
        """
        self.increment(f"messages.published.{queue}")

    def record_message_consumed(self, queue: str) -> None:
        """Record a message consumed from queue.

        Args:
            queue: Queue name
        """
        self.increment(f"messages.consumed.{queue}")

    def record_message_acked(self, queue: str) -> None:
        """Record a message successfully acked.

        Args:
            queue: Queue name
        """
        self.increment(f"messages.acked.{queue}")

    def record_message_nacked(self, queue: str, requeued: bool) -> None:
        """Record a message nacked (rejected).

        Args:
            queue: Queue name
            requeued: Whether message was requeued or sent to DLQ
        """
        metric_name = f"messages.nacked.{queue}"
        if requeued:
            self.increment(f"{metric_name}.requeued")
        else:
            self.increment(f"{metric_name}.dlq")

    def record_dlq_message(self, queue: str, reason: str) -> None:
        """Record a message sent to dead letter queue.

        Args:
            queue: Original queue name
            reason: Reason for DLQ (e.g., "validation_error", "permanent_error")
        """
        self.increment(f"dlq.messages.{queue}")
        self.increment(f"dlq.{queue}.{reason}")

    def get_counter(self, metric_name: str) -> int:
        """Get current counter value.

        Args:
            metric_name: Name of metric

        Returns:
            Current counter value
        """
        with self._lock:
            return self._counters.get(metric_name, 0)

    def get_gauge(self, metric_name: str) -> Optional[float]:
        """Get current gauge value.

        Args:
            metric_name: Name of metric

        Returns:
            Current gauge value or None if not set
        """
        with self._lock:
            return self._gauges.get(metric_name)

    def get_timer_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a timer metric.

        Args:
            metric_name: Name of timer metric

        Returns:
            Dict with min, max, avg, count
        """
        with self._lock:
            values = self._timers.get(metric_name, [])

            if not values:
                return {"count": 0}

            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "p50": self._percentile(values, 50),
                "p95": self._percentile(values, 95),
                "p99": self._percentile(values, 99),
            }

    def get_error_summary(self, queue: Optional[str] = None) -> Dict[str, Any]:
        """Get error summary for queue or all queues.

        Args:
            queue: Queue name (None for all queues)

        Returns:
            Dict with error counts by type
        """
        with self._lock:
            if queue:
                metric_name = f"errors.{queue}"
                return dict(self._errors.get(metric_name, {}))
            else:
                # Aggregate all errors
                summary = {}
                for metric_name, errors in self._errors.items():
                    queue_name = metric_name.replace("errors.", "")
                    summary[queue_name] = dict(errors)
                return summary

    def get_summary(self) -> Dict[str, Any]:
        """Get complete metrics summary.

        Returns:
            Dict with all metrics (counters, gauges, timers, errors)
        """
        with self._lock:
            # Timer stats
            timer_stats = {}
            for metric_name in self._timers.keys():
                timer_stats[metric_name] = self.get_timer_stats(metric_name)

            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timers": timer_stats,
                "errors": self.get_error_summary(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def reset(self, metric_name: Optional[str] = None) -> None:
        """Reset metrics.

        Args:
            metric_name: Specific metric to reset (None for all)
        """
        with self._lock:
            if metric_name:
                if metric_name in self._counters:
                    self._counters[metric_name] = 0
                if metric_name in self._timers:
                    self._timers[metric_name] = []
                if metric_name in self._gauges:
                    del self._gauges[metric_name]
            else:
                # Reset all
                self._counters.clear()
                self._timers.clear()
                self._gauges.clear()
                self._errors.clear()
                logger.info("All metrics reset")

    @staticmethod
    def _percentile(values: List[float], p: int) -> float:
        """Calculate percentile.

        Args:
            values: Sorted list of values
            p: Percentile (0-100)

        Returns:
            Value at given percentile
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f < len(sorted_values) - 1 else f

        if f == c:
            return sorted_values[f]

        # Interpolate
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    def __repr__(self) -> str:
        """String representation."""
        with self._lock:
            return (
                f"MessagingMetrics(counters={len(self._counters)}, "
                f"timers={len(self._timers)}, "
                f"gauges={len(self._gauges)}, "
                f"errors={len(self._errors)})"
            )


# Global metrics instance
_global_metrics: Optional[MessagingMetrics] = None
_metrics_lock = threading.Lock()


def get_metrics() -> MessagingMetrics:
    """Get or create global metrics instance.

    Returns:
        Singleton MessagingMetrics instance
    """
    global _global_metrics
    with _metrics_lock:
        if _global_metrics is None:
            _global_metrics = MessagingMetrics()
            logger.debug("Global metrics instance created")
    return _global_metrics


def reset_metrics(metric_name: Optional[str] = None) -> None:
    """Reset global metrics.

    Args:
        metric_name: Specific metric to reset (None for all)
    """
    metrics = get_metrics()
    metrics.reset(metric_name)
    logger.info(f"Metrics reset: {metric_name or 'all'}")

