"""Unit tests for DB config/session/health helpers."""

from __future__ import annotations

import types

import pytest

import src.shared.db.config as db_config_module
import src.shared.db.health as db_health
import src.shared.db.session as db_session


def test_database_config_builds_async_url() -> None:
    cfg = db_config_module.DatabaseConfig(host="h", port=5433, user="u", password="p", name="n")
    assert cfg.database_url == "postgresql+asyncpg://u:p@h:5433/n"


@pytest.mark.asyncio
async def test_session_get_factory_lazy_initializes(monkeypatch: pytest.MonkeyPatch) -> None:
    db_session._session_factory = None

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return types.SimpleNamespace(
                commit=lambda: None, rollback=lambda: None, close=lambda: None
            )

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(db_session, "get_session_factory", lambda: _Factory())
    factory = await db_session._get_factory()
    assert factory is not None


@pytest.mark.asyncio
async def test_quick_check_false_on_health_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_health, "check_health", _raise)
    assert await db_health.quick_check() is False
