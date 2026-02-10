"""Unit tests for DB decorators."""

from __future__ import annotations

import pytest

from src.shared.exceptions.database import DatabaseError
from src.shared.utils.db.decorators import db_transaction, query_timeout


class _Session:
    def __init__(self) -> None:
        self.committed = 0
        self.rolled_back = 0

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


@pytest.mark.asyncio
async def test_db_transaction_commits_on_success() -> None:
    session = _Session()

    @db_transaction
    async def _work(*, session):
        return "ok"

    result = await _work(session=session)
    assert result == "ok"
    assert session.committed == 1
    assert session.rolled_back == 0


@pytest.mark.asyncio
async def test_db_transaction_rolls_back_and_wraps_errors() -> None:
    session = _Session()

    @db_transaction
    async def _work(*, session):
        raise RuntimeError("boom")

    with pytest.raises(DatabaseError):
        await _work(session=session)
    assert session.committed == 0
    assert session.rolled_back == 1


@pytest.mark.asyncio
async def test_query_timeout_passthrough_without_session() -> None:
    called = {"ok": False}

    @query_timeout(seconds=1)
    async def _work():
        called["ok"] = True
        return 123

    assert await _work() == 123
    assert called["ok"] is True
