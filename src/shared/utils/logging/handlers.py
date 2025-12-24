"""Log handlers for structured logging."""
import json
import logging
import random
import time
from collections import deque
from typing import Callable, List, Optional

from src.shared.utils.logging.formatters import StructuredJSONFormatter


class SamplingHandler(logging.Handler):
    """Handler that samples logs based on level and configured rates.
    
    Never drops ERROR or CRITICAL logs.
    Samples INFO, DEBUG, WARNING logs based on configured rates.
    """
    
    def __init__(
        self,
        handler: logging.Handler,
        debug_rate: float = 0.01,      # 1% of DEBUG logs
        info_rate: float = 0.10,       # 10% of INFO logs
        warning_rate: float = 0.50,    # 50% of WARNING logs
    ):
        """Initialize sampling handler.
        
        Args:
            handler: Underlying handler to emit sampled logs
            debug_rate: Sampling rate for DEBUG level (0.0-1.0)
            info_rate: Sampling rate for INFO level (0.0-1.0)
            warning_rate: Sampling rate for WARNING level (0.0-1.0)
        
        Note: ERROR and CRITICAL are always sampled (rate = 1.0)
        """
        super().__init__()
        self.handler = handler
        self.debug_rate = debug_rate
        self.info_rate = info_rate
        self.warning_rate = warning_rate
        # ERROR and CRITICAL are always sampled
        self.error_rate = 1.0
        self.critical_rate = 1.0
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit record if sampling decision allows it.
        
        Args:
            record: LogRecord to potentially emit
        """
        # Get sampling rate for this log level
        sampling_rate = self._get_sampling_rate(record.levelno)
        
        # Always sample ERROR and CRITICAL
        if sampling_rate >= 1.0:
            self.handler.emit(record)
            return
        
        # Sample based on random number
        if random.random() < sampling_rate:
            self.handler.emit(record)
        else:
            # Log dropped (at DEBUG level for visibility)
            sampling_record = logging.LogRecord(
                name=record.name,
                level=logging.DEBUG,
                pathname=record.pathname,
                lineno=record.lineno,
                msg=f"[SAMPLED] {record.getMessage()}",
                args=record.args,
                exc_info=record.exc_info,
            )
            # Emit to show it was sampled
            self.handler.emit(sampling_record)
    
    def _get_sampling_rate(self, levelno: int) -> float:
        """Get sampling rate for a log level number.
        
        Args:
            levelno: Logging level number (logging.DEBUG, logging.INFO, etc.)
        
        Returns:
            Sampling rate (0.0-1.0)
        """
        if levelno <= logging.DEBUG:
            return self.debug_rate
        elif levelno <= logging.INFO:
            return self.info_rate
        elif levelno <= logging.WARNING:
            return self.warning_rate
        elif levelno <= logging.ERROR:
            return self.error_rate
        else:  # CRITICAL
            return self.critical_rate
    
    def close(self) -> None:
        """Close underlying handler."""
        self.handler.close()
    
    def flush(self) -> None:
        """Flush underlying handler."""
        self.handler.flush()


class NullHandler(logging.Handler):
    """Handler that drops all log messages.
    
    Useful for testing or disabling logging for specific modules.
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        """Drop all log records."""
        pass
    
    def flush(self) -> None:
        """No-op flush."""
        pass


class MetricsHandler(logging.Handler):
    """Handler that records log metrics (counts by level, etc.).
    
    Note: This is a placeholder. In production, integrate with Prometheus/StatsD.
    """
    
    def __init__(self, metrics_callback: Optional[Callable[[str, int], None]] = None):
        """Initialize metrics handler.
        
        Args:
            metrics_callback: Callback to record metrics. 
                Args: (level_name, value_to_increment)
        """
        super().__init__()
        self.metrics_callback = metrics_callback
        self.counts = {
            "DEBUG": 0,
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
        }
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit record and update metrics."""
        level_name = record.levelname
        if level_name in self.counts:
            self.counts[level_name] += 1
        
        # Call metrics callback if provided
        if self.metrics_callback:
            try:
                self.metrics_callback(level_name, 1)
            except Exception:
                # Don't fail logging if metrics callback fails
                pass
    
    def get_counts(self) -> dict:
        """Get current log counts by level."""
        return self.counts.copy()
    
    def reset_counts(self) -> None:
        """Reset all log counts."""
        for level in self.counts:
            self.counts[level] = 0


class SlidingWindowSamplingHandler(SamplingHandler):
    """Sampling handler with sliding window for adaptive sampling.
    
    Adapts sampling rate based on recent log volume.
    If recent logs exceed threshold, reduce sampling rate.
    """
    
    def __init__(
        self,
        handler: logging.Handler,
        window_seconds: int = 60,
        max_logs_per_window: int = 1000,
        base_debug_rate: float = 0.01,
        base_info_rate: float = 0.10,
        base_warning_rate: float = 0.50,
    ):
        """Initialize adaptive sampling handler.
        
        Args:
            handler: Underlying handler
            window_seconds: Time window for volume tracking
            max_logs_per_window: Target logs per window
            base_debug_rate: Base DEBUG rate
            base_info_rate: Base INFO rate
            base_warning_rate: Base WARNING rate
        """
        super().__init__(handler, base_debug_rate, base_info_rate, base_warning_rate)
        self.window_seconds = window_seconds
        self.max_logs = max_logs_per_window
        self.window = deque()
        self.base_debug_rate = base_debug_rate
        self.base_info_rate = base_info_rate
        self.base_warning_rate = base_warning_rate
    
    def _cleanup_window(self) -> None:
        """Remove old entries from window."""
        now = time.time()
        while self.window and self.window[0] < now - self.window_seconds:
            self.window.popleft()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit record with adaptive sampling."""
        self._cleanup_window()
        
        # Calculate current log count in window
        current_count = len(self.window)
        
        # Adjust sampling rate based on volume
        if current_count >= self.max_logs:
            # High volume: reduce sampling rate
            debug_rate = self.base_debug_rate * 0.5
            info_rate = self.base_info_rate * 0.5
            warning_rate = self.base_warning_rate * 0.5
        else:
            # Normal volume: use base rates
            debug_rate = self.base_debug_rate
            info_rate = self.base_info_rate
            warning_rate = self.base_warning_rate
        
        # Temporarily update rates for this emit
        old_debug = self.debug_rate
        old_info = self.info_rate
        old_warning = self.warning_rate
        
        self.debug_rate = debug_rate
        self.info_rate = info_rate
        self.warning_rate = warning_rate
        
        # Emit with adjusted rates
        super().emit(record)
        
        # Restore rates and add to window
        self.debug_rate = old_debug
        self.info_rate = old_info
        self.warning_rate = old_warning
        self.window.append(time.time())

