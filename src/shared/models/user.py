"""User profile models."""
import re
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, validates

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

    @validates("email")
    def validate_email(self, key: str, email: str) -> str:
        """Validate email format.

        Args:
            key: Field name
            email: Email to validate

        Returns:
            Validated email (lowercased and trimmed)

        Raises:
            ValueError: If email format is invalid
        """
        if not email or len(email) < 3:
            raise ValueError("Email must be at least 3 characters")

        if len(email) > 255:
            raise ValueError("Email must be 255 characters or less")

        # Basic email regex pattern
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            raise ValueError(f"Invalid email format: {email}")

        return email.lower().strip()

    @validates("preferences")
    def validate_preferences(self, key: str, preferences: dict) -> dict:
        """Validate preferences structure.

        Args:
            key: Field name
            preferences: Preferences dict

        Returns:
            Validated preferences

        Raises:
            ValueError: If preferences are invalid
        """
        if not isinstance(preferences, dict):
            raise ValueError("Preferences must be a dictionary")

        # Ensure it's JSON-serializable
        import json
        try:
            json.dumps(preferences)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Preferences must be JSON-serializable: {e}")

        return preferences

    @validates("learning_config")
    def validate_learning_config(self, key: str, config: dict) -> dict:
        """Validate learning configuration.

        Args:
            key: Field name
            config: Learning config dict

        Returns:
            Validated config

        Raises:
            ValueError: If config is invalid
        """
        if not isinstance(config, dict):
            raise ValueError("Learning config must be a dictionary")

        # Ensure it's JSON-serializable
        import json
        try:
            json.dumps(config)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Learning config must be JSON-serializable: {e}")

        return config

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, email={self.email})>"
