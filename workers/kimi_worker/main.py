"""CLI entrypoint for the Kimi experiment worker."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from workers.kimi_worker.mq_worker import run_queue_worker
from workers.kimi_worker.runner import load_job, run_job_from_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Kimi experiment worker for a job JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--job", help="Path to experiment job JSON")
    mode.add_argument("--queue", action="store_true", help="Run long-lived RabbitMQ worker mode")
    return parser


def _exit_code_for_status(status: str) -> int:
    if status == "success":
        return 0
    if status == "needs_human":
        return 2
    return 1


def main() -> int:
    load_dotenv()

    parser = _build_parser()
    args = parser.parse_args()

    if args.queue:
        try:
            asyncio.run(run_queue_worker())
            return 0
        except KeyboardInterrupt:
            print("Interrupted")
            return 1
        except Exception as exc:
            print(f"Queue worker crashed: {exc}")
            return 1

    job_path = Path(args.job).resolve()

    if not job_path.exists():
        print(f"Job file not found: {job_path}")
        return 1

    try:
        # Validate early for cleaner CLI feedback before async run.
        load_job(job_path)
    except Exception as exc:
        print(f"Invalid job file: {exc}")
        return 1

    try:
        result = asyncio.run(run_job_from_path(job_path))
    except KeyboardInterrupt:
        print("Interrupted")
        return 1
    except Exception as exc:
        print(f"Worker crashed: {exc}")
        return 1

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return _exit_code_for_status(result.status)


if __name__ == "__main__":
    sys.exit(main())
