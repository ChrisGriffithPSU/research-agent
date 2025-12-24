"""Database-related exceptions."""
from typing import Optional


class DatabaseError(Exception):
    """Base exception for database errors."""

    def __init__(self, message: str, original: Optional[Exception] = None):
        self.message = message
        self.original = original
        super().__init__(message)


class RepositoryNotFoundError(DatabaseError):
    """Exception raised when repository operation fails to find object.

    Example: Trying to update user with id=999 that doesn't exist.
    """

    pass


class RepositoryConflictError(DatabaseError):
    """Exception raised when repository operation violates constraints.

    Examples:
    - Inserting duplicate email
    - Inserting duplicate URL
    - Updating with invalid foreign key
    """

    pass


class DuplicateDetectionError(DatabaseError):
    """Exception raised during duplicate detection in deduplication service."""

    pass


class ConnectionPoolExhaustedError(DatabaseError):
    """Exception raised when connection pool is exhausted.

    All connections in use and timeout exceeded.
    """

    pass

