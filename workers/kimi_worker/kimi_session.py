"""Low-level Kimi SDK session wrapper with approvals and transcripts."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kaos.path import KaosPath
from kimi_agent_sdk import (
    ApprovalRequest,
    RunCancelled,
    Session,
    TextPart,
    ToolCallPart,
    ToolResult,
)

from workers.kimi_worker.approvals import ApprovalPolicy


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ApprovalRecord:
    """Captured approval decision record."""

    timestamp: str
    action: str
    description: str
    decision: str
    reason: str


@dataclass(slots=True)
class AgentEvent:
    """Captured wire event in normalized form."""

    timestamp: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunTranscript:
    """Complete transcript returned for one `Session.prompt` turn."""

    started_at: datetime
    finished_at: datetime
    text_output: str
    approvals: list[ApprovalRecord]
    events: list[AgentEvent]
    timed_out: bool = False
    stuck: bool = False
    cancelled: bool = False
    error_message: str | None = None


def _to_kaos_path(path: Path) -> KaosPath:
    """Best-effort conversion from pathlib Path to KaosPath."""
    try:
        return KaosPath(path)  # type: ignore[arg-type]
    except Exception:
        try:
            return KaosPath(str(path))  # type: ignore[arg-type]
        except Exception:
            original_cwd = Path.cwd()
            os.chdir(path)
            try:
                return KaosPath.cwd()
            finally:
                os.chdir(original_cwd)


def _append_stream_line(stream_log_path: Path | None, line: str) -> None:
    if stream_log_path is None:
        return
    stream_log_path.parent.mkdir(parents=True, exist_ok=True)
    with stream_log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")


def _payload_from_wire_message(wire_msg: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for attr in (
        "id",
        "tool_call_id",
        "sender",
        "action",
        "description",
        "name",
        "status",
        "text",
    ):
        value = getattr(wire_msg, attr, None)
        if value is not None:
            payload[attr] = str(value)

    usage = getattr(wire_msg, "token_usage", None)
    if usage is not None:
        payload["token_usage"] = str(usage)

    display = getattr(wire_msg, "display", None)
    if isinstance(display, list) and display:
        payload["display"] = [str(item) for item in display]

    return payload


async def run_agent_task(
    work_dir: Path,
    skills_dir: Path | None,
    prompt: str,
    approval_policy: ApprovalPolicy,
    timeout_s: int,
    *,
    stuck_timeout_s: int = 300,
    stream_log_path: Path | None = None,
    session: Session | None = None,
) -> AgentRunTranscript:
    """Run one low-level session turn with streaming and policy approvals."""
    own_session = session is None
    if session is None:
        session_kwargs: dict[str, Any] = {
            "work_dir": _to_kaos_path(work_dir),
            "yolo": approval_policy.yolo,
        }
        if skills_dir is not None:
            session_kwargs["skills_dir"] = _to_kaos_path(skills_dir)
        session = await Session.create(**session_kwargs)

    started_at = _utc_now()
    text_chunks: list[str] = []
    approvals: list[ApprovalRecord] = []
    events: list[AgentEvent] = []
    timed_out = False
    stuck = False
    cancelled = False
    error_message: str | None = None

    deadline = time.monotonic() + max(1, timeout_s)
    prompt_stream = session.prompt(prompt, merge_wire_messages=True)
    iterator = prompt_stream.__aiter__()

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                error_message = "agent turn exceeded timeout"
                session.cancel()
                break

            wait_window = min(float(stuck_timeout_s), remaining)
            try:
                wire_msg = await asyncio.wait_for(iterator.__anext__(), timeout=wait_window)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                session.cancel()
                if remaining <= float(stuck_timeout_s):
                    timed_out = True
                    error_message = "agent turn exceeded timeout"
                else:
                    stuck = True
                    error_message = f"agent made no progress for {stuck_timeout_s} seconds; watchdog cancelled turn"
                break

            timestamp = _utc_now().isoformat()
            event_type = wire_msg.__class__.__name__
            payload = _payload_from_wire_message(wire_msg)
            events.append(AgentEvent(timestamp=timestamp, event_type=event_type, payload=payload))
            _append_stream_line(
                stream_log_path,
                f"[{timestamp}] {event_type}: {json.dumps(payload, ensure_ascii=True)}",
            )

            if isinstance(wire_msg, TextPart):
                text = wire_msg.text
                text_chunks.append(text)
                _append_stream_line(stream_log_path, text)
                continue

            if isinstance(wire_msg, (ToolCallPart, ToolResult)):
                continue

            if isinstance(wire_msg, ApprovalRequest):
                decision = approval_policy.evaluate_request(wire_msg)
                wire_msg.resolve(decision.resolution)
                approvals.append(
                    ApprovalRecord(
                        timestamp=timestamp,
                        action=str(getattr(wire_msg, "action", "")),
                        description=str(getattr(wire_msg, "description", "")),
                        decision=decision.resolution,
                        reason=decision.reason,
                    )
                )
                _append_stream_line(
                    stream_log_path,
                    (
                        f"[{timestamp}] approval_decision={decision.resolution} "
                        f"reason={decision.reason}"
                    ),
                )
                if decision.resolution == "reject":
                    text_chunks.append(
                        f"\n[worker-policy] {approval_policy.denial_message(decision)}\n"
                    )

    except RunCancelled:
        cancelled = True
        if error_message is None:
            error_message = "agent run cancelled"
    except Exception as exc:
        error_message = f"session error: {exc}"
    finally:
        try:
            await prompt_stream.aclose()
        except Exception:
            pass
        if own_session:
            await session.close()

    finished_at = _utc_now()
    return AgentRunTranscript(
        started_at=started_at,
        finished_at=finished_at,
        text_output="".join(text_chunks),
        approvals=approvals,
        events=events,
        timed_out=timed_out,
        stuck=stuck,
        cancelled=cancelled,
        error_message=error_message,
    )
