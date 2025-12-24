"""Feedback repository."""
import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions import RepositoryNotFoundError
from src.shared.models.feedback import Feedback
from src.shared.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FeedbackRepository(BaseRepository[Feedback]):
    """Repository for feedback operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Feedback, session)

    async def get_for_item(self, digest_item_id: int) -> Optional[Feedback]:
        """Get feedback for a specific digest item.

        Args:
            digest_item_id: DigestItem ID

        Returns:
            Feedback instance or None if not found
        """
        logger.debug(
            f"FeedbackRepository: Getting feedback for digest_item_id={digest_item_id}"
        )
        try:
            query = select(Feedback).where(
                Feedback.digest_item_id == digest_item_id
            )
            result = await self.session.execute(query)
            feedback = result.scalar_one_or_none()
            if feedback:
                logger.debug(
                    f"FeedbackRepository: Found feedback for digest_item_id={digest_item_id}"
                )
            else:
                logger.debug(
                    f"FeedbackRepository: No feedback for digest_item_id={digest_item_id}"
                )
            return feedback
        except Exception as e:
            logger.error(
                f"FeedbackRepository: Error getting feedback for digest_item_id={digest_item_id}: {e}"
            )
            raise

    async def list_by_rating(
        self, rating: int, limit: Optional[int] = None
    ) -> List[Feedback]:
        """List feedback by rating.

        Args:
            rating: Rating value (-1 to 5)
            limit: Maximum number of results

        Returns:
            List of Feedback instances
        """
        logger.debug(f"FeedbackRepository: Listing by rating={rating}")
        return await self.list_by_field("rating", rating, limit=limit)

    async def get_aggregated_stats(self) -> dict:
        """Get aggregated feedback statistics.

        Returns:
            Dict with stats:
            - count: Total feedback count
            - avg_rating: Average rating
            - rating_distribution: Count per rating (-1, 1, 2, 3, 4, 5)
            - implemented_count: Number of implemented items
            - avg_time_spent: Average time spent reading (seconds)
        """
        logger.debug("FeedbackRepository: Getting aggregated stats")
        try:
            query = select(
                func.count(Feedback.id).label("count"),
                func.avg(Feedback.rating).label("avg_rating"),
                func.count(
                    func.case(
                        (Feedback.clicked_through == True, Feedback.id)
                    )
                ).label("implemented_count"),
                func.avg(Feedback.time_spent).label("avg_time_spent"),
            )
            result = await self.session.execute(query)
            row = result.one()

            stats = {
                "count": row.count or 0,
                "avg_rating": float(row.avg_rating) if row.avg_rating else 0.0,
                "implemented_count": row.implemented_count or 0,
                "avg_time_spent": float(row.avg_time_spent)
                if row.avg_time_spent
                else 0.0,
            }

            # Get rating distribution
            for rating_value in [-1, 1, 2, 3, 4, 5]:
                count_query = select(func.count(Feedback.id)).where(
                    Feedback.rating == rating_value
                )
                count_result = await self.session.execute(count_query)
                stats[f"rating_{rating_value}"] = count_result.scalar() or 0

            logger.debug(f"FeedbackRepository: Stats={stats}")
            return stats
        except Exception as e:
            logger.error(f"FeedbackRepository: Error getting aggregated stats: {e}")
            raise

    async def list_recent(
        self, limit: int = 100
    ) -> List[Feedback]:
        """List most recent feedback.

        Args:
            limit: Maximum number of results

        Returns:
            List of Feedback instances (most recent first)
        """
        logger.debug(f"FeedbackRepository: Listing recent feedback limit={limit}")
        try:
            query = (
                select(Feedback)
                .order_by(Feedback.created_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            feedback = list(result.scalars().all())
            logger.debug(f"FeedbackRepository: Found {len(feedback)} recent feedback")
            return feedback
        except Exception as e:
            logger.error(f"FeedbackRepository: Error listing recent feedback: {e}")
            raise

    async def update_notes(
        self, feedback_id: int, notes: str
    ) -> Feedback:
        """Update feedback notes.

        Args:
            feedback_id: Feedback ID
            notes: New notes text

        Returns:
            Updated Feedback instance
        """
        logger.debug(f"FeedbackRepository: Updating notes for id={feedback_id}")
        return await self.update(feedback_id, notes=notes)

    async def list_implemented(
        self, limit: Optional[int] = None
    ) -> List[Feedback]:
        """List feedback for implemented items.

        Args:
            limit: Maximum number of results

        Returns:
            List of Feedback instances where clicked_through=True
        """
        logger.debug("FeedbackRepository: Listing implemented items")
        return await self.list_by_field("clicked_through", True, limit=limit)

