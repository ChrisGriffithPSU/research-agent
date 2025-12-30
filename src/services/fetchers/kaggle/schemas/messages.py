"""Message schemas for Kaggle fetcher.

Defines message types for discovered notebooks:
- kaggle.discovered: Notebooks with full parsed content
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from uuid import uuid4

from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookSource,
    ParsedNotebook,
)


class KaggleDiscoveredMessage(BaseModel):
    """Message for discovered notebooks (Phase 1: Discovery).

    Published to: kaggle.discovered queue
    Consumed by: Intelligence Layer (for filtering)

    Contains full parsed notebook content.

    Attributes:
        correlation_id: Unique ID to trace message through pipeline
        created_at: Timestamp when discovered
        notebook_id: Kaggle notebook ID (e.g., 'username/notebook-slug')
        notebook_path: kagglehub path for downloading
        title: Notebook title
        authors: Author names
        competition_slug: Competition slug if from competition
        tags: Tags associated with the notebook
        votes: Number of votes/thumbs up
        total_views: Number of views
        notebook_content: Full parsed notebook content
        source: How the notebook was discovered (competition, tag, query)
        source_query: Original query that found this notebook
    """

    # Correlation for tracing through pipeline
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID to trace message through pipeline"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Timestamp when discovered"
    )

    # Core identifiers
    notebook_id: str = Field(
        ...,
        description="Kaggle notebook ID (e.g., 'username/notebook-slug')"
    )
    notebook_path: str = Field(
        ...,
        description="kagglehub path for downloading"
    )

    # Metadata
    title: str = Field(..., description="Notebook title")
    authors: List[str] = Field(
        default_factory=list,
        description="Author names"
    )
    competition_slug: Optional[str] = Field(
        None,
        description="Competition slug if from competition"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags associated with the notebook"
    )
    votes: int = Field(
        default=0,
        ge=0,
        description="Number of votes/thumbs up"
    )
    total_views: int = Field(
        default=0,
        ge=0,
        description="Number of views"
    )

    # Full parsed content
    notebook_content: ParsedNotebook = Field(
        ...,
        description="Full parsed notebook content"
    )

    # Discovery context
    source: NotebookSource = Field(
        default=NotebookSource.QUERY,
        description="How the notebook was discovered"
    )
    source_query: str = Field(
        default="",
        description="Original query that found this notebook"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class KaggleDiscoveryBatch(BaseModel):
    """Batch of discovered notebooks for efficient processing.

    Attributes:
        correlation_id: Batch correlation ID
        notebooks: List of discovered notebooks
        query: The query that generated these notebooks
        total_found: Total notebooks found before filtering
        batch_number: Batch number for large result sets
        total_batches: Total batches for this query
    """

    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Batch correlation ID"
    )
    notebooks: List[KaggleDiscoveredMessage] = Field(
        default_factory=list,
        description="List of discovered notebooks"
    )
    query: str = Field(default="", description="The query that generated these")
    total_found: int = Field(default=0, description="Total notebooks found")
    batch_number: int = Field(default=1, description="Batch number")
    total_batches: int = Field(default=1, description="Total batches")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


__all__ = [
    "KaggleDiscoveredMessage",
    "KaggleDiscoveryBatch",
]

