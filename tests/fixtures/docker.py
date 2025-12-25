"""Docker fixtures for integration tests.

Provides RabbitMQ and PostgreSQL containers for testing.
"""
import pytest
import asyncio
import os
from typing import Dict, Optional


# Skip integration tests if Docker is not available
# Set environment variable RUN_INTEGRATION_TESTS=1 to run
pytest_configure = None

def pytest_configure(config):
    """Configure pytest to handle integration test markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires Docker)"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests (requires full Docker stack)"
    )


def pytest_runtest_setup(item):
    """Skip integration tests if not enabled."""
    has_integration_marker = item.get_closest_marker("integration")
    has_e2e_marker = item.get_closest_marker("e2e")

    if has_integration_marker or has_e2e_marker:
        if not os.getenv("RUN_INTEGRATION_TESTS"):
            pytest.skip(
                "Integration tests skipped. Set RUN_INTEGRATION_TESTS=1 to run."
            )


class RabbitMQTestManager:
    """Manages RabbitMQ container for testing."""

    def __init__(self):
        self.container_name = "test-rabbitmq"
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.management_port = int(os.getenv("RABBITMQ_MANAGEMENT_PORT", "15672"))
        self.user = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASSWORD", "guest")

    async def is_ready(self) -> bool:
        """Check if RabbitMQ is ready to accept connections."""
        try:
            import aio_pika
            connection = await aio_pika.connect_robust(
                host=self.host,
                port=self.port,
                login=self.user,
                password=self.password,
                connection_timeout=2.0,
            )
            await connection.close()
            return True
        except Exception:
            return False

    async def wait_until_ready(self, timeout: int = 30):
        """Wait for RabbitMQ to be ready."""
        for _ in range(timeout):
            if await self.is_ready():
                return True
            await asyncio.sleep(1)
        raise TimeoutError(f"RabbitMQ not ready after {timeout} seconds")


class PostgreSQLTestManager:
    """Manages PostgreSQL container for testing."""

    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.user = os.getenv("POSTGRES_USER", "postgres")
        self.password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.database = os.getenv("POSTGRES_DB", "researcher_agent")

    async def is_ready(self) -> bool:
        """Check if PostgreSQL is ready."""
        try:
            import asyncpg
            conn = await asyncpg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=2.0,
            )
            await conn.close()
            return True
        except Exception:
            return False

    async def wait_until_ready(self, timeout: int = 30):
        """Wait for PostgreSQL to be ready."""
        for _ in range(timeout):
            if await self.is_ready():
                return True
            await asyncio.sleep(1)
        raise TimeoutError(f"PostgreSQL not ready after {timeout} seconds")


@pytest.fixture(scope="session")
async def rabbitmq_manager():
    """Provide RabbitMQ test manager.

    This fixture assumes RabbitMQ is already running via Docker.
    It provides methods to check readiness and wait for services.

    Usage:
        await rabbitmq.wait_until_ready()
    """
    manager = RabbitMQTestManager()

    # Wait for RabbitMQ to be ready
    await manager.wait_until_ready()

    yield manager

    # No cleanup needed - containers are managed externally


@pytest.fixture(scope="session")
async def postgres_manager():
    """Provide PostgreSQL test manager.

    This fixture assumes PostgreSQL is already running via Docker.
    It provides methods to check readiness and wait for services.

    Usage:
        await postgres.wait_until_ready()
    """
    manager = PostgreSQLTestManager()

    # Wait for PostgreSQL to be ready
    await manager.wait_until_ready()

    yield manager

    # No cleanup needed - containers are managed externally


@pytest.fixture(scope="session")
def docker_containers():
    """Provide connection information for Docker containers.

    Returns dictionary with host/port info for RabbitMQ and PostgreSQL.
    """
    return {
        "rabbitmq": {
            "host": os.getenv("RABBITMQ_HOST", "localhost"),
            "port": int(os.getenv("RABBITMQ_PORT", "5672")),
            "management_port": int(os.getenv("RABBITMQ_MANAGEMENT_PORT", "15672")),
            "user": os.getenv("RABBITMQ_USER", "guest"),
            "password": os.getenv("RABBITMQ_PASSWORD", "guest"),
        },
        "postgres": {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
            "database": os.getenv("POSTGRES_DB", "researcher_agent"),
        },
    }


# Environment variables for running integration tests
# Add these to your .env file or export before running tests:
# RUN_INTEGRATION_TESTS=1
# RABBITMQ_HOST=localhost
# RABBITMQ_PORT=5672
# RABBITMQ_USER=guest
# RABBITMQ_PASSWORD=guest
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=postgres
# POSTGRES_DB=researcher_agent

