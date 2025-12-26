"""Paper data classes for arXiv fetcher.

Defines data structures for paper metadata and parsed content.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


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
    paper_id: str = Field(..., description="arXiv ID (e.g., '2401.12345')")
    version: str = Field(default="v1", description="Version (v1, v2, etc.)")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(default="", description="Paper abstract")
    authors: List[str] = Field(default_factory=list, description="Author names")
    categories: List[str] = Field(
        default_factory=list,
        description="Primary categories (e.g., ['cs.LG', 'stat.ML'])"
    )
    subcategories: List[str] = Field(
        default_factory=list,
        description="All subcategories paper appears in"
    )
    submitted_date: str = Field(default="", description="Original submission date")
    updated_date: Optional[str] = Field(None, description="Last update date")
    doi: Optional[str] = Field(None, description="DOI if available")
    journal_ref: Optional[str] = Field(None, description="Journal reference")
    comments: Optional[str] = Field(None, description="Author comments")
    pdf_url: str = Field(default="", description="Direct URL to PDF")
    arxiv_url: str = Field(default="", description="URL to arXiv abstract page")
    source: PaperSource = Field(
        default=PaperSource.QUERY,
        description="How the paper was discovered"
    )
    source_query: str = Field(default="", description="Query that found this paper")
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score"
    )
    
    def __hash__(self):
        """Make hashable for deduplication."""
        return hash(self.paper_id)
    
    def __eq__(self, other):
        """Equality based on paper ID."""
        if isinstance(other, PaperMetadata):
            return self.paper_id == other.paper_id
        return False
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


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
    paper_id: str = Field(..., description="arXiv ID this content belongs to")
    text_content: str = Field(default="", description="Full text extracted from PDF")
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables with captions and data"
    )
    equations: List[str] = Field(
        default_factory=list,
        description="LaTeX equations found in the PDF"
    )
    figure_captions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Figure captions and their IDs"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extraction metadata"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class QueryExpansion(BaseModel):
    """Result of query expansion.
    
    Attributes:
        original_query: The original query
        expanded_queries: List of expanded query strings
        generated_at: When the expansion was generated
        cache_hit: Whether this was a cache hit
    """
    original_query: str = Field(..., description="The original query")
    expanded_queries: List[str] = Field(
        default_factory=list,
        description="List of expanded query strings"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the expansion was generated"
    )
    cache_hit: bool = Field(
        default=False,
        description="Whether this was a cache hit"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TableData(BaseModel):
    """Structured table data extracted from PDF.
    
    Attributes:
        caption: Table caption if available
        headers: Column headers
        rows: List of rows (each row is a list of cell values)
        row_count: Number of data rows
        col_count: Number of columns
        page_number: Page number where table appears
    """
    caption: Optional[str] = Field(None, description="Table caption")
    headers: List[str] = Field(default_factory=list, description="Column headers")
    rows: List[List[str]] = Field(default_factory=list, description="Table rows")
    row_count: int = Field(default=0, description="Number of data rows")
    col_count: int = Field(default=0, description="Number of columns")
    page_number: int = Field(default=0, description="Page number")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching."""
        return {
            "caption": self.caption,
            "headers": self.headers,
            "rows": self.rows,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "page_number": self.page_number,
        }


class FigureData(BaseModel):
    """Figure data extracted from PDF.
    
    Attributes:
        figure_id: Unique figure identifier
        caption: Figure caption
        page_number: Page number where figure appears
        alt_text: Alternative text if available
    """
    figure_id: str = Field(default="", description="Unique figure identifier")
    caption: str = Field(default="", description="Figure caption")
    page_number: int = Field(default=0, description="Page number")
    alt_text: Optional[str] = Field(None, description="Alternative text")
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for storage."""
        return {
            "figure_id": self.figure_id,
            "caption": self.caption,
            "page_number": str(self.page_number),
            "alt_text": self.alt_text,
        }

