"""Unit tests for paper repository duplicate-tracking operations."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.shared.models.base import Base
from src.shared.repositories.paper_repository import PaperModel, PaperRepository


@pytest.mark.asyncio
async def test_store_exists_and_update_status_roundtrip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        repo = PaperRepository(session)
        assert await repo.exists("p1") is False
        await repo.store_paper_id("p1", status="discovered")
        assert await repo.exists("p1") is True
        await repo.update_status("p1", "triaged")
        model = await session.get(PaperModel, "p1")
        assert model is not None
        assert model.status == "triaged"

    await engine.dispose()
