"""SQLAlchemy models for Quant Research Agent.

Import all models here to ensure they're registered with Base.metadata.
This is required for Alembic migrations to detect all tables.
"""

from src.shared.models.base import Base, TimestampMixin
from src.shared.repositories.paper_repository import PaperModel

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    # Paper tracking
    "PaperModel",
]
