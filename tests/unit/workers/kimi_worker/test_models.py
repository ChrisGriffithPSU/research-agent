"""Unit tests for Kimi worker schema models."""

from __future__ import annotations

from pathlib import Path

import pytest

from workers.kimi_worker.models import ExperimentJob, ExperimentResult


def _job_payload() -> dict:
    return {
        "job_id": "j1",
        "created_at": "2026-02-10T00:00:00Z",
        "priority": 0,
        "repo_root": "C:/repo",
        "dataset_refs": [],
        "experiment_plan": {
            "title": "t",
            "hypotheses": ["h"],
            "method": "m",
            "metrics": [{"name": "acc", "goal": "maximize", "target": 0.5}],
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
            "max_runtime_seconds": 10,
            "network_access": False,
            "yolo_approvals": False,
        },
        "output": {
            "run_dir": "C:/repo/runs/j1",
            "summary_path": "runs/j1/results/summary.json",
            "artifacts_dir": "runs/j1/artifacts",
        },
    }


def test_experiment_job_validates_happy_path() -> None:
    job = ExperimentJob.model_validate(_job_payload())
    assert job.job_id == "j1"
    assert job.output.run_dir.is_absolute()


def test_experiment_job_requires_absolute_paths() -> None:
    payload = _job_payload()
    payload["repo_root"] = "repo/relative"
    with pytest.raises(Exception):
        ExperimentJob.model_validate(payload)


def test_experiment_result_rejects_unknown_status() -> None:
    data = {
        "job_id": "j1",
        "status": "unknown",
        "started_at": "2026-02-10T00:00:00Z",
        "finished_at": "2026-02-10T00:00:10Z",
        "attempts": 1,
        "repo_commit": None,
        "summary": {
            "title": "x",
            "hypotheses_tested": [],
            "metrics": [],
            "key_findings": [],
            "regimes": [],
            "next_steps": [],
        },
        "artifacts": [],
        "errors": [],
    }
    with pytest.raises(Exception):
        ExperimentResult.model_validate(data)
