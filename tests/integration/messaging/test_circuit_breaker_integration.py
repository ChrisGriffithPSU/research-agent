"""Integration tests for CircuitBreaker with real failures.

These tests require RabbitMQ running via Docker.
Set RUN_INTEGRATION_TESTS=1 and ensure RabbitMQ is accessible.
"""
import pytest
import asyncio
import time

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.publisher import MessagePublisher
from src.shared.messaging.circuit_breaker import CircuitBreaker
from src.shared.messaging.schemas import SourceMessage, QueueName
from src.shared.models.source import SourceType
from src.shared.messaging.queue_setup import QueueSetup
from src.shared.messaging.exceptions import CircuitBreakerOpenError
from src.shared.messaging.metrics import get_metrics, reset_metrics
from src.shared.messaging.config import MessagingConfig


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_real_failures(rabbitmq_manager):
    """Test that circuit breaker opens after real RabbitMQ publish failures."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()
    queue_setup = QueueSetup(conn)
    await queue_setup.setup_all_queues()

    # Create circuit breaker
    breaker = CircuitBreaker(failure_threshold=3, timeout=0.2)

    # Simulate failures by calling a function that always fails
    failure_count = 0

    async def failing_operation():
        nonlocal failure_count
        failure_count += 1
        raise RuntimeError(f"Simulated failure {failure_count}")

    # Trigger 3 failures to open circuit
    for i in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(failing_operation)

    # Circuit breaker should be open
    assert breaker.is_open
    assert breaker.state == "open"
    assert breaker.failures == 3

    # Next call should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(failing_operation)

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_moves_to_half_open(rabbitmq_manager):
    """Test that circuit breaker moves to half-open after timeout."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()

    # Create circuit breaker with short timeout
    breaker = CircuitBreaker(failure_threshold=2, timeout=0.15)  # 150ms

    # Open the circuit
    async def failing_op():
        raise RuntimeError("Fail")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(failing_op)

    assert breaker.is_open

    # Wait for timeout to expire
    time.sleep(0.2)  # 200ms > 150ms timeout

    # Try to call - should allow one attempt (half-open state)
    with pytest.raises(RuntimeError):
        await breaker.call(failing_op)

    # Should be in half-open now (allowed the attempt)
    assert breaker.state == "half-open"

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_closes_on_half_open_success(rabbitmq_manager):
    """Test that circuit breaker closes after successful call in half-open."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()

    # Create circuit breaker
    breaker = CircuitBreaker(failure_threshold=2, timeout=0.15)

    # Open the circuit
    async def fail():
        raise RuntimeError("Fail")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.is_open

    # Wait for timeout
    time.sleep(0.2)

    # Successful call in half-open should close circuit
    async def succeed():
        return "success"

    result = await breaker.call(succeed)

    assert result == "success"
    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.is_closed

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_with_real_rabbitmq_failures(rabbitmq_manager):
    """Test circuit breaker protecting actual RabbitMQ publisher."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()
    queue_setup = QueueSetup(conn)
    await queue_setup.setup_all_queues()

    # Create publisher with circuit breaker
    publisher = MessagePublisher(
        conn,
        use_circuit_breaker=True
    )

    # Override circuit breaker with short timeout for testing
    publisher._circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=0.15)

    # Create message
    message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/cb-integration",
        title="Circuit Breaker Integration Test",
        content="Test content"
    )

    # Publish should succeed (RabbitMQ is running)
    await publisher.publish(message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Verify circuit breaker stayed closed
    assert publisher._circuit_breaker.state == "closed"
    assert publisher._circuit_breaker.failures == 0

    # Now simulate failures by closing connection
    await conn.close()

    # Try to publish - should fail and increment circuit breaker
    for i in range(3):
        try:
            await publisher.publish(message, routing_key=QueueName.CONTENT_DISCOVERED.value)
        except Exception:
            # Expected to fail (connection closed)
            pass

    # Circuit breaker should be open now
    assert publisher._circuit_breaker.is_open
    assert publisher._circuit_breaker.failures >= 3

    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_manual_reset(rabbitmq_manager):
    """Test manual reset of circuit breaker."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()

    # Create circuit breaker
    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # Open circuit
    async def fail():
        raise RuntimeError("Fail")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.is_open

    # Manual reset
    breaker.reset()

    # Should be closed now
    assert breaker.state == "closed"
    assert breaker.failures == 0
    assert breaker.is_closed

    # Should be able to call functions again
    async def succeed():
        return "success"

    result = await breaker.call(succeed)
    assert result == "success"

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_handles_mixed_success_failures(rabbitmq_manager):
    """Test circuit breaker with mix of successes and failures."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()

    breaker = CircuitBreaker(failure_threshold=3, timeout=60.0)

    # Simulate pattern: success, fail, success, fail, fail, fail (open)
    call_count = 0

    async def mixed_operation():
        nonlocal call_count
        call_count += 1

        # Fail on calls 2, 4, 5, 6
        if call_count in [2, 4, 5, 6]:
            raise RuntimeError(f"Failure {call_count}")

        return f"success-{call_count}"

    # Execute calls
    results = []
    for i in range(1, 4):
        try:
            result = await breaker.call(mixed_operation)
            results.append(result)
        except RuntimeError as e:
            results.append(str(e))

    # Circuit should still be closed (never hit threshold of 3 consecutive failures)
    assert breaker.state == "closed"

    # Now trigger 3 consecutive failures
    for i in range(4, 7):
        try:
            result = await breaker.call(mixed_operation)
            results.append(result)
        except RuntimeError as e:
            results.append(str(e))

    # Circuit should be open now (failures at 4, 5, 6)
    assert breaker.is_open
    assert breaker.failures == 3  # Only counts consecutive failures

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_properties_in_real_scenario(rabbitmq_manager):
    """Test circuit breaker properties during real usage."""
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    conn = RabbitMQConnection(config)
    await conn.connect()

    breaker = CircuitBreaker(failure_threshold=5, timeout=30.0)

    # Initial state
    assert breaker.is_closed
    assert not breaker.is_open
    assert repr(breaker) == "CircuitBreaker(state=closed, failures=0, threshold=5)"

    # Add some failures
    async def fail():
        raise RuntimeError("Test")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    # Still closed, but has failures
    assert breaker.is_closed
    assert breaker.failures == 3
    assert "failures=3" in repr(breaker)

    # Open circuit
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    # Now open
    assert breaker.is_open
    assert not breaker.is_closed
    assert "state=open" in repr(breaker)

    await conn.close()
    reset_metrics()

