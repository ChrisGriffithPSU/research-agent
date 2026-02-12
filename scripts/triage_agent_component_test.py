#!/usr/bin/env python3
"""Triage workflow integration test using real workers and shared messaging.

Flow:
1) Publish two `paper.triage.request` messages.
2) `PaperTriageWorker` consumes from queue and publishes triage decisions.
3) `PDFParserWorker` consumes accepted `paper.fulltext.request` messages.
4) Verify expected outcomes:
   - 1612.09328 -> REQUEST_FULL_TEXT -> parsed
   - 1505.04597 -> REJECT_PAPER -> not parsed

Notes:
- Main process should run in ArXiv venv (aio-pika + docling).
- LLM calls are delegated to TRIAGE_VENV_PATH subprocess so triage uses your
  real OpenAI client/prompt stack without duplicating worker logic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

PASS_PAPER_ID = "1612.09328"
REJECT_PAPER_ID = "1505.04597"
_REEXEC_GUARD_ENV = "TRIAGE_TEST_ARXIV_BOOTSTRAPPED"


def load_dotenv_file() -> None:
    """Load .env from project root for local script runs."""
    dotenv_path = project_root / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step: str) -> None:
    print(f"\n[STEP] {step}")


def print_success(msg: str) -> None:
    print(f"  [OK] {msg}")


def print_error(msg: str) -> None:
    print(f"  [ERROR] {msg}")


def print_info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def _resolve_python_from_venv(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    p = Path(raw_path).expanduser()
    if p.is_file():
        return p
    for name in ("python", "python3"):
        candidate = p / "bin" / name
        if candidate.exists():
            return candidate
    return None


def _resolve_arxiv_python() -> Path | None:
    override = _resolve_python_from_venv(os.environ.get("ARXIV_VENV_PATH"))
    if override is not None:
        return override

    for candidate in [
        project_root / ".venv-arxiv" / "bin" / "python",
        project_root / ".venv_arxiv" / "bin" / "python",
        project_root / "venv-arxiv" / "bin" / "python",
        project_root / "venv_arxiv" / "bin" / "python",
        project_root / "arxiv-venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return candidate
    return None


def ensure_arxiv_venv_python() -> None:
    if os.environ.get(_REEXEC_GUARD_ENV) == "1":
        return

    target = _resolve_arxiv_python()
    if target is None:
        return

    current = Path(sys.executable).expanduser().absolute()
    target = target.expanduser().absolute()
    if current == target:
        return

    print(f"[INFO] Re-launching with ArXiv venv Python: {target}")
    env = os.environ.copy()
    env[_REEXEC_GUARD_ENV] = "1"
    os.execve(str(target), [str(target), *sys.argv], env)


def resolve_triage_python() -> Path:
    override = _resolve_python_from_venv(os.environ.get("TRIAGE_VENV_PATH"))
    if override is not None:
        return override
    default = project_root / ".venv" / "bin" / "python"
    if default.exists():
        return default
    raise RuntimeError("Set TRIAGE_VENV_PATH to the venv with OpenAI dependencies")


class SubprocessLLMResponse:
    def __init__(self, content: str):
        self.content = content


class SubprocessLLMClient:
    """Adapter that preserves PaperTriageWorker API but executes LLM in TRIAGE venv."""

    def __init__(self, triage_python: Path):
        self._triage_python = triage_python

    async def complete(self, prompt: str, **kwargs) -> SubprocessLLMResponse:
        system_prompt = kwargs.get("system", "")
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 2000)
        response_format = kwargs.get("response_format", {"type": "json_object"})

        helper = r'''
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(sys.argv[1])
prompt = sys.argv[2]
system_prompt = sys.argv[3]
temperature = float(sys.argv[4])
max_tokens = int(sys.argv[5])
response_format = json.loads(sys.argv[6])

sys.path.insert(0, str(project_root))

from src.shared.llm.openai_client import OpenAIClient

async def main() -> int:
    client = OpenAIClient()
    response = await client.complete(
        prompt=prompt,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    print(response.content)
    return 0

raise SystemExit(asyncio.run(main()))
'''

        proc = await asyncio.to_thread(
            subprocess.run,
            [
                str(self._triage_python),
                "-c",
                helper,
                str(project_root),
                prompt,
                system_prompt,
                str(temperature),
                str(max_tokens),
                json.dumps(response_format),
            ],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            check=False,
        )

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "triage subprocess failed")

        output = proc.stdout.strip()
        if not output:
            raise RuntimeError("triage subprocess returned empty response")

        return SubprocessLLMResponse(content=output.splitlines()[-1])

    async def health_check(self) -> bool:
        return True


async def ensure_pipeline_queues(connection) -> None:
    channel = connection.channel
    exchange = await channel.declare_exchange(name="researcher", type="topic", durable=True)
    for queue_name in [
        "paper.triage.request",
        "paper.triage.decision",
        "paper.fulltext.request",
        "paper.parsed",
        "paper.concepts.request",
    ]:
        queue = await channel.declare_queue(name=queue_name, durable=True)
        await queue.bind(exchange, routing_key=queue_name)


async def wait_for_queue_count(connection, queue_name: str, minimum: int, timeout_seconds: int) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        info = await connection.get_queue_info(queue_name)
        count = info["message_count"] if info else 0
        if count >= minimum:
            return True
        await asyncio.sleep(0.5)
    return False


async def collect_queue_messages(
    connection,
    queue_name: str,
    timeout_seconds: int,
    stop_when: callable | None = None,
) -> list[dict]:
    """Collect messages from a queue until timeout or stop condition.

    This reads concrete payloads (not queue depth) to avoid race conditions with
    long-running handlers where queue stats can be misleading.
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    queue = await connection.channel.declare_queue(name=queue_name, passive=True)
    out: list[dict] = []

    while asyncio.get_running_loop().time() < deadline:
        msg = await queue.get(timeout=1, fail=False)
        if msg is None:
            await asyncio.sleep(0.25)
            continue

        payload = json.loads(msg.body.decode("utf-8"))
        out.append(payload)
        await msg.ack()

        if stop_when is not None and stop_when(out):
            break

    return out


async def purge_queue(connection, queue_name: str) -> None:
    queue = await connection.channel.declare_queue(name=queue_name, passive=True)
    await queue.purge()


async def drain_queue_json(connection, queue_name: str) -> list[dict]:
    queue = await connection.channel.declare_queue(name=queue_name, passive=True)
    out: list[dict] = []
    while True:
        msg = await queue.get(timeout=1, fail=False)
        if msg is None:
            break
        out.append(json.loads(msg.body.decode("utf-8")))
        await msg.ack()
    return out


async def stop_task(task: asyncio.Task | None, timeout_seconds: int = 10) -> None:
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def run_test() -> int:
    from src.services.fetchers.arxiv.config import ArxivFetcherConfig
    from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
    from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor
    from src.shared.messaging.config import MessagingConfig
    from src.shared.messaging.connection import RabbitMQConnection
    from src.shared.messaging.consumer import MessageConsumer
    from src.shared.messaging.publisher import MessagePublisher
    from src.shared.messaging.retry import ExponentialBackoffStrategy
    from src.workers.paper_triage.worker import PaperTriageWorker
    from src.workers.pdf_parser.worker import PDFParserWorker
    from src.workers.shared.message_schemas import PaperTriageRequest

    triage_python = resolve_triage_python()

    print_header("TRIAGE AGENT COMPONENT TEST")
    print_info(f"Pass candidate: {PASS_PAPER_ID}")
    print_info(f"Reject candidate: {REJECT_PAPER_ID}")
    print_info(f"ArXiv runtime Python: {sys.executable}")
    print_info(f"Triage runtime Python: {triage_python}")
    print_info(f"Started at: {datetime.now().isoformat()}")

    connection = None
    api_client = None
    triage_consumer = None
    parser_consumer = None
    triage_task = None
    parser_task = None

    try:
        print_step("Initializing shared messaging infrastructure")
        connection = RabbitMQConnection(config=MessagingConfig())
        await connection.connect()
        await ensure_pipeline_queues(connection)
        publisher = MessagePublisher(
            connection=connection,
            retry_strategy=ExponentialBackoffStrategy(max_attempts=3),
        )
        for queue_name in [
            "paper.triage.request",
            "paper.triage.decision",
            "paper.fulltext.request",
            "paper.parsed",
        ]:
            await purge_queue(connection, queue_name)
        print_success("Messaging infrastructure ready")

        print_step("Starting PaperTriageWorker")
        triage_consumer = MessageConsumer(connection=connection, prefetch_count=2)

        triage_worker = PaperTriageWorker(
            llm_client=SubprocessLLMClient(triage_python),
            message_consumer=triage_consumer,
            message_publisher=publisher,
        )

        triage_task = asyncio.create_task(triage_worker.start())
        print_success("PaperTriageWorker started")

        print_step("Fetching metadata for two test papers")
        api_client = ArxivAPIClient(config=ArxivFetcherConfig(default_results_per_query=5))
        await api_client.initialize()
        papers = await api_client.fetch_by_ids([PASS_PAPER_ID, REJECT_PAPER_ID])
        paper_by_id = {p.paper_id: p for p in papers}

        missing = [pid for pid in [PASS_PAPER_ID, REJECT_PAPER_ID] if pid not in paper_by_id]
        if missing:
            print_error(f"Missing expected arXiv IDs: {missing}")
            return 1
        print_success("Fetched both papers")

        print_step("Publishing paper.triage.request messages")
        for paper_id in [PASS_PAPER_ID, REJECT_PAPER_ID]:
            p = paper_by_id[paper_id]
            request = PaperTriageRequest(
                paper_id=p.paper_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                categories=p.categories,
                arxiv_url=p.arxiv_url,
                pdf_url=p.pdf_url,
                submitted_date=p.submitted_date,
            )
            await publisher.publish(message=request, routing_key="paper.triage.request")
            print_info(f"Published triage request for {paper_id}")

        expected_decision_ids = {PASS_PAPER_ID, REJECT_PAPER_ID}
        print_step("Waiting for concrete triage decisions")
        decisions_payload = await collect_queue_messages(
            connection=connection,
            queue_name="paper.triage.decision",
            timeout_seconds=300,
            stop_when=lambda items: {
                item.get("paper_id") for item in items if item.get("paper_id")
            }.issuperset(expected_decision_ids),
        )

        decisions_by_id = {x["paper_id"]: x["decision"] for x in decisions_payload if "paper_id" in x}
        if not expected_decision_ids.issubset(decisions_by_id.keys()):
            missing = sorted(expected_decision_ids.difference(decisions_by_id.keys()))
            print_error(f"Timed out waiting for triage decisions for: {missing}")
            return 1

        print_info(f"Decisions: {decisions_by_id}")

        if decisions_by_id.get(REJECT_PAPER_ID) != "REJECT_PAPER":
            print_error(
                f"Reject candidate misclassified ({REJECT_PAPER_ID} -> {decisions_by_id.get(REJECT_PAPER_ID)}). "
                "Skipping PDF parsing to avoid expensive unnecessary parse."
            )
            return 1

        print_step("Starting PDFParserWorker for accepted paper(s)")
        parser_consumer = MessageConsumer(connection=connection, prefetch_count=1)
        parser_config = ArxivFetcherConfig(
            pdf_do_ocr=False,
            pdf_do_table_structure=False,
            pdf_do_cell_matching=False,
        )
        parser_worker = PDFParserWorker(
            message_consumer=parser_consumer,
            message_publisher=publisher,
            pdf_processor=PDFProcessor(config=parser_config),
        )
        parser_task = asyncio.create_task(parser_worker.start())
        print_success("PDFParserWorker started")

        expected_parsed = 1 if decisions_by_id.get(PASS_PAPER_ID) == "REQUEST_FULL_TEXT" else 0
        if expected_parsed > 0:
            parsed_payload = await collect_queue_messages(
                connection=connection,
                queue_name="paper.parsed",
                timeout_seconds=420,
                stop_when=lambda items: len(items) >= expected_parsed,
            )
            if len(parsed_payload) < expected_parsed:
                print_error("Timed out waiting for parser output")
                return 1
        else:
            parsed_payload = await drain_queue_json(connection, "paper.parsed")
        parsed_ids = [x.get("paper_id") for x in parsed_payload if x.get("paper_id")]
        print_info(f"Parsed IDs: {parsed_ids}")

        failures: list[str] = []
        if decisions_by_id.get(PASS_PAPER_ID) != "REQUEST_FULL_TEXT":
            failures.append(
                f"Expected {PASS_PAPER_ID} -> REQUEST_FULL_TEXT, got {decisions_by_id.get(PASS_PAPER_ID)}"
            )
        if decisions_by_id.get(REJECT_PAPER_ID) != "REJECT_PAPER":
            failures.append(
                f"Expected {REJECT_PAPER_ID} -> REJECT_PAPER, got {decisions_by_id.get(REJECT_PAPER_ID)}"
            )
        if PASS_PAPER_ID not in parsed_ids:
            failures.append(f"Accepted paper {PASS_PAPER_ID} was not parsed")
        if REJECT_PAPER_ID in parsed_ids:
            failures.append(f"Rejected paper {REJECT_PAPER_ID} should not be parsed")

        print_header("RESULT")
        if failures:
            for failure in failures:
                print_error(failure)
            return 1

        print_success("Triage workflow test PASSED")
        return 0

    except Exception as exc:
        print_error(f"Test failed: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        if triage_consumer is not None:
            await triage_consumer.stop(graceful=False, timeout=0)
        if parser_consumer is not None:
            await parser_consumer.stop(graceful=False, timeout=0)
        await stop_task(triage_task)
        await stop_task(parser_task)
        if api_client is not None:
            await api_client.close()
        if connection is not None:
            await connection.close()


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Triage worker integration test").parse_args()


async def main() -> int:
    _ = parse_args()
    logging.basicConfig(level=logging.INFO)
    return await run_test()


if __name__ == "__main__":
    load_dotenv_file()
    ensure_arxiv_venv_python()
    sys.exit(asyncio.run(main()))
