"""Schema models for Kimi experiment jobs and results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetRef(BaseModel):
    """Dataset reference in an experiment job."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    format: Literal["parquet", "csv", "hdf5", "npy", "other"]


class MetricGoal(BaseModel):
    """Goal for an experiment metric."""

    model_config = ConfigDict(extra="forbid")

    name: str
    goal: Literal["maximize", "minimize", "target"]
    target: float


class ProtocolSpec(BaseModel):
    """Protocol section of an experiment plan."""

    model_config = ConfigDict(extra="forbid")

    time_horizon: Literal["5s", "10s", "30s"]
    labels: str
    validation: Literal["walk_forward", "purged_cv", "other"]
    constraints: list[str] = Field(default_factory=list)


class ExperimentPlan(BaseModel):
    """Plan that the coding agent must execute."""

    model_config = ConfigDict(extra="forbid")

    title: str
    hypotheses: list[str] = Field(default_factory=list)
    method: str
    metrics: list[MetricGoal] = Field(default_factory=list)
    protocol: ProtocolSpec
    implementation_notes: list[str] = Field(default_factory=list)


class ExecutionConfig(BaseModel):
    """Execution controls for a job run."""

    model_config = ConfigDict(extra="forbid")

    entrypoint_preference: Literal["notebook", "python_script"] = "python_script"
    max_runtime_seconds: int = Field(default=3600, gt=0)
    network_access: bool = False
    yolo_approvals: bool = False


class OutputConfig(BaseModel):
    """Output paths used by the worker and the coding agent."""

    model_config = ConfigDict(extra="forbid")

    run_dir: Path
    summary_path: str
    artifacts_dir: str

    @field_validator("run_dir")
    @classmethod
    def _ensure_abs_run_dir(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("output.run_dir must be an absolute path")
        return value


class ExperimentJob(BaseModel):
    """Input job contract for the Kimi worker."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    created_at: datetime
    priority: int = 0
    repo_root: Path
    dataset_refs: list[DatasetRef] = Field(default_factory=list)
    experiment_plan: ExperimentPlan
    execution: ExecutionConfig
    output: OutputConfig

    @field_validator("repo_root")
    @classmethod
    def _ensure_abs_repo_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("repo_root must be an absolute path")
        return value


class ResultMetric(BaseModel):
    """Metric result produced by executed code."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    threshold_met: bool


class ExperimentSummary(BaseModel):
    """Structured summary embedded in the final result payload."""

    model_config = ConfigDict(extra="forbid")

    title: str
    hypotheses_tested: list[str] = Field(default_factory=list)
    metrics: list[ResultMetric] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    regimes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    """Artifact metadata entry for the experiment result."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["plot", "table", "log", "notebook", "code_diff"]
    path: str
    description: str


class ResultError(BaseModel):
    """Error entry in result payload."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    message: str
    trace: str


class ExperimentResult(BaseModel):
    """Output result contract published by the worker."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["success", "failed", "needs_human"]
    started_at: datetime
    finished_at: datetime
    attempts: int
    repo_commit: str | None
    summary: ExperimentSummary
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    errors: list[ResultError] = Field(default_factory=list)
