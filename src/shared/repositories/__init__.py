"""Repository layer for database operations.

Import all repositories here for easy access.
"""

from src.shared.repositories.base import (
    BaseRepository,
    DatabaseError,
)
from src.shared.repositories.paper_repository import PaperRepository

__all__ = [
    # Base classes
    "BaseRepository",
    "DatabaseError",
    # Paper repositories
    "PaperRepository",
]
