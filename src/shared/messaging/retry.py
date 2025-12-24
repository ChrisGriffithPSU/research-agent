"""Retry strategies for messaging operations."""
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Optional

from src.shared.messaging.exceptions import PermanentError, TemporaryError

logger = logging.getLogger(__name__)


class IRetryStrategy(ABC):
    """Interface for retry behavior strategies.

    What changes: Max attempts, backoff duration, error types
    What never changes: Should retry and get_backoff interfaces
    """

    @abstractmethod
    async def should_retry(
        self,
        attempt: int,
        error: Exception,
    ) -> bool:
        """Determine if operation should be retried.

        Args:
            attempt: Current attempt number (0-indexed)
            error: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        pass

    @abstractmethod
    def get_backoff(self, attempt: int) -> float:
        """Get backoff duration in seconds.

        Args:
            attempt: Current attempt number

        Returns:
            Seconds to wait before retry
        """
        pass


class ExponentialBackoffStrategy(IRetryStrategy):
    """Exponential backoff with jitter.

    Doubles delay on each retry: base_delay * (2 ^ attempt)
    Adds jitter (±20%) to avoid thundering herd problem.
    Caps at max_delay to prevent excessive waits.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        """Initialize exponential backoff strategy.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds for first retry
            max_delay: Maximum delay cap in seconds
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def should_retry(
        self,
        attempt: int,
        error: Exception,
    ) -> bool:
        """Retry if under max attempts and not permanent error."""
        # Check max attempts
        if attempt >= self.max_attempts:
            logger.debug(f"Max attempts ({self.max_attempts}) reached, not retrying")
            return False

        # Permanent errors should not be retried
        if isinstance(error, PermanentError):
            logger.debug(f"Permanent error ({type(error).__name__}), not retrying")
            return False

        # PublishError and ConnectionError are usually permanent
        # Don't retry them (let the caller handle)
        from src.shared.messaging.exceptions import PublishError, ConnectionError
        if isinstance(error, (PublishError, ConnectionError)):
            logger.debug(f"Permanent messaging error ({type(error).__name__}), not retrying")
            return False

        # Retry all other errors (TemporaryError or unknown exceptions)
        logger.debug(f"Transient error ({type(error).__name__}), retrying (attempt {attempt + 1}/{self.max_attempts})")
        return True

    def get_backoff(self, attempt: int) -> float:
        """Calculate backoff with jitter."""
        # Exponential backoff
        delay = self.base_delay * (2 ** attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter (±20%) to avoid thundering herd
        # This prevents all retries from happening simultaneously
        jitter = delay * 0.2 * (random.random() * 2 - 1)
        final_delay = delay + jitter

        logger.debug(f"Backoff for attempt {attempt}: {final_delay:.2f}s (base: {delay:.2f}s, jitter: {jitter:.2f}s)")
        return final_delay


class LinearBackoffStrategy(IRetryStrategy):
    """Linear backoff strategy.

    Increments delay by fixed amount on each retry:
    base_delay + (increment * attempt)
    Useful for predictable, gradual backoff.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        increment: float = 1.0,
        max_delay: float = 60.0,
    ):
        """Initialize linear backoff strategy.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds for first retry
            increment: Increment added on each retry
            max_delay: Maximum delay cap in seconds
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.increment = increment
        self.max_delay = max_delay

    async def should_retry(
        self,
        attempt: int,
        error: Exception,
    ) -> bool:
        """Retry if under max attempts and not permanent error."""
        if attempt >= self.max_attempts:
            return False

        if isinstance(error, PermanentError):
            return False

        from src.shared.messaging.exceptions import PublishError, ConnectionError
        if isinstance(error, (PublishError, ConnectionError)):
            return False

        return True

    def get_backoff(self, attempt: int) -> float:
        """Calculate linear backoff."""
        # Linear increment
        delay = self.base_delay + (self.increment * attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        logger.debug(f"Backoff for attempt {attempt}: {delay:.2f}s")
        return delay


class NoRetryStrategy(IRetryStrategy):
    """No retry strategy (fail immediately).

    Useful when you want to fail fast without retries.
    """

    def __init__(self):
        """Initialize no-retry strategy."""
        pass

    async def should_retry(
        self,
        attempt: int,
        error: Exception,
    ) -> bool:
        """Never retry."""
        return False

    def get_backoff(self, attempt: int) -> float:
        """No backoff (not used)."""
        return 0.0

