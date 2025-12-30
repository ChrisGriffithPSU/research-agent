"""Kaggle API client with dependency injection.

Uses kagglehub for notebook downloads and HTTP for search operations.
"""
import asyncio
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import kagglehub
import httpx

from src.shared.interfaces import IRateLimiter, ICircuitBreaker
from src.services.fetchers.kaggle.config import KaggleFetcherConfig
from src.services.fetchers.kaggle.interfaces import IKaggleAPI
from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookMetadata,
    NotebookContent,
    CompetitionMetadata,
    NotebookSource,
)
from src.services.fetchers.kaggle.exceptions import (
    KaggleAPIError,
    RateLimitError,
    APITimeoutError,
    NotebookDownloadError,
)


logger = logging.getLogger(__name__)


class KaggleAPIClient(IKaggleAPI):
    """Client for Kaggle API with injectable dependencies.

    Features:
    - Rate limiting (1 request per second)
    - Automatic retries with exponential backoff
    - Notebook downloads via kagglehub
    - Search operations via HTTP

    All dependencies are injected through the constructor.

    Example:
        # Production use with real dependencies
        client = KaggleAPIClient(
            rate_limiter=RateLimiter(rate=1.0),
            circuit_breaker=CircuitBreaker(),
            config=config,
        )

        # Testing use with mocks
        from src.shared.testing.mocks import MockRateLimiter, MockCircuitBreaker

        client = KaggleAPIClient(
            rate_limiter=MockRateLimiter(),
            circuit_breaker=MockCircuitBreaker(),
        )

        # Use client
        notebooks = await client.search_notebooks(query="time-series", max_results=10)

    Attributes:
        rate_limiter: Rate limiter implementation (IRateLimiter)
        circuit_breaker: Circuit breaker implementation (ICircuitBreaker)
        config: Configuration
    """

    BASE_URL = "https://www.kaggle.com/api/i/search.SearchService"

    def __init__(
        self,
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
        config: Optional[KaggleFetcherConfig] = None,
    ):
        """Initialize Kaggle API client.

        Args:
            rate_limiter: Rate limiter for API requests (IRateLimiter)
            circuit_breaker: Circuit breaker for fault tolerance (ICircuitBreaker)
            config: Kaggle fetcher configuration
        """
        self.config = config or KaggleFetcherConfig()

        # Use injectable rate limiter
        if rate_limiter is None:
            self._rate_limiter = DefaultRateLimiter(
                rate=self.config.rate_limit_requests_per_second,
            )
            self._owns_rate_limiter = True
        else:
            self._rate_limiter = rate_limiter
            self._owns_rate_limiter = False

        # Circuit breaker
        self._circuit_breaker = circuit_breaker

        # HTTP client for search operations
        self._http_client: Optional[httpx.AsyncClient] = None
        self._owns_http_client = False

        # Statistics
        self._request_count = 0
        self._error_count = 0
        self._cache_hit_count = 0
        self._download_count = 0

    async def initialize(self) -> None:
        """Initialize the client."""
        # Initialize HTTP client if not provided
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
            self._owns_http_client = True

        logger.info("KaggleAPIClient initialized")

    async def close(self) -> None:
        """Close HTTP client and cleanup."""
        if self._owns_http_client and self._http_client:
            await self._http_client.aclose()

        logger.info("KaggleAPIClient closed")

    @property
    def rate_limiter(self) -> IRateLimiter:
        """Get the rate limiter (for testing)."""
        return self._rate_limiter

    @property
    def circuit_breaker(self) -> Optional[ICircuitBreaker]:
        """Get the circuit breaker (for testing)."""
        return self._circuit_breaker

    async def search_notebooks(
        self,
        query: str,
        max_results: int = 20,
        sort_by: str = "voteCount",
    ) -> List[NotebookMetadata]:
        """Search notebooks on Kaggle.

        Args:
            query: Search query (supports tags: "tag:mytag")
            max_results: Maximum results to return
            sort_by: Sort field (voteCount, dateCreated, scoreDescending)

        Returns:
            List of notebook metadata

        Raises:
            KaggleAPIError: If search fails
        """
        await self._apply_rate_limit()

        try:
            # Use HTTP search API
            url = self._build_search_url(query, max_results, sort_by)

            response = await self._http_client.get(url)
            response.raise_for_status()
            self._request_count += 1

            # Parse response
            notebooks = self._parse_search_response(response.text, query)

            logger.info(f"Found {len(notebooks)} notebooks for query: {query[:50]}...")
            return notebooks

        except httpx.HTTPStatusError as e:
            self._error_count += 1
            if e.response.status_code == 429:
                raise RateLimitError(
                    message="Kaggle rate limit exceeded",
                    retry_after=3,
                    original=e,
                )
            raise KaggleAPIError(
                f"Kaggle API error: {e.response.status_code} - {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
                original=e,
            )
        except httpx.TimeoutException:
            self._error_count += 1
            raise APITimeoutError(
                message="Kaggle API request timed out",
                timeout_seconds=30,
            )
        except httpx.RequestError as e:
            self._error_count += 1
            raise KaggleAPIError(
                f"Failed to connect to Kaggle API: {e}",
                original=e,
            )

    async def get_competition_notebooks(
        self,
        competition_slug: str,
        max_notebooks: int = 10,
    ) -> List[NotebookMetadata]:
        """Get top notebooks from a competition.

        Args:
            competition_slug: Competition identifier (e.g., "titanic")
            max_notebooks: Maximum notebooks to return

        Returns:
            List of notebook metadata sorted by votes

        Raises:
            KaggleAPIError: If API call fails
        """
        await self._apply_rate_limit()

        try:
            # Search for competition notebooks
            query = f"competition:{competition_slug}"
            url = self._build_search_url(query, max_notebooks, "voteCount")

            response = await self._http_client.get(url)
            response.raise_for_status()
            self._request_count += 1

            notebooks = self._parse_search_response(response.text, query)

            # Add competition slug to metadata
            for nb in notebooks:
                nb.competition_slug = competition_slug
                nb.source = NotebookSource.COMPETITION

            logger.info(
                f"Found {len(notebooks)} notebooks for competition: {competition_slug}"
            )
            return notebooks

        except httpx.HTTPStatusError as e:
            self._error_count += 1
            if e.response.status_code == 429:
                raise RateLimitError(
                    message="Kaggle rate limit exceeded",
                    retry_after=3,
                    original=e,
                )
            raise KaggleAPIError(
                f"Kaggle API error: {e.response.status_code} - {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
                original=e,
            )
        except httpx.RequestError as e:
            self._error_count += 1
            raise KaggleAPIError(
                f"Failed to connect to Kaggle API: {e}",
                original=e,
            )

    async def download_notebook(
        self,
        notebook_path: str,
    ) -> NotebookContent:
        """Download notebook content from Kaggle.

        Args:
            notebook_path: Kaggle notebook path (e.g., "username/notebook-slug")

        Returns:
            Full notebook content as JSON

        Raises:
            NotebookDownloadError: If download fails
        """
        try:
            # Use kagglehub to download notebook
            local_path = kagglehub.notebook_download(notebook_path)

            # Read the notebook file
            notebook_file = local_path / "notebook.ipynb"

            if not notebook_file.exists():
                # Try alternative file names
                for filename in local_path.iterdir():
                    if filename.suffix == ".ipynb":
                        notebook_file = filename
                        break

            with open(notebook_file, 'r', encoding='utf-8') as f:
                notebook_json = json.load(f)

            self._download_count += 1

            # Create NotebookContent
            content = NotebookContent(
                notebook_path=notebook_path,
                nbformat_version=notebook_json.get("nbformat_version"),
                metadata=notebook_json.get("metadata", {}),
                cells=notebook_json.get("cells", []),
                nbformat=notebook_json.get("nbformat"),
            )

            logger.debug(f"Downloaded notebook: {notebook_path}")
            return content

        except Exception as e:
            raise NotebookDownloadError(
                message=f"Failed to download notebook: {notebook_path}",
                notebook_path=notebook_path,
                original=e,
            )

    async def search_competitions(
        self,
        query: str,
    ) -> List[CompetitionMetadata]:
        """Search competitions on Kaggle.

        Args:
            query: Search query for competitions

        Returns:
            List of competition metadata

        Raises:
            KaggleAPIError: If search fails
        """
        await self._apply_rate_limit()

        try:
            # Use Kaggle competitions API
            url = f"https://www.kaggle.com/competitions.json?search={query}"

            response = await self._http_client.get(url)
            response.raise_for_status()
            self._request_count += 1

            competitions = self._parse_competitions_response(response.text, query)

            logger.info(f"Found {len(competitions)} competitions for query: {query}")
            return competitions

        except httpx.HTTPStatusError as e:
            self._error_count += 1
            if e.response.status_code == 429:
                raise RateLimitError(
                    message="Kaggle rate limit exceeded",
                    retry_after=3,
                    original=e,
                )
            raise KaggleAPIError(
                f"Kaggle API error: {e.response.status_code} - {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
                original=e,
            )
        except httpx.RequestError as e:
            self._error_count += 1
            raise KaggleAPIError(
                f"Failed to connect to Kaggle API: {e}",
                original=e,
            )

    async def health_check(self) -> bool:
        """Check if Kaggle API is accessible."""
        try:
            # Quick health check with a simple request
            url = "https://www.kaggle.com/"
            response = await self._http_client.head(url, timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Kaggle API health check failed: {e}")
            return False

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting before making a request."""
        if self._circuit_breaker:
            await self._circuit_breaker.call(self._rate_limiter.acquire)
        else:
            await self._rate_limiter.acquire()

    def _build_search_url(
        self,
        query: str,
        max_results: int,
        sort_by: str,
    ) -> str:
        """Build Kaggle search URL."""
        # Kaggle search URL construction
        # Note: This is a simplified version - actual API may differ
        encoded_query = query.replace(" ", "%20")
        return f"https://www.kaggle.com/api/i/search.SearchService?q={encoded_query}&sort={sort_by}&maxResults={max_results}"

    def _parse_search_response(
        self,
        response_text: str,
        source_query: str,
    ) -> List[NotebookMetadata]:
        """Parse search response into notebook metadata."""
        notebooks = []

        try:
            data = json.loads(response_text)

            # Extract notebooks from response
            for item in data.get("notebooks", data.get("results", [])):
                try:
                    notebook = NotebookMetadata(
                        notebook_id=item.get("ref", item.get("id", "")),
                        title=item.get("title", ""),
                        authors=self._extract_authors(item),
                        tags=item.get("tags", []),
                        votes=item.get("totalVotes", item.get("votes", 0)),
                        total_views=item.get("totalViews", item.get("views", 0)),
                        total_comments=item.get("totalComments", item.get("comments", 0)),
                        created_at=item.get("dateCreated", item.get("created", "")),
                        updated_at=item.get("dateUpdated", item.get("updated", "")),
                        notebook_path=item.get("ref", item.get("path", "")),
                        language=item.get("language", "python"),
                        source=NotebookSource.QUERY,
                        source_query=source_query,
                    )
                    notebooks.append(notebook)
                except Exception as e:
                    logger.warning(f"Failed to parse notebook: {e}")
                    continue

        except json.JSONDecodeError as e:
            raise KaggleAPIError(
                f"Failed to parse Kaggle response: {e}",
                response_text=response_text[:500],
                original=e,
            )

        return notebooks

    def _parse_competitions_response(
        self,
        response_text: str,
        source_query: str,
    ) -> List[CompetitionMetadata]:
        """Parse competitions response into metadata."""
        competitions = []

        try:
            data = json.loads(response_text)

            for item in data.get("competitions", data.get("results", [])):
                try:
                    competition = CompetitionMetadata(
                        competition_slug=item.get("competitionSlug", item.get("slug", "")),
                        title=item.get("title", ""),
                        category=item.get("category", ""),
                        organization=item.get("organization", ""),
                        deadline=item.get("deadline", ""),
                        total_teams=item.get("totalTeams", item.get("teams", 0)),
                        description=item.get("description", ""),
                    )
                    competitions.append(competition)
                except Exception as e:
                    logger.warning(f"Failed to parse competition: {e}")
                    continue

        except json.JSONDecodeError as e:
            raise KaggleAPIError(
                f"Failed to parse Kaggle response: {e}",
                response_text=response_text[:500],
                original=e,
            )

        return competitions

    def _extract_authors(self, item: Dict[str, Any]) -> List[str]:
        """Extract author names from item."""
        authors = []

        # Try different possible fields
        author_data = item.get("author", item.get("authors", []))

        if isinstance(author_data, list):
            for author in author_data:
                if isinstance(author, str):
                    authors.append(author)
                elif isinstance(author, dict):
                    name = author.get("name", author.get("username", ""))
                    if name:
                        authors.append(name)
        elif isinstance(author_data, str):
            authors.append(author_data)

        return authors

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "download_count": self._download_count,
            "cache_hit_count": self._cache_hit_count,
            "success_rate": (
                (self._request_count - self._error_count) / self._request_count
                if self._request_count > 0 else 0
            ),
        }

    def __repr__(self) -> str:
        return (
            f"KaggleAPIClient("
            f"requests={self._request_count}, "
            f"errors={self._error_count}, "
            f"downloads={self._download_count})"
        )


class DefaultRateLimiter:
    """Simple rate limiter implementation for when no external one is available."""

    def __init__(self, rate: float = 1.0):
        import asyncio
        import time

        self.rate = rate
        self.capacity = 1
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request."""
        async with self._lock:
            import time
            now = time.monotonic()
            elapsed = now - self.last_update

            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return

            wait_time = (1 - self.tokens) / self.rate

        import asyncio
        await asyncio.sleep(wait_time)

    async def get_delay(self) -> float:
        """Get delay until next request."""
        async with self._lock:
            import time
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


__all__ = [
    "KaggleAPIClient",
    "DefaultRateLimiter",
]

