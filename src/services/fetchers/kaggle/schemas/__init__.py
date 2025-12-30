"""Schemas for Kaggle fetcher.

Exports all data classes and message schemas.
"""

from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookSource,
    CellType,
    NotebookMetadata,
    Output,
    CodeCell,
    MarkdownCell,
    CodeAnalysis,
    NotebookContent,
    ParsedNotebook,
    CompetitionMetadata,
)

from src.services.fetchers.kaggle.schemas.messages import (
    KaggleDiscoveredMessage,
    KaggleDiscoveryBatch,
)

__all__ = [
    # Notebook schemas
    "NotebookSource",
    "CellType",
    "NotebookMetadata",
    "Output",
    "CodeCell",
    "MarkdownCell",
    "CodeAnalysis",
    "NotebookContent",
    "ParsedNotebook",
    "CompetitionMetadata",
    # Message schemas
    "KaggleDiscoveredMessage",
    "KaggleDiscoveryBatch",
]

