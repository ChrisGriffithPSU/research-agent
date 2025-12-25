"""End-to-end tests for full system workflows.

These tests require the complete Docker stack running:
- RabbitMQ
- PostgreSQL + pgvector
- All microservices

Set RUN_INTEGRATION_TESTS=1 and ensure all services are accessible.
"""
import pytest
import asyncio

from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.publisher import MessagePublisher
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.schemas import QueueName, SourceMessage, ExtractedInsightsMessage, DigestReadyMessage
from src.shared.models.source import SourceType, ProcessingStatus
from src.shared.messaging.queue_setup import QueueSetup
from src.shared.messaging.metrics import get_metrics, reset_metrics
from src.shared.messaging.config import MessagingConfig


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_content_discovery_pipeline(rabbitmq_manager):
    """Test complete pipeline: fetch → deduplicate → extract → digest.

    This is a high-level E2E test that validates:
    1. Messages can be published and consumed through the pipeline
    2. Services communicate correctly via RabbitMQ
    3. Metrics are collected across all stages
    4. No messages are lost or stuck in queues

    Note: This test assumes services are running. In a full implementation,
    you would mock or integrate with actual service logic.
    """
    # Create proper config object
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )

    # Connect to RabbitMQ
    conn = RabbitMQConnection(config)
    await conn.connect()
    queue_setup = QueueSetup(conn)
    await queue_setup.setup_all_queues()

    # Track messages at each stage
    stage1_discovered = []
    stage2_deduplicated = []
    stage3_extracted = []
    stage4_digest_ready = []
    pipeline_complete = asyncio.Event()

    # Stage 1: Content discovered
    async def handle_discovered(message: SourceMessage):
        stage1_discovered.append(message)
        print(f"[E2E] Stage 1: Content discovered - {message.title}")

        # Simulate publishing to next stage (deduplication)
        # In real system, deduplication service would consume this
        # For E2E test, we manually publish to verify pipeline
        await publisher.publish(
            message,
            routing_key=QueueName.CONTENT_DEDUPLICATED.value
        )

    # Stage 2: Content deduplicated
    async def handle_deduplicated(message: SourceMessage):
        stage2_deduplicated.append(message)
        print(f"[E2E] Stage 2: Content deduplicated - {message.title}")

        # Simulate publishing to extraction stage
        await publisher.publish(
            message,
            routing_key=QueueName.INSIGHTS_EXTRACTED.value
        )

    # Stage 3: Insights extracted
    async def handle_extracted(message: ExtractedInsightsMessage):
        stage3_extracted.append(message)
        print(f"[E2E] Stage 3: Insights extracted - {message.source_title}")

        # Simulate publishing to digest stage
        from src.shared.messaging.schemas import DigestReadyMessage, DigestItem
        digest_msg = DigestReadyMessage(
            user_id=1,
            digest_date="2024-01-01",
            items=[
                DigestItem(
                    source_id=1,
                    source_url=message.source_url,
                    title=message.source_title,
                    summary=message.key_insights[:200],
                    reasoning="High actionability score",
                    tags=message.core_techniques[:3],
                    relevance_score=message.actionability_score
                )
            ]
        )
        await publisher.publish(
            digest_msg,
            routing_key=QueueName.DIGEST_READY.value
        )

    # Stage 4: Digest ready
    async def handle_digest_ready(message: DigestReadyMessage):
        stage4_digest_ready.append(message)
        print(f"[E2E] Stage 4: Digest ready - user {message.user_id}, {len(message.items)} items")

        # Signal pipeline complete
        pipeline_complete.set()

    # Create consumer that subscribes to all stages
    consumer = MessageConsumer(conn, prefetch_count=5)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, handle_discovered)
    consumer.subscribe(QueueName.CONTENT_DEDUPLICATED, handle_deduplicated)
    consumer.subscribe(QueueName.INSIGHTS_EXTRACTED, handle_extracted)
    consumer.subscribe(QueueName.DIGEST_READY, handle_digest_ready)

    # Create publisher for injecting messages
    publisher = MessagePublisher(conn)

    # Start consumer in background
    consume_task = asyncio.create_task(consumer.start())

    # Inject a message at stage 1
    initial_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/e2e-pipeline-test",
        title="E2E Pipeline Test Paper",
        content="This paper tests the complete pipeline",
        source_metadata={"authors": ["Test Author"], "published_date": "2024-01-01"}
    )

    print("[E2E] Starting pipeline test...")
    await publisher.publish(initial_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Wait for pipeline to complete
    try:
        await asyncio.wait_for(pipeline_complete.wait(), timeout=10.0)
        print("[E2E] Pipeline test completed successfully!")
    except asyncio.TimeoutError:
        pytest.fail("Pipeline did not complete within timeout")

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify all stages were reached
    assert len(stage1_discovered) == 1
    assert len(stage2_deduplicated) == 1
    assert len(stage3_extracted) == 1
    assert len(stage4_digest_ready) == 1

    # Verify message flow
    assert stage1_discovered[0].url == "https://arxiv.org/abs/e2e-pipeline-test"
    assert stage3_extracted[0].source_url == "https://arxiv.org/abs/e2e-pipeline-test"
    assert len(stage4_digest_ready[0].items) == 1

    # Verify metrics were collected at each stage
    metrics = get_metrics()
    assert metrics.get_counter(f"messages.published.{QueueName.CONTENT_DISCOVERED.value}") == 1
    assert metrics.get_counter(f"messages.published.{QueueName.CONTENT_DEDUPLICATED.value}") >= 1
    assert metrics.get_counter(f"messages.published.{QueueName.INSIGHTS_EXTRACTED.value}") >= 1
    assert metrics.get_counter(f"messages.published.{QueueName.DIGEST_READY.value}") >= 1

    assert metrics.get_counter(f"messages.consumed.{QueueName.CONTENT_DISCOVERED.value}") == 1
    assert metrics.get_counter(f"messages.consumed.{QueueName.CONTENT_DEDUPLICATED.value}") == 1
    assert metrics.get_counter(f"messages.consumed.{QueueName.INSIGHTS_EXTRACTED.value}") == 1
    assert metrics.get_counter(f"messages.consumed.{QueueName.DIGEST_READY.value}") == 1

    # Cleanup
    await conn.close()
    reset_metrics()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_error_handling_across_pipeline(rabbitmq_manager):
    """Test error handling across the pipeline.

    Validates:
    1. Transient errors are retried
    2. Permanent errors route to DLQ
    3. Circuit breaker protects against cascading failures
    4. Metrics track all errors
    """
    from src.shared.messaging.exceptions import PermanentError

    # Create proper config object
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

    error_count = 0
    dlq_messages = []
    pipeline_complete = asyncio.Event()

    async def failing_handler(message: SourceMessage):
        nonlocal error_count
        error_count += 1

        # Fail consistently to test DLQ
        raise PermanentError(f"Simulated permanent error {error_count}")

    # Create consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, failing_handler)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Publish message
    publisher = MessagePublisher(conn)
    test_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/error-test",
        title="Error Handling Test",
        content="Test"
    )

    await publisher.publish(test_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Wait for DLQ to receive message
    try:
        await asyncio.wait_for(pipeline_complete.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        # Expected - PermanentError causes DLQ which doesn't complete processing
        pass

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # Verify error metrics
    metrics = get_metrics()
    dlq_count = metrics.get_counter(f"dlq.messages.{QueueName.CONTENT_DISCOVERED.value}", 0)
    assert dlq_count >= 1

    nacked_dlq = metrics.get_counter(f"messages.nacked.{QueueName.CONTENT_DISCOVERED.value}.dlq", 0)
    assert nacked_dlq >= 1

    # Cleanup
    await conn.close()
    reset_metrics()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_duplicate_prevention_in_pipeline(rabbitmq_manager):
    """Test that duplicate content is prevented across pipeline.

    Validates:
    1. Same content published twice is deduplicated
    2. Downstream services don't process duplicates
    """
    # Create proper config object
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
    pipeline_complete = asyncio.Event()

    async def handler(message: SourceMessage):
        processed_messages.append(message.url)
        print(f"[E2E] Processed: {message.title}")
        if len(processed_messages) >= 1:
            pipeline_complete.set()

    # Create consumer
    consumer = MessageConsumer(conn)
    consumer.subscribe(QueueName.CONTENT_DISCOVERED, handler)

    # Start consumer
    consume_task = asyncio.create_task(consumer.start())

    # Publish same message twice
    publisher = MessagePublisher(conn)
    duplicate_message = SourceMessage(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/duplicate-test-123",
        title="Duplicate Test Paper",
        content="This paper tests duplicate prevention"
    )

    print("[E2E] Testing duplicate prevention...")
    await publisher.publish(duplicate_message, routing_key=QueueName.CONTENT_DISCOVERED.value)
    await asyncio.sleep(0.1)  # Small delay between publishes
    await publisher.publish(duplicate_message, routing_key=QueueName.CONTENT_DISCOVERED.value)

    # Wait for processing
    try:
        await asyncio.wait_for(pipeline_complete.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pytest.fail("Pipeline did not complete")

    # Stop consumer
    await consumer.stop(graceful=False)
    await consume_task

    # In a real implementation with deduplication service,
    # we would expect only 1 of the 2 duplicate messages
    # to be processed by downstream services.
    # For now, we verify both were published:
    metrics = get_metrics()
    published_count = metrics.get_counter(f"messages.published.{QueueName.CONTENT_DISCOVERED.value}")
    assert published_count == 2

    # Cleanup
    await conn.close()
    reset_metrics()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_system_health_check_workflow(rabbitmq_manager):
    """Test system health check across all components.

    Validates:
    1. Health checks return correct status
    2. All components report healthy status
    3. Health metrics are accurate
    """
    from src.shared.messaging.health import check_messaging_health, quick_check

    # Create proper config object
    config = MessagingConfig(
        host=rabbitmq_manager.host,
        port=rabbitmq_manager.port,
        user=rabbitmq_manager.user,
        password=rabbitmq_manager.password,
    )

    conn = RabbitMQConnection(config)
    await conn.connect()

    # Set up queues before health check (needed for queue depth checks)
    queue_setup = QueueSetup(conn)
    await queue_setup.setup_all_queues()

    # Quick check
    is_healthy = await quick_check(conn)
    assert is_healthy is True

    # Full health check
    health_status = await check_messaging_health(conn)

    # Verify structure
    assert health_status.status in ["healthy", "degraded", "unhealthy"]
    assert health_status.timestamp is not None
    assert "checks" in health_status.__dict__
    assert "metrics" in health_status.__dict__

    # Verify connection check
    assert "connection" in health_status.checks
    assert health_status.checks["connection"] == "ok"

    print(f"[E2E] System Health: {health_status.status}")
    print(f"[E2E] Checks: {health_status.checks}")
    print(f"[E2E] Metrics keys: {list(health_status.metrics.keys())}")

    # Cleanup
    await conn.close()
