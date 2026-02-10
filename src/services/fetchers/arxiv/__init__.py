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
from src.services.fetchers.arxiv.services import (
    ArxivAPIClient,
    PDFProcessor,
)

__all__ = [
    "ArxivFetcherConfig",
    "PaperMetadata",
    "ParsedContent",
    "ArxivAPIClient",
    "PDFProcessor",
]
