"""Cron-based scheduler for ArXiv fetcher.

Simple cron-based scheduling using aioschedule.
Runs the fetcher at configured intervals.
"""

import asyncio
import logging
import os

import aioschedule as schedule

from src.workers.arxiv_fetcher.worker import ArxivFetcherWorker, FetcherDependencies

logger = logging.getLogger(__name__)


class ArxivScheduler:
    """Scheduler for ArXiv fetcher.

    Runs fetcher on a cron schedule (default: every 30 minutes).

    Example:
        scheduler = ArxivScheduler()
        await scheduler.start()

        # Or run once:
        await scheduler.run_once()
    """

    def __init__(
        self,
        interval_minutes: int | None = None,
        dependencies: FetcherDependencies | None = None,
    ):
        """Initialize scheduler.

        Args:
            interval_minutes: Fetch interval (default from env or 30)
            dependencies: Pre-configured dependencies (creates default if None)
        """
        self.interval_minutes = interval_minutes or int(
            os.getenv("ARXIV_FETCH_INTERVAL_MINUTES", "30")
        )
        self.dependencies = dependencies
        self._running = False
        self._worker: ArxivFetcherWorker | None = None

    async def start(self) -> None:
        """Start the scheduler.

        Schedules fetcher job and runs indefinitely.
        """
        logger.info(f"Starting ArXiv scheduler (interval: {self.interval_minutes} minutes)")

        # Schedule the job
        schedule.every(self.interval_minutes).minutes.do(self._run_fetcher)

        # Run immediately on start
        await self._run_fetcher()

        self._running = True

        # Keep running
        while self._running:
            await schedule.run_pending()
            await asyncio.sleep(60)  # Check every minute

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stopped")

    async def run_once(self) -> None:
        """Run fetcher once (for testing/manual invocation)."""
        await self._run_fetcher()

    async def _run_fetcher(self) -> None:
        """Run the fetcher job."""
        try:
            logger.info("Running scheduled ArXiv fetch")

            # Create dependencies if not provided
            if self.dependencies is None:
                deps = await ArxivFetcherWorker.create_dependencies()
            else:
                deps = self.dependencies

            # Create and run worker
            worker = ArxivFetcherWorker(deps)
            await worker.run()

            stats = worker.get_stats()
            logger.info(f"Fetch complete: {stats}")

        except Exception as e:
            logger.exception(f"Scheduled fetch failed: {e}")


async def main():
    """Main entry point for scheduler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    scheduler = ArxivScheduler()

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
