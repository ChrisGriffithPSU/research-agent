"""Circuit breaker pattern to prevent cascading failures.

This module re-exports the consolidated circuit breaker implementation
from src.shared.utils.circuit_breaker for backwards compatibility.

For new code, import directly from src.shared.utils.circuit_breaker.
"""

import warnings

from src.shared.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker,
)

warnings.warn(
    "src.shared.messaging.circuit_breaker is deprecated. "
    "Use src.shared.utils.circuit_breaker instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CircuitBreaker", "CircuitState", "circuit_breaker"]
