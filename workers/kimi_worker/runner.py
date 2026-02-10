"""Top-level orchestration state machine for Kimi experiment jobs."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from kaos.path import KaosPath
from kimi_agent_sdk import Session

from workers.kimi_worker.approvals import ApprovalPolicy
from workers.kimi_worker.kimi_session import run_agent_task
from workers.kimi_worker.models import (
    ArtifactRef,
    ExperimentJob,
    ExperimentResult,
    ExperimentSummary,
    ResultError,
)
from workers.kimi_worker.prompts import build_repair_packet, build_task_packet


MAX_AGENT_TURNS = 3  # initial + 2 repair attempts


@dataclass(slots=True)
class OutputValidation:
    """Validation result for summary/artifact outputs."""

    summary: ExperimentSummary | None
    error_message: str | None
    trace: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stuck_timeout_seconds() -> int:
    raw = os.getenv("KIMI_WORKER_STUCK_TIMEOUT_SECONDS", "300")
    try:
        value = int(raw)
    except ValueError:
        return 300
    return max(60, value)


def _to_kaos_path(path: Path) -> KaosPath:
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


def load_job(job_path: Path) -> ExperimentJob:
    """Load and validate an experiment job JSON from disk."""
    data = json.loads(job_path.read_text(encoding="utf-8"))
    data = _apply_env_overrides(data)

    return ExperimentJob.model_validate(data)


def job_from_payload(payload: dict[str, Any]) -> ExperimentJob:
    """Validate a job payload dict with environment overrides applied."""
    data = _apply_env_overrides(dict(payload))
    return ExperimentJob.model_validate(data)


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply optional environment-driven path overrides to a raw job payload."""

    repo_override = os.getenv("KIMI_WORKER_REPO_ROOT")
    if repo_override:
        data["repo_root"] = str(Path(repo_override).expanduser().resolve())

    run_root_override = os.getenv("KIMI_WORKER_RUNS_ROOT")
    if run_root_override:
        runs_root = Path(run_root_override).expanduser().resolve()
        job_id = str(data.get("job_id", "job"))
        output = data.setdefault("output", {})
        output["run_dir"] = str((runs_root / job_id).resolve())
        output.setdefault("summary_path", f"runs/{job_id}/results/summary.json")
        output.setdefault("artifacts_dir", f"runs/{job_id}/artifacts")

    return data


def _resolve_path(base: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _create_job_logger(job_id: str, worker_log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"kimi_worker.{job_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.FileHandler(worker_log_path, mode="w", encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def _tail_text(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _validate_outputs(summary_path: Path, artifacts_dir: Path) -> OutputValidation:
    messages: list[str] = []
    summary: ExperimentSummary | None = None

    if not summary_path.exists():
        messages.append(f"missing summary file: {summary_path}")
    else:
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            summary = ExperimentSummary.model_validate(payload)
        except Exception as exc:
            messages.append(f"invalid summary schema: {exc}")

    if not artifacts_dir.exists():
        messages.append(f"missing artifacts directory: {artifacts_dir}")
    else:
        files = [p for p in artifacts_dir.rglob("*") if p.is_file()]
        if not files:
            messages.append(f"no artifacts produced in: {artifacts_dir}")
        if files and not any(p.suffix.lower() == ".png" for p in files):
            messages.append("no PNG artifact found in artifacts directory")

    if not messages:
        return OutputValidation(summary=summary, error_message=None, trace="")
    return OutputValidation(
        summary=summary, error_message="; ".join(messages), trace="\n".join(messages)
    )


def _guess_artifact_type(path: Path) -> Literal["plot", "table", "log", "notebook", "code_diff"]:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "plot"
    if suffix == ".ipynb":
        return "notebook"
    if suffix in {".diff", ".patch"}:
        return "code_diff"
    if suffix in {".csv", ".parquet", ".hdf5", ".json", ".npy"}:
        return "table"
    return "log"


def _path_for_result(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _build_artifacts_manifest(
    repo_root: Path,
    artifacts_dir: Path,
    logs_dir: Path,
    notebooks_dir: Path,
) -> list[ArtifactRef]:
    refs: list[ArtifactRef] = []
    seen: set[str] = set()

    candidates: list[Path] = []
    for root in (artifacts_dir, logs_dir, notebooks_dir):
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())

    for path in sorted(candidates):
        display_path = _path_for_result(path, repo_root)
        if display_path in seen:
            continue
        seen.add(display_path)
        artifact_type = _guess_artifact_type(path)
        refs.append(
            ArtifactRef(
                type=artifact_type,
                path=display_path,
                description=f"Generated {artifact_type} artifact",
            )
        )

    return refs


def _capture_code_diff(repo_root: Path, artifacts_dir: Path, logger: logging.Logger) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--no-color"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        logger.warning("Unable to collect git diff artifact: %s", exc)
        return

    diff_text = proc.stdout.strip()
    if not diff_text:
        return
    diff_path = artifacts_dir / "repo.diff"
    diff_path.write_text(diff_text + "\n", encoding="utf-8")


def _repo_commit(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None


def _fallback_summary(job: ExperimentJob) -> ExperimentSummary:
    return ExperimentSummary(
        title=job.experiment_plan.title,
        hypotheses_tested=job.experiment_plan.hypotheses,
        metrics=[],
        key_findings=["No validated summary was produced by executed code."],
        regimes=[],
        next_steps=["Inspect logs and rerun with human supervision."],
    )


def _materialize_job_snapshot(job: ExperimentJob, run_dir: Path) -> None:
    snapshot_path = run_dir / "job.json"
    payload = json.dumps(job.model_dump(mode="json"), indent=2)
    snapshot_path.write_text(payload + "\n", encoding="utf-8")


async def run_job(job: ExperimentJob) -> ExperimentResult:
    """Execute a validated experiment job through the Kimi session runner."""
    started_at = _utc_now()
    started_monotonic = time.monotonic()

    run_dir = job.output.run_dir
    logs_dir = run_dir / "logs"
    notebooks_dir = run_dir / "notebooks"
    results_dir = run_dir / "results"
    run_artifacts_dir = run_dir / "artifacts"
    artifacts_dir = _resolve_path(job.repo_root, job.output.artifacts_dir)
    summary_path = _resolve_path(job.repo_root, job.output.summary_path)
    result_path = results_dir / "result.json"
    worker_log_path = logs_dir / "worker.log"
    stream_log_path = logs_dir / "agent_stream.txt"

    for path in (
        run_dir,
        logs_dir,
        notebooks_dir,
        results_dir,
        run_artifacts_dir,
        artifacts_dir,
        summary_path.parent,
    ):
        path.mkdir(parents=True, exist_ok=True)

    logger = _create_job_logger(job.job_id, worker_log_path)
    stream_log_path.write_text("", encoding="utf-8")
    _materialize_job_snapshot(job, run_dir)

    logger.info("Starting Kimi job %s", job.job_id)
    logger.info("Run dir: %s", run_dir)
    logger.info("Summary target: %s", summary_path)
    logger.info("Artifacts dir: %s", artifacts_dir)

    approval_policy = ApprovalPolicy(
        network_access=job.execution.network_access,
        yolo=job.execution.yolo_approvals,
    )
    skills_dir = job.repo_root / ".skills"
    skills_dir_or_none = skills_dir if skills_dir.exists() else None

    attempts = 0
    result_status: str = "needs_human"
    fatal_failure = False
    summary: ExperimentSummary | None = None
    errors: list[ResultError] = []
    prompt_text = build_task_packet(job)

    session_kwargs: dict[str, Any] = {
        "work_dir": _to_kaos_path(job.repo_root),
        "yolo": job.execution.yolo_approvals,
    }
    if skills_dir_or_none is not None:
        session_kwargs["skills_dir"] = _to_kaos_path(skills_dir_or_none)

    try:
        async with await Session.create(**session_kwargs) as session:
            for turn in range(1, MAX_AGENT_TURNS + 1):
                attempts = turn
                elapsed = int(time.monotonic() - started_monotonic)
                remaining = job.execution.max_runtime_seconds - elapsed
                if remaining <= 0:
                    fatal_failure = True
                    errors.append(
                        ResultError(
                            stage="runtime",
                            message="job exceeded max_runtime_seconds",
                            trace="no remaining runtime budget for next attempt",
                        )
                    )
                    logger.error("No remaining runtime budget for turn %s", turn)
                    break

                logger.info("Starting agent turn %s (remaining budget: %ss)", turn, remaining)

                transcript = await run_agent_task(
                    work_dir=job.repo_root,
                    skills_dir=skills_dir_or_none,
                    prompt=prompt_text,
                    approval_policy=approval_policy,
                    timeout_s=remaining,
                    stuck_timeout_s=_stuck_timeout_seconds(),
                    stream_log_path=stream_log_path,
                    session=session,
                )

                if transcript.error_message:
                    logger.warning("Agent turn %s reported: %s", turn, transcript.error_message)

                if transcript.stuck:
                    fatal_failure = True
                    errors.append(
                        ResultError(
                            stage="watchdog",
                            message="agent run cancelled due to no progress",
                            trace=transcript.error_message or "watchdog triggered",
                        )
                    )
                    logger.error("Watchdog triggered on turn %s", turn)
                    break

                if transcript.timed_out:
                    fatal_failure = True
                    errors.append(
                        ResultError(
                            stage="runtime",
                            message="agent run exceeded runtime budget",
                            trace=transcript.error_message or "turn timed out",
                        )
                    )
                    logger.error("Turn %s timed out", turn)
                    break

                validation = _validate_outputs(
                    summary_path=summary_path, artifacts_dir=artifacts_dir
                )
                if validation.error_message is None and validation.summary is not None:
                    summary = validation.summary
                    result_status = "success"
                    logger.info("Outputs validated successfully on turn %s", turn)
                    break

                last_error = (
                    validation.error_message or transcript.error_message or "unknown failure"
                )
                errors.append(
                    ResultError(
                        stage=f"attempt_{turn}",
                        message=last_error,
                        trace=validation.trace or _tail_text(stream_log_path),
                    )
                )
                logger.warning("Attempt %s failed validation: %s", turn, last_error)

                if turn < MAX_AGENT_TURNS:
                    prompt_text = build_repair_packet(
                        job=job,
                        attempt=turn + 1,
                        last_error=last_error,
                        log_snippet=_tail_text(stream_log_path),
                    )

    except Exception as exc:
        fatal_failure = True
        errors.append(
            ResultError(
                stage="runner",
                message="worker orchestration exception",
                trace=str(exc),
            )
        )
        logger.exception("Unhandled runner exception")

    if result_status != "success":
        result_status = "failed" if fatal_failure else "needs_human"

    _capture_code_diff(job.repo_root, artifacts_dir, logger)

    final_summary = summary if summary is not None else _fallback_summary(job)
    artifacts = _build_artifacts_manifest(
        repo_root=job.repo_root,
        artifacts_dir=artifacts_dir,
        logs_dir=logs_dir,
        notebooks_dir=notebooks_dir,
    )

    finished_at = _utc_now()
    result = ExperimentResult(
        job_id=job.job_id,
        status=result_status,
        started_at=started_at,
        finished_at=finished_at,
        attempts=attempts,
        repo_commit=_repo_commit(job.repo_root),
        summary=final_summary,
        artifacts=artifacts,
        errors=errors,
    )

    result_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote final result to %s", result_path)
    return result


async def run_job_from_path(job_path: Path) -> ExperimentResult:
    """Load a job from disk and execute it."""
    job = load_job(job_path)
    return await run_job(job)
