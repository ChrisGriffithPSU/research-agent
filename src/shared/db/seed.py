"""Database seeding script.

Populates database with initial data for development and testing.
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.shared.db.session import DatabaseSession
from src.shared.models import (
    FetcherStatus,
    FetcherState,
    Source,
    SystemState,
    UserProfile,
)
from src.shared.repositories import (
    FetcherStateRepository,
    SystemStateRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


async def seed_database() -> None:
    """Seed initial database data (idempotent).

    Creates:
    - Default user profile
    - System state configuration
    - Fetcher states for all sources
    """
    logger.info("Starting database seeding")

    async with DatabaseSession() as session:
        # Seed default user
        await seed_user_profile(session)

        # Seed system state
        await seed_system_state(session)

        # Seed fetcher states
        await seed_fetcher_states(session)

        logger.info("Database seeding completed successfully")


async def seed_user_profile(session) -> None:
    """Create default user profile if not exists."""
    logger.info("Seeding default user profile")
    user_repo = UserRepository(session)

    try:
        user = await user_repo.get_or_create_default()
        logger.info(f"User profile: {user.email} (ID: {user.id})")
    except Exception as e:
        logger.error(f"Failed to seed user profile: {e}")
        raise


async def seed_system_state(session) -> None:
    """Create initial system state configuration."""
    logger.info("Seeding system state")
    state_repo = SystemStateRepository(session)

    # Feature flags
    await state_repo.set_value(
        "feature:email_delivery_enabled",
        {"enabled": True, "last_email_at": None},
    )

    await state_repo.set_value(
        "feature:auto_digest_generation",
        {"enabled": True, "schedule_time": "03:00"},
    )

    await state_repo.set_value(
        "learning:retraining_threshold", {"min_ratings": 100}
    )

    await state_repo.set_value(
        "deduplication:settings",
        {"similarity_threshold": 0.85, "check_url_first": True},
    )

    # Digest configuration
    await state_repo.set_value(
        "digest:configuration",
        {
            "items_per_digest": 15,
            "quality_threshold": 0.6,
            "min_items": 5,
        },
    )

    logger.info("System state seeded with default configuration")


async def seed_fetcher_states(session) -> None:
    """Create fetcher states for all sources."""
    logger.info("Seeding fetcher states")
    fetcher_repo = FetcherStateRepository(session)

    fetchers = ["arxiv", "kaggle", "huggingface", "web_search"]

    for fetcher_name in fetchers:
        state = await fetcher_repo.get_or_create(fetcher_name)
        logger.info(
            f"Fetcher state: {state.fetcher_name} (status: {state.status})"
        )


async def main():
    """Main entry point for seeding."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        await seed_database()
        print("\n✅ Database seeding completed successfully!")
        print("\nSeeded data:")
        print("  - Default user profile")
        print("  - System state configuration")
        print("  - Fetcher states (arxiv, kaggle, huggingface, web_search)")
    except Exception as e:
        logger.error(f"❌ Database seeding failed: {e}")
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

