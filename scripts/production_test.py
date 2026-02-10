#!/usr/bin/env python3
"""Production-style integration test script.

Tests the pipeline WITHOUT LLM calls:
- ArXiv Fetcher (real API calls)
- Message Queue (RabbitMQ)
- Database (PostgreSQL)

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

HARDCODED_CATEGORIES = ["cs.LG", "stat.ML"]  # Categories to test
MAX_PAPERS = 3  # Limit papers for quick testing


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
# TEST 1: RABBITMQ MESSAGE QUEUE
# ============================================================================


async def test_rabbitmq() -> bool:
    """Test RabbitMQ connectivity and message operations."""
    print_header("TEST 1: RABBITMQ MESSAGE QUEUE")

    try:
        print_step("Initializing RabbitMQ connection...")
        from src.shared.messaging.connection import RabbitMQConnection
        from src.shared.messaging.config import MessagingConfig

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

        # Test publish
        print_step("Testing message publishing...")
        from src.shared.messaging.publisher import MessagePublisher
        from src.shared.messaging.retry import ExponentialBackoffStrategy
        from src.workers.shared.message_schemas import PaperTriageRequest

        publisher = MessagePublisher(
            connection=connection,
            retry_strategy=ExponentialBackoffStrategy(max_attempts=3),
        )

        # Create a test message
        test_message = PaperTriageRequest(
            paper_id="test.12345",
            title="Production Test Paper",
            authors=["Test Author"],
            abstract="This is a test paper for production testing.",
            categories=["cs.LG"],
            arxiv_url="https://arxiv.org/abs/test.12345",
            pdf_url="https://arxiv.org/pdf/test.12345.pdf",
        )

        await publisher.publish(
            message=test_message,
            routing_key="paper.triage.request",
        )
        print_success(f"Published test message to paper.triage.request")

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
# TEST 2: POSTGRESQL DATABASE
# ============================================================================


async def test_postgresql() -> bool:
    """Test PostgreSQL connectivity and operations."""
    print_header("TEST 2: POSTGRESQL DATABASE")

    try:
        print_step("Initializing database connection...")
        from src.shared.db.config import db_config, get_async_engine
        from src.shared.db.session import DatabaseSession
        from src.shared.repositories.paper_repository import PaperRepository

        print_info(
            f"Database URL: postgresql://{db_config.user}:***@{db_config.host}:{db_config.port}/{db_config.name}"
        )

        # Get engine
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

            # Test paper repository
            print_step("Testing paper repository...")
            repo = PaperRepository(session)

            test_paper_id = f"test.{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Check if exists
            exists = await repo.exists(test_paper_id)
            print_info(f"Paper exists: {exists}")

            # Store paper
            await repo.store_paper_id(test_paper_id, status="discovered")
            print_success(f"Stored paper: {test_paper_id}")

            # Verify
            exists = await repo.exists(test_paper_id)
            if exists:
                print_success("Paper verified in database")
            else:
                print_error("Paper not found after storing")
                return False

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
# TEST 3: ARXIV FETCHER (REAL API)
# ============================================================================


async def test_arxiv_fetcher() -> bool:
    """Test ArXiv fetcher with real API calls."""
    print_header("TEST 3: ARXIV FETCHER (REAL API)")

    try:
        print_step("Initializing ArXiv API client...")
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.workers.arxiv_fetcher.config import ArxivFetcherConfig

        config = ArxivFetcherConfig(
            max_results_per_category=MAX_PAPERS,
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

        # Fetch by categories
        print_step(f"Testing category fetch: {HARDCODED_CATEGORIES}...")
        papers = await api_client.fetch_by_categories(
            categories=HARDCODED_CATEGORIES,
            max_per_category=MAX_PAPERS,
            days_back=7,
        )

        print_success(f"Found {len(papers)} papers")

        if papers:
            print_step("Paper details:")
            for i, paper in enumerate(papers[:3], 1):
                print_info(f"\n  Paper {i}:")
                print_info(f"    ID: {paper.paper_id}")
                print_info(f"    Title: {paper.title[:60]}...")
                print_info(f"    Authors: {', '.join(paper.authors[:2])}")
                print_info(f"    Categories: {', '.join(paper.categories[:2])}")
                print_info(f"    ArXiv URL: {paper.arxiv_url}")

        # Get stats
        print_step("API client statistics:")
        stats = api_client.get_stats()
        print_info(f"Requests made: {stats['request_count']}")
        print_info(f"Errors: {stats['error_count']}")

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
# TEST 4: FULL PIPELINE
# ============================================================================


async def test_full_pipeline() -> bool:
    """Test the full pipeline: Fetch -> Publish -> Store."""
    print_header("TEST 4: FULL PIPELINE (FETCH -> QUEUE -> DATABASE)")

    try:
        # Initialize components
        print_step("Initializing components...")

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
            retry_strategy=ExponentialBackoffStrategy(max_attempts=3),
        )
        print_success("RabbitMQ publisher initialized")

        # ArXiv Fetcher
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.workers.arxiv_fetcher.config import ArxivFetcherConfig

        fetcher_config = ArxivFetcherConfig(
            max_results_per_category=MAX_PAPERS,
        )

        api_client = ArxivAPIClient(config=fetcher_config)
        await api_client.initialize()
        print_success("ArXiv fetcher initialized")

        # PHASE 1: Fetch papers
        print_step("PHASE 1: Fetching papers...")
        papers = await api_client.fetch_by_categories(
            categories=HARDCODED_CATEGORIES[:1],
            max_per_category=MAX_PAPERS,
            days_back=7,
        )
        print_success(f"Fetched {len(papers)} papers from ArXiv API")

        # PHASE 2: Publish to queue
        print_step("PHASE 2: Publishing papers to message queue...")
        from src.workers.shared.message_schemas import PaperTriageRequest

        published_count = 0
        for paper in papers:
            message = PaperTriageRequest(
                paper_id=paper.paper_id,
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                categories=paper.categories,
                arxiv_url=paper.arxiv_url,
                pdf_url=paper.pdf_url,
                submitted_date=paper.submitted_date,
            )
            await publisher.publish(
                message=message,
                routing_key="paper.triage.request",
            )
            published_count += 1

        print_success(f"Published {published_count} papers to queue")

        # PHASE 3: Store in database
        print_step("PHASE 3: Storing papers in database...")
        from src.shared.db.session import DatabaseSession
        from src.shared.repositories.paper_repository import PaperRepository

        stored_count = 0
        skipped_count = 0

        async with DatabaseSession() as session:
            repo = PaperRepository(session)

            for paper in papers:
                # Check for duplicates
                exists = await repo.exists(paper.paper_id)
                if exists:
                    print_info(f"  Skipping duplicate: {paper.paper_id}")
                    skipped_count += 1
                    continue

                # Store paper
                await repo.store_paper_id(paper.paper_id, status="discovered")
                print_info(f"  Stored: {paper.paper_id}")
                stored_count += 1

        print_success(f"Stored {stored_count} papers (skipped {skipped_count} duplicates)")

        # Cleanup
        print_step("Cleaning up resources...")
        await api_client.close()
        await mq_connection.close()

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
    print_info(f"Categories: {HARDCODED_CATEGORIES}")
    print_info(f"Max papers: {MAX_PAPERS}")
    print_info(f"Started at: {datetime.now().isoformat()}")

    results = {}

    # Run tests
    print_info("\nRunning tests in sequence...")

    results["RabbitMQ"] = await test_rabbitmq()
    results["PostgreSQL"] = await test_postgresql()
    results["ArXiv Fetcher"] = await test_arxiv_fetcher()
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
