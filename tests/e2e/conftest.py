"""Pytest fixtures for E2E tests."""
import pytest
import json
import os

# #region agent log
def _log_to_debug(location, message, data=None, hypothesis_id="A"):
    """Write debug log entry to debug.log."""
    try:
        log_path = r"c:\Users\stunn\Projects\researcher-agent\.cursor\debug.log"
        log_entry = {
            "sessionId": "debug-session",
            "runId": "initial",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "timestamp": None,  # Will be set when writing
        }
        if data:
            log_entry["data"] = data

        with open(log_path, "a") as f:
            import time
            log_entry["timestamp"] = int(time.time() * 1000)
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass  # Silently fail if logging fails
# #endregion

# Log conftest.py loading
_log_to_debug("tests/e2e/conftest.py:18", "conftest.py loaded for E2E tests", hypothesis_id="A")

# Import Docker fixtures for E2E testing
from tests.fixtures.docker import rabbitmq_manager, postgres_manager

# Log fixture import
_log_to_debug("tests/e2e/conftest.py:25", "Imported rabbitmq_manager fixture", {"fixture_name": "rabbitmq_manager"}, hypothesis_id="A")

