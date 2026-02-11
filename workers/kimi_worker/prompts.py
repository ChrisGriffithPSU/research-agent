"""Prompt builders for the Kimi experiment worker."""

from __future__ import annotations

import json

from workers.kimi_worker.approvals import ApprovalPolicy
from workers.kimi_worker.models import ExperimentJob


def build_task_packet(job: ExperimentJob) -> str:
    """Build the single initial task packet sent to the coding agent."""
    job_json = json.dumps(job.model_dump(mode="json"), indent=2)
    summary_path = job.output.summary_path
    artifacts_dir = job.output.artifacts_dir
    job_file_hint = f"runs/{job.job_id}/job.json"
    return f"""
You are the coding-and-execution agent for an autonomous MFT experiment worker.

You must execute the provided experiment job inside the repository and produce concrete files.
Do not return prose-only output.

Approval/runtime constraints:
- {ApprovalPolicy.policy_text()}
- If any command is rejected, immediately propose a safe alternative and continue.

Repository conventions (adapt if repo differs, and note differences in logs):
- Notebooks: notebooks/experiments/
- Python modules: src/
- Tests: tests/
- Dependency setup: uv sync --extra main (preferred) or uv pip install -r requirements.txt
- Notebook execution: python -m jupyter nbconvert --to notebook --execute ... (or papermill if available)

Hard requirements:
1) Inspect repository structure quickly.
2) Implement experiment code (notebook or python script based on job preference).
3) Create a fast smoke test before heavy execution.
4) Execute the experiment end-to-end.
5) Save artifacts (including at least one PNG plot) into {artifacts_dir}.
6) Write {summary_path} exactly in the required schema.
7) Do not invent results. Only report metrics produced by executed code.

Failure-handling requirements:
- If execution fails, read error logs/output, propose a fix, apply it, and rerun.
- Keep fixes minimal and deterministic.

Definition of Done (must all be true):
- Code changes are applied in repo.
- Experiment entrypoint exists and is runnable.
- summary.json exists and validates against this shape:
  {{
    "title": "string",
    "hypotheses_tested": ["string"],
    "metrics": [{{"name": "string", "value": 0.0, "threshold_met": true}}],
    "key_findings": ["string"],
    "regimes": ["string"],
    "next_steps": ["string"]
  }}
- At least one PNG exists in artifacts directory.

Preferred script CLI contract (if you create a Python script):
python <script> --job {job_file_hint} --out {summary_path} --artifacts {artifacts_dir}

Full Experiment Job JSON:
```json
{job_json}
```
""".strip()


def build_repair_packet(job: ExperimentJob, attempt: int, last_error: str, log_snippet: str) -> str:
    """Build a targeted repair prompt for retries."""
    job_json = json.dumps(job.model_dump(mode="json"), indent=2)
    summary_path = job.output.summary_path
    artifacts_dir = job.output.artifacts_dir
    return f"""
Repair attempt {attempt}.

The previous run did not satisfy Definition of Done.

Last error:
{last_error}

Relevant log snippet:
```text
{log_snippet}
```

Now do the following exactly:
1) Diagnose root cause from logs and files.
2) Apply the smallest correct code/config fix.
3) Re-run smoke test first, then full run.
4) Ensure {summary_path} is valid.
5) Ensure at least one PNG plot exists in {artifacts_dir}.
6) Do not invent metrics; only report computed values.

If a command is rejected by policy, propose a safe local alternative and continue.

Job JSON (for reference):
```json
{job_json}
```
""".strip()
