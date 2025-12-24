"""Database health check router for FastAPI services."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.shared.db.health import check_health, quick_check

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> JSONResponse:
    """Check database health status.

    Returns detailed health information including:
    - Overall status (healthy/unhealthy)
    - Timestamp
    - Connection status
    - Query status
    - Pool information
    """
    try:
        health_result = await check_health()
        status_code = 200 if health_result["status"] == "healthy" else 503
        return JSONResponse(
            content=health_result,
            status_code=status_code,
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            status_code=503,
        )


@router.get("/quick")
async def quick_health_check() -> JSONResponse:
    """Quick health check (connection test only).

    Returns simple status without detailed checks.
    Useful for load balancers and external monitoring.
    """
    try:
        is_healthy = await quick_check()
        status_code = 200 if is_healthy else 503
        return JSONResponse(
            content={
                "status": "healthy" if is_healthy else "unhealthy",
                "timestamp": datetime.now().isoformat(),
            },
            status_code=status_code,
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Quick health check failed: {e}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            status_code=503,
        )


@router.get("/liveness")
async def liveness_check() -> JSONResponse:
    """Kubernetes-style liveness probe.

    Returns 200 if the application is running (no DB check).
    """
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
        },
        status_code=200,
    )


@router.get("/readiness")
async def readiness_check() -> JSONResponse:
    """Kubernetes-style readiness probe.

    Returns 200 if the application is ready to serve traffic.
    Checks if database connection works.
    """
    try:
        is_healthy = await quick_check()
        status_code = 200 if is_healthy else 503
        return JSONResponse(
            content={
                "status": "ready" if is_healthy else "not_ready",
                "timestamp": datetime.now().isoformat(),
            },
            status_code=status_code,
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status": "not_ready",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            status_code=503,
        )

