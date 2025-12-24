"""Digest and digest item repositories."""
import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions import RepositoryNotFoundError
from src.shared.models.digest import Digest, DigestItem, DigestStatus
from src.shared.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DigestRepository(BaseRepository[Digest]):
    """Repository for digest operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Digest, session)

    async def get_by_date(
        self, user_id: int, digest_date: date
    ) -> Optional[Digest]:
        """Get digest by user and date.

        Args:
            user_id: User ID
            digest_date: Digest date

        Returns:
            Digest instance or None if not found
        """
        logger.debug(
            f"DigestRepository: Getting digest user_id={user_id}, date={digest_date}"
        )
        try:
            query = select(Digest).where(
                Digest.user_id == user_id,
                Digest.digest_date == digest_date,
            )
            result = await self.session.execute(query)
            digest = result.scalar_one_or_none()
            if digest:
                logger.debug(
                    f"DigestRepository: Found digest user_id={user_id}, date={digest_date}"
                )
            else:
                logger.debug(
                    f"DigestRepository: Digest not found user_id={user_id}, date={digest_date}"
                )
            return digest
        except Exception as e:
            logger.error(
                f"DigestRepository: Error getting digest user_id={user_id}, date={digest_date}: {e}"
            )
            raise

    async def get_by_date_or_create(
        self, user_id: int, digest_date: date
    ) -> Digest:
        """Get digest by user and date, or create if doesn't exist.

        Args:
            user_id: User ID
            digest_date: Digest date

        Returns:
            Digest instance (existing or newly created)
        """
        logger.debug(
            f"DigestRepository: Getting or creating digest user_id={user_id}, date={digest_date}"
        )
        digest = await self.get_by_date(user_id, digest_date)
        if digest is None:
            digest = await self.create(
                user_id=user_id,
                digest_date=digest_date,
                status=DigestStatus.PENDING,
            )
            logger.info(
                f"DigestRepository: Created digest user_id={user_id}, date={digest_date}"
            )
        return digest

    async def get_latest(
        self, user_id: int, limit: int = 10
    ) -> List[Digest]:
        """Get most recent digests for user.

        Args:
            user_id: User ID
            limit: Maximum number of results

        Returns:
            List of Digest instances (most recent first)
        """
        logger.debug(
            f"DigestRepository: Getting latest digests user_id={user_id}, limit={limit}"
        )
        try:
            # Eager load items to avoid N+1 queries
            query = (
                select(Digest)
                .where(Digest.user_id == user_id)
                .order_by(Digest.digest_date.desc())
                .options(selectinload(Digest.items))
                .limit(limit)
            )
            result = await self.session.execute(query)
            digests = list(result.scalars().all())
            logger.debug(f"DigestRepository: Found {len(digests)} digests")
            return digests
        except Exception as e:
            logger.error(
                f"DigestRepository: Error getting latest digests user_id={user_id}: {e}"
            )
            raise

    async def list_by_status(
        self,
        status: DigestStatus,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Digest]:
        """List digests by status.

        Args:
            status: Digest status
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Digest instances
        """
        logger.debug(f"DigestRepository: Listing by status={status}")
        return await self.list_by_field("status", status, limit=limit)

    async def update_status(
        self, digest_id: int, status: DigestStatus
    ) -> Digest:
        """Update digest status.

        Args:
            digest_id: Digest ID
            status: New status

        Returns:
            Updated Digest instance
        """
        logger.debug(f"DigestRepository: Updating status for id={digest_id} to {status}")
        digest = await self.update(digest_id, status=status)

        if status == DigestStatus.DELIVERED:
            # Set delivered_at timestamp
            digest.delivered_at = datetime.now()
            await self.session.flush()

        return digest

    async def mark_delivered(self, digest_id: int) -> Digest:
        """Mark digest as delivered with timestamp.

        Args:
            digest_id: Digest ID

        Returns:
            Updated Digest instance
        """
        logger.debug(f"DigestRepository: Marking digest id={digest_id} as delivered")
        return await self.update_status(digest_id, DigestStatus.DELIVERED)


class DigestItemRepository(BaseRepository[DigestItem]):
    """Repository for digest item operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(DigestItem, session)

    async def list_by_digest(
        self, digest_id: int, limit: Optional[int] = None
    ) -> List[DigestItem]:
        """List items in a digest, ordered by rank.

        Args:
            digest_id: Digest ID
            limit: Maximum number of results

        Returns:
            List of DigestItem instances (ranked)
        """
        logger.debug(
            f"DigestItemRepository: Listing items for digest_id={digest_id}"
        )
        try:
            # Eager load source to avoid N+1 queries
            query = (
                select(DigestItem)
                .where(DigestItem.digest_id == digest_id)
                .order_by(DigestItem.rank)
                .options(selectinload(DigestItem.source))
                .limit(limit)
            )
            result = await self.session.execute(query)
            items = list(result.scalars().all())
            logger.debug(
                f"DigestItemRepository: Found {len(items)} items for digest_id={digest_id}"
            )
            return items
        except Exception as e:
            logger.error(
                f"DigestItemRepository: Error listing items for digest_id={digest_id}: {e}"
            )
            raise

    async def list_by_source(
        self, source_id: int, limit: Optional[int] = None
    ) -> List[DigestItem]:
        """List digest items that reference a source.

        Args:
            source_id: Source ID
            limit: Maximum number of results

        Returns:
            List of DigestItem instances
        """
        logger.debug(
            f"DigestItemRepository: Listing items for source_id={source_id}"
        )
        return await self.list_by_field("source_id", source_id, limit=limit)

    async def list_by_tags(
        self, tags: List[str], limit: Optional[int] = None
    ) -> List[DigestItem]:
        """List items with any of the given tags.

        Args:
            tags: List of tags to filter by
            limit: Maximum number of results

        Returns:
            List of DigestItem instances matching any tag
        """
        logger.debug(f"DigestItemRepository: Listing items with tags={tags}")
        try:
            # Use PostgreSQL array overlap operator (&&)
            query = (
                select(DigestItem)
                .where(DigestItem.tags.overlap(tags))
                .order_by(DigestItem.created_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            items = list(result.scalars().all())
            logger.debug(
                f"DigestItemRepository: Found {len(items)} items with tags={tags}"
            )
            return items
        except Exception as e:
            logger.error(f"DigestItemRepository: Error listing by tags={tags}: {e}")
            raise

    async def update_rank(
        self, item_id: int, rank: int
    ) -> DigestItem:
        """Update item rank within digest.

        Args:
            item_id: DigestItem ID
            rank: New rank position

        Returns:
            Updated DigestItem instance
        """
        logger.debug(f"DigestItemRepository: Updating rank for id={item_id} to {rank}")
        return await self.update(item_id, rank=rank)

    async def list_by_relevance(
        self,
        min_score: float = 0.0,
        max_score: float = 1.0,
        limit: Optional[int] = None,
    ) -> List[DigestItem]:
        """List items by relevance score range.

        Args:
            min_score: Minimum relevance score
            max_score: Maximum relevance score
            limit: Maximum number of results

        Returns:
            List of DigestItem instances
        """
        logger.debug(
            f"DigestItemRepository: Listing by relevance score {min_score}-{max_score}"
        )
        try:
            from sqlalchemy import and_

            query = (
                select(DigestItem)
                .where(
                    and_(
                        DigestItem.relevance_score >= min_score,
                        DigestItem.relevance_score <= max_score,
                    )
                )
                .order_by(DigestItem.relevance_score.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            items = list(result.scalars().all())
            logger.debug(
                f"DigestItemRepository: Found {len(items)} items in relevance range"
            )
            return items
        except Exception as e:
            logger.error(
                f"DigestItemRepository: Error listing by relevance: {e}"
            )
            raise

