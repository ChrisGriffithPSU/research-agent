"""Source content models."""
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Enum as SQLEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.models.base import Base, TimestampMixin

import enum


class SourceType(str, enum.Enum):
    """Type of content source."""

    ARXIV = "arxiv"
    KAGGLE = "kaggle"
    HUGGINGFACE = "huggingface"
    WEB_SEARCH = "web_search"


class ProcessingStatus(str, enum.Enum):
    """Processing status of source content."""

    FETCHED = "fetched"  # Just fetched, not processed
    PROCESSING = "processing"  # Being processed by LLM pipeline
    PROCESSED = "processed"  # Fully processed
    FAILED = "failed"  # Processing failed
    DEDUPLICATED = "deduplicated"  # Identified as duplicate


class Source(Base, TimestampMixin):
    """Raw content fetched from various sources.

    Stores content before and after LLM processing.
    Includes vector embeddings for similarity search and deduplication.
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Source metadata
    source_type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType, native_enum=False), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Extracted/processed data (from LLM pipeline)
    # Example: {"techniques": [...], "applicability_score": 0.8, "category": "feature_engineering"}
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Additional metadata (source-specific fields)
    # Example: {"authors": [...], "published_date": "2024-01-01", "citations": 42}
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(1536), nullable=True, index=True
    )

    # Processing status
    status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, native_enum=False),
        nullable=False,
        default=ProcessingStatus.FETCHED,
        index=True,
    )

    # Timestamps
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, type={self.source_type}, title={self.title[:50]})>"
