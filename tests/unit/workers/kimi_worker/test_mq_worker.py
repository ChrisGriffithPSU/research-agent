"""Unit tests for Kimi MQ worker helpers."""

from __future__ import annotations

import os

from workers.kimi_worker.mq_worker import QueueWorkerConfig, _rabbitmq_url_from_env


def test_rabbitmq_url_prefers_direct_env(monkeypatch) -> None:
    monkeypatch.setenv("RABBITMQ_URL", "amqp://a:b@host:5672/")
    assert _rabbitmq_url_from_env() == "amqp://a:b@host:5672/"


def test_rabbitmq_url_builds_from_components(monkeypatch) -> None:
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.setenv("RABBITMQ_HOST", "mq")
    monkeypatch.setenv("RABBITMQ_PORT", "5673")
    monkeypatch.setenv("RABBITMQ_USER", "u")
    monkeypatch.setenv("RABBITMQ_PASSWORD", "p")
    monkeypatch.setenv("RABBITMQ_VHOST", "v1")
    assert _rabbitmq_url_from_env() == "amqp://u:p@mq:5673/v1"


def test_queue_config_reads_defaults(monkeypatch) -> None:
    monkeypatch.delenv("KIMI_WORKER_JOB_QUEUE", raising=False)
    cfg = QueueWorkerConfig.from_env()
    assert cfg.job_queue == "experiment.job.request"
    assert cfg.result_routing_key == "experiment.result"
