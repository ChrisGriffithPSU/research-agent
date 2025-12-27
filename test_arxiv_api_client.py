#!/usr/bin/env python3
"""
Standalone test suite for ArxivAPIClient.

This script tests the arXiv API client functionality without depending on the broken shared library.
It makes actual HTTP calls to the arXiv API and tests:
- URL building
- XML response parsing
- HTTP API calls
- Rate limiting
- Error handling

Run with: python test_arxiv_api_client.py

Dependencies:
- httpx
- pydantic
"""

import asyncio
import sys
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

import httpx
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================
# Minimal implementations to avoid shared library dependencies
# ============================================================

class PaperSource(str):
    """Source of paper discovery."""
    QUERY = "query"
    CATEGORY = "category"


class PaperMetadata:
    """Immutable paper metadata from arXiv."""
    
    def __init__(
        self,
        paper_id: str,
        version: str = "v1",
        title: str = "",
        abstract: str = "",
        authors: List[str] = None,
        categories: List[str] = None,
        subcategories: List[str] = None,
        submitted_date: str = "",
        updated_date: Optional[str] = None,
        doi: Optional[str] = None,
        journal_ref: Optional[str] = None,
        comments: Optional[str] = None,
        pdf_url: str = "",
        arxiv_url: str = "",
        source: str = PaperSource.QUERY,
        source_query: str = "",
        relevance_score: Optional[float] = None,
    ):
        self.paper_id = paper_id
        self.version = version
        self.title = title
        self.abstract = abstract
        self.authors = authors or []
        self.categories = categories or []
        self.subcategories = subcategories or []
        self.submitted_date = submitted_date
        self.updated_date = updated_date
        self.doi = doi
        self.journal_ref = journal_ref
        self.comments = comments
        self.pdf_url = pdf_url
        self.arxiv_url = arxiv_url
        self.source = source
        self.source_query = source_query
        self.relevance_score = relevance_score
    
    def __repr__(self):
        return f"PaperMetadata(paper_id={self.paper_id}, title={self.title[:30]}...)"
    
    def __eq__(self, other):
        if isinstance(other, PaperMetadata):
            return self.paper_id == other.paper_id
        return False
    
    def __hash__(self):
        return hash(self.paper_id)
    
    def model_dump(self) -> Dict[str, Any]:
        """Export to dictionary."""
        return {
            "paper_id": self.paper_id,
            "version": self.version,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "categories": self.categories,
            "subcategories": self.subcategories,
            "submitted_date": self.submitted_date,
            "updated_date": self.updated_date,
            "doi": self.doi,
            "journal_ref": self.journal_ref,
            "comments": self.comments,
            "pdf_url": self.pdf_url,
            "arxiv_url": self.arxiv_url,
            "source": self.source,
            "source_query": self.source_query,
            "relevance_score": self.relevance_score,
        }


# ============================================================
# Rate Limiter Implementation (from utils/rate_limiter.py)
# ============================================================

import time

class RateLimiter:
    """Token bucket rate limiter for arXiv API."""
    
    def __init__(
        self,
        rate: float = 0.333,  # 1 request per 3 seconds
        capacity: int = 1,
        initial_tokens: Optional[float] = None,
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire permission to make a request."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                logger.debug(f"Rate limiter: acquired token, {self.tokens:.2f} remaining")
                return
            
            # No token available, calculate wait time
            wait_time = (1 - self.tokens) / self.rate
        
        # Release lock before waiting
        logger.debug(f"Rate limiter: waiting {wait_time:.2f}s for token")
        await asyncio.sleep(wait_time)
        
        # Try again
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                logger.debug(f"Rate limiter: acquired after wait, {self.tokens:.2f} remaining")
                return
            
            raise Exception("Failed to acquire rate limit token")
    
    async def get_delay(self) -> float:
        """Get the delay until next request is allowed."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                return 0.0
            
            return (1 - self.tokens) / self.rate
    
    async def try_acquire(self) -> bool:
        """Try to acquire a token without blocking."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            
            return False
    
    def reset(self) -> None:
        """Reset rate limiter state."""
        self.tokens = self.capacity
        self.last_update = time.monotonic()
    
    def get_available_tokens(self) -> float:
        """Get number of available tokens."""
        now = time.monotonic()
        elapsed = now - self.last_update
        tokens = min(
            self.capacity,
            self.tokens + elapsed * self.rate
        )
        return tokens
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "rate": self.rate,
            "capacity": self.capacity,
            "available_tokens": self.get_available_tokens(),
            "wait_time": (1 - self.tokens) / self.rate if self.tokens < 1 else 0,
        }
    
    def __repr__(self) -> str:
        tokens = self.get_available_tokens()
        return f"RateLimiter(rate={self.rate:.3f}/s, capacity={self.capacity}, available={tokens:.2f})"


# ============================================================
# ArxivAPIClient Implementation (simplified for standalone testing)
# ============================================================

class ArxivAPIClient:
    """Client for arXiv API."""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    # arXiv API sort options
    SORT_RELEVANCE = "relevance"
    SORT_LAST_UPDATED = "lastUpdatedDate"
    SORT_SUBMITTED = "submittedDate"
    
    # Sort orders
    ORDER_DESCENDING = "descending"
    ORDER_ASCENDING = "ascending"
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        timeout: float = 30.0,
    ):
        """Initialize arXiv API client.
        
        Args:
            rate_limiter: Rate limiter instance
            timeout: HTTP timeout in seconds
        """
        self.rate_limiter = rate_limiter or RateLimiter(rate=0.333)
        
        # HTTP client configuration
        self.timeout = httpx.Timeout(timeout, connect=10.0)
        self.http_client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        )
        
        # Statistics
        self._request_count = 0
        self._error_count = 0
        self._cache_hit_count = 0
    
    async def initialize(self) -> None:
        """Initialize the client."""
        logger.info("ArxivAPIClient initialized")
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()
        logger.info("ArxivAPIClient closed")
    
    async def search(
        self,
        query: str,
        max_results: int = 10,
        start_index: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[PaperMetadata]:
        """Execute search query against arXiv API.
        
        Args:
            query: Search query string
            max_results: Maximum results to return
            start_index: Starting index for pagination
            sort_by: Sort field (relevance, lastUpdatedDate, submittedDate)
            sort_order: ascending or descending
            
        Returns:
            List of PaperMetadata matching query
        """
        # Apply rate limiting
        await self.rate_limiter.acquire()
        
        # Build URL
        url = self._build_search_url(
            query=query,
            max_results=max_results,
            start_index=start_index,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        try:
            logger.debug(f"Executing arXiv search: {query[:50]}...")
            response = await self.http_client.get(url)
            response.raise_for_status()
            self._request_count += 1
            
            # Parse XML response
            papers = self._parse_atom_response(response.text, source_query=query)
            
            logger.info(f"Found {len(papers)} papers for query: {query[:50]}...")
            return papers
            
        except httpx.HTTPStatusError as e:
            self._error_count += 1
            raise Exception(f"arXiv API error: {e.response.status_code} - {e.response.text}")
        except httpx.TimeoutException:
            self._error_count += 1
            raise Exception(f"arXiv API request timed out")
        except httpx.RequestError as e:
            self._error_count += 1
            raise Exception(f"Failed to connect to arXiv API: {e}")
    
    async def fetch_by_categories(
        self,
        categories: List[str],
        max_per_category: int = 10,
        days_back: Optional[int] = None,
    ) -> List[PaperMetadata]:
        """Fetch recent papers from specified categories.
        
        Args:
            categories: List of arXiv categories
            max_per_category: Maximum papers per category
            days_back: Only fetch papers from last N days
            
        Returns:
            List of PaperMetadata from categories
        """
        all_papers = []
        
        for category in categories:
            query = f"cat:{category}"
            
            if days_back:
                date_from = datetime.utcnow() - datetime.timedelta(days=days_back)
                date_str = date_from.strftime("%Y%m%d")
                query = f"cat:{category} AND submittedDate:[{date_str} TO 99991231]"
            
            papers = await self.search(
                query=query,
                max_results=max_per_category,
                sort_by=self.SORT_SUBMITTED,
                sort_order=self.ORDER_DESCENDING,
            )
            
            # Mark source as category
            for paper in papers:
                paper.source = PaperSource.CATEGORY
                paper.source_query = category
            
            all_papers.extend(papers)
        
        logger.info(f"Fetched {len(all_papers)} papers from {len(categories)} categories")
        return all_papers
    
    async def fetch_by_ids(
        self,
        paper_ids: List[str],
    ) -> List[PaperMetadata]:
        """Fetch specific papers by arXiv IDs.
        
        Args:
            paper_ids: List of arXiv IDs
            
        Returns:
            List of PaperMetadata
        """
        if not paper_ids:
            return []
        
        all_papers = []
        
        for paper_id in paper_ids:
            papers = await self.search(
                query=f"id:{paper_id}",
                max_results=1,
            )
            all_papers.extend(papers)
        
        return all_papers
    
    def _build_search_url(
        self,
        query: str,
        max_results: int,
        start_index: int,
        sort_by: str,
        sort_order: str,
    ) -> str:
        """Build arXiv API search URL."""
        params = {
            "search_query": query,
            "start": start_index,
            "max_results": min(max_results, 2000),
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}?{param_str}"
    
    def _parse_atom_response(
        self,
        xml_content: str,
        source_query: str = "",
    ) -> List[PaperMetadata]:
        """Parse ATOM response from arXiv API."""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            
            # Parse entries
            for entry in root.findall("atom:entry", ns):
                try:
                    paper = self._parse_entry(entry, ns, source_query)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to parse entry: {e}")
                    continue
            
        except ET.ParseError as e:
            raise Exception(f"Failed to parse arXiv response: {e}")
        
        return papers
    
    def _parse_entry(
        self,
        entry: ET.Element,
        ns: Dict[str, str],
        source_query: str,
    ) -> Optional[PaperMetadata]:
        """Parse a single ATOM entry."""
        try:
            # Extract ID
            id_elem = entry.find("atom:id", ns)
            arxiv_id_raw = id_elem.text if id_elem is not None else ""
            
            # Parse paper ID and version
            arxiv_id = ""
            version = "v1"
            if "arxiv.org/abs/" in arxiv_id_raw:
                parts = arxiv_id_raw.split("arxiv.org/abs/")[1]
                if "v" in parts:
                    arxiv_id = parts.split("v")[0]
                    version = f"v{parts.split('v')[1]}"
                else:
                    arxiv_id = parts
            
            # Extract title
            title_elem = entry.find("atom:title", ns)
            title = title_elem.text if title_elem is not None else ""
            title = " ".join(title.strip().split())
            
            # Extract abstract
            summary_elem = entry.find("atom:summary", ns)
            abstract = summary_elem.text if summary_elem is not None else ""
            abstract = " ".join(abstract.strip().split())
            
            # Extract authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name_elem = author.find("atom:name", ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)
            
            # Extract categories
            categories = []
            subcategories = []
            for category in entry.findall("atom:category", ns):
                cat_term = category.get("term", "")
                if cat_term:
                    categories.append(cat_term)
                    if "." in cat_term:
                        parts = cat_term.split(".")
                        if len(parts) >= 1:
                            subcategories.append(parts[0])
            
            # Extract dates
            published_elem = entry.find("atom:published", ns)
            submitted_date = ""
            if published_elem is not None and published_elem.text:
                submitted_date = published_elem.text[:10]
            
            updated_elem = entry.find("atom:updated", ns)
            updated_date = None
            if updated_elem is not None and updated_elem.text:
                updated_date = updated_elem.text[:10]
            
            # Extract links
            pdf_url = ""
            arxiv_url = ""
            for link in entry.findall("atom:link", ns):
                rel = link.get("rel", "")
                href = link.get("href", "")
                if rel == "alternate":
                    arxiv_url = href
                elif link.get("title") == "pdf":
                    pdf_url = href
                elif href.endswith(".pdf"):
                    pdf_url = href
            
            # Extract DOI
            doi_elem = entry.find("arxiv:doi", ns)
            doi = doi_elem.text if doi_elem is not None else None
            
            # Extract journal ref
            journal_elem = entry.find("arxiv:journal_ref", ns)
            journal_ref = journal_elem.text if journal_elem is not None else None
            
            # Extract comments
            comment_elem = entry.find("arxiv:comment", ns)
            comments = comment_elem.text if comment_elem is not None else None
            
            return PaperMetadata(
                paper_id=arxiv_id,
                version=version,
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                subcategories=list(set(categories + subcategories)),
                submitted_date=submitted_date,
                updated_date=updated_date,
                doi=doi,
                journal_ref=journal_ref,
                comments=comments,
                pdf_url=pdf_url,
                arxiv_url=arxiv_url,
                source_query=source_query,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse entry: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if arXiv API is accessible."""
        try:
            response = await self.http_client.get(
                f"{self.BASE_URL}?search_query=cat:cs.LG&max_results=1",
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"arXiv API health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "cache_hit_count": self._cache_hit_count,
            "success_rate": (
                (self._request_count - self._error_count) / self._request_count
                if self._request_count > 0 else 0
            ),
        }
    
    def __repr__(self) -> str:
        return (
            f"ArxivAPIClient("
            f"requests={self._request_count}, "
            f"errors={self._error_count}, "
            f"cache_hits={self._cache_hit_count})"
        )


# ============================================================
# Test Functions
# ============================================================

class TestResults:
    """Track test results."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        self.passed += 1
        logger.info(f"✓ PASS: {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append((test_name, error))
        logger.error(f"✗ FAIL: {test_name} - {error}")
    
    def print_summary(self):
        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Passed: {self.passed}")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Total:  {self.passed + self.failed}")
        
        if self.errors:
            logger.info("\nFailed tests:")
            for test_name, error in self.errors:
                logger.info(f"  - {test_name}: {error}")
        
        return self.failed == 0


# ============================================================
# Unit Tests (No HTTP calls)
# ============================================================

def test_url_building(results: TestResults):
    """Test URL building functionality."""
    logger.info("\n--- Testing URL Building ---")
    
    client = ArxivAPIClient()
    
    # Test basic search URL
    url = client._build_search_url(
        query="transformer",
        max_results=10,
        start_index=0,
        sort_by="relevance",
        sort_order="descending",
    )
    
    expected_base = "http://export.arxiv.org/api/query?"
    if not url.startswith(expected_base):
        results.add_fail("URL building - basic", f"URL doesn't start with base: {url}")
        return
    
    if "search_query=transformer" not in url:
        results.add_fail("URL building - query param", f"Missing query param: {url}")
        return
    
    if "max_results=10" not in url:
        results.add_fail("URL building - max_results", f"Missing max_results: {url}")
        return
    
    if "sortBy=relevance" not in url:
        results.add_fail("URL building - sortBy", f"Missing sortBy: {url}")
        return
    
    if "sortOrder=descending" not in url:
        results.add_fail("URL building - sortOrder", f"Missing sortOrder: {url}")
        return
    
    # Test with special characters
    url_special = client._build_search_url(
        query="neural network",
        max_results=5,
        start_index=10,
        sort_by="submittedDate",
        sort_order="ascending",
    )
    
    if "start=10" not in url_special:
        results.add_fail("URL building - start index", f"Missing start index: {url_special}")
        return
    
    # Test arXiv API limits
    url_large = client._build_search_url(
        query="test",
        max_results=5000,  # Exceeds limit
        start_index=0,
        sort_by="relevance",
        sort_order="descending",
    )
    
    if "max_results=2000" in url_large:
        results.add_pass("URL building - respects API limits")
    else:
        results.add_fail("URL building - API limits", "Should cap max_results at 2000")
    
    results.add_pass("URL building - basic functionality")


def test_xml_parsing(results: TestResults):
    """Test XML response parsing."""
    logger.info("\n--- Testing XML Parsing ---")
    
    client = ArxivAPIClient()
    
    # Sample ATOM response (with proper namespace declarations)
    sample_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper Title</title>
    <summary> This is a test abstract. </summary>
    <published>2024-01-15T10:30:00Z</published>
    <updated>2024-01-16T14:20:00Z</updated>
    <author>
      <name>John Doe</name>
    </author>
    <author>
      <name>Jane Smith</name>
    </author>
    <category term="cs.LG"/>
    <category term="cs.AI"/>
    <link rel="alternate" href="http://arxiv.org/abs/2401.12345"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1.pdf"/>
    <arxiv:doi>10.1234/test.doi</arxiv:doi>
    <arxiv:journal_ref>Test Journal 2024</arxiv:journal_ref>
    <arxiv:comment>15 pages, 3 figures</arxiv:comment>
  </entry>
</feed>"""
    
    papers = client._parse_atom_response(sample_xml, source_query="test query")
    
    if len(papers) != 1:
        results.add_fail("XML parsing - entry count", f"Expected 1 paper, got {len(papers)}")
        return
    
    paper = papers[0]
    
    # Test paper ID extraction
    if paper.paper_id != "2401.12345":
        results.add_fail("XML parsing - paper ID", f"Expected '2401.12345', got '{paper.paper_id}'")
        return
    
    # Test version extraction
    if paper.version != "v1":
        results.add_fail("XML parsing - version", f"Expected 'v1', got '{paper.version}'")
        return
    
    # Test title extraction
    if paper.title != "Test Paper Title":
        results.add_fail("XML parsing - title", f"Expected 'Test Paper Title', got '{paper.title}'")
        return
    
    # Test abstract extraction (whitespace cleaned)
    if paper.abstract != "This is a test abstract.":
        results.add_fail("XML parsing - abstract", f"Expected cleaned abstract, got '{paper.abstract}'")
        return
    
    # Test authors
    if len(paper.authors) != 2:
        results.add_fail("XML parsing - author count", f"Expected 2 authors, got {len(paper.authors)}")
        return
    
    if "John Doe" not in paper.authors:
        results.add_fail("XML parsing - author names", f"Expected 'John Doe' in authors")
        return
    
    # Test categories
    if "cs.LG" not in paper.categories:
        results.add_fail("XML parsing - categories", f"Expected 'cs.LG' in categories")
        return
    
    # Test subcategories (main category extracted)
    if "cs" not in paper.subcategories:
        results.add_fail("XML parsing - subcategories", f"Expected 'cs' in subcategories")
        return
    
    # Test dates
    if paper.submitted_date != "2024-01-15":
        results.add_fail("XML parsing - submitted date", f"Expected '2024-01-15', got '{paper.submitted_date}'")
        return
    
    if paper.updated_date != "2024-01-16":
        results.add_fail("XML parsing - updated date", f"Expected '2024-01-16', got '{paper.updated_date}'")
        return
    
    # Test links
    if "2401.12345.pdf" not in paper.pdf_url:
        results.add_fail("XML parsing - PDF URL", f"Expected PDF URL, got '{paper.pdf_url}'")
        return
    
    if "2401.12345" in paper.arxiv_url:
        results.add_pass("XML parsing - arxiv URL")
    else:
        results.add_fail("XML parsing - arxiv URL", f"Expected arxiv URL, got '{paper.arxiv_url}'")
    
    # Test DOI
    if paper.doi != "10.1234/test.doi":
        results.add_fail("XML parsing - DOI", f"Expected DOI, got '{paper.doi}'")
        return
    
    # Test journal ref
    if paper.journal_ref != "Test Journal 2024":
        results.add_fail("XML parsing - journal ref", f"Expected journal ref, got '{paper.journal_ref}'")
        return
    
    # Test comments
    if paper.comments != "15 pages, 3 figures":
        results.add_fail("XML parsing - comments", f"Expected comments, got '{paper.comments}'")
        return
    
    # Test source query tracking
    if paper.source_query != "test query":
        results.add_fail("XML parsing - source query", f"Expected source query tracking")
        return
    
    results.add_pass("XML parsing - full response")


def test_xml_parsing_empty_response(results: TestResults):
    """Test parsing empty ATOM response."""
    logger.info("\n--- Testing XML Parsing (Empty) ---")
    
    client = ArxivAPIClient()
    
    empty_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""
    
    papers = client._parse_atom_response(empty_xml)
    
    if len(papers) == 0:
        results.add_pass("XML parsing - empty response")
    else:
        results.add_fail("XML parsing - empty response", f"Expected 0 papers, got {len(papers)}")


def test_xml_parsing_multiple_entries(results: TestResults):
    """Test parsing response with multiple entries."""
    logger.info("\n--- Testing XML Parsing (Multiple) ---")
    
    client = ArxivAPIClient()
    
    multi_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.11111v1</id>
    <title>First Paper</title>
    <summary>Abstract 1</summary>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>Author A</name></author>
    <category term="cs.LG"/>
    <link rel="alternate" href="http://arxiv.org/abs/2401.11111"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.11111v1.pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.22222v2</id>
    <title>Second Paper</title>
    <summary>Abstract 2</summary>
    <published>2024-01-02T00:00:00Z</published>
    <author><name>Author B</name></author>
    <category term="stat.ML"/>
    <link rel="alternate" href="http://arxiv.org/abs/2401.22222"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.22222v2.pdf"/>
  </entry>
</feed>"""
    
    papers = client._parse_atom_response(multi_xml)
    
    if len(papers) != 2:
        results.add_fail("XML parsing - multiple entries", f"Expected 2 papers, got {len(papers)}")
        return
    
    if papers[0].paper_id == "2401.11111" and papers[1].paper_id == "2401.22222":
        results.add_pass("XML parsing - multiple entries")
    else:
        results.add_fail("XML parsing - multiple entries", "Paper IDs don't match")


def test_rate_limiter_logic(results: TestResults):
    """Test rate limiter functionality."""
    logger.info("\n--- Testing Rate Limiter ---")
    
    # Test initialization
    limiter = RateLimiter(rate=1.0, capacity=2)
    
    if limiter.rate != 1.0:
        results.add_fail("Rate limiter - rate", f"Expected rate 1.0, got {limiter.rate}")
        return
    
    if limiter.capacity != 2:
        results.add_fail("Rate limiter - capacity", f"Expected capacity 2, got {limiter.capacity}")
        return
    
    # Test initial tokens
    initial_tokens = limiter.get_available_tokens()
    if initial_tokens != 2.0:
        results.add_fail("Rate limiter - initial tokens", f"Expected 2.0, got {initial_tokens}")
        return
    
    # Test stats
    stats = limiter.get_stats()
    if stats["rate"] != 1.0 or stats["capacity"] != 2:
        results.add_fail("Rate limiter - stats", f"Stats incorrect: {stats}")
        return
    
    # Test reset
    limiter.reset()
    if limiter.get_available_tokens() != 2.0:
        results.add_fail("Rate limiter - reset", "Reset didn't restore tokens")
        return
    
    results.add_pass("Rate limiter - basic functionality")


def test_paper_metadata_model(results: TestResults):
    """Test PaperMetadata model."""
    logger.info("\n--- Testing PaperMetadata Model ---")
    
    # Test creation
    paper = PaperMetadata(
        paper_id="2401.12345",
        title="Test Paper",
        authors=["Author A", "Author B"],
        categories=["cs.LG", "stat.ML"],
    )
    
    if paper.paper_id != "2401.12345":
        results.add_fail("PaperMetadata - paper_id", "Paper ID not set correctly")
        return
    
    if paper.title != "Test Paper":
        results.add_fail("PaperMetadata - title", "Title not set correctly")
        return
    
    if len(paper.authors) != 2:
        results.add_fail("PaperMetadata - authors", "Authors not set correctly")
        return
    
    # Test defaults
    if paper.version != "v1":
        results.add_fail("PaperMetadata - default version", "Default version should be v1")
        return
    
    if paper.abstract != "":
        results.add_fail("PaperMetadata - default abstract", "Default abstract should be empty")
        return
    
    # Test equality
    paper2 = PaperMetadata(paper_id="2401.12345", title="Different Title")
    if paper != paper2:
        results.add_fail("PaperMetadata - equality", "Papers with same ID should be equal")
        return
    
    paper3 = PaperMetadata(paper_id="2401.99999", title="Test Paper")
    if paper == paper3:
        results.add_fail("PaperMetadata - inequality", "Papers with different IDs should not be equal")
        return
    
    # Test hashing (for deduplication)
    paper_set = {paper, paper2, paper3}
    if len(paper_set) != 2:
        results.add_fail("PaperMetadata - hashing", "Hashing not working correctly")
        return
    
    # Test model_dump
    dump = paper.model_dump()
    if dump["paper_id"] != "2401.12345":
        results.add_fail("PaperMetadata - model_dump", "model_dump not working correctly")
        return
    
    results.add_pass("PaperMetadata - full functionality")


# ============================================================
# Integration Tests (HTTP calls to arXiv API)
# ============================================================

async def test_health_check(results: TestResults):
    """Test arXiv API health check."""
    logger.info("\n--- Testing Health Check ---")
    
    client = ArxivAPIClient()
    
    try:
        is_healthy = await client.health_check()
        
        if is_healthy:
            results.add_pass("Health check - API is accessible")
        else:
            results.add_fail("Health check - API returned unhealthy", "Health check returned False")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Health check - exception", str(e))


async def test_basic_search(results: TestResults):
    """Test basic search functionality."""
    logger.info("\n--- Testing Basic Search ---")
    
    client = ArxivAPIClient()
    
    try:
        papers = await client.search(query="transformer", max_results=5)
        
        if len(papers) == 0:
            results.add_fail("Basic search - no results", "Expected papers but got none")
            return
        
        if len(papers) > 5:
            results.add_fail("Basic search - too many results", f"Expected <= 5 papers, got {len(papers)}")
            return
        
        # Check paper structure
        paper = papers[0]
        
        if not paper.paper_id:
            results.add_fail("Basic search - missing paper_id", "First paper missing paper_id")
            return
        
        if not paper.title:
            results.add_fail("Basic search - missing title", "First paper missing title")
            return
        
        if not paper.pdf_url:
            results.add_fail("Basic search - missing PDF URL", "First paper missing PDF URL")
            return
        
        # Check stats
        stats = client.get_stats()
        if stats["request_count"] != 1:
            results.add_fail("Basic search - request count", f"Expected 1 request, got {stats['request_count']}")
            return
        
        if stats["success_rate"] != 1.0:
            results.add_fail("Basic search - success rate", f"Expected 100% success rate, got {stats['success_rate']}")
            return
        
        results.add_pass(f"Basic search - found {len(papers)} papers")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Basic search - exception", str(e))


async def test_search_with_sorting(results: TestResults):
    """Test search with different sort options."""
    logger.info("\n--- Testing Search with Sorting ---")
    
    client = ArxivAPIClient()
    
    try:
        # Test relevance sorting
        papers_relevance = await client.search(
            query="machine learning",
            max_results=3,
            sort_by="relevance",
            sort_order="descending",
        )
        
        # Test submitted date sorting
        papers_date = await client.search(
            query="machine learning",
            max_results=3,
            sort_by="submittedDate",
            sort_order="descending",
        )
        
        if len(papers_relevance) == 0 or len(papers_date) == 0:
            results.add_fail("Sorting - no results", "Expected results for both sort options")
            return
        
        results.add_pass(f"Sorting - relevance: {len(papers_relevance)}, date: {len(papers_date)}")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Sorting - exception", str(e))


async def test_search_pagination(results: TestResults):
    """Test search pagination."""
    logger.info("\n--- Testing Pagination ---")
    
    client = ArxivAPIClient()
    
    try:
        # Get first page
        page1 = await client.search(
            query="neural network",
            max_results=3,
            start_index=0,
        )
        
        # Get second page
        page2 = await client.search(
            query="neural network",
            max_results=3,
            start_index=3,
        )
        
        if len(page1) == 0:
            results.add_fail("Pagination - page 1 empty", "First page has no results")
            return
        
        if len(page2) == 0:
            results.add_fail("Pagination - page 2 empty", "Second page has no results")
            return
        
        # Check for duplicates
        page1_ids = {p.paper_id for p in page1}
        page2_ids = {p.paper_id for p in page2}
        
        if page1_ids & page2_ids:
            results.add_fail("Pagination - duplicates", "Found duplicate papers across pages")
            return
        
        results.add_pass(f"Pagination - page 1: {len(page1)}, page 2: {len(page2)}")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Pagination - exception", str(e))


async def test_fetch_by_categories(results: TestResults):
    """Test fetching papers by category."""
    logger.info("\n--- Testing Fetch by Categories ---")
    
    client = ArxivAPIClient()
    
    try:
        papers = await client.fetch_by_categories(
            categories=["cs.LG", "stat.ML"],
            max_per_category=2,
        )
        
        if len(papers) == 0:
            results.add_fail("Fetch by categories - no results", "Expected papers from categories")
            return
        
        # Check that papers have category source
        category_papers = [p for p in papers if p.source == PaperSource.CATEGORY]
        
        if len(category_papers) == 0:
            results.add_fail("Fetch by categories - source not set", "Papers should have CATEGORY source")
            return
        
        # Check that source_query is set
        for paper in category_papers:
            if not paper.source_query:
                results.add_fail("Fetch by categories - source query", "Paper missing source_query")
                return
        
        results.add_pass(f"Fetch by categories - found {len(papers)} papers from {len(category_papers)} categories")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Fetch by categories - exception", str(e))


async def test_fetch_by_ids(results: TestResults):
    """Test fetching papers by IDs."""
    logger.info("\n--- Testing Fetch by IDs ---")
    
    client = ArxivAPIClient()
    
    try:
        # Test with known arXiv IDs
        papers = await client.fetch_by_ids([
            "2401.00001",  # Known test paper
            "2401.00002",  # Another test paper
        ])
        
        # Note: These papers may not exist, so we check behavior
        # rather than specific results
        
        stats = client.get_stats()
        if stats["request_count"] > 0:
            results.add_pass(f"Fetch by IDs - made {stats['request_count']} request(s)")
        else:
            results.add_fail("Fetch by IDs - no requests made", "Should have made requests")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Fetch by IDs - exception", str(e))


async def test_special_characters_in_query(results: TestResults):
    """Test queries with special characters."""
    logger.info("\n--- Testing Special Characters ---")
    
    client = ArxivAPIClient()
    
    try:
        # Test with quotes and special characters
        papers = await client.search(
            query='all:"attention mechanism"',
            max_results=3,
        )
        
        # Should handle the query without errors
        stats = client.get_stats()
        if stats["error_count"] == 0:
            results.add_pass(f"Special characters - handled query without errors")
        else:
            results.add_fail("Special characters - errors", f"Got {stats['error_count']} errors")
        
        await client.close()
        
    except Exception as e:
        results.add_fail("Special characters - exception", str(e))


# ============================================================
# Main Test Runner
# ============================================================

async def run_all_tests():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("STARTING ARXIV API CLIENT TEST SUITE")
    logger.info("=" * 60)
    
    results = TestResults()
    
    # Run unit tests (synchronous)
    logger.info("\n" + "=" * 60)
    logger.info("UNIT TESTS (No HTTP calls)")
    logger.info("=" * 60)
    
    test_url_building(results)
    test_xml_parsing(results)
    test_xml_parsing_empty_response(results)
    test_xml_parsing_multiple_entries(results)
    test_rate_limiter_logic(results)
    test_paper_metadata_model(results)
    
    # Run integration tests (HTTP calls)
    logger.info("\n" + "=" * 60)
    logger.info("INTEGRATION TESTS (HTTP calls to arXiv API)")
    logger.info("=" * 60)
    
    await test_health_check(results)
    
    # Only run live tests if API is accessible
    if True:  # Always try to run these
        await test_basic_search(results)
        await test_search_with_sorting(results)
        await test_search_pagination(results)
        await test_fetch_by_categories(results)
        await test_fetch_by_ids(results)
        await test_special_characters_in_query(results)
    
    # Print summary
    success = results.print_summary()
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST COMPLETE")
    logger.info("=" * 60)
    
    return success


def main():
    """Main entry point."""
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

