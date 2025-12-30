"""HuggingFace API client implementation.

Design Principles (from code-quality.mdc):
- Dependency Inversion: Implements IHuggingFaceAPI, not coupled to HfApi
- State Management: Mutable statistics separated from immutable config
- Graceful Degradation: Retry with exponential backoff for transient failures
- Observability: Structured logging, metrics, tracing at boundaries
- Error Handling: Clear domain exceptions with context
"""
import asyncio
import logging
import os
import time
import uuid
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime

import tenacity
from huggingface_hub import HfApi, ModelCard
from huggingface_hub.utils import HfHubHTTPError

from ..config import HFetcherConfig
from ..exceptions import (
    APIError,
    RateLimitError,
    ModelNotFoundError,
)
from ..interfaces import IHuggingFaceAPI
from ..schemas.model import ModelMetadata


logger = logging.getLogger(__name__)


@dataclass
class APIStats:
    """Mutable statistics for the API client.
    
    Separated from immutable configuration to enable
    thread-safe updates and clear state management.
    """
    request_count: int = 0
    error_count: int = 0
    cache_hit_count: int = 0
    last_request_at: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.request_count + self.error_count
        return self.request_count / total if total > 0 else 0.0


class HuggingFaceAPIClient(IHuggingFaceAPI):
    """Async API client for HuggingFace Hub.
    
    Responsibilities:
    - Wrap huggingface_hub with async interface
    - Implement retry logic with exponential backoff
    - Translate errors to domain exceptions
    - Emit observability data (logs, metrics)
    
    Immutable Dependencies:
    - config: Configuration (frozen)
    - token: HuggingFace API token
    
    Mutable State:
    - _api: HfApi instance (lazy initialized)
    - _initialized: Initialization flag
    - stats: Request/error statistics
    """
    
    def __init__(
        self,
        config: Optional[HFetcherConfig] = None,
        token: Optional[str] = None,
    ):
        """Initialize the HuggingFace API client.
        
        Args:
            config: Configuration (injected, frozen)
            token: HuggingFace API token (injected or from environment)
        """
        self._config = config or HFetcherConfig()
        self._token = token or os.getenv("HF_TOKEN")
        self._api: Optional[HfApi] = None
        self._initialized: bool = False
        self._stats = APIStats()
    
    async def initialize(self) -> None:
        """Initialize the API client.
        
        Side effects:
        - Creates HfApi instance
        - Logs initialization
        """
        if self._initialized:
            return
        
        # Run sync initialization in thread pool
        loop = asyncio.get_event_loop()
        self._api = await loop.run_in_executor(
            None,
            lambda: HfApi(token=self._token)
        )
        
        self._initialized = True
        logger.info(
            "HuggingFaceAPIClient initialized",
            extra={"event": "api_client_init"}
        )
    
    def _ensure_initialized(self) -> None:
        """Ensure the client is initialized.
        
        Raises:
            APIError: If client not initialized
        """
        if not self._initialized:
            raise APIError(
                message="HuggingFaceAPIClient not initialized. Call initialize() first.",
                query=None,
            )
    
    def _translate_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> Exception:
        """Translate huggingface_hub errors to domain exceptions.
        
        Preserves original exception for debugging while providing
        domain-specific error type for callers.
        
        Args:
            error: Original exception
            context: Additional context (model_id, query, etc.)
            
        Returns:
            Domain-specific exception
        """
        if isinstance(error, HfHubHTTPError):
            status_code = getattr(error, "status_code", None)
            
            if status_code == 429:
                retry_after = None
                if hasattr(error, "headers"):
                    retry_after = error.headers.get("Retry-After")
                return RateLimitError(
                    message=f"Rate limit exceeded: {error}",
                    retry_after=retry_after,
                    original=error,
                )
            elif status_code == 404:
                model_id = context.get("model_id") if context else None
                return ModelNotFoundError(
                    model_id=model_id or "unknown",
                    original=error,
                )
            else:
                return APIError(
                    message=f"HuggingFace API error (status={status_code}): {error}",
                    status_code=status_code,
                    query=context.get("query") if context else None,
                    original=error,
                )
        elif isinstance(error, tenacity.RetryError):
            return APIError(
                message=f"Max retries exceeded after exponential backoff",
                query=context.get("query") if context else None,
                original=error,
            )
        else:
            return APIError(
                message=f"Unexpected error during API call: {error}",
                query=context.get("query") if context else None,
                original=error,
            )
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(
            (HfHubHTTPError, ConnectionError, TimeoutError)
        ),
        before_sleep=lambda rs: logger.warning(
            f"Retrying HuggingFace API call (attempt {rs.attempt_number}/3)",
            extra={
                "event": "api_retry",
                "attempt": rs.attempt_number,
                "exception": str(rs.outcome.exception()),
            }
        ),
        after=lambda rs: logger.info(
            f"Retry successful after {rs.attempt_number} attempts",
            extra={
                "event": "api_retry_success",
                "attempts": rs.attempt_number,
            }
        ) if rs.outcome.exception() is None else None,
    )
    async def search_models(
        self,
        query: str,
        task: Optional[str] = None,
        max_results: int = 20,
        sort_by: str = "downloads",
    ) -> List[ModelMetadata]:
        """Search for models matching query.
        
        This method:
        1. Ensures client is initialized
        2. Executes API call in thread pool
        3. Translates errors to domain exceptions
        4. Converts API response to domain models
        
        Args:
            query: Search query string
            task: Optional task filter (e.g., 'time-series-forecasting')
            max_results: Maximum results to return (default 20)
            sort_by: Sort field - 'downloads', 'likes', or 'lastModified'
            
        Returns:
            List of ModelMetadata matching query
            
        Raises:
            APIError: If API request fails (after retries)
            RateLimitError: If rate limit is exceeded
        """
        self._ensure_initialized()
        
        logger.debug(
            f"Searching HuggingFace for: query='{query}', task={task}",
            extra={
                "event": "api_search",
                "query": query,
                "task": task,
                "max_results": max_results,
            }
        )
        
        start_time = time.perf_counter()
        context = {"query": query, "task": task}
        
        try:
            # Run sync API call in thread pool
            loop = asyncio.get_event_loop()
            
            filters = [task] if task else None
            
            models = await loop.run_in_executor(
                None,
                lambda: list(
                    self._api.list_models(
                        search=query,
                        filter=filters,
                        sort=sort_by,
                        direction=-1,  # Descending
                        limit=max_results,
                    )
                )
            )
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._stats.request_count += 1
            self._stats.last_request_at = datetime.utcnow()
            
            # Convert to domain models
            result = []
            for m in models:
                metadata = self._convert_to_model_metadata(m, query, task)
                if metadata:
                    result.append(metadata)
            
            logger.info(
                f"Found {len(result)} models for query: {query}",
                extra={
                    "event": "api_search_success",
                    "query": query,
                    "result_count": len(result),
                    "latency_ms": round(elapsed_ms, 2),
                }
            )
            
            return result
            
        except Exception as e:
            self._stats.error_count += 1
            error = self._translate_error(e, context)
            
            logger.error(
                f"Search failed for '{query}': {error}",
                extra={
                    "event": "api_search_error",
                    "query": query,
                    "error": str(error),
                }
            )
            
            raise error
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(
            (HfHubHTTPError, ConnectionError, TimeoutError)
        ),
    )
    async def get_model_info(
        self,
        model_id: str,
    ) -> ModelMetadata:
        """Get detailed metadata for a specific model.
        
        Args:
            model_id: HuggingFace model ID (org/model-name)
            
        Returns:
            ModelMetadata
            
        Raises:
            APIError: If API request fails
            ModelNotFoundError: If model doesn't exist
        """
        self._ensure_initialized()
        
        logger.debug(
            f"Getting model info: {model_id}",
            extra={
                "event": "api_model_info",
                "model_id": model_id,
            }
        )
        
        start_time = time.perf_counter()
        context = {"model_id": model_id}
        
        try:
            loop = asyncio.get_event_loop()
            
            model_info = await loop.run_in_executor(
                None,
                lambda: self._api.model_info(
                    repo_id=model_id,
                    files_metadata=False,
                )
            )
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._stats.request_count += 1
            self._stats.last_request_at = datetime.utcnow()
            
            # Extract arxiv IDs from tags
            tags = list(getattr(model_info, "tags", []) or [])
            arxiv_ids = [
                tag.replace("arxiv:", "")
                for tag in tags
                if tag.startswith("arxiv:")
            ]
            
            # Get card data if available
            card_data = getattr(model_info, "card_data", None)
            license = getattr(card_data, "license", None) if card_data else None
            library_name = getattr(card_data, "library_name", None) if card_data else None
            
            metadata = ModelMetadata(
                model_id=model_info.id,
                name=model_info.id.split("/")[-1] if "/" in model_info.id else model_info.id,
                downloads=getattr(model_info, "downloads", 0) or 0,
                likes=getattr(model_info, "likes", 0) or 0,
                tags=tags,
                pipeline_tag=getattr(model_info, "pipeline_tag", None),
                license=license,
                library_name=library_name,
                language=getattr(model_info, "language", []) or [],
                created_at=str(getattr(model_info, "created_at", None) or ""),
                last_modified=str(getattr(model_info, "last_modified", None) or ""),
                url=f"https://huggingface.co/{model_id}",
                revision=getattr(model_info, "sha", None),
                siblings=[s.rfilename for s in getattr(model_info, "siblings", []) or []],
                arxiv_ids=arxiv_ids,
            )
            
            logger.debug(
                f"Retrieved model info: {model_id}",
                extra={
                    "event": "api_model_info_success",
                    "model_id": model_id,
                    "downloads": metadata.downloads,
                    "latency_ms": round(elapsed_ms, 2),
                }
            )
            
            return metadata
            
        except Exception as e:
            self._stats.error_count += 1
            error = self._translate_error(e, context)
            
            logger.error(
                f"Failed to get model info for '{model_id}': {error}",
                extra={
                    "event": "api_model_info_error",
                    "model_id": model_id,
                    "error": str(error),
                }
            )
            
            raise error
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(
            (HfHubHTTPError, ConnectionError, TimeoutError)
        ),
    )
    async def get_model_card(
        self,
        model_id: str,
    ) -> str:
        """Fetch raw model card content.
        
        Args:
            model_id: HuggingFace model ID
            
        Returns:
            Raw markdown content of model card
            
        Raises:
            APIError: If API request fails
            ModelNotFoundError: If model doesn't exist
        """
        self._ensure_initialized()
        
        logger.debug(
            f"Fetching model card: {model_id}",
            extra={
                "event": "api_model_card",
                "model_id": model_id,
            }
        )
        
        start_time = time.perf_counter()
        context = {"model_id": model_id}
        
        try:
            loop = asyncio.get_event_loop()
            
            # ModelCard.load() returns a ModelCard object
            card = await loop.run_in_executor(
                None,
                lambda: ModelCard.load(model_id)
            )
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._stats.request_count += 1
            self._stats.last_request_at = datetime.utcnow()
            
            content = card.text or ""
            
            logger.debug(
                f"Fetched model card: {model_id} ({len(content)} chars)",
                extra={
                    "event": "api_model_card_success",
                    "model_id": model_id,
                    "content_length": len(content),
                    "latency_ms": round(elapsed_ms, 2),
                }
            )
            
            return content
            
        except Exception as e:
            self._stats.error_count += 1
            error = self._translate_error(e, context)
            
            logger.error(
                f"Failed to fetch model card for '{model_id}': {error}",
                extra={
                    "event": "api_model_card_error",
                    "model_id": model_id,
                    "error": str(error),
                }
            )
            
            raise error
    
    def _convert_to_model_metadata(
        self,
        model: Any,
        query: str,
        task: Optional[str],
    ) -> Optional[ModelMetadata]:
        """Convert huggingface_hub model object to domain ModelMetadata.
        
        Pure data transformation - no side effects.
        
        Args:
            model: ModelInfo object from huggingface_hub
            query: Original search query
            task: Task filter applied
            
        Returns:
            ModelMetadata or None if conversion fails
        """
        try:
            # Extract arxiv IDs from tags
            tags = list(getattr(model, "tags", []) or [])
            arxiv_ids = [
                tag.replace("arxiv:", "")
                for tag in tags
                if tag.startswith("arxiv:")
            ]
            
            # Get card data if available
            card_data = getattr(model, "card_data", None)
            license = getattr(card_data, "license", None) if card_data else None
            library_name = getattr(card_data, "library_name", None) if card_data else None
            
            return ModelMetadata(
                model_id=model.id,
                name=model.id.split("/")[-1] if "/" in model.id else model.id,
                downloads=getattr(model, "downloads", 0) or 0,
                likes=getattr(model, "likes", 0) or 0,
                tags=tags,
                pipeline_tag=getattr(model, "pipeline_tag", None),
                license=license,
                library_name=library_name,
                language=getattr(model, "language", []) or [],
                created_at=str(getattr(model, "created_at", None) or ""),
                last_modified=str(getattr(model, "last_modified", None) or ""),
                url=f"https://huggingface.co/{model.id}",
                revision=getattr(model, "sha", None),
                siblings=[],
                arxiv_ids=arxiv_ids,
                source_query=query,
            )
            
        except Exception as e:
            logger.warning(
                f"Failed to convert model metadata: {e}",
                extra={
                    "event": "model_conversion_error",
                    "model_id": getattr(model, "id", "unknown"),
                    "error": str(e),
                }
            )
            return None
    
    async def health_check(self) -> bool:
        """Check if HuggingFace API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            self._ensure_initialized()
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._api.list_models(limit=1)
            )
            return True
            
        except Exception as e:
            logger.warning(
                f"HuggingFace API health check failed: {e}",
                extra={
                    "event": "health_check_failed",
                    "error": str(e),
                }
            )
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "request_count": self._stats.request_count,
            "error_count": self._stats.error_count,
            "success_rate": self._stats.success_rate,
            "last_request_at": (
                self._stats.last_request_at.isoformat()
                if self._stats.last_request_at else None
            ),
            "initialized": self._initialized,
        }
    
    async def close(self) -> None:
        """Clean up resources.
        
        Side effects:
        - Sets initialized to False
        - Clears API reference
        """
        self._initialized = False
        self._api = None
        logger.info(
            "HuggingFaceAPIClient closed",
            extra={"event": "api_client_close"}
        )
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"HuggingFaceAPIClient("
            f"requests={stats['request_count']}, "
            f"errors={stats['error_count']}, "
            f"success_rate={stats['success_rate']:.2%})"
        )

