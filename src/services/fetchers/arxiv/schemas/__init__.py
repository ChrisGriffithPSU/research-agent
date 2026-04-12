"""Schemas for arXiv fetcher plugin.

Exports:
- PaperMetadata: Paper metadata from arXiv
- ParsedContent: Extracted PDF content
"""

from src.services.fetchers.arxiv.schemas.paper import (
    PaperMetadata,
    ParsedContent,
)

__all__ = [
    "PaperMetadata",
    "ParsedContent",
]
