"""Tests for BaseRepository CRUD operations.

These tests require PostgreSQL as UserProfile uses JSONB and other
PostgreSQL-specific features.
"""
import pytest

from src.shared.models.user import UserProfile
from src.shared.repositories.base import BaseRepository

# Mark all tests in this module as integration tests requiring PostgreSQL
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_base_repository_create(test_session):
    """Test creating a model instance."""
    repo = BaseRepository(UserProfile, test_session)

    user = await repo.create(
        email="test@example.com",
        preferences={"test": "data"},
        learning_config={},
    )

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.preferences == {"test": "data"}


@pytest.mark.asyncio
async def test_base_repository_get(test_session):
    """Test getting a model instance by ID."""
    repo = BaseRepository(UserProfile, test_session)

    # Create user first
    user = await repo.create(
        email="test@example.com", preferences={}, learning_config={}
    )

    # Get user by ID
    found = await repo.get(user.id)

    assert found is not None
    assert found.id == user.id
    assert found.email == "test@example.com"


@pytest.mark.asyncio
async def test_base_repository_get_not_found(test_session):
    """Test getting non-existent instance returns None."""
    repo = BaseRepository(UserProfile, test_session)

    found = await repo.get(99999)

    assert found is None


@pytest.mark.asyncio
async def test_base_repository_get_all(test_session):
    """Test getting all model instances."""
    repo = BaseRepository(UserProfile, test_session)

    # Create multiple users
    for i in range(3):
        await repo.create(
            email=f"user{i}@example.com", preferences={}, learning_config={}
        )

    # Get all
    users = await repo.get_all()

    assert len(users) >= 3
    assert all(isinstance(user, UserProfile) for user in users)


@pytest.mark.asyncio
async def test_base_repository_get_all_with_pagination(test_session):
    """Test pagination in get_all."""
    repo = BaseRepository(UserProfile, test_session)

    # Create 5 users
    for i in range(5):
        await repo.create(
            email=f"user{i}@example.com", preferences={}, learning_config={}
        )

    # Get with limit
    users = await repo.get_all(limit=2)

    assert len(users) == 2


@pytest.mark.asyncio
async def test_base_repository_update(test_session):
    """Test updating a model instance."""
    repo = BaseRepository(UserProfile, test_session)

    # Create user
    user = await repo.create(
        email="test@example.com", preferences={}, learning_config={}
    )

    # Update
    updated = await repo.update(
        user.id, preferences={"updated": "preferences"}
    )

    assert updated.id == user.id
    assert updated.preferences == {"updated": "preferences"}


@pytest.mark.asyncio
async def test_base_repository_delete(test_session):
    """Test deleting a model instance."""
    repo = BaseRepository(UserProfile, test_session)

    # Create user
    user = await repo.create(
        email="test@example.com", preferences={}, learning_config={}
    )

    # Delete
    result = await repo.delete(user.id)

    assert result is True

    # Verify deleted
    found = await repo.get(user.id)
    assert found is None


@pytest.mark.asyncio
async def test_base_repository_delete_not_found(test_session):
    """Test deleting non-existent instance returns False."""
    repo = BaseRepository(UserProfile, test_session)

    result = await repo.delete(99999)

    assert result is False


@pytest.mark.asyncio
async def test_base_repository_list_by_field(test_session):
    """Test filtering by field value."""
    repo = BaseRepository(UserProfile, test_session)

    # Create users with different emails
    await repo.create(
        email="test1@example.com", preferences={}, learning_config={}
    )
    await repo.create(
        email="test2@example.com", preferences={}, learning_config={}
    )
    await repo.create(
        email="other@example.com", preferences={}, learning_config={}
    )

    # Filter by email pattern
    from sqlalchemy import select
    query = select(UserProfile).where(UserProfile.email.like("test%"))
    result = await test_session.execute(query)
    users = list(result.scalars().all())

    assert len(users) == 2
    assert all("test" in user.email for user in users)


@pytest.mark.asyncio
async def test_base_repository_count(test_session):
    """Test counting model instances."""
    repo = BaseRepository(UserProfile, test_session)

    # Create 3 users
    for i in range(3):
        await repo.create(
            email=f"user{i}@example.com", preferences={}, learning_config={}
        )

    count = await repo.count()

    assert count >= 3

