"""Unit tests for Kimi worker CLI entrypoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import workers.kimi_worker.main as main_module


def test_main_returns_error_for_missing_job_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prog", "--job", "missing.json"])
    assert main_module.main() == 1


def test_main_runs_job_mode_and_maps_success_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job_path = tmp_path / "job.json"
    job_path.write_text("{}", encoding="utf-8")

    class _Result:
        status = "success"

        def model_dump(self, mode: str = "json"):
            return {"status": "success"}

    monkeypatch.setattr(main_module, "load_job", lambda path: object())
    monkeypatch.setattr(main_module, "run_job_from_path", lambda path: _Result())
    monkeypatch.setattr(main_module.asyncio, "run", lambda coro: _Result())
    monkeypatch.setattr(sys, "argv", ["prog", "--job", str(job_path)])
    assert main_module.main() == 0


def test_exit_code_mapping() -> None:
    assert main_module._exit_code_for_status("success") == 0
    assert main_module._exit_code_for_status("needs_human") == 2
    assert main_module._exit_code_for_status("failed") == 1


def test_main_queue_mode_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prog", "--queue"])
    monkeypatch.setattr(main_module.asyncio, "run", lambda coro: None)
    assert main_module.main() == 0
