"""Root pytest configuration."""
import pytest
import os


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


# Import fixtures from fixtures module to make them available globally
pytest_plugins = [
    "tests.fixtures.docker",
]
