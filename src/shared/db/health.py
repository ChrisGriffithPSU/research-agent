"""Database health check functionality."""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.session import _get_factory

logger = logging.getLogger(__name__)


async def check_health() -> dict:
    """Check database health status.

    Returns:
        Health check result with status, timestamp, and checks
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    try:
        factory = _get_factory()
        async with factory() as session:
            # Test 1: Basic connection
            try:
                await session.execute(text("SELECT 1"))
                health["checks"]["connection"] = "ok"
                logger.debug("Health check: Connection OK")
            except Exception as e:
                health["checks"]["connection"] = "failed"
                health["checks"]["connection_error"] = str(e)
                logger.error(f"Health check: Connection failed: {e}")

            # Test 2: Simple query
            try:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM user_profiles")
                )
                count = result.scalar()
                health["checks"]["query"] = "ok"
                health["checks"]["user_count"] = count
                logger.debug(f"Health check: Query OK (users: {count})")
            except Exception as e:
                health["checks"]["query"] = "failed"
                health["checks"]["query_error"] = str(e)
                logger.error(f"Health check: Query failed: {e}")

            # Test 3: Check pool status (basic)
            try:
                engine = session.get_bind()
                pool = engine.pool
                health["checks"]["pool"] = {
                    "size": pool.size(),
                    "overflow": pool.overflow(),
                    "checkedin": pool.checkedout(),
                }
                logger.debug(f"Health check: Pool OK (size={pool.size()})")
            except Exception as e:
                health["checks"]["pool"] = "failed"
                health["checks"]["pool_error"] = str(e)
                logger.error(f"Health check: Pool check failed: {e}")

    except Exception as e:
        health["status"] = "unhealthy"
        health["error"] = str(e)
        health["checks"]["connection"] = "failed"
        health["checks"]["query"] = "failed"
        logger.error(f"Health check failed: {e}")

    logger.info(f"Health check result: {health['status']}")
    return health


async def quick_check() -> bool:
    """Quick check if database connection works.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        await check_health()
        return True
    except Exception:
        return False

