"""Repository layer for database operations.

Import all repositories here for easy access.
"""

from src.shared.repositories.base import (
    BaseRepository,
    DatabaseError,
    VectorSearchMixin,
)
from src.shared.repositories.digest_repository import (
    DigestItemRepository,
    DigestRepository,
)
from src.shared.repositories.feedback_repository import FeedbackRepository
from src.shared.repositories.source_repository import SourceRepository
from src.shared.repositories.system_repository import (
    FetcherStateRepository,
    ModelMetadataRepository,
    PreferenceWeightRepository,
    SearchQueryRepository,
    SystemStateRepository,
)
from src.shared.repositories.user_repository import UserRepository

__all__ = [
    # Base classes
    "BaseRepository",
    "VectorSearchMixin",
    "DatabaseError",
    # User repositories
    "UserRepository",
    # Source repositories
    "SourceRepository",
    # Digest repositories
    "DigestRepository",
    "DigestItemRepository",
    # Feedback repositories
    "FeedbackRepository",
    # System repositories
    "SystemStateRepository",
    "FetcherStateRepository",
    "SearchQueryRepository",
    "ModelMetadataRepository",
    "PreferenceWeightRepository",
]

