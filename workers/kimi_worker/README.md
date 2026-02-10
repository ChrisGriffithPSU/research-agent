# Kimi Worker

This worker executes a single Experiment Job JSON using the low-level Kimi Agent SDK `Session` API.

It creates a run workspace, streams agent output, applies policy-based approvals, performs bounded retries, validates outputs, and writes a deterministic `result.json` payload.

## How To Run Locally

1. Ensure Kimi Code CLI is installed and configured on this machine.
2. Install dependencies:

```bash
uv sync
```

Optional `.env` overrides (recommended for existing codebases):

```bash
KIMI_WORKER_REPO_ROOT=/absolute/path/to/your/repo
KIMI_WORKER_RUNS_ROOT=/absolute/path/to/your/repo/runs
```

- `KIMI_WORKER_REPO_ROOT` overrides `repo_root` from the job JSON.
- `KIMI_WORKER_RUNS_ROOT` rewrites `output.run_dir` to `<runs_root>/<job_id>`.

3. Run with the example job:

```bash
python -m workers.kimi_worker.main --job runs/example_job.json
```

Queue-integrated mode (Option 1):

```bash
python -m workers.kimi_worker.main --queue
```

Or through the app CLI:

```bash
python -m src.main worker kimi
```

Queue mode environment variables:

```bash
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
KIMI_WORKER_EXCHANGE=researcher
KIMI_WORKER_JOB_QUEUE=experiment.job.request
KIMI_WORKER_JOB_ROUTING_KEY=experiment.job.request
KIMI_WORKER_RESULT_QUEUE=experiment.result
KIMI_WORKER_RESULT_ROUTING_KEY=experiment.result
KIMI_WORKER_PREFETCH=1
```

In queue mode, the worker consumes `ExperimentJob` JSON from the configured routing key and publishes `ExperimentResult` JSON to `KIMI_WORKER_RESULT_ROUTING_KEY`.

Expected outputs:
- `runs/<job_id>/job.json`
- `runs/<job_id>/logs/worker.log`
- `runs/<job_id>/logs/agent_stream.txt`
- `runs/<job_id>/results/summary.json` (produced by the coding agent)
- `runs/<job_id>/results/result.json` (produced by the worker)
- at least one artifact in `runs/<job_id>/artifacts/`

## What This Worker Implements

- Low-level `Session.create(...)` + `Session.prompt(...)` integration.
- Manual approval handling via `ApprovalPolicy` with:
  - allowlist
  - blocklist
  - network gating
  - optional YOLO mode per job
- Retry model: initial run + up to 2 repair cycles.
- Watchdog cancellation for "no progress" (default 300 seconds; override via `KIMI_WORKER_STUCK_TIMEOUT_SECONDS`).
- Runtime budget enforcement using `job.execution.max_runtime_seconds`.
- Deterministic result envelope with status, summary, artifacts, and structured errors.

## Assumptions

- This module focuses on single-job execution from JSON (`--job ...`) and file outputs.
- Queue integration is available via `--queue` and RabbitMQ environment variables.
- Relative output paths in job JSON are resolved against `repo_root`.
- The worker requires `output.run_dir` to be an absolute path.
