"""Structured JSON log formatters."""
import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict


def _serialize_value(value: Any) -> Any:
    """Safely serialize value to JSON-compatible type."""
    if value is None:
        return None
    elif isinstance(value, (str, int, float, bool)):
        return value
    elif isinstance(value, (list, dict)):
        return value
    elif hasattr(value, "isoformat"):
        # Handle datetime objects
        return value.isoformat()
    else:
        # Fallback: try to convert to string
        try:
            return str(value)
        except Exception:
            return f"<unserializable: {type(value).__name__}>"

# Sensitive data patterns to redact
_SENSITIVE_PATTERNS = [
    ("api_key", "api_key"),
    ("password", "password"),
    ("passwd", "passwd"),
    ("token", "token"),
    ("secret", "secret"),
    ("authorization", "authorization"),
    ("bearer", "bearer"),
]


def _redact_sensitive(data: Any) -> Any:
    """Redact sensitive values from data.
    
    Args:
        data: Data to redact (can be dict, list, or primitive)
    
    Returns:
        Redacted data with sensitive values replaced with [REDACTED]
    """
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            # Check if key matches sensitive patterns
            key_lower = key.lower()
            if any(pattern in key_lower for pattern, _ in _SENSITIVE_PATTERNS):
                redacted[key] = "[REDACTED]"
            elif isinstance(value, (dict, list)):
                redacted[key] = _redact_sensitive(value)
            else:
                redacted[key] = value
        return redacted
    elif isinstance(data, list):
        return [_redact_sensitive(item) for item in data]
    else:
        return data


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.
    
    Formats log records as JSON with consistent fields:
    - timestamp (ISO 8601 UTC)
    - level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - service_name (from context)
    - logger_name (module name)
    - message (log message)
    - correlation_id (from context)
    - request_id (from context)
    - operation_name (from context)
    - exception (if applicable)
    - stack_trace (if exception)
    """
    
    def __init__(self, service_name: str = "unknown"):
        """Initialize formatter.
        
        Args:
            service_name: Default service name (can be overridden by context)
        """
        super().__init__()
        self.service_name = service_name
    
    def format(self, record: logging.LogRecord) -> bool:
        """Format log record as JSON.
        
        Args:
            record: LogRecord to format
        
        Returns:
            JSON string
        """
        # Extract context if available
        context = getattr(record, "extra_context", {})
        
        # Build log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "service_name": context.get("service_name", self.service_name),
            "logger_name": record.name,
            "message": record.getMessage(),
            "correlation_id": context.get("correlation_id"),
            "request_id": context.get("request_id"),
            "operation_name": context.get("operation_name"),
        }
        
        # Add source info
        if hasattr(record, "pathname"):
            log_entry["source_file"] = record.pathname
        if hasattr(record, "lineno"):
            log_entry["source_line"] = record.lineno
        if hasattr(record, "funcName"):
            log_entry["source_function"] = record.funcName
        
        # Add exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            log_entry["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "module": exc_type.__module__ if exc_type else None,
            }
            
            # Add stack trace if available
            if exc_tb:
                log_entry["stack_trace"] = traceback.format_exception(exc_type, exc_value, exc_tb)
        
        # Redact sensitive data from extra fields
        extra_context_redacted = _redact_sensitive(context)
        log_entry.update(extra_context_redacted)
        
        # Ensure all values are JSON-serializable
        log_entry_serializable = {}
        for key, value in log_entry.items():
            log_entry_serializable[key] = _serialize_value(value)
        
        try:
            return json.dumps(log_entry_serializable, default=str)
        except Exception as e:
            # Fallback if JSON serialization fails
            return json.dumps({
                "error": "Failed to serialize log entry",
                "original_message": record.getMessage(),
                "serialization_error": str(e),
            })

