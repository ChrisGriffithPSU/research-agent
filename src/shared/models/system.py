"""System state and metadata models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.models.base import Base, TimestampMixin
import enum


class FetcherStatus(str, enum.Enum):
    """Status of fetcher service."""

    ACTIVE = "active"  # Fetcher is running and healthy
    PAUSED = "paused"  # Fetcher paused by user
    ERROR = "error"  # Fetcher encountered error


class SystemState(Base, TimestampMixin):
    """Key-value store for system-wide configuration.

    Stores configuration that doesn't belong in environment variables.
    Examples: feature flags, last run timestamps, counters.
    """

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    # JSON value (flexible structure)
    # Example: {"enabled": true, "last_run": "2024-01-01T00:00:00Z"}
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<SystemState(key={self.key})>"


class FetcherState(Base, TimestampMixin):
    """Track fetcher service health and status.

    Monitors each fetcher (arxiv, kaggle, huggingface, web_search)
    for failures, last fetch time, and configuration.
    """

    __tablename__ = "fetcher_state"

    # Fetcher name (primary key)
    # Examples: "arxiv", "kaggle", "huggingface", "web_search"
    fetcher_name: Mapped[str] = mapped_column(String(50), primary_key=True, nullable=False)

    # Last successful fetch timestamp
    last_fetch_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Current status
    status: Mapped[FetcherStatus] = mapped_column(
        String(20), nullable=False, default=FetcherStatus.ACTIVE
    )

    # Consecutive error count (for circuit breaker)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Fetcher-specific configuration (JSON)
    # Example: {"enabled": true, "queries_per_day": 5, "categories": [...]}
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<FetcherState(name={self.fetcher_name}, status={self.status})>"


class SearchQuery(Base, TimestampMixin):
    """History of LLM-generated search queries.

    Tracks queries to prevent duplicates and analyze query effectiveness.
    """

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Source that generated the query
    # Examples: "arxiv", "kaggle", "huggingface", "web_search"
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Query text
    # Example: "attention mechanisms for time series forecasting"
    query_text: Mapped[str] = mapped_column(Text, nullable=False)

    # When query was executed
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Number of results returned
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<SearchQuery(id={self.id}, source={self.source}, text={self.query_text[:50]})>"


class ModelMetadata(Base, TimestampMixin):
    """Learning model versioning and training history.

    Tracks recommendation model versions, training data, and performance.
    """

    __tablename__ = "model_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Model version identifier
    # Example: "v1.0", "v2.1", "v3.0-beta"
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # When model was trained
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Number of training samples used
    training_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Performance metrics (JSON)
    # Example: {"accuracy": 0.85, "precision": 0.82, "recall": 0.88}
    performance_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Path to model file (if persisted to disk)
    # Example: "/app/models/recommendation_v1.0.pkl"
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<ModelMetadata(id={self.id}, version={self.version})>"


class PreferenceWeight(Base, TimestampMixin):
    """Store learned preference scores per dimension.

    Learning system updates these weights based on user feedback.
    Used to score/rank content during synthesis.
    """

    __tablename__ = "preference_weights"

    # Dimension identifier (primary key)
    # Examples: "category:feature_engineering", "source:arxiv", "topic:attention"
    dimension: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False)

    # Weight score (higher = more preference)
    # Range: -1.0 (avoid) to 1.0 (strong preference)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    def __repr__(self) -> str:
        return f"<PreferenceWeight(dimension={self.dimension}, weight={self.weight})>"

