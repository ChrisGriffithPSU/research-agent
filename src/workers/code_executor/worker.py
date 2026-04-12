"""Code Executor worker.

Takes experiment plans, uses LLM to generate experiment code,
writes it to files, runs it via subprocess, and retries with
LLM-assisted fixes on failure (up to N iterations).
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.shared.llm.openai_client import OpenAIClient
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    CodeExecutionResult,
    ExperimentEvaluationRequest,
    PlanGenerated,
)

logger = logging.getLogger(__name__)


class CodeExecutorWorker(BaseWorker):
    """Worker that generates and executes experiment code.

    Flow:
    1. Receive PlanGenerated message with experiment plan path
    2. For each experiment in the plan:
       a. Call LLM to generate Python code for the experiment
       b. Write code to a file in the artifacts directory
       c. Run via subprocess
       d. If error: feed error + code back to LLM for fix, retry (up to N times)
       e. Publish CodeExecutionResult
    """

    SYSTEM_PROMPT = (
        Path(__file__).parent.parent.parent
        / "shared"
        / "llm"
        / "prompts"
        / "code-execution-agent.txt"
    )

    def __init__(
        self,
        llm_client: OpenAIClient,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: LocalArtifactStore | None = None,
        config: WorkerConfig | None = None,
        max_fix_iterations: int = 5,
        execution_timeout_seconds: int = 300,
    ):
        config = config or WorkerConfig(
            queue_name="plan.generated",
            dlq_name="code.execution.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.llm = llm_client
        self.max_fix_iterations = max_fix_iterations
        self.execution_timeout = execution_timeout_seconds
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            return self.SYSTEM_PROMPT.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return (
                "You are a code execution agent. Generate working Python code "
                "for experiments. Return JSON with a 'code' field."
            )

    def get_message_type(self):
        return PlanGenerated

    async def process(self, message: PlanGenerated) -> None:
        """Process a plan generated message.

        Reads the plan JSON, iterates over experiments, generates
        and executes code for each one.
        """
        logger.info(
            f"Processing plan for paper: {message.paper_id} "
            f"({message.experiment_count} experiments)"
        )

        # Load the plan JSON from artifact storage
        plan_data = await self._load_plan(message.plan_json_path)
        if plan_data is None:
            logger.error(f"Could not load plan: {message.plan_json_path}")
            return

        # Extract experiments from the plan
        experiments = self._extract_experiments(plan_data)

        for experiment in experiments:
            try:
                result = await self._execute_experiment(
                    paper_id=message.paper_id,
                    experiment=experiment,
                )
                # Store result artifact
                result_key = (
                    f"{message.paper_id}/execution/"
                    f"{experiment.get('experiment_id', 'unknown')}_result.json"
                )
                result_json = json.dumps(result, indent=2, default=str)
                result_path = await self.store_artifact(
                    key=result_key,
                    data=result_json.encode("utf-8"),
                    content_type="application/json",
                )

                # Build execution result message
                execution_result = CodeExecutionResult(
                    work_id=message.work_id,
                    parent_work_id=message.parent_work_id,
                    paper_id=message.paper_id,
                    experiment_id=experiment.get("experiment_id", "unknown"),
                    hypothesis_id=experiment.get("hypothesis_id", "unknown"),
                    status=result["status"],
                    code_path=result.get("code_path"),
                    stdout=result.get("stdout"),
                    stderr=result.get("stderr"),
                    exit_code=result.get("exit_code"),
                    result_data=result.get("result_data"),
                    fix_iterations=result.get("fix_iterations", 0),
                    fix_history=result.get("fix_history", []),
                    artifact_refs=[result_path],
                )

                await self.publish("code.execution.result", execution_result)

                # Also publish evaluation request
                eval_request = ExperimentEvaluationRequest(
                    work_id=message.work_id,
                    parent_work_id=message.parent_work_id,
                    paper_id=message.paper_id,
                    experiment_id=experiment.get("experiment_id", "unknown"),
                    hypothesis_id=experiment.get("hypothesis_id", "unknown"),
                    execution_status=result["status"],
                    execution_result=result.get("result_data"),
                    stdout=result.get("stdout"),
                    stderr=result.get("stderr"),
                )
                await self.publish("experiment.evaluation.request", eval_request)

            except Exception as e:
                logger.exception(
                    f"Failed to process experiment "
                    f"{experiment.get('experiment_id', 'unknown')}: {e}"
                )

    async def _load_plan(self, plan_path: str) -> dict[str, Any] | None:
        """Load plan JSON from artifact storage."""
        try:
            # Try to load from local path
            path = Path(plan_path)
            if path.exists():
                data = path.read_text(encoding="utf-8")
                return json.loads(data)

            # Try loading from artifact store
            data = await self.artifact_store.retrieve(plan_path)
            if data:
                return json.loads(data.decode("utf-8"))

            # Try as relative key
            key = str(path).replace("\\", "/")
            # Strip artifacts base dir prefix if present
            artifacts_dir = os.getenv("ARTIFACTS_BASE_DIR", "./artifacts")
            if key.startswith(artifacts_dir):
                key = key[len(artifacts_dir) :].lstrip("/\\")

            data = await self.artifact_store.retrieve(key)
            if data:
                return json.loads(data.decode("utf-8"))

            logger.error(f"Plan not found at: {plan_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to load plan from {plan_path}: {e}")
            return None

    def _extract_experiments(self, plan_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract individual experiments from plan data."""
        experiments = []

        for package in plan_data.get("experiment_packages", []):
            concept_id = package.get("concept_id", "unknown")
            concept_name = package.get("concept_name", "unknown")

            for experiment in package.get("experiments", []):
                experiment["concept_id"] = concept_id
                experiment["concept_name"] = concept_name
                experiments.append(experiment)

        return experiments

    async def _execute_experiment(
        self,
        paper_id: str,
        experiment: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate, run, and potentially fix code for one experiment.

        Returns a dict with status, code_path, stdout, stderr, exit_code,
        result_data, fix_iterations, fix_history.
        """
        experiment_id = experiment.get("experiment_id", "unknown")
        fix_history: list[dict[str, str]] = []

        # Prepare the experiment spec for LLM
        llm_input = json.dumps(experiment, indent=2)

        for iteration in range(self.max_fix_iterations + 1):
            # Generate code
            if iteration == 0:
                prompt = self._build_initial_prompt(llm_input)
            else:
                last_error = fix_history[-1]["error"] if fix_history else ""
                last_code_summary = fix_history[-1].get("code_summary", "")
                prompt = self._build_fix_prompt(last_code_summary, last_error, experiment)

            code_response = await self._generate_code(prompt)
            if code_response is None:
                return {
                    "status": "failed",
                    "code_path": None,
                    "stdout": None,
                    "stderr": "LLM failed to generate code",
                    "exit_code": -1,
                    "result_data": None,
                    "fix_iterations": iteration,
                    "fix_history": fix_history,
                }

            code = code_response.get("code", "")
            if not code:
                return {
                    "status": "failed",
                    "code_path": None,
                    "stdout": None,
                    "stderr": "LLM returned empty code",
                    "exit_code": -1,
                    "result_data": None,
                    "fix_iterations": iteration,
                    "fix_history": fix_history,
                }

            # Write code to file
            code_dir = f"{paper_id}/execution"
            code_filename = f"{experiment_id}_v{iteration}.py"
            code_key = f"{code_dir}/{code_filename}"
            code_path = await self.store_artifact(
                key=code_key,
                data=code.encode("utf-8"),
                content_type="text/x-python",
            )

            # Run the code
            run_result = await self._run_code(code, code_path)

            if run_result["exit_code"] == 0:
                # Parse result data from stdout
                result_data = self._parse_stdout(run_result["stdout"])
                return {
                    "status": "success",
                    "code_path": code_path,
                    "stdout": run_result["stdout"],
                    "stderr": run_result["stderr"],
                    "exit_code": 0,
                    "result_data": result_data,
                    "fix_iterations": iteration,
                    "fix_history": fix_history,
                }

            # Code failed - record error for fix attempt
            error_msg = run_result["stderr"] or run_result["stdout"] or "Unknown error"
            fix_history.append(
                {
                    "iteration": str(iteration),
                    "code_summary": code[:500] + ("..." if len(code) > 500 else ""),
                    "error": error_msg[:2000],
                }
            )

            logger.warning(
                f"Experiment {experiment_id} failed on iteration {iteration}: {error_msg[:200]}"
            )

        # Exhausted all fix iterations
        return {
            "status": "escalated",
            "code_path": code_path if iteration > 0 else None,
            "stdout": run_result.get("stdout"),
            "stderr": run_result.get("stderr"),
            "exit_code": run_result.get("exit_code", -1),
            "result_data": None,
            "fix_iterations": self.max_fix_iterations,
            "fix_history": fix_history,
        }

    def _build_initial_prompt(self, experiment_spec: str) -> str:
        return json.dumps(
            {
                "task": "generate",
                "experiment_spec": experiment_spec,
            },
            indent=2,
        )

    def _build_fix_prompt(self, code_summary: str, error: str, experiment: dict[str, Any]) -> str:
        return json.dumps(
            {
                "task": "fix",
                "experiment_id": experiment.get("experiment_id", "unknown"),
                "experiment_goal": experiment.get("goal", ""),
                "code_summary": code_summary,
                "error_output": error,
            },
            indent=2,
        )

    async def _generate_code(self, prompt: str) -> dict[str, Any] | None:
        """Call LLM to generate or fix code."""
        try:
            response = await self.llm.complete(
                prompt=prompt,
                system=self._system_prompt,
                temperature=0.2,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            return json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM code response: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def _run_code(self, code: str, code_path: str) -> dict[str, Any]:
        """Run Python code in a subprocess.

        Returns dict with stdout, stderr, exit_code.
        """
        # Write to a temp file for execution
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(code_path).parent),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.execution_timeout,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "stdout": None,
                    "stderr": f"Execution timed out after {self.execution_timeout}s",
                    "exit_code": -1,
                }

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else -1

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            }
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    @staticmethod
    def _parse_stdout(stdout: str | None) -> dict[str, Any] | None:
        """Try to parse JSON from the last line of stdout."""
        if not stdout:
            return None

        # Try to find JSON in the output (last non-empty line first)
        lines = stdout.strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                result = json.loads(line)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

        # Try the whole output
        try:
            result = json.loads(stdout.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        return {"raw_output": stdout}

    async def health_check(self) -> bool:
        return await self.llm.health_check()
