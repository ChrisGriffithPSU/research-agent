"""Schemas for arXiv fetcher plugin.

Exports:
- PaperMetadata: Paper metadata from arXiv
- ParsedContent: Extracted PDF content
- QueryExpansion: Query expansion result
- ArxivDiscoveredMessage: Message for discovered papers
- ArxivParseRequestMessage: Parse request message
- ArxivExtractedMessage: Message with extracted content
"""
from src.services.fetchers.arxiv.schemas.paper import (
    PaperMetadata,
    ParsedContent,
    QueryExpansion,
    TableData,
    FigureData,
)
from src.services.fetchers.arxiv.schemas.messages import (
    ArxivDiscoveredMessage,
    ArxivParseRequestMessage,
    ArxivExtractedMessage,
    ArxivDiscoveryBatch,
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

