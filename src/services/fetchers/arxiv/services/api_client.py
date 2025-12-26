"""arXiv API client with rate limiting and caching.

Integrates with existing cache infrastructure.
Handles rate limiting (1 req/3 sec), pagination, and error handling.
"""
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any
import httpx
import asyncio
import logging
from datetime import datetime

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import PaperMetadata, PaperSource
from src.services.fetchers.arxiv.services.cache_manager import CacheManager
from src.services.fetchers.arxiv.utils.rate_limiter import RateLimiter
from src.services.fetchers.arxiv.exceptions import (
    ArxivAPIError,
    RateLimitError,
    APITimeoutError,
    APIResponseError,
)


logger = logging.getLogger(__name__)


class ArxivAPIError(Exception):
    """Exception for arXiv API errors."""
    pass


class ArxivAPIClient:
    """Client for arXiv API.
    
    Features:
    - Rate limiting (1 request per 3 seconds)
    - Automatic pagination
    - Response caching
    - XML parsing
    - Error handling with retries
    
    Attributes:
        base_url: arXiv API base URL
        rate_limiter: Rate limiter instance
        cache: Optional cache manager
        config: Configuration
        http_client: HTTP client
    """
    
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
        config: Optional[ArxivFetcherConfig] = None,
        cache: Optional[CacheManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """Initialize arXiv API client.
        
        Args:
            config: ArXiv fetcher configuration
            cache: Cache manager for caching responses
            rate_limiter: Rate limiter instance
        """
        self.config = config or ArxivFetcherConfig()
        self.cache = cache
        self.rate_limiter = rate_limiter or RateLimiter(
            rate=self.config.rate_limit_requests_per_second,
        )
        
        # HTTP client configuration
        self.timeout = httpx.Timeout(30.0, connect=10.0)
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
        max_results: Optional[int] = None,
        start_index: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[PaperMetadata]:
        """Execute search query against arXiv API.
        
        Args:
            query: Search query string
            max_results: Maximum results to return (default: config default)
            start_index: Starting index for pagination
            sort_by: Sort field (relevance, lastUpdatedDate, submittedDate)
            sort_order: ascending or descending
            
        Returns:
            List of PaperMetadata matching query
            
        Raises:
            ArxivAPIError: If API request fails
        """
        max_results = max_results or self.config.default_results_per_query
        
        # Check cache first
        if self.cache:
            cache_key_params = {
                "query": query,
                "max_results": max_results,
                "start_index": start_index,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }
            cached = await self.cache.get_api_response(query, **cache_key_params)
            if cached:
                self._cache_hit_count += 1
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return self._parse_cached_response(cached)
        
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
            
            # Cache the response
            if self.cache:
                cache_data = {
                    "query": query,
                    "max_results": max_results,
                    "start_index": start_index,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                    "papers": [p.model_dump() for p in papers],
                    "fetched_at": datetime.utcnow().isoformat(),
                }
                await self.cache.set_api_response(query, **cache_key_params, response=cache_data)
            
            logger.info(f"Found {len(papers)} papers for query: {query[:50]}...")
            return papers
            
        except httpx.HTTPStatusError as e:
            self._error_count += 1
            if e.response.status_code == 429:
                raise RateLimitError(
                    message="arXiv rate limit exceeded",
                    retry_after=3,  # arXiv uses 3 second intervals
                    original=e,
                )
            raise ArxivAPIError(
                f"arXiv API error: {e.response.status_code} - {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
                original=e,
            )
        except httpx.TimeoutException:
            self._error_count += 1
            raise APITimeoutError(
                message="arXiv API request timed out",
                timeout_seconds=30,
            )
        except httpx.RequestError as e:
            self._error_count += 1
            raise ArxivAPIError(
                f"Failed to connect to arXiv API: {e}",
                original=e,
            )
    
    async def fetch_by_categories(
        self,
        categories: List[str],
        max_per_category: int = 50,
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
            # Build category query
            query = f"cat:{category}"
            
            if days_back:
                # Add date filter
                from datetime import datetime, timedelta
                date_from = datetime.utcnow() - timedelta(days=days_back)
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
        
        logger.info(
            f"Fetched {len(all_papers)} papers from {len(categories)} categories"
        )
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
        
        # arXiv API limits to 2000 IDs per query
        batch_size = 100
        all_papers = []
        
        for i in range(0, len(paper_ids), batch_size):
            batch = paper_ids[i:i + batch_size]
            id_query = " OR ".join(f"id:{pid}" for pid in batch)
            
            papers = await self.search(
                query=id_query,
                max_results=len(batch),
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
        """Build arXiv API search URL.
        
        Args:
            query: Search query
            max_results: Maximum results
            start_index: Starting index
            sort_by: Sort field
            sort_order: Sort order
            
        Returns:
            Full API URL
        """
        params = {
            "search_query": query,
            "start": start_index,
            "max_results": min(max_results, 2000),  # arXiv limit
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        
        # Build URL
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}?{param_str}"
    
    def _parse_atom_response(
        self,
        xml_content: str,
        source_query: str = "",
    ) -> List[PaperMetadata]:
        """Parse ATOM response from arXiv API.
        
        Args:
            xml_content: XML response content
            source_query: Original query for tracking
            
        Returns:
            List of PaperMetadata
        """
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
            raise APIResponseError(
                message=f"Failed to parse arXiv response: {e}",
                response_text=xml_content[:500],
                original=e,
            )
        
        return papers
    
    def _parse_entry(
        self,
        entry: ET.Element,
        ns: Dict[str, str],
        source_query: str,
    ) -> Optional[PaperMetadata]:
        """Parse a single ATOM entry.
        
        Args:
            entry: XML element for entry
            namespaces: XML namespaces
            source_query: Original query
            
        Returns:
            PaperMetadata or None if parsing fails
        """
        try:
            # Extract ID (format: http://arxiv.org/abs/2401.12345v1)
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
            # Clean title (arXiv titles have newlines)
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
                    # Extract main category and subcategory
                    if "." in cat_term:
                        parts = cat_term.split(".")
                        if len(parts) >= 1:
                            subcategories.append(parts[0])  # Main category
            
            # Extract dates
            published_elem = entry.find("atom:published", ns)
            submitted_date = ""
            if published_elem is not None and published_elem.text:
                submitted_date = published_elem.text[:10]  # YYYY-MM-DD
            
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
    
    def _parse_cached_response(self, cached_data: Dict[str, Any]) -> List[PaperMetadata]:
        """Parse cached response data.
        
        Args:
            cached_data: Cached response dict
            
        Returns:
            List of PaperMetadata
        """
        papers = []
        for paper_data in cached_data.get("papers", []):
            try:
                papers.append(PaperMetadata(**paper_data))
            except Exception as e:
                logger.warning(f"Failed to parse cached paper: {e}")
        return papers
    
    async def health_check(self) -> bool:
        """Check if arXiv API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Simple health check - try a minimal query
            response = await self.http_client.get(
                f"{self.BASE_URL}?search_query=cat:cs.LG&max_results=1",
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"arXiv API health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics.
        
        Returns:
            Dict with request/cache stats
        """
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

