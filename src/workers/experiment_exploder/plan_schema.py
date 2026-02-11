"""Pydantic models for Experiment Exploder plan JSON.

The Experiment Exploder prompt specifies a concrete JSON schema. This module
provides best-effort validation so downstream code can rely on the shape.
"""

from __future__ import annotations

from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class CandidateObservationLens(BaseModel):
    model_config = ConfigDict(extra="allow")

    lens_name: str
    observables: List[str] = Field(default_factory=list)
    notes: str = ""


class Manifestation(BaseModel):
    model_config = ConfigDict(extra="allow")

    manifestation_type: str
    description: str
    candidate_observation_lenses: List[CandidateObservationLens] = Field(default_factory=list)


class BinaryOutcomeDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    true_if: str
    false_if: str


class DiscriminatingTest(BaseModel):
    model_config = ConfigDict(extra="allow")

    test_name: str
    binary_outcome_definition: BinaryOutcomeDefinition


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="allow")

    hypothesis_id: str
    track: Literal["A", "B"]
    statement: str
    mechanism: str
    predictions: List[str] = Field(default_factory=list)
    discriminating_test: DiscriminatingTest
    minimal_viable_experiment: str
    kill_criteria: str
    promote_criteria: str
    status: Literal["proposed", "active", "killed", "promoted"] = "proposed"
    notes: str = ""


class MatrixEffect(BaseModel):
    model_config = ConfigDict(extra="allow")

    hypothesis_id: str
    effect: Literal["kills", "supports", "irrelevant"]


class DiscriminatingTestMatrixRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    test_name: str
    effects: List[MatrixEffect] = Field(default_factory=list)
    notes: str = ""


class PassFailContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    pass_if: str
    fail_if: str


class Batch(BaseModel):
    model_config = ConfigDict(extra="allow")

    batch_id: str
    purpose: Literal[
        "baseline",
        "comparison",
        "normalization",
        "conditioning",
        "confound_null",
        "symmetry",
        "other",
    ]
    hypotheses_targeted: List[str] = Field(default_factory=list)
    required_inputs: str
    outputs: str
    pass_fail_contract: PassFailContract
    notes: str = ""


class HorizonSeconds(BaseModel):
    model_config = ConfigDict(extra="allow")

    min: int
    max: int


class ExperimentalDesign(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit_of_analysis: str
    conditioning: List[str] = Field(default_factory=list)
    controls: List[str] = Field(default_factory=list)
    train_test_protocol: str
    regime_splits: List[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    primary_metrics: List[str] = Field(default_factory=list)
    secondary_metrics: List[str] = Field(default_factory=list)
    acceptance_thresholds: List[str] = Field(default_factory=list)
    kill_criteria: List[str] = Field(default_factory=list)


class RobustnessPerturbation(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    values: List[str] = Field(default_factory=list)
    expected_effect_if_real: str
    failure_signature: str


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    description: str
    why_it_matters: str


class EstimatedCost(BaseModel):
    model_config = ConfigDict(extra="allow")

    relative_compute: str
    relative_time_to_run: str


class Priority(BaseModel):
    model_config = ConfigDict(extra="allow")

    score_0_to_100: int
    rationale: str


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    experiment_id: str
    hypothesis_id: str
    experiment_name: str
    goal: str
    observables_required: List[str] = Field(default_factory=list)
    preprocessing: List[str] = Field(default_factory=list)
    test_horizon_seconds: HorizonSeconds
    experimental_design: ExperimentalDesign
    evaluation: Evaluation
    robustness_perturbations: List[RobustnessPerturbation] = Field(default_factory=list)
    diagnostics_to_generate: List[Diagnostic] = Field(default_factory=list)
    latency_sensitivity_notes: str
    estimated_cost: EstimatedCost
    priority: Priority


class ExperimentPackage(BaseModel):
    model_config = ConfigDict(extra="allow")

    concept_id: str
    concept_name: str
    invariant_restatement: str
    manifestation_space: List[Manifestation] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    discriminating_test_matrix: List[DiscriminatingTestMatrixRow] = Field(default_factory=list)
    batches: List[Batch] = Field(default_factory=list)
    experiments: List[ExperimentSpec] = Field(default_factory=list)


class PlanMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_experiments_per_concept: int = 0
    max_total_experiments: int = 0
    produced_total_experiments: int = 0


class ExperimentExploderPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    batch_id: str
    experiment_packages: List[ExperimentPackage] = Field(default_factory=list)
    meta: PlanMeta = Field(default_factory=PlanMeta)

    def inferred_experiment_count(self) -> int:
        return sum(len(pkg.experiments) for pkg in self.experiment_packages)


def coerce_plan(data: Any) -> ExperimentExploderPlan | None:
    """Best-effort validation. Returns None if validation fails."""

    try:
        return ExperimentExploderPlan.model_validate(data)
    except Exception:
        return None
