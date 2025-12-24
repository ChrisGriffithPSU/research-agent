"""Unit tests for health checks."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.shared.messaging.health import (
    check_messaging_health,
    quick_check,
    HealthStatus,
)
from src.shared.messaging.schemas import QueueName


@pytest.mark.asyncio
async def test_quick_check_connected():
    """Should return True when connection is connected."""
    connection = MagicMock(spec=["is_connected"])
    connection.is_connected = True

    result = await quick_check(connection)

    assert result is True


@pytest.mark.asyncio
async def test_quick_check_not_connected():
    """Should return False when connection is not connected."""
    connection = MagicMock(spec=["is_connected"])
    connection.is_connected = False

    result = await quick_check(connection)

    assert result is False


@pytest.mark.asyncio
async def test_check_messaging_health_all_healthy():
    """Should return healthy status when all checks pass."""
    connection = MagicMock(spec=["is_connected", "channel"])
    connection.is_connected = True

    status = await check_messaging_health(connection)

    assert status.status == "healthy"
    assert status.checks["connection"] == "ok"
    assert status.timestamp is not None


@pytest.mark.asyncio
async def test_check_messaging_health_connection_failed():
    """Should return unhealthy when connection fails."""
    connection = MagicMock(spec=["is_connected", "channel"])
    connection.is_connected = False

    status = await check_messaging_health(connection)

    assert status.status == "unhealthy"
    assert status.checks["connection"] == "failed"
    assert status.metrics["connection.status"] == "disconnected"


@pytest.mark.asyncio
async def test_health_status_structure():
    """Should have correct structure."""
    timestamp = datetime.now(timezone.utc)

    status = HealthStatus(
        status="healthy",
        timestamp=timestamp,
        checks={"connection": "ok"},
        metrics={"test.metric": 42},
    )

    assert status.status == "healthy"
    assert status.timestamp == timestamp
    assert status.checks["connection"] == "ok"
    assert status.metrics["test.metric"] == 42
    assert "timestamp" in status.metrics

