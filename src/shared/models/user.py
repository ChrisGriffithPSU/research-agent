"""User profile models."""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.models.base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    """User profile and preferences.

    Stores user preferences for digest generation and learning.
    Since this is a single-user app, there will typically be only one record.
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Preferences stored as JSON
    # Example: {"topics": ["transformers", "time_series"], "sources": ["arxiv", "kaggle"], ...}
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Learning preferences
    # Example: {"feedback_weight": 0.7, "exploration_rate": 0.2, ...}
    learning_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, email={self.email})>"
