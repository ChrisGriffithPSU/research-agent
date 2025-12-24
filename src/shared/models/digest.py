"""Digest models for daily curated content."""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ARRAY, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.models.base import Base, TimestampMixin

import enum

if TYPE_CHECKING:
    from src.shared.models.feedback import Feedback


class DigestStatus(str, enum.Enum):
    """Status of digest generation."""

    PENDING = "pending"  # Scheduled but not started
    GENERATING = "generating"  # Currently being generated
    READY = "ready"  # Generated and ready to send
    DELIVERED = "delivered"  # Sent to user
    FAILED = "failed"  # Generation failed


class Digest(Base, TimestampMixin):
    """Daily digest of curated ML techniques.

    Each digest contains 10-15 actionable items ranked by relevance.
    """

    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)

    # User reference (for future multi-user support)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Digest date (unique per user per day)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Status
    status: Mapped[DigestStatus] = mapped_column(
        SQLEnum(DigestStatus, native_enum=False),
        nullable=False,
        default=DigestStatus.PENDING,
        index=True,
    )

    # Delivery timestamp
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    items: Mapped[list["DigestItem"]] = relationship(
        "DigestItem",
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="DigestItem.rank",
    )

    def __repr__(self) -> str:
        return f"<Digest(id={self.id}, date={self.digest_date}, status={self.status})>"


class DigestItem(Base, TimestampMixin):
    """Individual item in a digest.

    Represents a single ML technique or insight from a source.
    """

    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Parent digest
    digest_id: Mapped[int] = mapped_column(
        ForeignKey("digests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source reference
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ranking within digest (1 = highest priority)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # Content
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM reasoning for inclusion
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    # Tags/categories (e.g., ["feature_engineering", "transformers"])
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )

    # Relevance score (from learning model)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    digest: Mapped[Digest] = relationship("Digest", back_populates="items")
    feedback: Mapped[Optional["Feedback"]] = relationship(
        "Feedback",
        back_populates="digest_item",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<DigestItem(id={self.id}, rank={self.rank}, title={self.title[:50]})>"
