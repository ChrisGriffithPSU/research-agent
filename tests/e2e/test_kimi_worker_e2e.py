"""E2E tests for Kimi job execution flow (in-process, deterministic)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import workers.kimi_worker.runner as runner
from workers.kimi_worker.kimi_session import AgentRunTranscript


def _transcript() -> AgentRunTranscript:
    now = datetime.now(timezone.utc)
    return AgentRunTranscript(
        started_at=now,
        finished_at=now,
        text_output="ok",
        approvals=[],
        events=[],
    )


def _job_file(tmp_path: Path) -> Path:
    payload = {
        "job_id": "e2e_job",
        "created_at": "2026-02-10T00:00:00Z",
        "priority": 0,
        "repo_root": str(tmp_path),
        "dataset_refs": [],
        "experiment_plan": {
            "title": "E2E",
            "hypotheses": ["h"],
            "method": "m",
            "metrics": [{"name": "metric", "goal": "maximize", "target": 0.1}],
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
            "run_dir": str(tmp_path / "runs" / "e2e_job"),
            "summary_path": "runs/e2e_job/results/summary.json",
            "artifacts_dir": "runs/e2e_job/artifacts",
        },
    }
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    return job_path


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_kimi_job_end_to_end_produces_result_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job_path = _job_file(tmp_path)
    summary_path = tmp_path / "runs" / "e2e_job" / "results" / "summary.json"
    artifact_path = tmp_path / "runs" / "e2e_job" / "artifacts" / "plot.png"

    async def _fake_run_agent_task(**kwargs):
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "title": "E2E",
                    "hypotheses_tested": ["h"],
                    "metrics": [{"name": "metric", "value": 0.2, "threshold_met": True}],
                    "key_findings": ["kf"],
                    "regimes": ["normal"],
                    "next_steps": ["next"],
                }
            ),
            encoding="utf-8",
        )
        artifact_path.write_bytes(b"png")
        return _transcript()

    monkeypatch.setattr(runner, "run_agent_task", _fake_run_agent_task)
    result = await runner.run_job_from_path(job_path)

    assert result.status == "success"
    result_path = tmp_path / "runs" / "e2e_job" / "results" / "result.json"
    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert any(a["type"] == "plot" for a in payload["artifacts"])
