"""Experiment Evaluator worker.

Uses LLM to evaluate the results of executed experiments and decide
whether to PROMOTE, KILL, INVESTIGATE, or RETRY.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.shared.llm.openai_client import OpenAIClient
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    ExperimentEvaluationRequest,
    ExperimentEvaluationResult,
    NotificationRequest,
)

logger = logging.getLogger(__name__)


class ExperimentEvaluatorWorker(BaseWorker):
    """Worker that evaluates experiment execution results.

    Takes the stdout/stderr/metrics from a code execution and asks
    an LLM to determine whether the experiment is worth pursuing.
    """

    SYSTEM_PROMPT = (
        Path(__file__).parent.parent.parent
        / "shared"
        / "llm"
        / "prompts"
        / "experiment-evaluator-agent.txt"
    )

    def __init__(
        self,
        llm_client: OpenAIClient,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: LocalArtifactStore | None = None,
        config: WorkerConfig | None = None,
    ):
        config = config or WorkerConfig(
            queue_name="experiment.evaluation.request",
            dlq_name="experiment.evaluation.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.llm = llm_client
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            return self.SYSTEM_PROMPT.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return (
                "You are an experiment evaluator. Evaluate experiment results "
                "and return JSON with recommendation, confidence, reasoning."
            )

    def get_message_type(self):
        return ExperimentEvaluationRequest

    async def process(self, message: ExperimentEvaluationRequest) -> None:
        """Process an evaluation request."""
        logger.info(
            f"Evaluating experiment {message.experiment_id} "
            f"for paper {message.paper_id} (status: {message.execution_status})"
        )

        # Build LLM input
        llm_input = self._prepare_llm_input(message)

        # Get evaluation from LLM
        evaluation = await self._evaluate(llm_input)

        # Store evaluation artifact
        eval_key = f"{message.paper_id}/evaluation/{message.experiment_id}_evaluation.json"
        eval_json = json.dumps(evaluation, indent=2, default=str)
        eval_path = await self.store_artifact(
            key=eval_key,
            data=eval_json.encode("utf-8"),
            content_type="application/json",
        )

        # Build and publish evaluation result
        result = ExperimentEvaluationResult(
            work_id=message.work_id,
            parent_work_id=message.parent_work_id,
            paper_id=message.paper_id,
            experiment_id=message.experiment_id,
            hypothesis_id=message.hypothesis_id,
            recommendation=evaluation.get("recommendation", "INVESTIGATE"),
            confidence=evaluation.get("confidence", 0.5),
            reasoning=evaluation.get("reasoning", "Evaluation completed"),
            key_findings=evaluation.get("key_findings", []),
            next_steps=evaluation.get("next_steps", []),
            artifact_refs=[eval_path],
        )

        await self.publish("experiment.evaluation.result", result)

        # Send notification for PROMOTE or escalated results
        if result.recommendation in ("PROMOTE", "INVESTIGATE"):
            notification = NotificationRequest(
                work_id=message.work_id,
                parent_work_id=message.parent_work_id,
                paper_id=message.paper_id,
                experiment_id=message.experiment_id,
                status="SUCCESS" if result.recommendation == "PROMOTE" else "NEEDS_HUMAN",
                title=f"Experiment {message.experiment_id}: {result.recommendation}",
                message=(
                    f"Paper: {message.paper_id}\n"
                    f"Hypothesis: {message.hypothesis_id}\n"
                    f"Recommendation: {result.recommendation}\n"
                    f"Confidence: {result.confidence:.2f}\n"
                    f"Reasoning: {result.reasoning}"
                ),
                artifact_refs=[eval_path],
                recommendation=result.recommendation,
            )
            await self.publish("notify.send", notification)

        logger.info(
            f"Evaluated {message.experiment_id}: "
            f"{result.recommendation} (confidence: {result.confidence:.2f})"
        )

    def _prepare_llm_input(self, message: ExperimentEvaluationRequest) -> str:
        """Build the LLM input from evaluation request."""
        input_data = {
            "experiment_id": message.experiment_id,
            "hypothesis_id": message.hypothesis_id,
            "execution_status": message.execution_status,
            "stdout": (message.stdout or "")[:5000],  # Truncate large outputs
            "stderr": (message.stderr or "")[:3000],
            "result_data": message.execution_result,
        }
        return json.dumps(input_data, indent=2)

    async def _evaluate(self, llm_input: str) -> dict[str, Any]:
        """Call LLM to evaluate experiment results."""
        try:
            response = await self.llm.complete(
                prompt=llm_input,
                system=self._system_prompt,
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.content)

            # Validate required fields with defaults
            if "recommendation" not in result:
                result["recommendation"] = "INVESTIGATE"
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "reasoning" not in result:
                result["reasoning"] = "Evaluation completed"
            if "key_findings" not in result:
                result["key_findings"] = []
            if "next_steps" not in result:
                result["next_steps"] = []

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM evaluation response: {e}")
            return {
                "recommendation": "INVESTIGATE",
                "confidence": 0.3,
                "reasoning": f"Parse error during evaluation: {str(e)}",
                "key_findings": [],
                "next_steps": ["Manual review recommended"],
            }
        except Exception as e:
            logger.error(f"LLM evaluation call failed: {e}")
            return {
                "recommendation": "INVESTIGATE",
                "confidence": 0.3,
                "reasoning": f"Evaluation failed: {str(e)}",
                "key_findings": [],
                "next_steps": ["Manual review recommended"],
            }

    async def health_check(self) -> bool:
        return await self.llm.health_check()
