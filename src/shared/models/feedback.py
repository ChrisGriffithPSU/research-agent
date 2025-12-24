"""Feedback models for learning system."""
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.models.base import Base, TimestampMixin


class Feedback(Base, TimestampMixin):
    """User feedback on digest items.

    Used by the learning system to improve recommendations.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Reference to digest item
    digest_item_id: Mapped[int] = mapped_column(
        ForeignKey("digest_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One feedback per digest item
        index=True,
    )

    # Rating (1-5 scale, or -1 for "not useful")
    # 5 = extremely useful, immediately actionable
    # 4 = very useful, will try soon
    # 3 = interesting, might use later
    # 2 = somewhat relevant but not applicable
    # 1 = not relevant to my use case
    # -1 = not interested, don't show similar content
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional notes from user
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Implicit signals (computed)
    # Time spent reading (seconds)
    time_spent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Whether user clicked through to source
    clicked_through: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    digest_item: Mapped["DigestItem"] = relationship(
        "DigestItem", back_populates="feedback"
    )

    def __repr__(self) -> str:
        return f"<Feedback(id={self.id}, digest_item_id={self.digest_item_id}, rating={self.rating})>"
