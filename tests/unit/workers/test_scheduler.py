"""Unit tests for scheduler orchestration."""

from __future__ import annotations

import pytest

import src.scheduler as scheduler_module
from src.scheduler import ArxivScheduler


@pytest.mark.asyncio
async def test_run_once_invokes_worker_run(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"run": 0}

    class _FakeWorker:
        def __init__(self, deps):
            self.deps = deps

        async def run(self):
            called["run"] += 1

        def get_stats(self):
            return {"ok": True}

    monkeypatch.setattr(scheduler_module, "ArxivFetcherWorker", _FakeWorker)
    scheduler = ArxivScheduler(interval_minutes=1, dependencies=object())
    await scheduler.run_once()
    assert called["run"] == 1
