"""Database-related exceptions."""
from typing import Optional

from src.shared.exceptions.base import ResearchAgentError


class DatabaseError(ResearchAgentError):
    """Base exception for database errors.

    All database-related exceptions inherit from this class.
    Provides structured error information with error codes and details.

    Args:
        message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "DB_ERROR",
            details=details,
            original=original,
        )


class RepositoryNotFoundError(DatabaseError):
    """Exception raised when repository operation fails to find object.

    Example: Trying to update user with id=999 that doesn't exist.

    Args:
        message: Human-readable error message
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str = "Repository object not found",
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            error_code="REPOSITORY_NOT_FOUND",
            details=details,
            original=original,
        )


class RepositoryConflictError(DatabaseError):
    """Exception raised when repository operation violates constraints.

    Examples:
    - Inserting duplicate email
    - Inserting duplicate URL
    - Updating with invalid foreign key

    Args:
        message: Human-readable error message
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str = "Repository conflict error",
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            error_code="REPOSITORY_CONFLICT",
            details=details,
            original=original,
        )


class DuplicateDetectionError(DatabaseError):
    """Exception raised during duplicate detection in deduplication service.

    Args:
        message: Human-readable error message
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str = "Duplicate detected",
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            error_code="DUPLICATE_DETECTION",
            details=details,
            original=original,
        )


class ConnectionPoolExhaustedError(DatabaseError):
    """Exception raised when connection pool is exhausted.

    All connections in use and timeout exceeded.

    Args:
        message: Human-readable error message
        details: Additional context as dictionary
        original: Original exception if wrapping another exception
    """

    def __init__(
        self,
        message: str = "Connection pool exhausted",
        details: Optional[dict] = None,
        original: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            error_code="CONNECTION_POOL_EXHAUSTED",
            details=details,
            original=original,
        )

