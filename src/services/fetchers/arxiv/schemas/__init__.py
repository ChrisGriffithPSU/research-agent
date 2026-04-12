"""Schemas for arXiv fetcher plugin.

Exports:
- PaperMetadata: Paper metadata from arXiv
- ParsedContent: Extracted PDF content
- QueryExpansion: Query expansion result
- ArxivDiscoveredMessage: Message for discovered papers
- ArxivParseRequestMessage: Parse request message
- ArxivExtractedMessage: Message with extracted content
"""
from src.services.fetchers.arxiv.schemas.messages import (
    ArxivDiscoveredMessage,
    ArxivDiscoveryBatch,
    ArxivExtractedMessage,
    ArxivParseRequestMessage,
)
from src.services.fetchers.arxiv.schemas.paper import (
    FigureData,
    PaperMetadata,
    ParsedContent,
    QueryExpansion,
    TableData,
)

__all__ = [
    "PaperMetadata",
    "ParsedContent",
    "QueryExpansion",
    "TableData",
    "FigureData",
    "ArxivDiscoveredMessage",
    "ArxivParseRequestMessage",
    "ArxivExtractedMessage",
    "ArxivDiscoveryBatch",
]

