"""In-process integration tests for Kimi runner state machine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import workers.kimi_worker.runner as runner
from workers.kimi_worker.kimi_session import AgentRunTranscript


def _job_payload(tmp_path: Path, job_id: str = "j1") -> dict:
    return {
        "job_id": job_id,
        "created_at": "2026-02-10T00:00:00Z",
        "priority": 0,
        "repo_root": str(tmp_path),
        "dataset_refs": [],
        "experiment_plan": {
            "title": "Experiment",
            "hypotheses": ["h1"],
            "method": "m",
            "metrics": [{"name": "score", "goal": "maximize", "target": 0.1}],
            "protocol": {
                "time_horizon": "10s",
                "labels": "y",
                "validation": "walk_forward",
                "constraints": [],
            },
            "implementation_notes": [],
        },
        "execution": {
            "entrypoint_preference": "python_script",
            "max_runtime_seconds": 120,
            "network_access": False,
            "yolo_approvals": False,
        },
        "output": {
            "run_dir": str(tmp_path / "runs" / job_id),
            "summary_path": f"runs/{job_id}/results/summary.json",
            "artifacts_dir": f"runs/{job_id}/artifacts",
        },
    }


def _transcript() -> AgentRunTranscript:
    now = datetime.now(timezone.utc)
    return AgentRunTranscript(
        started_at=now,
        finished_at=now,
        text_output="ok",
        approvals=[],
        events=[],
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_job_success_when_summary_and_artifact_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = runner.job_from_payload(_job_payload(tmp_path))
    summary_path = tmp_path / "runs" / "j1" / "results" / "summary.json"
    artifact_path = tmp_path / "runs" / "j1" / "artifacts" / "plot.png"

    async def _fake_run_agent_task(**kwargs):
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "title": "Experiment",
                    "hypotheses_tested": ["h1"],
                    "metrics": [{"name": "score", "value": 0.5, "threshold_met": True}],
                    "key_findings": ["k"],
                    "regimes": ["r"],
                    "next_steps": ["n"],
                }
            ),
            encoding="utf-8",
        )
        artifact_path.write_bytes(b"png")
        return _transcript()

    monkeypatch.setattr(runner, "run_agent_task", _fake_run_agent_task)
    result = await runner.run_job(job)
    assert result.status == "success"
    assert result.attempts == 1
    assert (tmp_path / "runs" / "j1" / "results" / "result.json").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_job_needs_human_after_exhausted_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = runner.job_from_payload(_job_payload(tmp_path, job_id="j2"))

    async def _fake_run_agent_task(**kwargs):
        return _transcript()

    monkeypatch.setattr(runner, "run_agent_task", _fake_run_agent_task)
    result = await runner.run_job(job)
    assert result.status in {"needs_human", "failed"}
    assert result.attempts == 3
    assert len(result.errors) >= 1
