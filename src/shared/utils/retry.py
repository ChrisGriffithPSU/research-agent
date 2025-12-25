"""Retry utilities with exponential backoff and jitter."""
import asyncio
import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type

from src.shared.exceptions import ResearchAgentError


logger = logging.getLogger(__name__)


def calculate_backoff(
    attempt: int,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    max_seconds: float = 60.0,
    jitter_percent: float = 0.25,
) -> float:
    """Calculate exponential backoff delay with random jitter.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_seconds: Base delay for first retry
        factor: Exponential factor
        max_seconds: Maximum delay
        jitter_percent: Jitter percentage (0.0-1.0)
    
    Returns:
        Delay in seconds
    """
    delay = base_seconds * (factor ** attempt)
    delay = min(delay, max_seconds)
    
    # Add jitter: +/- jitter_percent
    if jitter_percent > 0:
        jitter = delay * jitter_percent
        delay = delay + random.uniform(-jitter, jitter)
    
    return max(0, delay)


def retry(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    backoff_base: float = 1.0,
    max_backoff_seconds: float = 60.0,
    jitter_percent: float = 0.25,
    retry_on: Optional[Tuple[Type[Exception]]] = None,
    on_retry_callback: Optional[Callable[[int, Exception], None]] = None,
):
    """Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (including first)
        backoff_factor: Exponential factor for delay calculation
        backoff_base: Base delay in seconds
        max_backoff_seconds: Maximum delay between attempts
        jitter_percent: Jitter percentage (0.0 = no jitter)
        retry_on: Tuple of exception types to retry on. If None, retry on all exceptions.
        on_retry_callback: Callback called after each failed attempt. 
            Args: (attempt_number, exception)
    
    Example:
        @retry(max_attempts=3, retry_on=(APITimeoutError, APIConnectionError))
        async def call_external_api():
            # Will retry 3 times on timeout/connection errors
            return await api_client.fetch()
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        delay = calculate_backoff(
                            attempt=attempt,
                            base_seconds=backoff_base,
                            factor=backoff_factor,
                            max_seconds=max_backoff_seconds,
                            jitter_percent=jitter_percent,
                        )
                        logger.debug(
                            f"Retrying {func.__name__} (attempt {attempt + 1}/{max_attempts})",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "delay_seconds": round(delay, 2),
                            },
                        )
                        await asyncio.sleep(delay)
                    
                    return await func(*args, **kwargs)
                
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry this exception
                    if retry_on is not None and not isinstance(e, retry_on):
                        logger.error(
                            f"Non-retryable exception in {func.__name__}: {type(e).__name__}: {e}",
                            extra={"function": func.__name__, "exception_type": type(e).__name__},
                        )
                        raise
                    
                    # Call callback if provided
                    if on_retry_callback:
                        try:
                            on_retry_callback(attempt, e)
                        except Exception as cb_error:
                            logger.error(
                                f"Retry callback failed: {cb_error}",
                                extra={"function": func.__name__, "callback_error": str(cb_error)},
                            )
                    
                    # Log retry
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {type(e).__name__}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "exception_type": type(e).__name__,
                            "exception_message": str(e),
                        },
                    exc_info=True,
                    )
            
            # Max attempts reached, raise last exception
            logger.error(
                f"{func.__name__} failed after {max_attempts} attempts",
                extra={"function": func.__name__, "max_attempts": max_attempts},
            )
            if last_exception is not None:
                raise last_exception
            else:
                raise RuntimeError(f"{func.__name__} failed with no exception logged")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        delay = calculate_backoff(
                            attempt=attempt,
                            base_seconds=backoff_base,
                            factor=backoff_factor,
                            max_seconds=max_backoff_seconds,
                            jitter_percent=jitter_percent,
                        )
                        logger.debug(
                            f"Retrying {func.__name__} (attempt {attempt + 1}/{max_attempts})",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "delay_seconds": round(delay, 2),
                            },
                        )
                        time.sleep(delay)
                    
                    return func(*args, **kwargs)
                
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry this exception
                    if retry_on is not None and not isinstance(e, retry_on):
                        logger.error(
                            f"Non-retryable exception in {func.__name__}: {type(e).__name__}: {e}",
                            extra={"function": func.__name__, "exception_type": type(e).__name__},
                        )
                        raise
                    
                    # Call callback if provided
                    if on_retry_callback:
                        try:
                            on_retry_callback(attempt, e)
                        except Exception as cb_error:
                            logger.error(
                                f"Retry callback failed: {cb_error}",
                                extra={"function": func.__name__, "callback_error": str(cb_error)},
                            )
                    
                    # Log retry
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {type(e).__name__}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "exception_type": type(e).__name__,
                            "exception_message": str(e),
                        },
                        exc_info=True,
                    )
            
            # Max attempts reached, raise last exception
            logger.error(
                f"{func.__name__} failed after {max_attempts} attempts",
                extra={"function": func.__name__, "max_attempts": max_attempts},
            )
            if last_exception is not None:
                raise last_exception
            else:
                raise RuntimeError(f"{func.__name__} failed with no exception logged")
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

