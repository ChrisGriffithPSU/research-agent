"""Services for arXiv fetcher plugin."""

from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient

try:
    # Optional heavy dependency (docling) lives behind the `arxiv` extra.
    from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor
except ImportError:  # pragma: no cover
    PDFProcessor = None  # type: ignore[assignment]

__all__ = [
    "ArxivAPIClient",
]

if PDFProcessor is not None:
    __all__.append("PDFProcessor")
