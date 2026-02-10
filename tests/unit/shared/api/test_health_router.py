"""Unit tests for FastAPI health router handlers."""

from __future__ import annotations

import json

import pytest

import src.shared.api.health_router as router


def _body(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_health_check_returns_200_for_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok():
        return {"status": "healthy", "checks": {"connection": "ok"}}

    monkeypatch.setattr(router, "check_health", _ok)
    response = await router.health_check()
    assert response.status_code == 200
    assert _body(response)["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_returns_503_for_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _bad():
        return {"status": "unhealthy", "checks": {"connection": "failed"}}

    monkeypatch.setattr(router, "check_health", _bad)
    response = await router.health_check()
    assert response.status_code == 503
    assert _body(response)["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_quick_readiness_and_liveness_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _true():
        return True

    async def _false():
        return False

    monkeypatch.setattr(router, "quick_check", _true)
    quick = await router.quick_health_check()
    ready = await router.readiness_check()
    live = await router.liveness_check()
    assert quick.status_code == 200
    assert _body(ready)["status"] == "ready"
    assert _body(live)["status"] == "ok"

    monkeypatch.setattr(router, "quick_check", _false)
    quick2 = await router.quick_health_check()
    ready2 = await router.readiness_check()
    assert quick2.status_code == 503
    assert _body(ready2)["status"] == "not_ready"
