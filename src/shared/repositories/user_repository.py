"""User profile repository."""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions import RepositoryNotFoundError
from src.shared.models.user import UserProfile
from src.shared.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[UserProfile]):
    """Repository for user profile operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(UserProfile, session)

    async def get_by_email(self, email: str) -> Optional[UserProfile]:
        """Get user by email address.

        Args:
            email: User email address

        Returns:
            UserProfile instance or None if not found
        """
        logger.debug(f"UserRepository: Getting user by email={email}")
        try:
            query = select(UserProfile).where(UserProfile.email == email)
            result = await self.session.execute(query)
            user = result.scalar_one_or_none()
            if user:
                logger.debug(f"UserRepository: Found user email={email}")
            else:
                logger.debug(f"UserRepository: User not found email={email}")
            return user
        except Exception as e:
            logger.error(f"UserRepository: Error getting user email={email}: {e}")
            raise

    async def get_or_create_default(self) -> UserProfile:
        """Get default user or create if doesn't exist.

        Returns:
            UserProfile instance (existing or newly created)
        """
        logger.debug("UserRepository: Getting or creating default user")
        user = await self.get(1)  # Assume ID 1 is default
        if user is None:
            user = await self.create(
                id=1,
                email="user@example.com",
                preferences={},
                learning_config={},
            )
            logger.info("UserRepository: Created default user")
        return user

    async def update_preferences(self, user_id: int, preferences: dict) -> UserProfile:
        """Update user preferences.

        Args:
            user_id: User ID
            preferences: New preferences dict

        Returns:
            Updated UserProfile instance
        """
        logger.debug(f"UserRepository: Updating preferences for user_id={user_id}")
        return await self.update(user_id, preferences=preferences)

    async def update_learning_config(
        self, user_id: int, learning_config: dict
    ) -> UserProfile:
        """Update user learning configuration.

        Args:
            user_id: User ID
            learning_config: New learning config dict

        Returns:
            Updated UserProfile instance
        """
        logger.debug(
            f"UserRepository: Updating learning_config for user_id={user_id}"
        )
        return await self.update(user_id, learning_config=learning_config)

    async def list_users(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[UserProfile]:
        """List all users with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of UserProfile instances
        """
        logger.debug("UserRepository: Listing all users")
        return await self.get_all(limit=limit, offset=offset)

