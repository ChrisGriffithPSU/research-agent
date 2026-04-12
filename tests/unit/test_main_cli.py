"""Unit tests for top-level CLI command wiring in src.main."""

from __future__ import annotations

import asyncio

import pytest

import src.main as main_module


def _run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_version_command_outputs_version(capsys) -> None:
    main_module.version()
    captured = capsys.readouterr()
    assert "0.2.0" in captured.out


def test_worker_command_rejects_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["src.main", "worker", "nonexistent"])
    with pytest.raises(SystemExit) as exc_info:
        main_module.app(["worker", "nonexistent"], standalone_mode=False)
    # typer exits with code 1 for unknown worker
    assert exc_info.value.code == 1
