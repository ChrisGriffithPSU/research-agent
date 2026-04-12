"""Database-related exceptions."""


from src.shared.exceptions.base import ResearchAgentError


class DatabaseError(ResearchAgentError):
    """Base exception for database errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict | None = None,
        original: Exception | None = None,
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
        details: dict | None = None,
        original: Exception | None = None,
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
        details: dict | None = None,
        original: Exception | None = None,
    ):
        super().__init__(
            message=message,
            error_code="REPOSITORY_CONFLICT",
            details=details,
            original=original,
        )
