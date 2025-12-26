"""Token bucket rate limiter for arXiv API.

Implements rate limiting at 1 request per 3 seconds (arXiv limit).
Uses asyncio for async-compatible rate limiting.
"""
import asyncio
import time
import logging
from typing import Optional

from src.services.fetchers.arxiv.exceptions import RateLimitError


logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for arXiv API.
    
    Implements rate limiting with configurable tokens per second.
    arXiv requires 1 request per 3 seconds (0.333 req/s).
    
    Features:
    - Token bucket algorithm
    - Async-compatible
    - Burst handling
    - Automatic refill
    
    Attributes:
        rate: Tokens per second (default: 0.333 for arXiv)
        capacity: Maximum tokens in bucket (default: 1)
        tokens: Current token count
        last_update: Last update timestamp
    """
    
    def __init__(
        self,
        rate: float = 0.333,  # 1 request per 3 seconds
        capacity: int = 1,
        initial_tokens: Optional[float] = None,
    ):
        """Initialize rate limiter.
        
        Args:
            rate: Tokens per second (0.333 for arXiv's 1 req/3s)
            capacity: Maximum tokens in bucket
            initial_tokens: Initial token count (defaults to capacity)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire permission to make a request.
        
        Blocks until a token is available.
        
        Raises:
            RateLimitError: If rate limiting fails
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                # Token available, consume it
                self.tokens -= 1
                logger.debug(f"Rate limiter: acquired token, {self.tokens:.2f} remaining")
                return
            
            # No token available, calculate wait time
            wait_time = (1 - self.tokens) / self.rate
        
        # Release lock before waiting
        logger.debug(f"Rate limiter: waiting {wait_time:.2f}s for token")
        await asyncio.sleep(wait_time)
        
        # Try again (should have token now)
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                logger.debug(f"Rate limiter: acquired after wait, {self.tokens:.2f} remaining")
                return
            
            # This shouldn't happen, but handle gracefully
            raise RateLimitError(
                message="Failed to acquire rate limit token",
                retry_after=int(wait_time + 1),
            )
    
    async def get_delay(self) -> float:
        """Get the delay until next request is allowed.
        
        Returns:
            Delay in seconds (0 if available now)
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                return 0.0
            
            return (1 - self.tokens) / self.rate
    
    async def try_acquire(self) -> bool:
        """Try to acquire a token without blocking.
        
        Returns:
            True if token acquired, False otherwise
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            
            return False
    
    def reset(self) -> None:
        """Reset rate limiter state."""
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        logger.info("Rate limiter reset")
    
    def get_available_tokens(self) -> float:
        """Get number of available tokens.
        
        Returns:
            Current token count
        """
        now = time.monotonic()
        elapsed = now - self.last_update
        tokens = min(
            self.capacity,
            self.tokens + elapsed * self.rate
        )
        return tokens
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics.
        
        Returns:
            Dict with rate limiter stats
        """
        return {
            "rate": self.rate,
            "capacity": self.capacity,
            "available_tokens": self.get_available_tokens(),
            "wait_time": (1 - self.tokens) / self.rate if self.tokens < 1 else 0,
        }
    
    def __repr__(self) -> str:
        tokens = self.get_available_tokens()
        return (
            f"RateLimiter("
            f"rate={self.rate:.3f}/s, "
            f"capacity={self.capacity}, "
            f"available={tokens:.2f})"
        )


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts based on API responses.
    
    Starts with conservative rate and adjusts based on 429 responses.
    
    Attributes:
        base_rate: Starting rate (requests per second)
        min_rate: Minimum rate to use
        max_rate: Maximum rate to use
        backoff_factor: Multiplier for backoff on 429
        recovery_factor: Multiplier for rate recovery on success
    """
    
    def __init__(
        self,
        base_rate: float = 0.33,  # 1 req/3s
        min_rate: float = 0.1,    # 1 req/10s
        max_rate: float = 0.5,    # 1 req/2s
        backoff_factor: float = 0.8,
        recovery_factor: float = 1.1,
    ):
        """Initialize adaptive rate limiter.
        
        Args:
            base_rate: Starting rate
            min_rate: Minimum rate
            max_rate: Maximum rate
            backoff_factor: Multiplier for backoff on 429
            recovery_factor: Multiplier for recovery on success
        """
        self.base_rate = base_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        
        self.current_rate = base_rate
        self.rate_limiter = RateLimiter(rate=base_rate)
        self._consecutive_429s = 0
        self._consecutive_successes = 0
    
    async def acquire(self) -> None:
        """Acquire permission with adaptive rate limiting."""
        await self.rate_limiter.acquire()
    
    async def on_success(self) -> None:
        """Called on successful API response."""
        self._consecutive_429s = 0
        self._consecutive_successes += 1
        
        # Gradually increase rate on success
        if self._consecutive_successes >= 3:
            new_rate = min(
                self.max_rate,
                self.current_rate * self.recovery_factor
            )
            if new_rate != self.current_rate:
                self.current_rate = new_rate
                self.rate_limiter = RateLimiter(rate=new_rate)
                logger.info(f"Rate limiter: increased rate to {new_rate:.3f}/s")
            self._consecutive_successes = 0
    
    async def on_rate_limit(self, retry_after: int = 3) -> None:
        """Called on 429 rate limit response.
        
        Args:
            retry_after: Retry-After header value (seconds)
        """
        self._consecutive_429s += 1
        self._consecutive_successes = 0
        
        # Decrease rate based on consecutive failures
        new_rate = max(
            self.min_rate,
            self.current_rate * (self.backoff_factor ** self._consecutive_429s)
        )
        
        if new_rate != self.current_rate:
            self.current_rate = new_rate
            self.rate_limiter = RateLimiter(rate=new_rate)
            logger.warning(
                f"Rate limiter: decreased rate to {new_rate:.3f}/s "
                f"({self._consecutive_429s} consecutive 429s)"
            )
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics.
        
        Returns:
            Dict with stats
        """
        return {
            **self.rate_limiter.get_stats(),
            "current_rate": self.current_rate,
            "consecutive_429s": self._consecutive_429s,
            "consecutive_successes": self._consecutive_successes,
        }
    
    def __repr__(self) -> str:
        return (
            f"AdaptiveRateLimiter("
            f"rate={self.current_rate:.3f}/s, "
            f"429s={self._consecutive_429s})"
        )

