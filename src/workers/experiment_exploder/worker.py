"""Experiment Exploder Agent worker.

Takes concept objects and generates testable hypotheses and experiment specs.
Produces hypothesis trees with falsifiable experiments for MFT research.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.shared.llm.openai_client import OpenAIClient
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.experiment_exploder.plan_schema import coerce_plan
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    ConceptsGenerated,
    NotificationRequest,
    PlanGenerated,
)

logger = logging.getLogger(__name__)


class ExperimentExploderWorker(BaseWorker):
    """Worker that explodes concepts into experiment plans."""

    SYSTEM_PROMPT = (
        Path(__file__).parent.parent.parent / "shared" / "llm" / "prompts" / "experiment-agent.txt"
    )

    def __init__(
        self,
        llm_client: OpenAIClient,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: LocalArtifactStore | None = None,
        config: WorkerConfig | None = None,
        max_experiments_per_concept: int = 5,
        max_total_experiments: int = 20,
        holding_time_min: int = 5,
        holding_time_max: int = 30,
    ):
        config = config or WorkerConfig(
            queue_name="plan.generate.request",
            dlq_name="plan.generate.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.llm = llm_client
        self.max_experiments_per_concept = max_experiments_per_concept
        self.max_total_experiments = max_total_experiments
        self.holding_time_min = holding_time_min
        self.holding_time_max = holding_time_max
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            return self.SYSTEM_PROMPT.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return (
                "You are an experiment exploder. Generate testable hypotheses "
                "and experiment specifications from concept objects. Return valid JSON."
            )

    def get_message_type(self):
        return ConceptsGenerated

    async def process(self, message: ConceptsGenerated) -> None:
        logger.info(
            f"Exploding {len(message.concept_objects)} concepts for paper: {message.paper_id}"
        )

        llm_input = self._prepare_llm_input(message)
        plan_data = await self._generate_plan(llm_input)

        # Best-effort shape validation
        plan_model = coerce_plan(plan_data)
        if plan_model is None:
            logger.warning("Experiment plan did not validate against expected schema")

        produced_total = plan_data.get("meta", {}).get("produced_total_experiments")
        if not isinstance(produced_total, int):
            produced_total = plan_model.inferred_experiment_count() if plan_model else 0

        # Store plan.json artifact
        plan_json = json.dumps(plan_data, indent=2)
        artifact_key = f"{message.paper_id}/plan/plan.json"
        artifact_path = await self.store_artifact(
            key=artifact_key,
            data=plan_json.encode("utf-8"),
            content_type="application/json",
        )

        # Publish notification
        notification = NotificationRequest(
            work_id=message.work_id,
            parent_work_id=message.parent_work_id,
            paper_id=message.paper_id,
            status="INFO",
            title=f"Experiment Plan Generated for {message.paper_id}",
            message=(
                f"Generated experiment plan with "
                f"{produced_total} "
                f"experiments from {len(message.concept_objects)} concepts"
            ),
            artifact_refs=[artifact_path, message.concepts_json_path],
        )
        await self.publish("notify.send", notification)

        # Publish plan generated message for code executor
        plan_generated = PlanGenerated(
            work_id=message.work_id,
            parent_work_id=message.parent_work_id,
            paper_id=message.paper_id,
            plan_json_path=artifact_path,
            batch_id=plan_data.get("batch_id"),
            experiment_count=produced_total,
        )
        await self.publish("plan.generated", plan_generated)

        logger.info(f"Experiment plan generated for: {message.paper_id}")

    def _prepare_llm_input(self, message: ConceptsGenerated) -> str:
        concept_dicts = [concept.model_dump() for concept in message.concept_objects]

        input_data = {
            "batch_id": message.work_id,
            "concept_objects": concept_dicts,
            "research_constraints": {
                "holding_time_seconds_min": self.holding_time_min,
                "holding_time_seconds_max": self.holding_time_max,
                "market_focus": ["equity", "futures", "crypto"],
                "data_available": [
                    "LOB events",
                    "trades",
                    "quotes",
                    "midprice",
                    "spread",
                    "depth",
                ],
                "max_experiments_per_concept": self.max_experiments_per_concept,
                "max_total_experiments": self.max_total_experiments,
                "latency_assumptions_ms": {
                    "min": 1,
                    "max": 200,
                },
            },
        }

        return json.dumps(input_data, indent=2)

    async def _generate_plan(self, llm_input: str) -> dict[str, Any]:
        try:
            response = await self.llm.complete(
                prompt=llm_input,
                system=self._system_prompt,
                temperature=0.4,
                max_tokens=6000,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.content)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                "batch_id": "error",
                "experiment_packages": [],
                "meta": {
                    "max_experiments_per_concept": self.max_experiments_per_concept,
                    "max_total_experiments": self.max_total_experiments,
                    "produced_total_experiments": 0,
                    "error": f"Parse error: {str(e)}",
                },
            }
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def health_check(self) -> bool:
        return await self.llm.health_check()
