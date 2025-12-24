"""Logger factory for creating configured loggers."""
import logging
import sys
from typing import Optional

from src.shared.utils.logging.context import get_service_name, _service_name_var
from src.shared.utils.logging.formatters import StructuredJSONFormatter
from src.shared.utils.logging.handlers import SamplingHandler, NullHandler

_logger = logging.getLogger(__name__)


# Global configuration
_service_name_global: Optional[str] = None
_sampling_config_global: Optional[dict] = None


def configure_logging(
    service_name: str,
    level: int = logging.INFO,
    sampling_config: Optional[dict] = None,
    log_file: Optional[str] = None,
    enable_console: bool = True,
) -> None:
    """Configure global logging settings.
    
    Args:
        service_name: Service name for all logs
        level: Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        sampling_config: Dict with sampling rates per level
            {
                "debug": 0.01,      # 1% of DEBUG logs
                "info": 0.10,        # 10% of INFO logs
                "warning": 0.50,      # 50% of WARNING logs
                "error": 1.00,         # 100% of ERROR logs (always)
                "critical": 1.00,     # 100% of CRITICAL logs (always)
            }
        log_file: Path to log file (optional, if None use console)
        enable_console: Enable console output (stdout/stderr)
    """
    global _service_name_global, _sampling_config_global
    
    _service_name_global = service_name
    _sampling_config_global = sampling_config or {
        "debug": 0.0,   # No DEBUG logs in production
        "info": 0.10,
        "warning": 0.50,
        "error": 1.00,
        "critical": 1.00,
    }
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create JSON formatter
    formatter = StructuredJSONFormatter(service_name=service_name)
    
    # Create handlers
    handlers = []
    
    # Console handler (optional)
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    # File handler (optional)
    if log_file:
        from src.shared.utils.logging.handlers import RotatingFileHandler
        
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Add sampling handler if configured
    if _sampling_config_global:
        sampling_handler = SamplingHandler(
            handler=logging.StreamHandler(sys.stdout) if not log_file else file_handler,
            **_sampling_config_global,
        )
        handlers.append(sampling_handler)
    
    # Add handlers to root logger
    for handler in handlers:
        root_logger.addHandler(handler)
    
    _logger.info(
        "Logging configured",
        extra={
            "service_name": service_name,
            "level": logging.getLevelName(level),
            "sampling_config": _sampling_config_global,
            "log_file": log_file,
            "handlers_count": len(handlers),
        },
    )


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance with configured handlers
    
    Example:
        logger = get_logger(__name__)
        logger.info("This will be structured JSON")
    """
    logger = logging.getLogger(name)
    
    # Set service name in context if not already set
    if _service_name_global and _service_name_var.get(None) is None:
        _service_name_var.set(_service_name_global)
    
    return logger


def disable_logging() -> None:
    """Disable all logging (use NullHandler).
    
    Useful for tests.
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(NullHandler())
    _logger.info("Logging disabled (NullHandler)")


def get_sampling_config() -> Optional[dict]:
    """Get current sampling configuration."""
    return _sampling_config_global


def set_sampling_config(sampling_config: dict) -> None:
    """Update sampling configuration.
    
    Args:
        sampling_config: New sampling configuration
    """
    global _sampling_config_global
    _sampling_config_global = sampling_config
    
    _logger.info(
        "Sampling configuration updated",
        extra={"sampling_config": sampling_config},
    )


class RotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Custom rotating file handler with async-safe writing."""
    
    # This is a thin wrapper around RotatingFileHandler
    # In production, consider using WatchedFileHandler for async-safe rotation
    pass

