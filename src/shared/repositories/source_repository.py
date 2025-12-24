"""Source content repository with vector search capabilities."""
import logging
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models.source import ProcessingStatus, Source, SourceType
from src.shared.repositories.base import BaseRepository, VectorSearchMixin

logger = logging.getLogger(__name__)


class SourceRepository(BaseRepository[Source], VectorSearchMixin[Source]):
    """Repository for source content operations with vector search."""

    def __init__(self, session: AsyncSession):
        BaseRepository.__init__(self, Source, session)
        VectorSearchMixin.__init__(self, Source, session)

    async def get_by_url(self, url: str) -> Optional[Source]:
        """Get source by URL (exact match).

        Args:
            url: Source URL

        Returns:
            Source instance or None if not found
        """
        logger.debug(f"SourceRepository: Getting source by url={url}")
        try:
            query = select(Source).where(Source.url == url)
            result = await self.session.execute(query)
            source = result.scalar_one_or_none()
            if source:
                logger.debug(f"SourceRepository: Found source url={url}")
            else:
                logger.debug(f"SourceRepository: Source not found url={url}")
            return source
        except Exception as e:
            logger.error(f"SourceRepository: Error getting source url={url}: {e}")
            raise

    async def is_duplicate_url(self, url: str) -> bool:
        """Check if source with URL already exists.

        Args:
            url: Source URL to check

        Returns:
            True if duplicate, False otherwise
        """
        logger.debug(f"SourceRepository: Checking duplicate url={url}")
        existing = await self.get_by_url(url)
        is_dup = existing is not None
        logger.debug(f"SourceRepository: URL duplicate={is_dup} for url={url}")
        return is_dup

    async def is_duplicate_hybrid(
        self, url: str, embedding: List[float], threshold: float = 0.85
    ) -> Tuple[bool, str]:
        """Check for duplicate using URL and semantic similarity.

        Args:
            url: Source URL
            embedding: Content embedding (1536 dimensions)
            threshold: Similarity threshold (0-1)

        Returns:
            (is_duplicate, duplicate_type)
            duplicate_type: "exact_url" or "semantic_similarity" or None
        """
        logger.debug(
            f"SourceRepository: Hybrid duplicate check url={url}, threshold={threshold}"
        )

        # Fast path: exact URL match
        if await self.is_duplicate_url(url):
            logger.info(f"SourceRepository: Exact URL duplicate for url={url}")
            return True, "exact_url"

        # Slow path: semantic similarity
        similar = await self.find_similar(embedding, threshold=threshold, limit=1)
        if similar:
            logger.info(
                f"SourceRepository: Semantic similarity duplicate for url={url}"
            )
            return True, "semantic_similarity"

        logger.debug(f"SourceRepository: No duplicate found for url={url}")
        return False, None

    async def list_by_type(
        self,
        source_type: SourceType,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Source]:
        """List sources by type with pagination.

        Args:
            source_type: Source type (arxiv, kaggle, etc.)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Source instances
        """
        logger.debug(f"SourceRepository: Listing by type={source_type}")
        return await self.list_by_field(
            "source_type", source_type, limit=limit
        )

    async def list_by_status(
        self,
        status: ProcessingStatus,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Source]:
        """List sources by processing status.

        Args:
            status: Processing status
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Source instances
        """
        logger.debug(f"SourceRepository: Listing by status={status}")
        return await self.list_by_field("status", status, limit=limit)

    async def list_processed(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Source]:
        """List fully processed sources (status=PROCESSED).

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Source instances with extracted_data
        """
        logger.debug("SourceRepository: Listing processed sources")
        try:
            query = (
                select(Source)
                .where(Source.status == ProcessingStatus.PROCESSED)
                .where(Source.extracted_data.is_not(None))
            )
            if limit is not None:
                query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)
            result = await self.session.execute(query)
            sources = list(result.scalars().all())
            logger.debug(f"SourceRepository: Found {len(sources)} processed sources")
            return sources
        except Exception as e:
            logger.error(f"SourceRepository: Error listing processed sources: {e}")
            raise

    async def update_status(
        self, source_id: int, status: ProcessingStatus
    ) -> Source:
        """Update source processing status.

        Args:
            source_id: Source ID
            status: New status

        Returns:
            Updated Source instance
        """
        logger.debug(f"SourceRepository: Updating status for id={source_id} to {status}")
        return await self.update(source_id, status=status)

    async def update_extracted_data(
        self, source_id: int, extracted_data: dict
    ) -> Source:
        """Update source with extracted data.

        Args:
            source_id: Source ID
            extracted_data: Extracted insights and metadata

        Returns:
            Updated Source instance
        """
        logger.debug(f"SourceRepository: Updating extracted_data for id={source_id}")
        return await self.update(source_id, extracted_data=extracted_data)

    async def update_embedding(
        self, source_id: int, embedding: List[float]
    ) -> Source:
        """Update source with embedding.

        Args:
            source_id: Source ID
            embedding: Vector embedding (1536 dimensions)

        Returns:
            Updated Source instance
        """
        logger.debug(f"SourceRepository: Updating embedding for id={source_id}")
        return await self.update(source_id, embedding=embedding)

    async def list_with_embeddings(
        self, limit: Optional[int] = None
    ) -> List[Source]:
        """List sources that have embeddings.

        Args:
            limit: Maximum number of results

        Returns:
            List of Source instances with embeddings
        """
        logger.debug("SourceRepository: Listing sources with embeddings")
        try:
            query = select(Source).where(Source.embedding.is_not(None))
            if limit is not None:
                query = query.limit(limit)
            result = await self.session.execute(query)
            sources = list(result.scalars().all())
            logger.debug(
                f"SourceRepository: Found {len(sources)} sources with embeddings"
            )
            return sources
        except Exception as e:
            logger.error(
                f"SourceRepository: Error listing sources with embeddings: {e}"
            )
            raise

