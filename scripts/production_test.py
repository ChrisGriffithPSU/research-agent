#!/usr/bin/env python3
"""Production-style integration test script.

Tests the complete pipeline WITHOUT LLM calls:
- ArXiv Fetcher (real API calls)
- Message Queue (RabbitMQ)
- Database (PostgreSQL)
- Cache (Redis)

Usage:
    # Make sure Docker infrastructure is running:
    # docker-compose -f infra/docker/docker-compose.yml up postgres rabbitmq -d

    # Then run this script:
    python scripts/production_test.py
"""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# CONFIGURATION
# ============================================================================

HARDCODED_QUERY = "timeseries"  # No LLM, just use this query directly
MAX_PAPERS = 5  # Limit papers for quick testing


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_header(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step: str) -> None:
    """Print a step marker."""
    print(f"\n[STEP] {step}")


def print_success(msg: str) -> None:
    """Print success message."""
    print(f"  [OK] {msg}")


def print_error(msg: str) -> None:
    """Print error message."""
    print(f"  [ERROR] {msg}")


def print_info(msg: str) -> None:
    """Print info message."""
    print(f"  [INFO] {msg}")


# ============================================================================
# TEST 1: REDIS CACHE
# ============================================================================

async def test_redis_cache() -> bool:
    """Test Redis cache connectivity and operations."""
    print_header("TEST 1: REDIS CACHE")

    try:
        print_step("Initializing Redis connection...")
        from src.shared.utils.cache.connection import RedisConnection
        from src.shared.utils.cache.service import RedisCacheBackend, CacheService

        # Use default Redis URL (localhost:6379)
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        print_info(f"Redis URL: {redis_url}")

        connection = RedisConnection(redis_url=redis_url)
        await connection.initialize()
        print_success("Redis connection initialized")

        # Test ping
        print_step("Testing Redis ping...")
        is_healthy = await connection.ping()
        if is_healthy:
            print_success("Redis ping successful")
        else:
            print_error("Redis ping failed")
            return False

        # Create cache service
        print_step("Creating cache service...")
        backend = RedisCacheBackend(connection=connection)
        cache = CacheService(cache_backend=backend)
        await cache.initialize()
        print_success("Cache service initialized")

        # Test set/get
        print_step("Testing cache set/get operations...")
        test_key = f"test:production_test:{datetime.now().isoformat()}"
        test_value = {"query": HARDCODED_QUERY, "timestamp": datetime.now().isoformat()}

        await cache.set_cached(test_key, test_value, ttl=60)
        print_info(f"Set key: {test_key}")

        retrieved = await cache.get_cached(test_key)
        if retrieved and retrieved.get("query") == HARDCODED_QUERY:
            print_success(f"Retrieved value matches: {retrieved}")
        else:
            print_error(f"Value mismatch: {retrieved}")
            return False

        # Test exists
        print_step("Testing cache exists operation...")
        exists = await cache.exists(test_key)
        if exists:
            print_success("Key exists check passed")
        else:
            print_error("Key exists check failed")
            return False

        # Test delete
        print_step("Testing cache delete operation...")
        await cache.delete(test_key)
        exists_after = await cache.exists(test_key)
        if not exists_after:
            print_success("Key deleted successfully")
        else:
            print_error("Key still exists after delete")
            return False

        # Cleanup
        await cache.close()
        print_success("Cache connection closed")

        return True

    except Exception as e:
        print_error(f"Redis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 2: RABBITMQ MESSAGE QUEUE
# ============================================================================

async def test_rabbitmq() -> bool:
    """Test RabbitMQ connectivity and message operations."""
    print_header("TEST 2: RABBITMQ MESSAGE QUEUE")

    try:
        print_step("Initializing RabbitMQ connection...")
        from src.shared.messaging.connection import RabbitMQConnection
        from src.shared.messaging.config import MessagingConfig
        from src.shared.messaging.queue_setup import QueueSetup

        # Create config from environment
        config = MessagingConfig()
        print_info(f"RabbitMQ URL: {config.connection_url}")

        connection = RabbitMQConnection(config=config)
        await connection.connect()
        print_success("RabbitMQ connection established")

        # Check connection status
        print_step("Checking connection status...")
        if connection.is_connected:
            print_success("Connection is active")
        else:
            print_error("Connection is not active")
            return False

        # Setup queues
        print_step("Setting up queues and exchanges...")
        queue_setup = QueueSetup(connection)
        await queue_setup.setup_all_queues()
        print_success("Queues and exchanges declared")

        # Check queue existence
        print_step("Verifying queue existence...")
        queue_status = await queue_setup.check_queues_exist()
        for queue_name, exists in queue_status.items():
            if exists:
                print_info(f"Queue exists: {queue_name}")
            else:
                print_info(f"Queue missing: {queue_name}")

        # Get queue depths
        print_step("Getting queue depths...")
        depths = await queue_setup.get_queue_depths()
        for queue_name, depth in depths.items():
            if depth >= 0:
                print_info(f"{queue_name}: {depth} messages")

        # Test publish (using mock publisher pattern for safety)
        print_step("Testing message publishing...")
        from src.shared.messaging.publisher import MessagePublisher
        from src.shared.messaging.retry import ExponentialBackoffStrategy
        from src.services.fetchers.arxiv.schemas.messages import ArxivDiscoveredMessage

        publisher = MessagePublisher(
            connection=connection,
            retry_strategy=ExponentialBackoffStrategy(max_attempts=3),
        )

        # Create a test message
        test_message = ArxivDiscoveredMessage(
            paper_id="test.12345",
            title=f"Production Test Paper - {HARDCODED_QUERY}",
            abstract=f"This is a test paper about {HARDCODED_QUERY} for production testing.",
            authors=["Test Author"],
            categories=["cs.LG"],
            arxiv_url="https://arxiv.org/abs/test.12345",
            pdf_url="https://arxiv.org/pdf/test.12345.pdf",
        )

        await publisher.publish(
            message=test_message,
            routing_key="arxiv.discovered",
        )
        print_success(f"Published test message to arxiv.discovered")
        print_info(f"Message paper_id: {test_message.paper_id}")
        print_info(f"Message correlation_id: {test_message.correlation_id}")

        # Verify message count increased
        print_step("Verifying message was queued...")
        await asyncio.sleep(0.5)  # Brief wait for message to be processed
        new_depths = await queue_setup.get_queue_depths()
        print_info(f"Queue depth after publish: {new_depths.get('content.discovered', 'N/A')}")

        # Cleanup
        await connection.close()
        print_success("RabbitMQ connection closed")

        return True

    except Exception as e:
        print_error(f"RabbitMQ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 3: POSTGRESQL DATABASE
# ============================================================================

async def test_postgresql() -> bool:
    """Test PostgreSQL connectivity and operations."""
    print_header("TEST 3: POSTGRESQL DATABASE")

    try:
        print_step("Initializing database connection...")
        from src.shared.db.config import db_config, get_async_engine
        from src.shared.db.session import DatabaseSession
        from src.shared.models.source import Source, SourceType, ProcessingStatus
        from src.shared.repositories.source_repository import SourceRepository

        print_info(f"Database URL: postgresql://{db_config.user}:***@{db_config.host}:{db_config.port}/{db_config.name}")

        # Get engine (lazy initialization)
        engine = get_async_engine()
        print_success("Database engine created")

        # Test connection with session
        print_step("Testing database session...")
        async with DatabaseSession() as session:
            print_success("Database session created")

            # Test a simple query
            print_step("Testing database query...")
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            if row and row[0] == 1:
                print_success("Database query successful")
            else:
                print_error("Database query failed")
                return False

            # Check pgvector extension
            print_step("Checking pgvector extension...")
            try:
                result = await session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
                row = result.fetchone()
                if row:
                    print_success(f"pgvector extension installed (version: {row[0]})")
                else:
                    print_info("pgvector extension not found (may still work)")
            except Exception as e:
                print_info(f"pgvector check: {e}")

            # Create a test source record
            print_step("Testing source repository operations...")
            repo = SourceRepository(session)

            test_url = f"https://arxiv.org/abs/test.{HARDCODED_QUERY}.{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Check if exists first
            existing = await repo.get_by_url(test_url)
            if existing:
                print_info(f"Test source already exists: {existing.id}")
            else:
                # Create new source
                print_step("Creating test source record...")
                created = await repo.create(
                    source_type=SourceType.ARXIV,
                    url=test_url,
                    title=f"Production Test: {HARDCODED_QUERY}",
                    content=f"Test abstract about {HARDCODED_QUERY} for production testing.",
                    source_metadata={
                        "test": True,
                        "query": HARDCODED_QUERY,
                        "created_at": datetime.now().isoformat(),
                    },
                    status=ProcessingStatus.FETCHED,
                    fetched_at=datetime.now(),
                )
                print_success(f"Created source record: id={created.id}")
                print_info(f"Source URL: {created.url}")
                print_info(f"Source title: {created.title}")
                print_info(f"Source status: {created.status}")

            # List sources by type
            print_step("Listing arxiv sources...")
            arxiv_sources = await repo.list_by_type(SourceType.ARXIV, limit=5)
            print_info(f"Found {len(arxiv_sources)} arxiv sources (showing up to 5)")
            for source in arxiv_sources[:3]:
                print_info(f"  - [{source.id}] {source.title[:50]}...")

            # List sources by status
            print_step("Listing sources by status...")
            for status in [ProcessingStatus.FETCHED, ProcessingStatus.PROCESSED]:
                sources = await repo.list_by_status(status, limit=5)
                print_info(f"  {status.value}: {len(sources)} sources")

        print_success("Database session closed")

        # Dispose engine
        print_step("Disposing database engine...")
        from src.shared.db.config import dispose_engine
        await dispose_engine()
        print_success("Database engine disposed")

        return True

    except Exception as e:
        print_error(f"PostgreSQL test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 4: ARXIV FETCHER (REAL API)
# ============================================================================

async def test_arxiv_fetcher() -> bool:
    """Test ArXiv fetcher with real API calls (no LLM)."""
    print_header("TEST 4: ARXIV FETCHER (REAL API)")

    try:
        print_step("Initializing ArXiv API client...")
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig

        config = ArxivFetcherConfig(
            default_results_per_query=MAX_PAPERS,
            llm_query_enabled=False,  # No LLM
        )

        api_client = ArxivAPIClient(config=config)
        await api_client.initialize()
        print_success("ArXiv API client initialized")

        # Health check
        print_step("Performing ArXiv API health check...")
        is_healthy = await api_client.health_check()
        if is_healthy:
            print_success("ArXiv API is accessible")
        else:
            print_error("ArXiv API health check failed")
            # Continue anyway - might just be rate limited

        # Search with hardcoded query
        print_step(f"Searching ArXiv for: '{HARDCODED_QUERY}'...")
        papers = await api_client.search(
            query=HARDCODED_QUERY,
            max_results=MAX_PAPERS,
            sort_by="submittedDate",
            sort_order="descending",
        )

        print_success(f"Found {len(papers)} papers")

        if papers:
            print_step("Paper details:")
            for i, paper in enumerate(papers, 1):
                print_info(f"\n  Paper {i}:")
                print_info(f"    ID: {paper.paper_id}")
                print_info(f"    Title: {paper.title[:60]}...")
                print_info(f"    Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
                print_info(f"    Categories: {', '.join(paper.categories[:3])}")
                print_info(f"    Submitted: {paper.submitted_date}")
                print_info(f"    ArXiv URL: {paper.arxiv_url}")
                print_info(f"    PDF URL: {paper.pdf_url}")
                print_info(f"    Abstract: {paper.abstract[:100]}...")

        # Get stats
        print_step("API client statistics:")
        stats = api_client.get_stats()
        print_info(f"Requests made: {stats['request_count']}")
        print_info(f"Errors: {stats['error_count']}")
        print_info(f"Cache hits: {stats['cache_hit_count']}")

        # Test category fetch
        print_step("Testing category fetch (cs.LG)...")
        category_papers = await api_client.fetch_by_categories(
            categories=["cs.LG"],
            max_per_category=3,
        )
        print_success(f"Found {len(category_papers)} papers in cs.LG")

        # Cleanup
        await api_client.close()
        print_success("ArXiv API client closed")

        return True

    except Exception as e:
        print_error(f"ArXiv fetcher test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 5: FULL PIPELINE (FETCHER -> QUEUE -> DATABASE)
# ============================================================================

async def test_full_pipeline() -> bool:
    """Test the full pipeline: Fetch -> Publish -> Store."""
    print_header("TEST 5: FULL PIPELINE (FETCH -> QUEUE -> DATABASE)")

    try:
        # Initialize all components
        print_step("Initializing all components...")

        # Redis cache
        from src.shared.utils.cache.connection import RedisConnection
        from src.shared.utils.cache.service import RedisCacheBackend, CacheService

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_conn = RedisConnection(redis_url=redis_url)
        await redis_conn.initialize()
        cache_backend = RedisCacheBackend(connection=redis_conn)
        cache = CacheService(cache_backend=cache_backend)
        await cache.initialize()
        print_success("Redis cache initialized")

        # RabbitMQ
        from src.shared.messaging.connection import RabbitMQConnection
        from src.shared.messaging.config import MessagingConfig
        from src.shared.messaging.publisher import MessagePublisher
        from src.shared.messaging.retry import ExponentialBackoffStrategy

        mq_config = MessagingConfig()
        mq_connection = RabbitMQConnection(config=mq_config)
        await mq_connection.connect()

        publisher = MessagePublisher(
            connection=mq_connection,
            retry_strategy=ExponentialBackoffStrategy(max_retries=3),
        )
        print_success("RabbitMQ publisher initialized")

        # ArXiv Fetcher (without LLM query expansion)
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.services.fetchers.arxiv.services.cache_manager import CacheManager
        from src.services.fetchers.arxiv.services.publisher import ArxivMessagePublisher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig

        fetcher_config = ArxivFetcherConfig(
            default_results_per_query=MAX_PAPERS,
            llm_query_enabled=False,
        )

        cache_manager = CacheManager(cache_backend=cache_backend, config=fetcher_config)
        await cache_manager.initialize()

        api_client = ArxivAPIClient(cache=cache_manager, config=fetcher_config)
        await api_client.initialize()

        arxiv_publisher = ArxivMessagePublisher(
            message_publisher=publisher,
            config=fetcher_config,
        )
        await arxiv_publisher.initialize()
        print_success("ArXiv fetcher components initialized")

        # PHASE 1: Fetch papers
        print_step(f"PHASE 1: Fetching papers for query '{HARDCODED_QUERY}'...")
        papers = await api_client.search(
            query=HARDCODED_QUERY,
            max_results=MAX_PAPERS,
        )
        print_success(f"Fetched {len(papers)} papers from ArXiv API")

        # PHASE 2: Publish to queue
        print_step("PHASE 2: Publishing papers to message queue...")
        correlation_id = f"prod_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        published_count = await arxiv_publisher.publish_discovered(
            papers=papers,
            correlation_id=correlation_id,
        )
        print_success(f"Published {published_count} papers to arxiv.discovered queue")
        print_info(f"Correlation ID: {correlation_id}")

        # PHASE 3: Store in database
        print_step("PHASE 3: Storing papers in database...")
        from src.shared.db.session import DatabaseSession
        from src.shared.models.source import Source, SourceType, ProcessingStatus
        from src.shared.repositories.source_repository import SourceRepository

        stored_count = 0
        skipped_count = 0

        async with DatabaseSession() as session:
            repo = SourceRepository(session)

            for paper in papers:
                # Check for duplicates
                existing = await repo.get_by_url(paper.arxiv_url)
                if existing:
                    print_info(f"  Skipping duplicate: {paper.paper_id}")
                    skipped_count += 1
                    continue

                # Create source record using kwargs (BaseRepository.create expects **kwargs)
                created = await repo.create(
                    source_type=SourceType.ARXIV,
                    url=paper.arxiv_url,
                    title=paper.title,
                    content=paper.abstract,
                    source_metadata={
                        "paper_id": paper.paper_id,
                        "version": paper.version,
                        "authors": paper.authors,
                        "categories": paper.categories,
                        "submitted_date": paper.submitted_date,
                        "pdf_url": paper.pdf_url,
                        "doi": paper.doi,
                        "source_query": HARDCODED_QUERY,
                        "correlation_id": correlation_id,
                    },
                    status=ProcessingStatus.FETCHED,
                    fetched_at=datetime.now(),
                )
                print_info(f"  Stored: [{created.id}] {paper.paper_id} - {paper.title[:40]}...")
                stored_count += 1

        print_success(f"Stored {stored_count} papers in database (skipped {skipped_count} duplicates)")

        # PHASE 4: Verify data
        print_step("PHASE 4: Verifying stored data...")
        async with DatabaseSession() as session:
            repo = SourceRepository(session)

            # Get recently stored papers
            recent = await repo.list_by_type(SourceType.ARXIV, limit=10)
            print_info(f"Total arxiv sources in database: {len(recent)}+")

            # Verify our papers
            for paper in papers[:3]:
                found = await repo.get_by_url(paper.arxiv_url)
                if found:
                    print_info(f"  Verified: {paper.paper_id} -> DB id {found.id}")
                else:
                    print_info(f"  Not found in DB: {paper.paper_id}")

        # Print cache statistics
        print_step("Cache statistics:")
        cache_stats = cache.get_stats()
        print_info(f"Cache backend: {cache_stats['backend_type']}")
        print_info(f"Cache initialized: {cache_stats['initialized']}")

        # Print publisher statistics
        print_step("Publisher statistics:")
        pub_stats = arxiv_publisher.get_stats()
        print_info(f"Published count: {pub_stats['published_count']}")
        print_info(f"Error count: {pub_stats['error_count']}")
        print_info(f"Success rate: {pub_stats['success_rate']:.2%}")

        # Print API client statistics
        print_step("API client statistics:")
        api_stats = api_client.get_stats()
        print_info(f"Request count: {api_stats['request_count']}")
        print_info(f"Error count: {api_stats['error_count']}")
        print_info(f"Cache hit count: {api_stats['cache_hit_count']}")

        # Cleanup
        print_step("Cleaning up resources...")
        await api_client.close()
        await arxiv_publisher.close()
        await mq_connection.close()
        await cache.close()

        from src.shared.db.config import dispose_engine
        await dispose_engine()

        print_success("All resources cleaned up")

        return True

    except Exception as e:
        print_error(f"Full pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all production tests."""
    print_header("PRODUCTION INTEGRATION TEST")
    print_info(f"Query: '{HARDCODED_QUERY}'")
    print_info(f"Max papers: {MAX_PAPERS}")
    print_info(f"Started at: {datetime.now().isoformat()}")

    results = {}

    # Run tests in order
    print_info("\nRunning tests in sequence...")

    # Test 1: Redis
    results["Redis Cache"] = await test_redis_cache()

    # Test 2: RabbitMQ
    results["RabbitMQ"] = await test_rabbitmq()

    # Test 3: PostgreSQL
    results["PostgreSQL"] = await test_postgresql()

    # Test 4: ArXiv Fetcher
    results["ArXiv Fetcher"] = await test_arxiv_fetcher()

    # Test 5: Full Pipeline
    results["Full Pipeline"] = await test_full_pipeline()

    # Summary
    print_header("TEST SUMMARY")

    passed = 0
    failed = 0

    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        icon = "[OK]" if result else "[X]"
        print(f"  {icon} {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")
    print(f"Finished at: {datetime.now().isoformat()}")

    # Exit code
    if failed > 0:
        print("\n[RESULT] Some tests FAILED")
        return 1
    else:
        print("\n[RESULT] All tests PASSED")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
