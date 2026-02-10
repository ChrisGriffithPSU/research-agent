# Test Suite

This test suite is rebuilt for the current codebase and is designed to be lightweight and deterministic.

## Layout

- `tests/unit/`: pure logic and module-level behavior with fakes.
- `tests/integration/`: in-process component interaction tests (still no external services).
- `tests/e2e/`: end-to-end in-process workflow tests.

## Principles

- No network calls.
- No real RabbitMQ/Postgres dependencies.
- Dummy data everywhere.
- Every test validates current code paths and contracts.

## Running

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/e2e -q
```

If dependency resolution blocks `pytest` in your environment, you can still run a fast syntax sanity pass:

```bash
python -m compileall tests
```

## Notes

- The suite intentionally stubs optional heavy/runtime-only dependencies (`docling`, `kaos`, `kimi_agent_sdk`) in `tests/conftest.py`.
- This keeps tests lightweight and independent from machine-specific tooling.
