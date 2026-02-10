"""Unit tests for Kimi runner helper behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import workers.kimi_worker.runner as runner


def _job_payload(tmp_path: Path) -> dict:
    return {
        "job_id": "j1",
        "created_at": "2026-02-10T00:00:00Z",
        "priority": 0,
        "repo_root": str(tmp_path),
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
            "max_runtime_seconds": 120,
            "network_access": False,
            "yolo_approvals": False,
        },
        "output": {
            "run_dir": str(tmp_path / "runs" / "j1"),
            "summary_path": "runs/j1/results/summary.json",
            "artifacts_dir": "runs/j1/artifacts",
        },
    }


def test_job_from_payload_applies_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _job_payload(tmp_path)
    monkeypatch.setenv("KIMI_WORKER_REPO_ROOT", str(tmp_path / "other_repo"))
    monkeypatch.setenv("KIMI_WORKER_RUNS_ROOT", str(tmp_path / "custom_runs"))
    job = runner.job_from_payload(payload)
    assert str(job.repo_root).endswith("other_repo")
    assert "custom_runs" in str(job.output.run_dir)


def test_validate_outputs_success_and_failure(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    summary = {
        "title": "t",
        "hypotheses_tested": [],
        "metrics": [],
        "key_findings": [],
        "regimes": [],
        "next_steps": [],
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (artifacts_dir / "plot.png").write_bytes(b"png")

    ok = runner._validate_outputs(summary_path, artifacts_dir)
    assert ok.error_message is None

    bad = runner._validate_outputs(tmp_path / "missing.json", artifacts_dir)
    assert bad.error_message is not None
