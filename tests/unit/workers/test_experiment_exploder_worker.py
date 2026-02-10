"""Unit tests for experiment exploder worker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.experiment_exploder.worker import ExperimentExploderWorker
from src.workers.shared.message_schemas import ConceptObject, ConceptsGenerated
from tests.helpers.fakes import DummyConsumer, DummyLLMClient, DummyPublisher


def _plan_payload() -> str:
    return json.dumps(
        {
            "batch_id": "b1",
            "experiment_packages": [{"id": "e1"}],
            "meta": {"produced_total_experiments": 1},
        }
    )


def _concepts_msg() -> ConceptsGenerated:
    concept = ConceptObject(
        concept_id="c1",
        concept_name="name",
        origin_domain="domain",
        concept_summary="summary",
        core_problem_it_solves="problem",
    )
    return ConceptsGenerated(
        paper_id="p1",
        concept_objects=[concept],
        concepts_json_path="artifacts/p1/concepts.json",
    )


@pytest.mark.asyncio
async def test_process_writes_plan_and_publishes_notifications(tmp_path: Path) -> None:
    worker = ExperimentExploderWorker(
        llm_client=DummyLLMClient(_plan_payload()),  # type: ignore[arg-type]
        message_consumer=DummyConsumer(),  # type: ignore[arg-type]
        message_publisher=DummyPublisher(),  # type: ignore[arg-type]
        artifact_store=LocalArtifactStore(base_dir=str(tmp_path)),
    )
    await worker.process(_concepts_msg())

    assert (tmp_path / "p1" / "plan" / "plan.json").exists()
    published = worker.publisher.published  # type: ignore[attr-defined]
    assert [entry["routing_key"] for entry in published] == ["notify.send", "plan.generated"]
    assert published[1]["message"]["paper_id"] == "p1"
