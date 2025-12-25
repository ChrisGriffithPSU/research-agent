"""Tests for database health check functionality.

These tests require PostgreSQL as they use models with ARRAY types.
"""
import pytest

from src.shared.db.health import check_health, quick_check

# Mark database health tests as integration tests (they create tables with PostgreSQL types)
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_check_health_success(test_engine):
    """Test successful health check."""
    # Create all tables for health check to find
    from src.shared.models import Base
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Run health check
    health = await check_health()
    
    assert health["status"] == "healthy"
    assert "connection" in health["checks"]
    assert health["checks"]["connection"] == "ok"
    assert "query" in health["checks"]
    assert health["checks"]["query"] == "ok"
    assert "pool" in health["checks"]
    assert "timestamp" in health
    assert health["checks"]["pool"]["size"] == 5  # Default pool size
    assert health["checks"]["pool"]["overflow"] == 0
    assert health["checks"]["pool"]["checkedin"] == 3  # Some connections checked out


@pytest.mark.asyncio
async def test_check_health_quick(test_session):
    """Test quick health check (connection test only)."""
    # Quick check should work with empty database
    is_healthy = await quick_check()
    
    assert is_healthy is True


def test_check_health_sync():
    """Test health check works synchronously (for simple scripts)."""
    import asyncio
    result = asyncio.run(check_health())
    
    assert result["status"] == "healthy"
    assert "checks" in result
    assert result["checks"]["connection"] == "ok"


if __name__ == "__main__":
    # Quick verification that health check works
    test_check_health_sync()
    print("✅ Health check implementation verified!")

