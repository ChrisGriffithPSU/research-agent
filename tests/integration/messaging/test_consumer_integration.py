"""Integration tests for MessageConsumer with real RabbitMQ.

These tests require RabbitMQ running via Docker.
Set RUN_INTEGRATION_TESTS=1 and ensure RabbitMQ is accessible.
"""
import pytest
import asyncio
import json

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.messaging.retry import ExponentialBackoffStrategy
from src.shared.messaging.schemas import QueueName, SourceMessage, ExtractedInsightsMessage
from src.shared.messaging.exceptions import TemporaryError, PermanentError
from src.shared.models.source import SourceType
from src.shared.messaging.queue_setup import QueueSetup
from src.shared.messaging.metrics import get_metrics, reset_metrics
from src.shared.messaging.config import MessagingConfig


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_receives_and_processes_message(rabbitmq_manager):
    """Test consumer receives and processes messages from RabbitMQ."""
    # Create config from manager
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )
    # Connect and setup
    conn = RabbitMQConnection(config)
    await conn.connect()
    queue_setup = QueueSetup(conn)
    await queue_setup.setup_all_queues()

    # Track received messages
    received_messages = []
    processing_complete = asyncio.Event()

    async def handle_message(message: SourceMessage):
        received_messages.append(message)
        processing_complete.set()

    # Create and configure consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, handle_message)

    # Publish a message
    publisher = MessagePublisher(conn)
    test_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/test-consumer-123",
        title="Consumer Test",
        content="Test content"
    )
    await publisher.publish(test_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Start consumer in background
    consume_task = asyncio.create_task(consumer.start())

    # Wait for message to be processed
    try:
        await asyncio.wait_for(processing_complete.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pytest.fail("Message was not processed within timeout")

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify message was received
    assert len(received_messages) == 1
    assert received_messages[0].url == "https://arxiv.org/abs/test-consumer-123"
    assert received_messages[0].title == "Consumer Test"
    assert received_messages[0].content == "Test content"

    # Verify metrics
    metrics = get_metrics()
    assert metrics.get_counter(f"messages.consumed.{QueueName.CONTENT_DISCOVERED.value}") == 1
    assert metrics.get_counter(f"messages.acked.{QueueName.CONTENT_DISCOVERED.value}") == 1

    # Cleanup
    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_requeues_on_transient_error(rabbitmq_manager):
    """Test consumer requeues messages on transient errors."""
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

    attempt_count = 0
    processing_complete = asyncio.Event()

    async def flaky_handler(message: SourceMessage):
        nonlocal attempt_count
        attempt_count += 1

        # Fail first 2 times, succeed on 3rd
        if attempt_count < 3:
            raise TemporaryError(f"Temporary error attempt {attempt_count}")

        processing_complete.set()

    # Create and configure consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, flaky_handler)

    # Publish message
    publisher = MessagePublisher(conn)
    test_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/flaky-retry",
        title="Flaky Test",
        content="Test"
    )
    await publisher.publish(test_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Wait for processing to complete (after retries)
    try:
        await asyncio.wait_for(processing_complete.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("Message was not processed within timeout")

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify handler was called 3 times (2 retries + 1 success)
    assert attempt_count == 3

    # Verify metrics show nack with requeue
    metrics = get_metrics()
    nacked_count = metrics.get_counter(f"messages.nacked.{QueueName.CONTENT_DISCOVERED.value}.requeued", 0)
    # We should have nack+requeued for the first 2 failed attempts
    assert nacked_count >= 2

    # Finally acked on success
    assert metrics.get_counter(f"messages.acked.{QueueName.CONTENT_DISCOVERED.value}") == 1

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_sends_to_dlq_on_permanent_error(rabbitmq_manager):
    """Test consumer sends malformed messages to DLQ."""
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

    processing_complete = asyncio.Event()

    async def failing_handler(message: SourceMessage):
        raise PermanentError("This will never work")

    # Create and configure consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, failing_handler)

    # Publish message
    publisher = MessagePublisher(conn)
    test_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/dlq-test",
        title="DLQ Test",
        content="Test"
    )
    await publisher.publish(test_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Wait for processing
    try:
        await asyncio.wait_for(processing_complete.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        # Expected - PermanentError causes DLQ which doesn't complete processing
        pass

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify DLQ metrics
    metrics = get_metrics()
    assert metrics.get_counter(f"dlq.messages.{QueueName.CONTENT_DISCOVERED.value}") == 1
    assert metrics.get_counter(f"messages.nacked.{QueueName.CONTENT_DISCOVERED.value}.dlq") == 1

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_handles_multiple_queues(rabbitmq_manager):
    """Test consumer can subscribe to multiple queues."""
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

    received_sources = []
    received_insights = []
    processing_complete = asyncio.Event()

    async def source_handler(message: SourceMessage):
        received_sources.append(message)
        check_completion()

    async def insights_handler(message: ExtractedInsightsMessage):
        received_insights.append(message)
        check_completion()

    def check_completion():
        if len(received_sources) >= 1 and len(received_insights) >= 1:
            processing_complete.set()

    # Create and configure consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, source_handler)
    consumer.subscribe(QueueName.INSIGHTS_EXTRACTED, insights_handler)

    # Publish messages to both queues
    publisher = MessagePublisher(conn)

    from src.shared.messaging.schemas import ExtractedInsightsMessage
    source_msg = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/multi-1",
        title="Source Message",
        content="Content"
    )
    insights_msg = ExtractedInsightsMessage(
        source_type=SourceType.ARXIV,
        source_url="https://arxiv.org/abs/multi-2",
        source_title="Insights Message",
        key_insights="Key insights",
        core_techniques=["Technique 1"],
        code_snippets=["code"],
        actionability_score=0.8
    )

    await publisher.publish(source_msg, routing_key=QueueName.CONTENT_DISCOVERED.value)
    await publisher.publish(insights_msg, routing_key=QueueName.INSIGHTS_EXTRACTED.value)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Wait for processing
    try:
        await asyncio.wait_for(processing_complete.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pytest.fail("Messages were not processed within timeout")

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify both messages received
    assert len(received_sources) == 1
    assert len(received_insights) == 1

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_prefetch_count(rabbitmq_manager):
    """Test consumer respects prefetch count."""
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

    processed_count = 0
    all_messages_published = asyncio.Event()

    async def slow_handler(message: SourceMessage):
        nonlocal processed_count
        processed_count += 1
        # Simulate slow processing
        await asyncio.sleep(0.5)

    # Create consumer with prefetch=2
    consumer = MessageConsumer(conn, prefetch_count=2)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, slow_handler)

    # Publish 5 messages quickly
    publisher = MessagePublisher(conn)
    for i in range(5):
        msg = SourceMessage(
            source_type=SourceType.ARXIV,
            url=f"https://arxiv.org/abs/prefetch-{i}",
            title=f"Message {i}",
            content="Content"
        )
        await publisher.publish(msg, routing_key=QueueName.CONTENT_DISCOVERED.value)

    all_messages_published.set()

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Wait for some messages to be processed
    await asyncio.sleep(2.0)

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify some messages were processed
    # With prefetch=2, it should have processed at least 2-4 messages
    assert processed_count >= 2

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_graceful_shutdown(rabbitmq_manager):
    """Test consumer shuts down gracefully."""
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

    processed_messages = []

    async def handler(message: SourceMessage):
        processed_messages.append(message)
        await asyncio.sleep(0.1)  # Simulate processing

    # Create consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, handler)

    # Publish multiple messages
    publisher = MessagePublisher(conn)
    for i in range(3):
        msg = SourceMessage(
            source_type=SourceType.ARXIV,
            url=f"https://arxiv.org/abs/shutdown-{i}",
            title=f"Message {i}",
            content="Content"
        )
        await publisher.publish(msg, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Wait for at least one message to be processed
    await asyncio.sleep(0.5)

    # Request graceful shutdown (with timeout)
    await consumer.stop(graceful=True, timeout=1.0)
    await consume_task

    # Verify some messages were processed before shutdown
    # It might not have processed all 3 due to shutdown timing
    assert len(processed_messages) >= 1
    assert len(processed_messages) <= 3

    # Verify consumer state
    assert not consumer._consuming
    assert consumer._shutdown_requested

    await conn.close()
    reset_metrics()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consumer_health_check(rabbitmq_manager):
    """Test consumer health check returns correct status."""
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

    consumer = MessageConsumer(conn)

    # Should be healthy when connected and not consuming
    is_healthy = await consumer.health_check()
    assert is_healthy is False  # Not consuming yet

    # Start consuming
    async def dummy_handler(message: SourceMessage):
        pass

    consumer.subscribe(QueueName.CONTENT_DISCOVERED, dummy_handler)
    consume_task = asyncio.create_task(consumer.start())

    # Give it a moment to start
    await asyncio.sleep(0.2)

    # Should be healthy now
    is_healthy = await consumer.health_check()
    assert is_healthy is True

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Should be unhealthy when stopped
    is_healthy = await consumer.health_check()
    assert is_healthy is False

    await conn.close()
    reset_metrics()

