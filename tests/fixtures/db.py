"""Database fixtures for testing.

Provides test database setup and cleanup for pytest.
"""
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.models import Base


# Test database URL (in-memory SQLite for speed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    """Create test database engine.

    The engine is created per test function and disposed after.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session(test_engine):
    """Create test database session.

    Session is created per test and committed/rolled back appropriately.
    """
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        # Session is committed/rolled back by repository methods


@pytest.fixture(scope="session")
def test_config():
    """Provide test database configuration.

    Override production config for testing.
    """
    from src.shared.db.config import DatabaseConfig

    class TestConfig(DatabaseConfig):
        """Test configuration with SQLite."""

        @property
        def database_url(self) -> str:
            return TEST_DATABASE_URL

    return TestConfig()

