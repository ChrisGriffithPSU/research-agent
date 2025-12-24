"""Async session management for database operations."""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.config import get_session_factory

# Global session factory (created on first use)
_session_factory = None


def _get_factory():
    """Get session factory (lazy initialization)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for FastAPI endpoints.

    Yields an async session and ensures proper cleanup.
    Usage in FastAPI:

        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_session)):
            # Use db here
            pass

    The session is automatically committed and closed after the request.
    """
    factory = _get_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseSession:
    """Context manager for manual async session usage.

    Use this when not using FastAPI dependency injection.
    Usage:

        async with DatabaseSession() as session:
            source = Source(...)
            session.add(source)
            # Session commits and closes automatically on exit
    """

    def __init__(self):
        self._session: AsyncSession = None

    async def __aenter__(self) -> AsyncSession:
        """Enter context and create session."""
        factory = _get_factory()
        self._session = factory()
        await self._session.begin()
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and cleanup session."""
        if self._session is None:
            return

        if exc_type is None:
            # No exception, commit transaction
            await self._session.commit()
        else:
            # Exception occurred, rollback transaction
            await self._session.rollback()

        # Always close session
        await self._session.close()
        self._session = None

