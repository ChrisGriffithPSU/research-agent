"""arXiv Fetcher Plugin.

A comprehensive arXiv paper discovery and extraction system.

Components:
- ArxivAPIClient: arXiv API integration with rate limiting
- ArxivMessagePublisher: Message publishing to RabbitMQ
- PDFProcessor: PDF content extraction using docling
"""

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import (
    PaperMetadata,
    ParsedContent,
)
from src.services.fetchers.arxiv.services import ArxivAPIClient

try:
    # Optional heavy dependency (docling) lives behind the `arxiv` extra.
    from src.services.fetchers.arxiv.services import PDFProcessor
except ImportError:  # pragma: no cover
    PDFProcessor = None  # type: ignore[assignment]

__all__ = [
    "ArxivFetcherConfig",
    "PaperMetadata",
    "ParsedContent",
    "ArxivAPIClient",
]

if PDFProcessor is not None:
    __all__.append("PDFProcessor")
