"""Abstract interfaces for arXiv fetcher plugin.

Defines contracts that components must honor.
Allows for different implementations (e.g., mock for testing).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PaperSource(str, Enum):
    """Source of paper discovery."""
    QUERY = "query"
    CATEGORY = "category"


@dataclass
class PaperMetadata:
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
    paper_id: str
    version: str = "v1"
    title: str = ""
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    subcategories: List[str] = field(default_factory=list)
    submitted_date: str = ""
    updated_date: Optional[str] = None
    doi: Optional[str] = None
    journal_ref: Optional[str] = None
    comments: Optional[str] = None
    pdf_url: str = ""
    arxiv_url: str = ""
    source: PaperSource = PaperSource.QUERY
    source_query: str = ""
    relevance_score: Optional[float] = None


@dataclass
class ParsedContent:
    """Extracted content from PDF.
    
    Attributes:
        paper_id: arXiv ID this content belongs to
        text_content: Full text extracted from PDF
        tables: List of extracted tables with captions and data
        equations: LaTeX equations found in the PDF
        figure_captions: Figure captions and their IDs
        metadata: Additional extraction metadata
    """
    paper_id: str
    text_content: str = ""
    tables: List[Dict[str, Any]] = field(default_factory=list)
    equations: List[str] = field(default_factory=list)
    figure_captions: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryExpansion:
    """Result of query expansion.
    
    Attributes:
        original_query: The original query
        expanded_queries: List of expanded query strings
        generated_at: When the expansion was generated
        cache_hit: Whether this was a cache hit
    """
    original_query: str
    expanded_queries: List[str]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    cache_hit: bool = False


class IArxivAPI(ABC):
    """Interface for arXiv API client.
    
    What changes: HTTP client implementation, retry logic, rate limiting strategy
    What must not change: Query execution, result parsing, pagination contract
    """
    
    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        start_index: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[PaperMetadata]:
        """Execute search query against arXiv API.
        
        Args:
            query: Search query string
            max_results: Maximum results to return (None for default)
            start_index: Starting index for pagination
            sort_by: Sort field (relevance, lastUpdatedDate, submittedDate)
            sort_order: ascending or descending
            
        Returns:
            List of paper metadata matching query
        """
        pass
    
    @abstractmethod
    async def fetch_by_categories(
        self,
        categories: List[str],
        max_per_category: int = 50,
        days_back: Optional[int] = None,
    ) -> List[PaperMetadata]:
        """Fetch recent papers from specified categories.
        
        Args:
            categories: List of arXiv categories (e.g., ['cs.LG', 'stat.ML'])
            max_per_category: Maximum papers per category
            days_back: Only fetch papers from last N days (None for all)
            
        Returns:
            List of paper metadata from categories
        """
        pass
    
    @abstractmethod
    async def fetch_by_ids(
        self,
        paper_ids: List[str],
    ) -> List[PaperMetadata]:
        """Fetch specific papers by arXiv IDs.
        
        Args:
            paper_ids: List of arXiv IDs (e.g., ['2101.12345'])
            
        Returns:
            List of paper metadata
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if arXiv API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        pass


class IPDFParser(ABC):
    """Interface for PDF content extraction.
    
    What changes: PDF library implementation, extraction algorithm
    What must not change: Output format (ParsedContent dataclass)
    """
    
    @abstractmethod
    async def extract(
        self,
        pdf_url: str,
        paper_id: str,
    ) -> ParsedContent:
        """Extract content from PDF at URL.
        
        Args:
            pdf_url: URL to PDF file
            paper_id: arXiv ID for this paper
            
        Returns:
            ParsedContent with extracted text, tables, equations, captions
        """
        pass
    
    @abstractmethod
    async def extract_from_bytes(
        self,
        pdf_bytes: bytes,
        paper_id: str,
    ) -> ParsedContent:
        """Extract content from PDF bytes (for cached PDFs).
        
        Args:
            pdf_bytes: Raw PDF file bytes
            paper_id: arXiv ID for this paper
            
        Returns:
            ParsedContent with extracted content
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if PDF parser is healthy.
        
        Returns:
            True if parser is healthy, False otherwise
        """
        pass


class ICacheBackend(ABC):
    """Interface for caching layer.
    
    What changes: Redis, disk, memory implementations
    What must not change: Get/set/delete interface, TTL handling
    """
    
    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        """Get cached value by key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached bytes or None if not found
        """
        pass
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set cached value with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached value.
        
        Args:
            key: Cache key to delete
        """
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close cache connection."""
        pass


class IMessagePublisher(ABC):
    """Interface for message publishing.
    
    What changes: Queue implementation (RabbitMQ, Redis, etc.)
    What must not change: Publish interface, message format contract
    """
    
    @abstractmethod
    async def publish_discovered(
        self,
        papers: List[PaperMetadata],
        correlation_id: Optional[str] = None,
    ) -> int:
        """Publish discovered papers to arxiv.discovered queue.
        
        Args:
            papers: List of paper metadata to publish
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            Number of papers published successfully
        """
        pass
    
    @abstractmethod
    async def publish_parse_request(
        self,
        paper_id: str,
        pdf_url: str,
        correlation_id: str,
        original_correlation_id: str,
        priority: int = 5,
        relevance_score: Optional[float] = None,
        intelligence_notes: Optional[str] = None,
    ) -> None:
        """Publish a parse request to arxiv.parse_request queue.
        
        Args:
            paper_id: arXiv ID to parse
            pdf_url: URL to PDF
            correlation_id: Correlation ID for this request
            original_correlation_id: Original discovery correlation ID
            priority: Parse priority (1-10)
            relevance_score: LLM-assigned relevance score
            intelligence_notes: Optional notes from intelligence layer
        """
        pass
    
    @abstractmethod
    async def publish_extracted(
        self,
        paper: PaperMetadata,
        content: ParsedContent,
        discovery_correlation_id: str,
        parse_correlation_id: str,
    ) -> None:
        """Publish extracted paper to content.extracted queue.
        
        Args:
            paper: Original paper metadata
            content: Extracted PDF content
            discovery_correlation_id: Original discovery correlation
            parse_correlation_id: Parse request correlation
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close publisher connection."""
        pass


class IQueryProcessor(ABC):
    """Interface for query processing before API call.
    
    What changes: Query transformation logic, fuzzy matching implementation
    What must not change: Input/output contract
    """
    
    @abstractmethod
    async def expand_query(
        self,
        raw_query: str,
    ) -> QueryExpansion:
        """Expand raw query into multiple search queries.
        
        Args:
            raw_query: Query from external orchestration
            
        Returns:
            QueryExpansion with expanded queries
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if query processor is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        pass


class IRateLimiter(ABC):
    """Interface for rate limiting.
    
    What changes: Token bucket, sliding window, etc.
    What must not change: acquire() interface
    """
    
    @abstractmethod
    async def acquire(self) -> None:
        """Acquire permission to make a request.
        
        Blocks if rate limit is exceeded.
        """
        pass
    
    @abstractmethod
    async def get_delay(self) -> float:
        """Get the delay until next request is allowed.
        
        Returns:
            Delay in seconds (0 if available now)
        """
        pass
    
    @abstractmethod
    async def reset(self) -> None:
        """Reset rate limiter state."""
        pass


class IArxivFetcher(ABC):
    """Main interface for arXiv fetcher.
    
    Orchestrates all components for paper discovery.
    """
    
    @abstractmethod
    async def run_discovery(
        self,
        queries: List[str],
        categories: Optional[List[str]] = None,
    ) -> int:
        """Run paper discovery for queries and/or categories.
        
        Args:
            queries: List of search queries
            categories: Optional list of categories to also monitor
            
        Returns:
            Number of papers discovered and published
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all components.
        
        Returns:
            Dict mapping component name to health status
        """
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize all components."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Clean up all resources."""
        pass

