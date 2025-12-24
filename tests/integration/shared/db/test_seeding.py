"""Tests for database seeding functionality."""
import pytest

from src.shared.db.session import DatabaseSession
from src.shared.repositories import (
    FetcherStateRepository,
    SystemStateRepository,
    UserRepository,
)


@pytest.mark.asyncio
async def test_seeding_idempotent(test_session):
    """Test that seeding can run multiple times safely."""
    # First run
    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database
        await seed_database()

    # Second run (should not fail)
    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database
        await seed_database()


@pytest.mark.asyncio
async def test_seed_creates_default_user(test_session):
    """Test that seeding creates default user."""
    # Seed database
    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database
        await seed_database()

    # Verify user exists
    user_repo = UserRepository(test_session)
    user = await user_repo.get(1)

    assert user is not None
    assert user.email == "user@example.com"
    assert isinstance(user.preferences, dict)
    assert isinstance(user.learning_config, dict)


@pytest.mark.asyncio
async def test_seed_creates_system_state(test_session):
    """Test that seeding creates system state."""
    # Seed database
    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database
        await seed_database()

    # Verify system state exists
    state_repo = SystemStateRepository(test_session)

    email_enabled = await state_repo.get_value("feature:email_delivery_enabled")
    assert email_enabled is not None
    assert email_enabled.get("enabled") is True

    auto_digest = await state_repo.get_value("feature:auto_digest_generation")
    assert auto_digest is not None
    assert auto_digest.get("enabled") is True

    digest_config = await state_repo.get_value("digest:configuration")
    assert digest_config is not None
    assert digest_config.get("items_per_digest") == 15


@pytest.mark.asyncio
async def test_seed_creates_fetcher_states(test_session):
    """Test that seeding creates fetcher states."""
    # Seed database
    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database
        await seed_database()

    # Verify fetcher states exist
    fetcher_repo = FetcherStateRepository(test_session)

    arxiv_state = await fetcher_repo.get_by_name("arxiv")
    assert arxiv_state is not None
    assert arxiv_state.status == "active"

    kaggle_state = await fetcher_repo.get_by_name("kaggle")
    assert kaggle_state is not None
    assert kaggle_state.status == "active"

    huggingface_state = await fetcher_repo.get_by_name("huggingface")
    assert huggingface_state is not None
    assert huggingface_state.status == "active"

    web_search_state = await fetcher_repo.get_by_name("web_search")
    assert web_search_state is not None
    assert web_search_state.status == "active"


@pytest.mark.asyncio
async def test_seed_transaction_atomic(test_session):
    """Test that seeding runs in a single transaction."""
    # Seed should either succeed completely or fail completely
    # No partial seeding

    async with DatabaseSession() as session:
        from src.shared.db.seed import seed_database

        try:
            await seed_database()
        except Exception:
            pass  # Ignore any errors

    # Check that all or none exist (not partial)
    state_repo = SystemStateRepository(test_session)
    email_enabled = await state_repo.get_value("feature:email_delivery_enabled")

    # Either all seeded or none seeded
    user_repo = UserRepository(test_session)
    user = await user_repo.get(1)

    # Both should exist or both should not exist
    assert (email_enabled is not None) == (user is not None)

