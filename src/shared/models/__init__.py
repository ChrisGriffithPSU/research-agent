"""SQLAlchemy models for Researcher Agent.

Import all models here to ensure they're registered with Base.metadata.
This is required for Alembic migrations to detect all tables.
"""

from src.shared.models.base import Base, TimestampMixin
from src.shared.models.digest import Digest, DigestItem, DigestStatus
from src.shared.models.feedback import Feedback
from src.shared.models.source import ProcessingStatus, Source, SourceType
from src.shared.models.system import (
    FetcherStatus,
    FetcherState,
    ModelMetadata,
    PreferenceWeight,
    SearchQuery,
    SystemState,
)
from src.shared.models.user import UserProfile

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    # User models
    "UserProfile",
    # Source models
    "Source",
    "SourceType",
    "ProcessingStatus",
    # Digest models
    "Digest",
    "DigestItem",
    "DigestStatus",
    # Feedback models
    "Feedback",
    # System models
    "SystemState",
    "FetcherState",
    "FetcherStatus",
    "SearchQuery",
    "ModelMetadata",
    "PreferenceWeight",
]
