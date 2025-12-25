# Test Suite Documentation

## Overview

This test suite follows a **three-axis testing strategy** to ensure comprehensive coverage:

1. **Axis 1: Logic/Algorithm Tests** - Pure unit tests with no external dependencies
2. **Axis 2: Integration Tests** - Tests with real infrastructure (Docker)
3. **Axis 3: E2E Tests** - End-to-end workflows

---

## Test Structure

```
tests/
├── fixtures/
│   └── docker.py                 # Docker fixtures for integration tests
│
├── unit/                            # Axis 1: Pure logic tests (no infrastructure)
│   └── shared/
│       ├── messaging/
│       │   ├── test_circuit_breaker.py          # Async behavior tests
│       │   ├── test_circuit_breaker_logic.py    # State machine tests
│       │   ├── test_config.py                      # Keep existing ✓
│       │   ├── test_health.py                       # HealthStatus structure only
│       │   ├── test_metrics.py                     # Keep existing ✓
│       │   ├── test_retry.py                       # Keep existing (refactored)
│       │   └── test_schemas.py                     # Keep existing ✓
│       └── repositories/
│           └── test_base_repository.py       # CRUD with SQLite ✓
│
├── integration/                       # Axis 2: Real infrastructure tests
│   └── shared/
│       ├── db/
│       │   ├── test_seeding.py                     # Keep existing ✓
│       │   └── test_vector_search_postgres.py # NEW: pgvector tests
│       └── messaging/
│           ├── test_publisher_integration.py   # NEW: Real RabbitMQ
│           ├── test_consumer_integration.py    # NEW: Real RabbitMQ
│           └── test_circuit_breaker_integration.py # NEW: Real failures
│
└── e2e/                             # Axis 3: End-to-end workflows
    └── test_full_workflow.py         # NEW: Complete pipeline tests
```

---

## Running Tests

### Quick Unit Tests (No Docker Required)

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/shared/messaging/test_retry.py -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Integration Tests (Requires Docker)

Integration tests require RabbitMQ and PostgreSQL running:

```bash
# Option 1: Using existing Docker Compose
cd infra/docker
docker-compose up -d postgres rabbitmq

# Option 2: Set environment variables
export RABBITMQ_HOST=localhost
export RABBITMQ_PORT=5672
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export RUN_INTEGRATION_TESTS=1

# Run integration tests
pytest tests/integration/ -v -m integration
```

### E2E Tests (Requires Full Docker Stack)

```bash
# Start all services
cd infra/docker
docker-compose --profile all up -d

# Run E2E tests
pytest tests/e2e/ -v -m e2e
```

---

## Test Categories Explained

### Unit Tests (Axis 1)

**Purpose**: Test pure algorithms and business logic without external dependencies.

**Characteristics**:
- Fast execution (milliseconds)
- Deterministic (no timing issues)
- Mock-free when possible
- Test core algorithms and state machines

**Examples**:
- `test_circuit_breaker_logic.py` - State machine transitions
- `test_retry.py` - Backoff calculation (with jitter tolerance)
- `test_metrics.py` - Counter/gauge/timer logic
- `test_schemas.py` - Pydantic validation

**When to Write**: For any algorithm, calculation, or pure logic function.

---

### Integration Tests (Axis 2)

**Purpose**: Test components with real infrastructure (RabbitMQ, PostgreSQL).

**Characteristics**:
- Require Docker services
- Test actual network I/O
- Verify real message flow
- Test failure scenarios

**Examples**:
- `test_publisher_integration.py` - Real RabbitMQ publishing
- `test_consumer_integration.py` - Real RabbitMQ consuming
- `test_circuit_breaker_integration.py` - Real failure patterns
- `test_vector_search_postgres.py` - Real pgvector operations

**When to Write**: For any component that interacts with external services.

---

### E2E Tests (Axis 3)

**Purpose**: Test complete workflows as users would experience them.

**Characteristics**:
- Test multiple components together
- Verify message flow through entire pipeline
- Test error handling across system
- Validate metrics and observability

**Examples**:
- `test_full_workflow.py` - Content discovery → deduplicate → extract → digest
- Duplicate prevention across pipeline
- Error handling (DLQ, retries, circuit breaker)

**When to Write**: For critical user-facing workflows.

---

## Test Markers

```python
@pytest.mark.integration   # Integration test (requires Docker)
@pytest.mark.e2e           # End-to-end test (requires full stack)
```

---

## What Each Test Covers

### Messaging Tests

| Test File | Axes Covered | What's Tested |
|-----------|--------------|----------------|
| `test_circuit_breaker.py` | Logic | Async call behavior, state transitions |
| `test_circuit_breaker_logic.py` | Logic | State machine logic, no timing |
| `test_circuit_breaker_integration.py` | Integration | Real failures with RabbitMQ |
| `test_retry.py` | Logic | Backoff calculation, error type detection |
| `test_config.py` | Logic | Configuration validation |
| `test_health.py` | Logic | HealthStatus data structure |
| `test_publisher_integration.py` | Integration | Real RabbitMQ publish, retry, circuit breaker |
| `test_consumer_integration.py` | Integration | Real RabbitMQ consume, ack/nack, DLQ |
| `test_schemas.py` | Logic | Pydantic model validation |
| `test_metrics.py` | Logic | Counter, gauge, timer operations |

### Database Tests

| Test File | Axes Covered | What's Tested |
|-----------|--------------|----------------|
| `test_base_repository.py` | Logic | CRUD operations with SQLite |
| `test_vector_search_postgres.py` | Integration | pgvector similarity, duplicate detection |
| `test_seeding.py` | Integration | Database seeding, idempotency |

### E2E Tests

| Test File | Axes Covered | What's Tested |
|-----------|--------------|----------------|
| `test_full_workflow.py` | E2E | Complete pipeline, error handling, metrics |

---

## Key Improvements Made

### Fixed Issues

1. ✅ **Removed broken `test_vector_search.py`**
   - Problem: Tests used pgvector operators (`<=>`) on SQLite
   - Solution: Created new PostgreSQL integration tests

2. ✅ **Refactored `test_circuit_breaker.py`**
   - Problem: Tests called internal methods directly (`_on_failure()`)
   - Solution: Tests now use actual `call()` method with async functions

3. ✅ **Fixed `test_retry.py`**
   - Problem: Exact value assertions didn't account for jitter
   - Solution: Use range assertions (±20% tolerance)

4. ✅ **Cleaned up `test_health.py` (messaging)**
   - Problem: Used MagicMock, didn't test real behavior
   - Solution: Focus on data structure tests, real tests in integration

### New Tests Added

5. ✅ **Created `test_circuit_breaker_logic.py`**
   - Pure state machine tests
   - No async timing, just logic

6. ✅ **Created Docker fixtures**
   - `tests/fixtures/docker.py` with connection managers
   - Skip integration tests by default (use `RUN_INTEGRATION_TESTS=1`)

7. ✅ **Created integration tests**
   - `test_publisher_integration.py` - 6 tests with real RabbitMQ
   - `test_consumer_integration.py` - 7 tests with real RabbitMQ
   - `test_circuit_breaker_integration.py` - 7 tests with real failures
   - `test_vector_search_postgres.py` - 8 tests with pgvector

8. ✅ **Created E2E tests**
   - `test_full_workflow.py` - 4 complete workflow tests

---

## Test Coverage Goals

| Component | Unit Tests | Integration Tests | E2E Tests | Total |
|-----------|-------------|------------------|-------------|--------|
| Circuit Breaker | 8 | 7 | 0 | 15 |
| Retry | 10 | 0 | 0 | 10 |
| Publisher | 0 | 6 | 0 | 6 |
| Consumer | 0 | 7 | 0 | 7 |
| Metrics | 21 | 0 | 0 | 21 |
| Schemas | 15 | 0 | 0 | 15 |
| Health | 4 | 0 | 0 | 4 |
| Repositories | 10 | 8 | 0 | 18 |
| Workflows | 0 | 0 | 4 | 4 |
| **Total** | **68** | **28** | **4** | **100** |

---

## Best Practices

### Writing New Tests

1. **Choose the right axis**:
   - Pure algorithm? → `tests/unit/`
   - External service? → `tests/integration/`
   - User workflow? → `tests/e2e/`

2. **Follow naming convention**:
   - Unit: `test_{component}.py`
   - Integration: `test_{component}_integration.py`
   - E2E: `test_{workflow}.py`

3. **Use descriptive test names**:
   - Bad: `test_basic()`
   - Good: `test_publisher_sends_message_to_queue()`

4. **Test both normal and edge cases**:
   - Normal: What happens when everything works?
   - Edge: What happens at boundaries? (empty inputs, max values, etc.)
   - Error: What happens when things fail?

5. **Verify side effects**:
   - Metrics recorded?
   - Logs written?
   - State updated?

6. **Clean up after each test**:
   - Reset state
   - Close connections
   - Clear metrics

---

## Troubleshooting

### Integration Tests Fail to Connect

**Problem**: Tests skip or fail with connection errors

**Solution**:
```bash
# Verify Docker is running
docker ps | grep -E 'rabbitmq|postgres'

# Check logs
docker logs researcher-rabbitmq
docker logs researcher-postgres

# Verify ports
docker port researcher-rabbitmq
```

### Tests Timeout

**Problem**: Tests hang or timeout

**Solution**:
- Increase timeout in test fixtures
- Check if services are slow to start
- Verify RabbitMQ queue isn't blocked

### Tests Flaky

**Problem**: Tests pass/fail inconsistently

**Solution**:
- Add sleep after async operations
- Use range assertions instead of exact values
- Check for race conditions

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ -v --cov

  integration:
    runs-on: ubuntu-latest
    services:
      rabbitmq:
        image: rabbitmq:3.12-management-alpine
      postgres:
        image: pgvector/pgvector:pg15
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements.txt
      - run: pytest tests/integration/ -v -m integration
        env:
          RABBITMQ_HOST: localhost
          POSTGRES_HOST: localhost
          RUN_INTEGRATION_TESTS: 1
```

---

## Summary

This test suite provides:

✅ **Comprehensive coverage** - Logic, integration, and E2E
✅ **Fast feedback** - Unit tests in seconds, integration tests in minutes
✅ **Real-world validation** - Tests use actual infrastructure
✅ **Maintainability** - Clear structure, good naming
✅ **Documentation** - Each test explains what it validates

For questions or improvements, see the implementation process at:
`.cursor/rules/implementation-process.mdc`

