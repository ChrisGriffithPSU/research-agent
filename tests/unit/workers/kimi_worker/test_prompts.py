"""Unit tests for Kimi prompt builders."""

from __future__ import annotations

from workers.kimi_worker.models import ExperimentJob
from workers.kimi_worker.prompts import build_repair_packet, build_task_packet


def _job() -> ExperimentJob:
    return ExperimentJob.model_validate(
        {
            "job_id": "j1",
            "created_at": "2026-02-10T00:00:00Z",
            "priority": 0,
            "repo_root": "C:/repo",
            "dataset_refs": [],
            "experiment_plan": {
                "title": "t",
                "hypotheses": ["h"],
                "method": "m",
                "metrics": [{"name": "m", "goal": "maximize", "target": 0.1}],
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
                "max_runtime_seconds": 60,
                "network_access": False,
                "yolo_approvals": False,
            },
            "output": {
                "run_dir": "C:/repo/runs/j1",
                "summary_path": "runs/j1/results/summary.json",
                "artifacts_dir": "runs/j1/artifacts",
            },
        }
    )


def test_task_packet_contains_job_json_and_required_paths() -> None:
    prompt = build_task_packet(_job())
    assert "Full Experiment Job JSON" in prompt
    assert "runs/j1/results/summary.json" in prompt
    assert "runs/j1/artifacts" in prompt
    assert "Do not invent results" in prompt


def test_repair_packet_contains_error_and_log_snippet() -> None:
    prompt = build_repair_packet(_job(), attempt=2, last_error="x", log_snippet="trace")
    assert "Repair attempt 2" in prompt
    assert "Last error" in prompt
    assert "trace" in prompt
