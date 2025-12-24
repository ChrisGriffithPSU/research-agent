# Messaging Infrastructure

Complete RabbitMQ messaging infrastructure for the researcher-agent system.

---

## Overview

This messaging infrastructure provides:
- **Async connection management** to RabbitMQ
- **Message schemas** with Pydantic validation
- **Publisher API** with retry and circuit breaker protection
- **Consumer API** with QoS, ack/nack, and DLQ routing
- **Metrics collection** for observability
- **Health checks** for monitoring

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Messaging Infrastructure                  │
│                                                         │
│  ┌──────────────────────────────────────────────┐     │
│  │         Core Logic                       │     │
│  │                                         │     │
│  │  • Retry Strategies                    │     │
│  │  • Circuit Breaker                    │     │
│  │  • Metrics Tracking                   │     │
│  └──────────────────────────────────────────────┘     │
│                                                         │
│  ┌──────────────────────────────────────────────┐     │
│  │         Infrastructure                   │     │
│  │                                         │     │
│  │  • RabbitMQConnection                 │     │
│  │  • QueueSetup                       │     │
│  │  • Exchange/Queue declarations          │     │
│  └──────────────────────────────────────────────┘     │
│                                                         │
│  ┌──────────────────────────────────────────────┐     │
│  │         Publisher/Consumer APIs          │     │
│  │                                         │     │
│  │  • MessagePublisher                   │     │
│  │  • MessageConsumer                   │     │
│  │  • Health Checks                    │     │
│  └──────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Configuration (`config.py`)

**Class**: `MessagingConfig`

**Features**:
- Load from environment variables (`.env` file)
- Sensible defaults for development
- Connection parameters (host, port, user, password)
- Queue configuration (max length, TTL)
- Retry configuration (max attempts, backoff duration)
- Circuit breaker configuration (failure threshold, timeout)
- Consumer configuration (prefetch count)

**Environment Variables**:
```bash
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
```

**Usage**:
```python
from src.shared.messaging import messaging_config

print(messaging_config.host)  # localhost
print(messaging_config.connection_url)  # amqp://guest:guest@localhost:5672/
```

---

### 2. Exceptions (`exceptions.py`)

**Hierarchy**:
- `MessagingError` - Base exception
  - `ConnectionError` - RabbitMQ connection failed
  - `PublishError` - Failed to publish message
  - `ConsumeError` - Failed to consume message
  - `MessageValidationError` - Invalid message format
  - `QueueError` - Queue operation failed
  - `CircuitBreakerOpenError` - Circuit breaker preventing operations
- `PermanentError` - Permanent failure (don't retry)
- `TemporaryError` - Transient failure (retry)

---

### 3. Message Schemas (`schemas.py`)

**Base Class**: `BaseMessage`
- `correlation_id` (auto-generated UUID)
- `created_at` (auto-generated timestamp)
- `retry_count` (default 0)

**Message Types**:

| Message Type | Source Queue | Destination Queue | Fields |
|--------------|---------------|-------------------|--------|
| `SourceMessage` | - | `content.discovered` | source_type, url, title, content, metadata |
| `DeduplicatedContentMessage` | `content.discovered` | `content.deduplicated` | source_type, url, title, content, metadata, original_correlation_id |
| `ExtractedInsightsMessage` | `content.deduplicated` | `insights.extracted` | source_type, source_url, source_title, key_insights, core_techniques, code_snippets, actionability_score, correlation chain |
| `DigestItem` | - | - | Component of digest |
| `DigestReadyMessage` | `insights.extracted` | `digest.ready` | digest_items, item_count, generated_at, categories, insight_correlation_ids |
| `FeedbackMessage` | - | `feedback.submitted` | item_id, rating, implemented, notes, category, source_type |
| `TrainingTriggerMessage` | `feedback.submitted` | `training.trigger` | trigger_reason, feedback_count, model_version, triggered_at, feedback_correlation_ids |

**Queue Names** (Enum):
- Main queues: `content.discovered`, `content.deduplicated`, `insights.extracted`, `digest.ready`, `feedback.submitted`, `training.trigger`
- DLQs: `content.discovered.dlq`, `content.deduplicated.dlq`, etc.

---

### 4. Retry Strategies (`retry.py`)

**Interface**: `IRetryStrategy`

**Implementations**:
- `ExponentialBackoffStrategy` (default)
  - Formula: `base_delay * (2 ^ attempt)`
  - Adds jitter (±20%) to avoid thundering herd
  - Caps at `max_delay`
- `LinearBackoffStrategy`
  - Formula: `base_delay + (increment * attempt)`
  - Caps at `max_delay`
- `NoRetryStrategy`
  - Never retry, fail immediately

**Usage**:
```python
from src.shared.messaging import ExponentialBackoffStrategy

strategy = ExponentialBackoffStrategy(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
)

should_retry = await strategy.should_retry(attempt=0, error=Exception("test"))
backoff = strategy.get_backoff(attempt=0)
```

---

### 5. Circuit Breaker (`circuit_breaker.py`)

**Class**: `CircuitBreaker`

**States**:
- `closed` - Normal operation
- `open` - Blocking calls (too many failures)
- `half-open` - Testing recovery

**Behavior**:
- Opens after N consecutive failures (default: 3)
- Moves to half-open after timeout (default: 60s)
- Closes on successful call in half-open
- Resets failure count on any success

**Decorator**: `@circuit_breaker()`
```python
from src.shared.messaging import circuit_breaker

@circuit_breaker(failure_threshold=3, timeout=60.0)
async def protected_function():
    # This function is protected by circuit breaker
    pass
```

---

### 6. Connection Manager (`connection.py`)

**Class**: `RabbitMQConnection`

**Features**:
- Singleton pattern (one connection per service)
- Async connection establishment
- Graceful shutdown
- Auto-reconnect (via aio-pika's robust connection)
- Queue info retrieval
- Queue purge capability

**Usage**:
```python
from src.shared.messaging import get_connection, disconnect

# Get global connection
conn = get_connection()
await conn.connect()

# Check queue depth
info = await conn.get_queue_info("content.discovered")
print(info["message_count"])

# Close on shutdown
await disconnect()
```

---

### 7. Queue Setup (`queue_setup.py`)

**Class**: `QueueSetup`

**Features**:
- Declare topic exchange (`researcher`)
- Declare DLQ exchange (`researcher.dlq`)
- Declare all main queues with:
  - Durability (persist across restarts)
  - Max length (drop oldest when full)
  - Message TTL (auto-retry from DLQ)
  - DLQ routing (automatic on failure)
- Bind queues to exchange with routing keys
- Query queue depths
- Check queue existence

**Queue Configuration**:

| Queue | Max Length | TTL | DLQ |
|--------|------------|-----|------|
| `content.discovered` | 10,000 | 24h | `content.discovered.dlq` |
| `content.deduplicated` | 10,000 | 24h | `content.deduplicated.dlq` |
| `insights.extracted` | 5,000 | 24h | `insights.extracted.dlq` |
| `digest.ready` | 100 | 24h | `digest.ready.dlq` |
| `feedback.submitted` | 10,000 | None | `feedback.submitted.dlq` |
| `training.trigger` | 10 | 24h | `training.trigger.dlq` |

**Usage**:
```python
from src.shared.messaging import QueueSetup, get_connection

conn = get_connection()
setup = QueueSetup(conn)

# Setup all queues
await setup.setup_all_queues()

# Get queue depths
depths = await setup.get_queue_depths()
print(depths)
```

---

### 8. Publisher (`publisher.py`)

**Class**: `MessagePublisher`

**Features**:
- Async publishing
- Publisher confirms (wait for RabbitMQ ack)
- Automatic JSON serialization
- Retry with exponential backoff
- Circuit breaker protection
- Metrics collection

**Usage**:
```python
from src.shared.messaging import get_publisher, SourceMessage

# Get global publisher
publisher = get_publisher()

# Publish message
message = SourceMessage(
    source_type=SourceType.ARXIV,
    url="https://arxiv.org/abs/2401.xxxxx",
    title="Test Paper",
    content="Abstract content",
)

await publisher.publish(
    message=message,
    routing_key="content.discovered",
)

# Health check
is_healthy = await publisher.health_check()
```

---

### 9. Consumer (`consumer.py`)

**Class**: `MessageConsumer`

**Features**:
- Async message handlers
- QoS with prefetch count (default: 10)
- Manual ack/nack control
- Automatic DLQ routing on permanent errors
- Retry on transient errors (nack with requeue)
- Metrics collection
- Graceful shutdown

**Usage**:
```python
from src.shared.messaging import get_consumer, QueueName, SourceMessage, message_handler

# Get consumer
consumer = get_consumer(prefetch_count=10)

# Register handler
@message_handler(QueueName.CONTENT_DISCOVERED)
async def handle_discovered(message: SourceMessage):
    # Process message
    # If exception raised:
    # - TemporaryError → nack with requeue
    # - PermanentError → nack (send to DLQ)
    pass

consumer.subscribe(QueueName.CONTENT_DISCOVERED, handle_discovered)

# Start consuming
await consumer.start()

# Stop gracefully
await consumer.stop(graceful=True, timeout=30.0)
```

**Message Handler Decorator**:
```python
from src.shared.messaging import message_handler, QueueName

@message_handler(QueueName.CONTENT_DISCOVERED)
async def handle_message(message: SourceMessage):
    # Decorator adds:
    # - Metrics (processing time, success/failure)
    # - Logging with correlation ID
    # - Error handling
    pass
```

---

### 10. Metrics (`metrics.py`)

**Class**: `MessagingMetrics`

**Metrics Types**:
- **Counters**: Published, consumed, acked, nacked, DLQ
- **Timers**: Processing time, latency (with p50, p95, p99)
- **Gauges**: Queue depth, connection status
- **Errors**: By queue and error type

**Usage**:
```python
from src.shared.messaging import get_metrics

metrics = get_metrics()

# Increment counter
metrics.increment("messages.published.content.discovered")

# Record time
metrics.record_time("processing.content.discovered", latency_ms=150.5)

# Set gauge
metrics.set_gauge("queue.depth.content.discovered", 42.0)

# Record error
metrics.record_error("content.discovered", "ValidationError")

# Get summary
summary = metrics.get_summary()
```

---

### 11. Health Checks (`health.py`)

**Functions**:
- `check_messaging_health()` - Full health check
  - Connection status
  - Queue depths (with warning at 80% capacity)
  - Metrics summary
  - Error rates (>10% = degraded)
  - DLQ message counts

- `quick_check()` - Fast connection test only

**Usage**:
```python
from src.shared.messaging import check_messaging_health, quick_check, get_connection

conn = get_connection()

# Full health check
health = await check_messaging_health(conn)
print(health.status)  # "healthy", "unhealthy", "degraded"
print(health.checks)
print(health.metrics)

# Quick check
is_healthy = await quick_check(conn)
```

---

## Integration with Services

### Publisher Pattern (Fetchers, Extraction, Synthesis, Feedback)

```python
from src.shared.messaging import get_publisher, SourceMessage, QueueName

class ArxivFetcher:
    async def fetch_and_publish(self):
        # Fetch papers from arXiv
        papers = await self.fetch_papers()

        # Get publisher
        publisher = get_publisher()

        # Publish each paper
        for paper in papers:
            message = SourceMessage(
                source_type=SourceType.ARXIV,
                url=paper.url,
                title=paper.title,
                content=paper.abstract,
                metadata={"authors": paper.authors, "published": paper.published},
            )
            await publisher.publish(
                message=message,
                routing_key="content.discovered",
            )
```

### Consumer Pattern (Deduplication, Extraction, Synthesis, Digest Gen, Learning)

```python
from src.shared.messaging import get_consumer, QueueName, message_handler

class DeduplicationService:
    def __init__(self):
        self.consumer = get_consumer()

    @message_handler(QueueName.CONTENT_DISCOVERED)
    async def handle_discovered(message: SourceMessage):
        # Deduplication logic
        is_duplicate = await self.check_duplicate(message)

        if not is_duplicate:
            # Publish to next stage
            from src.shared.messaging import get_publisher, DeduplicatedContentMessage
            publisher = get_publisher()
            await publisher.publish(
                message=DeduplicatedContentMessage(...),
                routing_key="content.deduplicated",
            )

    async def start(self):
        self.consumer.subscribe(QueueName.CONTENT_DISCOVERED, self.handle_discovered)
        await self.consumer.start()
```

---

## Testing

### Unit Tests

Located in `tests/unit/shared/messaging/`:

- `test_config.py` - Configuration and validation
- `test_schemas.py` - Message schemas and serialization
- `test_retry.py` - Retry strategies
- `test_circuit_breaker.py` - Circuit breaker logic
- `test_metrics.py` - Metrics collection
- `test_health.py` - Health checks

### Integration Tests

To be added in `tests/integration/shared/messaging/`:

- End-to-end publish/consume
- DLQ routing
- Circuit breaker activation
- Connection failure recovery

---

## Docker Integration

RabbitMQ is already configured in `infra/docker/docker-compose.yml`:

```yaml
rabbitmq:
  image: rabbitmq:3.12-management-alpine
  container_name: researcher-rabbitmq
  environment:
    RABBITMQ_DEFAULT_USER: guest
    RABBITMQ_DEFAULT_PASS: guest
  ports:
    - "5672:5672"  # AMQP
    - "15672:15672"  # Management UI
  volumes:
    - rabbitmq-data:/var/lib/rabbitmq
```

**Environment Variables for Services**:

Services using messaging need to set:
```bash
RABBITMQ_HOST=rabbitmq  # In Docker
RABBITMQ_HOST=localhost   # Local development
```

---

## Configuration Files

### `.env` Example

```bash
# RabbitMQ Connection
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Queue Configuration
RABBITMQ_QUEUE_MAX_LENGTH=10000
RABBITMQ_QUEUE_MESSAGE_TTL=86400000

# Retry Configuration
RABBITMQ_PUBLISH_RETRY_MAX_ATTEMPTS=3
RABBITMQ_PUBLISH_RETRY_BASE_DELAY=1.0
RABBITMQ_PUBLISH_RETRY_MAX_DELAY=60.0

# Circuit Breaker
RABBITMQ_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
RABBITMQ_CIRCUIT_BREAKER_TIMEOUT=60.0

# Consumer
RABBITMQ_CONSUMER_PREFETCH_COUNT=10
```

---

## Message Flow

```
┌─────────────┐
│   Fetchers  │  Publishes to content.discovered
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Deduplication  │  Consumes content.discovered
│                │  Publishes to content.deduplicated
└──────┬────────┘
       │
       ▼
┌─────────────────┐
│   Extraction   │  Consumes content.deduplicated
│                │  Publishes to insights.extracted
└──────┬────────┘
       │
       ▼
┌─────────────────┐
│   Synthesis    │  Consumes insights.extracted
│                │  Publishes to digest.ready
└──────┬────────┘
       │
       ▼
┌─────────────────┐
│Digest Generation│  Consumes digest.ready
│                │  Stores in DB, sends email
└─────────────────┘
```

---

## Observability

### Logging

All operations are logged with appropriate levels:
- `DEBUG`: Connection details, message IDs, retry attempts
- `INFO`: Published, consumed, acked messages
- `WARNING`: Retries, DLQ routing, high queue depth
- `ERROR`: Failures, connection loss, validation errors

### Metrics

Metrics are available via:
```python
from src.shared.messaging import get_metrics

metrics = get_metrics()
summary = metrics.get_summary()
```

Metrics include:
- Message counts (published, consumed, acked, nacked)
- Processing time (avg, p50, p95, p99)
- Queue depths
- Error counts by type and queue
- Error rates

### Health Checks

Health endpoint (to be added to each service's health router):

```
GET /health
{
  "status": "healthy",  # or "unhealthy", "degraded"
  "timestamp": "2024-01-01T00:00:00Z",
  "checks": {
    "connection": "ok",
    "content.discovered.depth": "ok",
    "content.deduplicated.depth": "warning"  # >80% capacity
  },
  "metrics": {
    "queues": { "content.discovered": 8500, ... },
    "metrics": { ... },
    "errors": { ... }
  }
}
```

---

## Error Handling

### Transient Errors (Retry)

- Network timeout
- Temporary connection loss
- LLM API rate limit (when publishing back)
- Database deadlock (temporary)

**Behavior**: Retry with exponential backoff (3 attempts), then raise exception.

### Permanent Errors (DLQ)

- Invalid message format
- Missing required fields
- Business logic errors (can't be resolved by retry)
- Validation errors

**Behavior**: Send to DLQ, do not retry.

### Circuit Breaker

When RabbitMQ is repeatedly failing:
1. Open circuit after 3 consecutive failures
2. Reject all new operations
3. After 60s timeout, move to half-open
4. Test with next operation
5. If successful, close circuit; otherwise, keep open

---

## Performance Characteristics

- **Throughput**: 100+ messages/second (publish)
- **Latency**: <50ms p99 (publish with confirms)
- **Concurrency**: Supports multiple consumers per queue (via QoS prefetch)
- **Backpressure**: Queue max length prevents unbounded growth

---

## Best Practices

### For Publishers

1. **Always use Pydantic models** - Ensures type safety and validation
2. **Let publisher handle retries** - Don't implement your own retry logic
3. **Monitor circuit breaker** - Check if it's open before critical operations
4. **Log correlation IDs** - Essential for tracing

### For Consumers

1. **Use `@message_handler` decorator** - Adds metrics and logging
2. **Return normally on success** - Auto-acks message
3. **Raise `PermanentError`** for non-retryable errors (sends to DLQ)
4. **Raise `TemporaryError`** for retryable errors (nacks with requeue)
5. **Handle graceful shutdown** - Use `await stop(graceful=True)`

### For Services

1. **Get connection once at startup** - Use `get_connection()`
2. **Setup queues on startup** - Use `QueueSetup.setup_all_queues()`
3. **Close connection on shutdown** - Use `disconnect()`
4. **Monitor health** - Expose health endpoint
5. **Handle connection failures** - Circuit breaker and retry logic handle this

---

## Troubleshooting

### Messages Not Being Consumed

1. **Check connection**: Is service connected to RabbitMQ?
2. **Check consumer**: Is `consumer.start()` called?
3. **Check handler**: Is handler registered with `subscribe()`?
4. **Check routing**: Is queue bound to exchange with correct routing key?
5. **Check DLQ**: Are messages going to DLQ? (Check handler exceptions)

### High Queue Depth

1. **Check consumer speed**: Is handler slow?
2. **Check prefetch count**: Reduce if consumer can't keep up
3. **Check consumer count**: Need more consumers?
4. **Check DLQ**: Are messages failing and retrying?

### Circuit Breaker Stays Open

1. **Check RabbitMQ health**: Is it actually down?
2. **Check timeout**: Is timeout too short?
3. **Reset manually**: Call `publisher.reset_circuit_breaker()`
4. **Check failure threshold**: Is it too sensitive?

---

## Next Steps

1. **Integration**: Integrate messaging into fetchers and services
2. **Airflow**: Add Airflow DAG to orchestrate workflow
3. **Monitoring**: Add metrics export to Prometheus/Grafana (optional)
4. **DLQ Replay**: Implement DLQ inspection and replay functionality
5. **Message Priority**: Add priority queue support if needed

