"""Unit tests for top-level CLI command wiring in src.main."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

import src.main as main_module


def _run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_worker_kimi_dispatch_calls_queue_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"queue": 0}

    async def _queue_worker():
        called["queue"] += 1

    fake_module = types.ModuleType("workers.kimi_worker.mq_worker")
    setattr(fake_module, "run_queue_worker", _queue_worker)
    monkeypatch.setitem(sys.modules, "workers.kimi_worker.mq_worker", fake_module)

    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    monkeypatch.setattr(main_module.asyncio, "run", _run_sync)

    main_module.worker(name="kimi", verbose=False)
    assert called["queue"] == 1


def test_worker_unknown_name_exits_with_code_1(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Conn:
        def __init__(self, config):
            pass

        async def connect(self):
            return None

        async def close(self):
            return None

    class _LLM:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    monkeypatch.setattr(main_module, "RabbitMQConnection", _Conn)
    monkeypatch.setattr(main_module, "MessageConsumer", lambda connection: object())
    monkeypatch.setattr(main_module, "MessagePublisher", lambda connection: object())
    monkeypatch.setattr(main_module, "OpenAIClient", _LLM)
    monkeypatch.setattr(main_module.asyncio, "run", _run_sync)

    with pytest.raises(SystemExit) as exc:
        main_module.worker(name="does_not_exist", verbose=False)
    assert exc.value.code == 1


def test_worker_triage_starts_worker_and_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"started": 0, "closed": 0, "profile": None}

    class _Conn:
        def __init__(self, config):
            pass

        async def connect(self):
            return None

        async def close(self):
            state["closed"] += 1

    class _LLM:
        def __init__(self, *args, **kwargs):
            state["profile"] = kwargs.get("profile")

    class _Worker:
        def __init__(self, **kwargs):
            pass

        async def start(self):
            state["started"] += 1

        async def stop(self):
            return None

    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    monkeypatch.setattr(main_module, "RabbitMQConnection", _Conn)
    monkeypatch.setattr(main_module, "MessageConsumer", lambda connection: object())
    monkeypatch.setattr(main_module, "MessagePublisher", lambda connection: object())
    monkeypatch.setattr(main_module, "OpenAIClient", _LLM)
    monkeypatch.setattr(main_module, "PaperTriageWorker", _Worker)
    monkeypatch.setattr(main_module.asyncio, "run", _run_sync)

    main_module.worker(name="triage", verbose=False)
    assert state["started"] == 1
    assert state["closed"] == 1
    assert state["profile"] == "triage"
