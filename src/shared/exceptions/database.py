"""Database-related exceptions."""

from typing import Optional

from src.shared.exceptions.base import ResearchAgentError


class DatabaseError(ResearchAgentError):
    """Base exception for database errors."""

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
    """Exception raised when repository operation fails to find object."""

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
    """Exception raised when repository operation violates constraints."""

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
