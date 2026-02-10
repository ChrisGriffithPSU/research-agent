"""RabbitMQ-backed runtime for the Kimi experiment worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aio_pika

from workers.kimi_worker.models import (
    ExperimentResult,
    ExperimentSummary,
    ResultError,
)
from workers.kimi_worker.runner import job_from_payload, run_job


logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class QueueWorkerConfig:
    """Configuration for queue-driven worker mode."""

    rabbitmq_url: str
    exchange_name: str
    job_queue: str
    job_routing_key: str
    result_queue: str
    result_routing_key: str
    prefetch_count: int

    @staticmethod
    def from_env() -> "QueueWorkerConfig":
        """Load queue worker configuration from environment variables."""
        return QueueWorkerConfig(
            rabbitmq_url=_rabbitmq_url_from_env(),
            exchange_name=os.getenv("KIMI_WORKER_EXCHANGE", "researcher"),
            job_queue=os.getenv("KIMI_WORKER_JOB_QUEUE", "experiment.job.request"),
            job_routing_key=os.getenv("KIMI_WORKER_JOB_ROUTING_KEY", "experiment.job.request"),
            result_queue=os.getenv("KIMI_WORKER_RESULT_QUEUE", "experiment.result"),
            result_routing_key=os.getenv("KIMI_WORKER_RESULT_ROUTING_KEY", "experiment.result"),
            prefetch_count=max(1, int(os.getenv("KIMI_WORKER_PREFETCH", "1"))),
        )


def _rabbitmq_url_from_env() -> str:
    direct = os.getenv("RABBITMQ_URL")
    if direct:
        return direct

    host = os.getenv("RABBITMQ_HOST", "localhost")
    port = int(os.getenv("RABBITMQ_PORT", "5672"))
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASSWORD", "guest")
    vhost = os.getenv("RABBITMQ_VHOST") or os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
    if not vhost.startswith("/"):
        vhost = f"/{vhost}"
    return f"amqp://{user}:{password}@{host}:{port}{vhost}"


def _fallback_failed_result(raw_job: dict[str, Any], error: Exception) -> ExperimentResult:
    job_id = str(raw_job.get("job_id", "unknown"))
    now = datetime.now(timezone.utc)
    summary = ExperimentSummary(
        title=str(raw_job.get("experiment_plan", {}).get("title", "Kimi Experiment")),
        hypotheses_tested=list(raw_job.get("experiment_plan", {}).get("hypotheses", [])),
        metrics=[],
        key_findings=["Job failed before execution completed."],
        regimes=[],
        next_steps=["Inspect worker logs and retry with corrected input."],
    )
    return ExperimentResult(
        job_id=job_id,
        status="failed",
        started_at=now,
        finished_at=now,
        attempts=0,
        repo_commit=None,
        summary=summary,
        artifacts=[],
        errors=[
            ResultError(
                stage="queue_consume",
                message="failed to parse or execute experiment job",
                trace=str(error),
            )
        ],
    )


async def _publish_result(
    exchange: aio_pika.abc.AbstractExchange,
    routing_key: str,
    result: ExperimentResult,
) -> None:
    body = result.model_dump_json().encode("utf-8")
    message = aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        timestamp=int(datetime.now(timezone.utc).timestamp()),
    )
    await exchange.publish(message, routing_key=routing_key)


async def run_queue_worker(config: QueueWorkerConfig | None = None) -> None:
    """Run long-lived queue consumer mode for experiment jobs."""
    cfg = config or QueueWorkerConfig.from_env()
    logger.info("Starting Kimi queue worker at %s", _utc_now_iso())
    logger.info("RabbitMQ URL host configured")
    logger.info("Exchange=%s queue=%s", cfg.exchange_name, cfg.job_queue)

    connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=cfg.prefetch_count)

    exchange = await channel.declare_exchange(
        cfg.exchange_name,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )
    queue = await channel.declare_queue(cfg.job_queue, durable=True)
    await queue.bind(exchange, routing_key=cfg.job_routing_key)

    result_queue = await channel.declare_queue(cfg.result_queue, durable=True)
    await result_queue.bind(exchange, routing_key=cfg.result_routing_key)

    stop_event = asyncio.Event()

    def _request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows event loop may not support add_signal_handler.
            pass

    async def _on_message(message: aio_pika.IncomingMessage) -> None:
        raw_payload: dict[str, Any] = {}
        try:
            raw_payload = json.loads(message.body.decode("utf-8"))
            job = job_from_payload(raw_payload)
            logger.info("Received experiment job: %s", job.job_id)
            result = await run_job(job)
            await _publish_result(exchange, cfg.result_routing_key, result)
            logger.info("Published experiment result: %s (%s)", result.job_id, result.status)
            await message.ack()
        except Exception as exc:
            logger.exception("Failed processing experiment job message")
            result = _fallback_failed_result(raw_payload, exc)
            await _publish_result(exchange, cfg.result_routing_key, result)
            await message.ack()

    consumer_tag = await queue.consume(_on_message, no_ack=False)
    logger.info("Kimi queue worker is consuming (consumer_tag=%s)", consumer_tag)

    try:
        await stop_event.wait()
    finally:
        await queue.cancel(consumer_tag)
        await channel.close()
        await connection.close()
        logger.info("Kimi queue worker stopped")
