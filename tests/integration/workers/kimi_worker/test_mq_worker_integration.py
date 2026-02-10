"""In-process integration tests for Kimi MQ worker loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import workers.kimi_worker.mq_worker as mq
from workers.kimi_worker.models import ExperimentResult, ExperimentSummary


class _Incoming:
    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode("utf-8")
        self.acked = False

    async def ack(self):
        self.acked = True


class _Queue:
    def __init__(self):
        self.bound = []
        self.cancelled = False

    async def bind(self, exchange, routing_key: str):
        self.bound.append((exchange, routing_key))

    async def consume(self, callback, no_ack: bool = False):
        payload = {
            "job_id": "j1",
            "created_at": "2026-02-10T00:00:00Z",
            "priority": 0,
            "repo_root": "C:/repo",
            "dataset_refs": [],
            "experiment_plan": {
                "title": "t",
                "hypotheses": ["h"],
                "method": "m",
                "metrics": [{"name": "m", "goal": "maximize", "target": 0.1}],
                "protocol": {
                    "time_horizon": "10s",
                    "labels": "y",
                    "validation": "walk_forward",
                    "constraints": [],
                },
                "implementation_notes": [],
            },
            "execution": {
                "entrypoint_preference": "python_script",
                "max_runtime_seconds": 60,
                "network_access": False,
                "yolo_approvals": False,
            },
            "output": {
                "run_dir": "C:/repo/runs/j1",
                "summary_path": "runs/j1/results/summary.json",
                "artifacts_dir": "runs/j1/artifacts",
            },
        }
        incoming = _Incoming(payload)
        await callback(incoming)
        return "tag-1"

    async def cancel(self, consumer_tag: str):
        self.cancelled = True


class _Exchange:
    def __init__(self):
        self.published = []

    async def publish(self, message, routing_key: str):
        self.published.append((message, routing_key))


class _Channel:
    def __init__(self):
        self.exchange = _Exchange()
        self.queues = {}

    async def set_qos(self, prefetch_count: int):
        return None

    async def declare_exchange(self, name, *_args, **_kwargs):
        return self.exchange

    async def declare_queue(self, name, durable: bool = True):
        queue = self.queues.get(name)
        if queue is None:
            queue = _Queue()
            self.queues[name] = queue
        return queue

    async def close(self):
        return None


class _Connection:
    def __init__(self):
        self.channel_obj = _Channel()

    async def channel(self):
        return self.channel_obj

    async def close(self):
        return None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_queue_worker_processes_message_and_publishes_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _Connection()

    async def _connect(_url: str):
        return conn

    monkeypatch.setattr(mq.aio_pika, "connect_robust", _connect)

    class _Event:
        async def wait(self):
            return None

        def set(self):
            return None

    monkeypatch.setattr(mq.asyncio, "Event", _Event)

    async def _fake_run_job(job):
        now = datetime.now(timezone.utc)
        return ExperimentResult(
            job_id=job.job_id,
            status="success",
            started_at=now,
            finished_at=now,
            attempts=1,
            repo_commit=None,
            summary=ExperimentSummary(
                title="t",
                hypotheses_tested=["h"],
                metrics=[],
                key_findings=[],
                regimes=[],
                next_steps=[],
            ),
            artifacts=[],
            errors=[],
        )

    monkeypatch.setattr(mq, "run_job", _fake_run_job)
    monkeypatch.setattr(mq, "_rabbitmq_url_from_env", lambda: "amqp://guest:guest@localhost:5672/")

    await mq.run_queue_worker(mq.QueueWorkerConfig.from_env())
    assert len(conn.channel_obj.exchange.published) >= 1
