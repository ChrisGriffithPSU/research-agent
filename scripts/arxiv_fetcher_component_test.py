#!/usr/bin/env python3
"""ArXiv fetcher component test using project messaging/worker infrastructure.

Flow:
1) Fetch one paper from arXiv category.
2) Publish `paper.triage.request`.
3) Publish `paper.fulltext.request`.
4) Run `PDFParserWorker` (real worker) to consume full-text request.
5) Verify `paper.parsed` was emitted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

_REEXEC_GUARD_ENV = "ARXIV_TEST_VENV_BOOTSTRAPPED"


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


def _resolve_arxiv_python() -> Path | None:
    override = os.environ.get("ARXIV_VENV_PATH")
    if override:
        p = Path(override).expanduser()
        if p.is_file():
            return p
        for name in ("python", "python3"):
            candidate = p / "bin" / name
            if candidate.exists():
                return candidate

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

    target_python = _resolve_arxiv_python()
    if target_python is None:
        return

    current_python = Path(sys.executable).expanduser().absolute()
    target_python = target_python.expanduser().absolute()
    if current_python == target_python:
        return

    print(f"[INFO] Re-launching with ArXiv venv Python: {target_python}")
    env = os.environ.copy()
    env[_REEXEC_GUARD_ENV] = "1"
    os.execve(str(target_python), [str(target_python), *sys.argv], env)


async def ensure_pipeline_queues(connection) -> None:
    channel = connection.channel
    exchange = await channel.declare_exchange(name="researcher", type="topic", durable=True)
    for queue_name in [
        "paper.triage.request",
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


async def wait_for_single_message(connection, queue_name: str, timeout_seconds: int):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    queue = await connection.channel.declare_queue(name=queue_name, passive=True)

    while asyncio.get_running_loop().time() < deadline:
        message = await queue.get(timeout=1, fail=False)
        if message is not None:
            return message
    return None


async def purge_queue(connection, queue_name: str) -> None:
    queue = await connection.channel.declare_queue(name=queue_name, passive=True)
    await queue.purge()


async def run_test(category: str, max_papers: int, days_back: int) -> int:
    from src.services.fetchers.arxiv.config import ArxivFetcherConfig
    from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
    from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor
    from src.shared.messaging.config import MessagingConfig
    from src.shared.messaging.connection import RabbitMQConnection
    from src.shared.messaging.consumer import MessageConsumer
    from src.shared.messaging.publisher import MessagePublisher
    from src.shared.messaging.retry import ExponentialBackoffStrategy
    from src.workers.pdf_parser.worker import PDFParserWorker
    from src.workers.shared.message_schemas import FullTextRequest, PaperTriageRequest

    print_header("ARXIV FETCHER COMPONENT TEST")
    print_info(f"Category: {category}")
    print_info(f"Max papers: {max_papers}")
    print_info(f"Days back: {days_back}")
    print_info(f"Started at: {datetime.now().isoformat()}")

    connection = None
    api_client = None

    try:
        print_step("Initializing shared RabbitMQ connection/publisher")
        connection = RabbitMQConnection(config=MessagingConfig())
        await connection.connect()
        await ensure_pipeline_queues(connection)
        publisher = MessagePublisher(
            connection=connection,
            retry_strategy=ExponentialBackoffStrategy(max_attempts=3),
        )
        for queue_name in ["paper.triage.request", "paper.fulltext.request", "paper.parsed"]:
            await purge_queue(connection, queue_name)
        print_success("Messaging infrastructure ready")

        print_step("Fetching paper from arXiv")
        fetcher_config = ArxivFetcherConfig(
            categories=[category],
            default_results_per_query=max_papers,
            rate_limit_requests_per_second=0.5,
        )
        api_client = ArxivAPIClient(config=fetcher_config)
        await api_client.initialize()

        papers = await api_client.fetch_by_categories(
            categories=[category],
            max_per_category=max_papers,
            days_back=days_back,
        )
        if not papers:
            print_error("No papers returned for category/time window")
            return 1

        paper = next((p for p in papers if p.pdf_url), papers[0])
        print_success(f"Fetched {len(papers)} papers")
        print_info(f"Selected: {paper.paper_id}")
        print_info(f"Title: {paper.title[:90]}")

        print_step("Publishing triage request using shared MessagePublisher")
        triage_message = PaperTriageRequest(
            paper_id=paper.paper_id,
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            arxiv_url=paper.arxiv_url,
            pdf_url=paper.pdf_url,
            submitted_date=paper.submitted_date,
        )
        await publisher.publish(message=triage_message, routing_key="paper.triage.request")
        print_success("Published paper.triage.request")

        print_step("Starting PDFParserWorker and publishing full-text request")
        parser_config = ArxivFetcherConfig(
            pdf_do_ocr=False,
            pdf_do_table_structure=False,
            pdf_do_cell_matching=False,
        )
        parser_consumer = MessageConsumer(connection=connection, prefetch_count=1)
        parser_worker = PDFParserWorker(
            message_consumer=parser_consumer,
            message_publisher=publisher,
            pdf_processor=PDFProcessor(config=parser_config),
        )
        parser_task = asyncio.create_task(parser_worker.start())

        fulltext = FullTextRequest(
            paper_id=paper.paper_id,
            pdf_url=paper.pdf_url,
            triage_decision={"decision": "REQUEST_FULL_TEXT", "source": "component_test"},
        )
        await publisher.publish(message=fulltext, routing_key="paper.fulltext.request")
        print_success("Published paper.fulltext.request")

        parsed_message = await wait_for_single_message(
            connection=connection,
            queue_name="paper.parsed",
            timeout_seconds=300,
        )

        await parser_consumer.stop(graceful=False, timeout=0)
        try:
            await asyncio.wait_for(parser_task, timeout=10)
        except asyncio.TimeoutError:
            parser_task.cancel()
            await asyncio.gather(parser_task, return_exceptions=True)

        if parsed_message is None:
            print_error("Timed out waiting for paper.parsed")
            return 1

        payload = parsed_message.body.decode("utf-8")
        await parsed_message.ack()

        try:
            parsed_data = json.loads(payload)
            parsed_id = parsed_data.get("paper_id", "unknown")
            print_info(f"Received paper.parsed for: {parsed_id}")
        except Exception:
            print_info("Received paper.parsed message")

        parsed_info = await connection.get_queue_info("paper.parsed")
        parsed_count = parsed_info["message_count"] if parsed_info else 0
        print_success("PDFParserWorker consumed full-text request")
        print_info(f"paper.parsed queue depth: {parsed_count}")

        print_header("RESULT")
        print_success("ArXiv fetch -> publish -> PDFParserWorker parse PASSED")
        return 0

    except Exception as exc:
        print_error(f"Test failed: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        if api_client is not None:
            await api_client.close()
        if connection is not None:
            await connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ArXiv fetcher component integration test")
    parser.add_argument("--category", default="cs.LG")
    parser.add_argument("--max-papers", type=int, default=1)
    parser.add_argument("--days-back", type=int, default=7)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    return await run_test(args.category, args.max_papers, args.days_back)


if __name__ == "__main__":
    ensure_arxiv_venv_python()
    sys.exit(asyncio.run(main()))
