"""Unit tests for low-level Kimi session wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kimi_agent_sdk import ApprovalRequest, TextPart

from workers.kimi_worker.approvals import ApprovalPolicy
from workers.kimi_worker.kimi_session import run_agent_task


class _PromptStream:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        await asyncio.sleep(0)
        return item

    async def aclose(self):
        return None


class _Session:
    def __init__(self, items):
        self._items = items
        self.cancelled = False

    def prompt(self, prompt: str, merge_wire_messages: bool = True):
        return _PromptStream(self._items)

    def cancel(self) -> None:
        self.cancelled = True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_agent_task_captures_text_and_approvals(tmp_path: Path) -> None:
    approval = ApprovalRequest(action="pytest -q", description="run tests")
    session = _Session([TextPart("hello"), approval, TextPart(" world")])
    transcript = await run_agent_task(
        work_dir=tmp_path,
        skills_dir=None,
        prompt="go",
        approval_policy=ApprovalPolicy(),
        timeout_s=5,
        stream_log_path=tmp_path / "agent_stream.txt",
        session=session,  # type: ignore[arg-type]
    )
    assert transcript.text_output == "hello world"
    assert len(transcript.approvals) == 1
    assert transcript.approvals[0].decision in {"approve", "reject"}
    assert transcript.timed_out is False
