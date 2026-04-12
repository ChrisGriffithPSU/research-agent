"""Custom exceptions for the application."""

from src.shared.exceptions.base import (
    CircuitOpenError,
    ResearchAgentError,
)
from src.shared.exceptions.database import (
    DatabaseError,
    RepositoryConflictError,
    RepositoryNotFoundError,
)
from src.shared.exceptions.llm import (
    LLMError,
    LLMProviderError,
)

__all__ = [
    # Base exceptions
    "ResearchAgentError",
    "CircuitOpenError",
    # Database exceptions
    "DatabaseError",
    "RepositoryNotFoundError",
    "RepositoryConflictError",
    # LLM exceptions
    "LLMError",
    "LLMProviderError",
]
