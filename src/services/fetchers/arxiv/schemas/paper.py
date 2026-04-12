"""Paper data classes for arXiv fetcher.

Defines data structures for paper metadata and parsed content.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaperSource(str, Enum):
    """Source of paper discovery."""

    QUERY = "query"
    CATEGORY = "category"


class PaperMetadata(BaseModel):
    """Immutable paper metadata from arXiv.

    Attributes:
        paper_id: arXiv ID (e.g., '2401.12345')
        version: Version string (e.g., 'v1', 'v2')
        title: Paper title
        abstract: Paper abstract
        authors: List of author names
        categories: Primary categories
        subcategories: All subcategories paper appears in
        submitted_date: Original submission date
        updated_date: Last update date
        doi: DOI if available
        journal_ref: Journal reference
        comments: Author comments
        pdf_url: Direct URL to PDF
        arxiv_url: URL to arXiv abstract page
        source: How the paper was discovered (query or category)
        source_query: Query that found this paper (if applicable)
        relevance_score: Optional relevance score from intelligence layer
    """

    model_config = ConfigDict()

    paper_id: str = Field(..., description="arXiv ID (e.g., '2401.12345')")
    version: str = Field(default="v1", description="Version (v1, v2, etc.)")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(default="", description="Paper abstract")
    authors: list[str] = Field(default_factory=list, description="Author names")
    categories: list[str] = Field(
        default_factory=list,
        description="Primary categories (e.g., ['cs.LG', 'stat.ML'])",
    )
    subcategories: list[str] = Field(
        default_factory=list,
        description="All subcategories paper appears in",
    )
    submitted_date: str = Field(default="", description="Original submission date")
    updated_date: str | None = Field(None, description="Last update date")
    doi: str | None = Field(None, description="DOI if available")
    journal_ref: str | None = Field(None, description="Journal reference")
    comments: str | None = Field(None, description="Author comments")
    pdf_url: str = Field(default="", description="Direct URL to PDF")
    arxiv_url: str = Field(default="", description="URL to arXiv abstract page")
    source: PaperSource = Field(
        default=PaperSource.QUERY,
        description="How the paper was discovered",
    )
    source_query: str = Field(default="", description="Query that found this paper")
    relevance_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score",
    )

    def __hash__(self):
        """Make hashable for deduplication."""
        return hash(self.paper_id)

    def __eq__(self, other):
        """Equality based on paper ID."""
        if isinstance(other, PaperMetadata):
            return self.paper_id == other.paper_id
        return False


class ParsedContent(BaseModel):
    """Extracted content from PDF.

    Attributes:
        paper_id: arXiv ID this content belongs to
        text_content: Full text extracted from PDF
        tables: List of extracted tables with captions and data
        equations: LaTeX equations found in the PDF
        figure_captions: Figure captions and their IDs
        metadata: Additional extraction metadata
    """

    model_config = ConfigDict()

    paper_id: str = Field(..., description="arXiv ID this content belongs to")
    text_content: str = Field(default="", description="Full text extracted from PDF")
    tables: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables with captions and data",
    )
    equations: list[str] = Field(
        default_factory=list,
        description="LaTeX equations found in the PDF",
    )
    figure_captions: list[dict[str, str]] = Field(
        default_factory=list,
        description="Figure captions and their IDs",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extraction metadata",
    )
