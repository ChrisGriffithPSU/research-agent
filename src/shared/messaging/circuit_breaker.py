"""Circuit breaker pattern to prevent cascading failures.

This module re-exports the consolidated circuit breaker implementation
from src.shared.utils.circuit_breaker for backwards compatibility.

For new code, import directly from src.shared.utils.circuit_breaker.
"""
import logging

from src.shared.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker,
)

logger = logging.getLogger(__name__)

logger.warning(
    "src.shared.messaging.circuit_breaker is deprecated. "
    "Use src.shared.utils.circuit_breaker instead."
)

__all__ = ["CircuitBreaker", "CircuitState", "circuit_breaker"]
