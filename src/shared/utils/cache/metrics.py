"""Cache metrics collection."""
import logging
import time
from collections import deque
from typing import Callable, Optional


logger = logging.getLogger(__name__)


class CacheMetrics:
    """Simple counter-based cache metrics.
    
    Tracks hits, misses, and calculates hit rate on demand.
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.hits = 0
        self.misses = 0
    
    def record_hit(self, cache_key: Optional[str] = None) -> None:
        """Record a cache hit.
        
        Args:
            cache_key: Cache key (optional, for logging)
        """
        self.hits += 1
        
        logger.debug(
            f"Cache hit",
            extra={"cache_key": cache_key, "total_hits": self.hits},
        )
    
    def record_miss(self, cache_key: Optional[str] = None) -> None:
        """Record a cache miss.
        
        Args:
            cache_key: Cache key (optional, for logging)
        """
        self.misses += 1
        
        logger.debug(
            f"Cache miss",
            extra={"cache_key": cache_key, "total_misses": self.misses},
        )
    
    def get_hit_rate(self) -> float:
        """Calculate cache hit rate.
        
        Returns:
            Hit rate as float (0.0 to 1.0)
        """
        total = self.hits + self.misses
        
        if total == 0:
            return 0.0
        
        return self.hits / total
    
    def get_stats(self) -> dict:
        """Get current statistics.
        
        Returns:
            Dict with:
                - hits: Total hit count
                - misses: Total miss count
                - hit_rate: Hit rate (0.0-1.0)
                - total_operations: Total operations (hits + misses)
        """
        hit_rate = self.get_hit_rate()
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "total_operations": self.hits + self.misses,
        }
    
    def reset(self) -> None:
        """Reset all counters.
        
        Useful for testing or periodic reset.
        """
        self.hits = 0
        self.misses = 0
        
        logger.debug("Cache metrics reset")


class SlidingWindowCacheMetrics:
    """Time-based sliding window cache metrics.
    
    Tracks hits and misses within a time window to show recent performance.
    More expensive than simple counters but provides recent trends.
    """
    
    def __init__(self, window_seconds: int = 300):
        """Initialize sliding window metrics.
        
        Args:
            window_seconds: Time window in seconds (default: 300 = 5 minutes)
        """
        self.window_seconds = window_seconds
        self.window = deque()  # List of (timestamp, is_hit_bool)
        self.hits = 0
        self.misses = 0
    
    def _cleanup_window(self) -> None:
        """Remove old entries from window."""
        now = time.time()
        
        while self.window and self.window[0] < now - self.window_seconds:
            self.window.popleft()
    
    def record_hit(self, cache_key: Optional[str] = None) -> None:
        """Record a cache hit within window."""
        self._cleanup_window()
        
        now = time.time()
        self.window.append((now, True))
        self.hits += 1
        
        logger.debug(
            f"Cache hit (windowed)",
            extra={
                "cache_key": cache_key,
                "window_size": len(self.window),
            },
        )
    
    def record_miss(self, cache_key: Optional[str] = None) -> None:
        """Record a cache miss within window."""
        self._cleanup_window()
        
        now = time.time()
        self.window.append((now, False))
        self.misses += 1
        
        logger.debug(
            f"Cache miss (windowed)",
            extra={
                "cache_key": cache_key,
                "window_size": len(self.window),
            },
        )
    
    def get_hit_rate(self) -> float:
        """Calculate cache hit rate from window.
        
        Returns:
            Hit rate within time window (0.0 to 1.0)
        """
        self._cleanup_window()
        
        window_size = len(self.window)
        
        if window_size == 0:
            return 0.0
        
        # Count hits in window
        window_hits = sum(1 for _, is_hit in self.window if is_hit)
        
        return window_hits / window_size
    
    def get_stats(self) -> dict:
        """Get current statistics.
        
        Returns:
            Dict with:
                - hits: Total hit count (cumulative)
                - misses: Total miss count (cumulative)
                - hit_rate: Hit rate from window (recent)
                - window_size: Number of operations in window
                - total_operations: Total operations (hits + misses)
        """
        window_size = len(self.window)
        hit_rate = self.get_hit_rate()
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "window_size": window_size,
            "window_seconds": self.window_seconds,
            "total_operations": self.hits + self.misses,
        }
    
    def reset(self) -> None:
        """Reset all counters and clear window."""
        self.hits = 0
        self.misses = 0
        self.window.clear()
        
        logger.debug("Sliding window cache metrics reset")


class MetricsTracker:
    """Tracks metrics with optional callback for external monitoring.
    
    Can integrate with Prometheus, StatsD, or other metrics systems.
    """
    
    def __init__(self, metrics_callback: Optional[Callable[[str, int], None]] = None):
        """Initialize metrics tracker.
        
        Args:
            metrics_callback: Optional callback to record metrics externally.
                                Called with (metric_name, value)
        """
        self.metrics_callback = metrics_callback
        self.counters = {
            "cache_hits": 0,
            "cache_misses": 0,
        "cache_errors": 0,
        "cache_timeouts": 0,
        "cache_size_bytes": 0,
        "cache_operations_total": 0,
        }
        
        if metrics_callback:
            logger.info("Metrics tracker initialized with external callback")
    
    def record_hit(self) -> None:
        """Record cache hit."""
        self.counters["cache_hits"] += 1
        self.counters["cache_operations_total"] += 1
        self._emit_metric("cache_hits")
    
    def record_miss(self) -> None:
        """Record cache miss."""
        self.counters["cache_misses"] += 1
        self.counters["cache_operations_total"] += 1
        self._emit_metric("cache_misses")
    
    def record_error(self) -> None:
        """Record cache error."""
        self.counters["cache_errors"] += 1
        self._emit_metric("cache_errors")
    
    def record_timeout(self) -> None:
        """Record cache timeout."""
        self.counters["cache_timeouts"] += 1
        self._emit_metric("cache_timeouts")
    
    def record_size(self, size_bytes: int) -> None:
        """Record cached item size (for memory tracking)."""
        self.counters["cache_size_bytes"] += size_bytes
        self.counters["cache_operations_total"] += 1
        self._emit_metric("cache_size_bytes")
    
    def get_counts(self) -> dict:
        """Get current counter values."""
        return self.counters.copy()
    
    def reset(self) -> None:
        """Reset all counters."""
        for key in self.counters:
            self.counters[key] = 0
        
        logger.debug("Metrics tracker counters reset")
    
    def _emit_metric(self, metric_name: str) -> None:
        """Emit metric to callback if configured."""
        if self.metrics_callback:
            try:
                self.metrics_callback(metric_name, self.counters.get(metric_name, 0))
            except Exception as e:
                logger.error(f"Metrics callback failed: {e}", exc_info=True)


def get_metrics(use_window: bool = False, window_seconds: int = 300) -> object:
    """Factory function to get metrics instance.
    
    Args:
        use_window: Use sliding window metrics (default: False)
        window_seconds: Window duration for sliding metrics (default: 300s)
    
    Returns:
        CacheMetrics or SlidingWindowCacheMetrics instance
    
    Example:
        metrics = get_metrics(use_window=False)  # Returns CacheMetrics
        metrics = get_metrics(use_window=True, window_seconds=600)  # Returns SlidingWindowCacheMetrics
    """
    if use_window:
        return SlidingWindowCacheMetrics(window_seconds=window_seconds)
    else:
        return CacheMetrics()

