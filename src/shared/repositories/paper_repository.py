"""Paper repository for tracking processed papers.

Simple repository for duplicate detection and paper tracking.
"""

from typing import Optional
from sqlalchemy import Column, String, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from src.shared.models.base import Base


class PaperModel(Base):
    """Database model for tracking papers."""

    __tablename__ = "papers"

    paper_id = Column(String, primary_key=True)
    status = Column(
        String, default="discovered"
    )  # discovered, triaged, rejected, concepts_extracted
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PaperRepository:
    """Repository for paper operations.

    Provides methods for tracking papers and detecting duplicates.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository.

        Args:
            session: Database session
        """
        self.session = session

    async def exists(self, paper_id: str) -> bool:
        """Check if paper exists.

        Args:
            paper_id: ArXiv paper ID

        Returns:
            True if paper exists in database
        """
        result = await self.session.execute(
            select(PaperModel).where(PaperModel.paper_id == paper_id)
        )
        return result.scalar_one_or_none() is not None

    async def store_paper_id(self, paper_id: str, status: str = "discovered") -> None:
        """Store paper ID for tracking.

        Args:
            paper_id: ArXiv paper ID
            status: Processing status
        """
        paper = PaperModel(
            paper_id=paper_id,
            status=status,
        )
        self.session.add(paper)
        await self.session.commit()

    async def update_status(self, paper_id: str, status: str) -> None:
        """Update paper processing status.

        Args:
            paper_id: ArXiv paper ID
            status: New status
        """
        result = await self.session.execute(
            select(PaperModel).where(PaperModel.paper_id == paper_id)
        )
        paper = result.scalar_one_or_none()

        if paper:
            paper.status = status
            paper.updated_at = datetime.now(timezone.utc)
            await self.session.commit()
