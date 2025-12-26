"""Message schemas for arXiv fetcher.

Defines message types for two-phase architecture:
- arxiv.discovered: Papers with metadata only (Phase 1)
- arxiv.parse_request: Request to parse specific paper (Phase 2)
- content.extracted: Fully extracted paper content (Phase 3)
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from uuid import uuid4


class ArxivDiscoveredMessage(BaseModel):
    """Message for discovered papers (Phase 1: Discovery).
    
    Published to: arxiv.discovered queue
    Consumed by: Intelligence Layer (for filtering)
    
    Contains metadata only - NO PDF content.
    Intelligence layer decides which papers to parse.
    
    Attributes:
        correlation_id: Unique ID to trace message through pipeline
        created_at: Timestamp when discovered
        paper_id: arXiv ID (e.g., '2401.12345')
        version: Version (v1, v2, etc.)
        title: Paper title
        abstract: Paper abstract (for LLM evaluation)
        authors: Author names
        categories: Primary categories
        subcategories: All subcategories paper appears in
        arxiv_url: URL to arXiv abstract page
        pdf_url: URL to PDF
        submitted_date: Original submission date
        updated_date: Last update date
        doi: DOI if available
        journal_ref: Journal reference
        comments: Author comments
        source_query: Original query that found this paper
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
    paper_id: str = Field(..., description="arXiv ID (e.g., '2401.12345')")
    version: str = Field(default="v1", description="Version (v1, v2, etc.)")
    
    # Metadata for LLM evaluation
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract (for LLM evaluation)")
    authors: List[str] = Field(default_factory=list, description="Author names")
    
    # Categorization
    categories: List[str] = Field(
        default_factory=list,
        description="Primary categories (e.g., ['cs.LG', 'stat.ML'])"
    )
    subcategories: List[str] = Field(
        default_factory=list,
        description="All subcategories paper appears in"
    )
    
    # Access
    arxiv_url: str = Field(
        ...,
        description="URL to arXiv abstract page"
    )
    pdf_url: str = Field(
        ...,
        description="URL to PDF (https://arxiv.org/pdf/{id}.pdf)"
    )
    
    # Additional metadata
    submitted_date: str = Field(default="", description="Original submission date")
    updated_date: Optional[str] = Field(None, description="Last update date")
    doi: Optional[str] = Field(None, description="DOI if available")
    journal_ref: Optional[str] = Field(None, description="Journal reference")
    comments: Optional[str] = Field(None, description="Author comments")
    
    # For tracking
    source_query: str = Field(
        default="",
        description="Original query that found this paper"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ArxivParseRequestMessage(BaseModel):
    """Request to parse a specific paper (Phase 2: On-demand).
    
    Published by: Intelligence Layer (when paper is "interesting")
    Consumed by: PDF Parser Service
    
    Contains just enough info to identify and parse the paper.
    
    Attributes:
        correlation_id: Correlation ID for this request
        original_correlation_id: Original discovery correlation ID
        created_at: When the request was created
        paper_id: arXiv ID to parse
        pdf_url: URL to PDF for parsing
        priority: Parse priority (1=highest, 10=lowest)
        relevance_score: LLM-assigned relevance score
        intelligence_notes: Optional notes from intelligence layer
    """
    
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for this request"
    )
    original_correlation_id: str = Field(
        ...,
        description="Correlation ID from original ArxivDiscoveredMessage"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    
    # Identification
    paper_id: str = Field(..., description="arXiv ID")
    pdf_url: str = Field(..., description="URL to PDF for parsing")
    
    # Priority (optional, for scheduling)
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Parse priority (1=highest, 10=lowest)"
    )
    
    # Context from intelligence layer
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score"
    )
    intelligence_notes: Optional[str] = Field(
        None,
        description="Optional notes from intelligence layer"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ArxivExtractedMessage(BaseModel):
    """Message with fully extracted paper content (Phase 3).
    
    Published by: PDF Parser Service
    Consumed by: Synthesis, Digest Generation, etc.
    
    Contains full PDF content extracted by docling.
    
    Attributes:
        correlation_id: Correlation ID for this message
        discovery_correlation_id: Original discovery correlation
        parse_correlation_id: Parse request correlation
        created_at: When extraction was completed
        paper_id: arXiv ID
        version: Paper version
        title: Paper title
        arxiv_url: URL to arXiv abstract
        pdf_url: URL to PDF
        authors: Author names
        categories: Primary categories
        subcategories: All subcategories
        submitted_date: Original submission date
        doi: DOI if available
        text_content: Full text extracted from PDF
        tables: Extracted tables with captions and data
        equations: LaTeX equations extracted from PDF
        figure_captions: Figure captions and IDs
        extraction_metadata: docling version, processing time, etc.
    """
    
    # Correlation chain
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for this message"
    )
    discovery_correlation_id: str = Field(
        ...,
        description="Original discovery correlation ID"
    )
    parse_correlation_id: str = Field(
        ...,
        description="Parse request correlation ID"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    
    # Paper identification
    paper_id: str = Field(..., description="arXiv ID")
    version: str = Field(default="v1")
    title: str = Field(..., description="Paper title")
    arxiv_url: str = Field(..., description="URL to arXiv abstract")
    pdf_url: str = Field(..., description="URL to PDF")
    
    # Metadata
    authors: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    subcategories: List[str] = Field(default_factory=list)
    submitted_date: str = Field(default="")
    doi: Optional[str] = Field(None)
    
    # Extracted content (from docling)
    text_content: str = Field(
        ...,
        description="Full text extracted from PDF"
    )
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables with captions and data"
    )
    equations: List[str] = Field(
        default_factory=list,
        description="LaTeX equations extracted from PDF"
    )
    figure_captions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Figure captions and IDs"
    )
    
    # Extraction metadata
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="docling version, processing time, etc."
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ArxivDiscoveryBatch(BaseModel):
    """Batch of discovered papers for efficient processing.
    
    Attributes:
        correlation_id: Batch correlation ID
        papers: List of discovered papers
        query: The query that generated these papers
        total_found: Total papers found before filtering
        batch_number: Batch number for large result sets
        total_batches: Total batches for this query
    """
    
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Batch correlation ID"
    )
    papers: List[ArxivDiscoveredMessage] = Field(
        default_factory=list,
        description="List of discovered papers"
    )
    query: str = Field(default="", description="The query that generated these")
    total_found: int = Field(default=0, description="Total papers found")
    batch_number: int = Field(default=1, description="Batch number")
    total_batches: int = Field(default=1, description="Total batches")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

