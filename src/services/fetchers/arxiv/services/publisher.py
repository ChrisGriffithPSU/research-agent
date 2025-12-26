"""Message publisher for arXiv fetcher.

Integrates with existing MessagePublisher from src/shared/messaging/
Publishes to arxiv.discovered and arxiv.parse_request queues.
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.shared.messaging.publisher import MessagePublisher, get_publisher
from src.shared.messaging.schemas import BaseMessage
from src.shared.models.source import SourceType

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import PaperMetadata, ParsedContent
from src.services.fetchers.arxiv.schemas.messages import (
    ArxivDiscoveredMessage,
    ArxivParseRequestMessage,
    ArxivExtractedMessage,
)
from src.services.fetchers.arxiv.exceptions import MessagePublishingError


logger = logging.getLogger(__name__)


class ArxivMessagePublisher:
    """Publisher for arXiv paper messages.
    
    Uses existing MessagePublisher from src/shared/messaging/publisher.py
    Publishes to:
    - arxiv.discovered: Papers with metadata only
    - arxiv.parse_request: Parse requests from intelligence layer
    - content.extracted: Fully extracted paper content
    
    Attributes:
        publisher: Existing MessagePublisher instance
        config: ArXiv fetcher configuration
        discovered_queue: Queue for discovered papers
        parse_request_queue: Queue for parse requests
        extracted_queue: Queue for extracted content
    """
    
    def __init__(
        self,
        publisher: Optional[MessagePublisher] = None,
        config: Optional[ArxivFetcherConfig] = None,
    ):
        """Initialize message publisher.
        
        Args:
            publisher: Existing MessagePublisher instance
            config: ArXiv fetcher configuration
        """
        self.publisher = publisher
        self.config = config or ArxivFetcherConfig()
        self._initialized = False
        
        # Queue names from config
        self.discovered_queue = self.config.discovered_queue
        self.parse_request_queue = self.config.parse_request_queue
        self.extracted_queue = self.config.extracted_queue
        
        # Statistics
        self._published_count = 0
        self._error_count = 0
    
    async def initialize(self) -> None:
        """Initialize publisher connection."""
        if self._initialized:
            return
            
        if self.publisher is None:
            self.publisher = await get_publisher()
        
        self._initialized = True
        logger.info(
            f"ArxivMessagePublisher initialized, "
            f"queues: {self.discovered_queue}, {self.parse_request_queue}, {self.extracted_queue}"
        )
    
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
            
        Raises:
            MessagePublishingError: If publishing fails
        """
        if not self._initialized:
            await self.initialize()
        
        if not papers:
            return 0
        
        published = 0
        
        for paper in papers:
            try:
                message = self._build_discovered_message(paper, correlation_id)
                
                await self.publisher.publish(
                    message=message,
                    routing_key=self.discovered_queue,
                )
                
                published += 1
                self._published_count += 1
                
                logger.debug(f"Published discovered paper: {paper.paper_id}")
                
            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Failed to publish discovered paper {paper.paper_id}: {e}"
                )
                continue
        
        logger.info(
            f"Published {published}/{len(papers)} papers to {self.discovered_queue}"
        )
        return published
    
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
            
        Raises:
            MessagePublishingError: If publishing fails
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            message = ArxivParseRequestMessage(
                correlation_id=correlation_id,
                original_correlation_id=original_correlation_id,
                paper_id=paper_id,
                pdf_url=pdf_url,
                priority=priority,
                relevance_score=relevance_score,
                intelligence_notes=intelligence_notes,
            )
            
            await self.publisher.publish(
                message=message,
                routing_key=self.parse_request_queue,
            )
            
            logger.info(
                f"Published parse request for {paper_id} (priority: {priority})"
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to publish parse request for {paper_id}: {e}")
            raise MessagePublishingError(
                message=f"Failed to publish parse request: {e}",
                queue_name=self.parse_request_queue,
                message_type="parse_request",
                correlation_id=correlation_id,
                original=e,
            )
    
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
            
        Raises:
            MessagePublishingError: If publishing fails
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            message = ArxivExtractedMessage(
                correlation_id=parse_correlation_id,
                discovery_correlation_id=discovery_correlation_id,
                parse_correlation_id=parse_correlation_id,
                paper_id=paper.paper_id,
                version=paper.version,
                title=paper.title,
                arxiv_url=paper.arxiv_url,
                pdf_url=paper.pdf_url,
                authors=paper.authors,
                categories=paper.categories,
                subcategories=paper.subcategories,
                submitted_date=paper.submitted_date,
                doi=paper.doi,
                text_content=content.text_content,
                tables=content.tables,
                equations=content.equations,
                figure_captions=content.figure_captions,
                extraction_metadata=content.metadata,
            )
            
            await self.publisher.publish(
                message=message,
                routing_key=self.extracted_queue,
            )
            
            self._published_count += 1
            logger.info(f"Published extracted paper: {paper.paper_id}")
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to publish extracted paper {paper.paper_id}: {e}")
            raise MessagePublishingError(
                message=f"Failed to publish extracted content: {e}",
                queue_name=self.extracted_queue,
                message_type="extracted",
                correlation_id=parse_correlation_id,
                original=e,
            )
    
    async def publish_batch_discovered(
        self,
        papers: List[PaperMetadata],
        correlation_id: Optional[str] = None,
        batch_size: int = 10,
    ) -> int:
        """Publish papers in batches.
        
        Args:
            papers: List of paper metadata
            correlation_id: Optional correlation ID
            batch_size: Papers per batch
            
        Returns:
            Total papers published
        """
        total_published = 0
        
        for i in range(0, len(papers), batch_size):
            batch = papers[i:i + batch_size]
            batch_id = f"{correlation_id}_batch_{i//batch_size}" if correlation_id else None
            
            try:
                published = await self.publish_discovered(batch, batch_id)
                total_published += published
                
                # Small delay between batches to avoid overwhelming queue
                if i + batch_size < len(papers):
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Failed to publish batch {i//batch_size}: {e}")
                continue
        
        return total_published
    
    def _build_discovered_message(
        self,
        paper: PaperMetadata,
        correlation_id: Optional[str] = None,
    ) -> ArxivDiscoveredMessage:
        """Build discovered message from paper metadata.
        
        Args:
            paper: Paper metadata
            correlation_id: Optional correlation ID
            
        Returns:
            ArxivDiscoveredMessage
        """
        return ArxivDiscoveredMessage(
            correlation_id=correlation_id or paper.paper_id,
            paper_id=paper.paper_id,
            version=paper.version,
            title=paper.title,
            abstract=paper.abstract,
            authors=paper.authors,
            categories=paper.categories,
            subcategories=paper.subcategories,
            arxiv_url=paper.arxiv_url,
            pdf_url=paper.pdf_url,
            submitted_date=paper.submitted_date,
            updated_date=paper.updated_date,
            doi=paper.doi,
            journal_ref=paper.journal_ref,
            comments=paper.comments,
            source_query=paper.source_query,
        )
    
    async def health_check(self) -> bool:
        """Check if publisher is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._initialized or self.publisher is None:
            return False
        
        try:
            return await self.publisher.health_check()
        except Exception as e:
            logger.warning(f"Publisher health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close publisher connection."""
        self._initialized = False
        logger.info("ArxivMessagePublisher closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get publisher statistics.
        
        Returns:
            Dict with publishing stats
        """
        return {
            "published_count": self._published_count,
            "error_count": self._error_count,
            "success_rate": (
                self._published_count / (self._published_count + self._error_count)
                if (self._published_count + self._error_count) > 0 else 0
            ),
            "queues": {
                "discovered": self.discovered_queue,
                "parse_request": self.parse_request_queue,
                "extracted": self.extracted_queue,
            },
        }
    
    def __repr__(self) -> str:
        return (
            f"ArxivMessagePublisher("
            f"published={self._published_count}, "
            f"errors={self._error_count})"
        )

