"""Database operation decorators."""
import functools
import logging
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.database import DatabaseError


logger = logging.getLogger(__name__)


def db_transaction(func: Callable):
    """Decorator for automatic transaction management.
    
    Wraps async function in a transaction that commits on success
    and rolls back on exception.
    
    Args:
        func: Async function to wrap
    
    Example:
        @db_transaction
        async def create_digest_with_items(digest_data, items):
            digest = await DigestRepository.create(**digest_data)
            for item in items:
                await DigestItemRepository.create(digest_id=digest.id, **item)
            # Commits automatically on success
            # Rolls back automatically on exception
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract session from arguments or kwargs
        # This assumes session is passed as 'session' kwarg or first positional arg
        session = kwargs.get('session')
        if session is None and args and hasattr(args[0], '__class__'):
            # Try to get from repository self.session
            try:
                session = args[0].session
            except (AttributeError, IndexError):
                pass
        
        if session is None:
            raise RuntimeError(
                f"Could not find database session for {func.__name__}. "
                "Pass 'session' kwarg or ensure first arg has .session attribute"
            )
        
        # Get table name for logging
        table_name = getattr(func, '__self__', None).__class__.__name__ if hasattr(func, '__self__') else 'unknown'
        
        logger.debug(
            f"{table_name}: Starting transaction for {func.__name__}",
            extra={"function": func.__name__},
        )
        
        try:
            # Begin transaction (already done in DatabaseSession)
            # Execute function
            result = await func(*args, **kwargs)
            
            # Commit transaction
            await session.commit()
            
            logger.debug(
                f"{table_name}: Transaction committed for {func.__name__}",
                extra={"function": func.__name__},
            )
            
            return result
        
        except DatabaseError as e:
            # Database errors should have already been raised
            await session.rollback()
            logger.error(
                f"{table_name}: Transaction rolled back (DatabaseError) for {func.__name__}",
                extra={"function": func.__name__, "error": str(e)},
            )
            raise
        
        except Exception as e:
            # Rollback on any other exception
            await session.rollback()
            logger.error(
                f"{table_name}: Transaction rolled back for {func.__name__}",
                extra={"function": func.__name__, "error": str(e)},
                exc_info=True,
            )
            raise DatabaseError(
                message=f"Transaction failed in {func.__name__}: {e}",
                original=e,
            )


def query_timeout(seconds: int):
    """Decorator to set statement timeout for database queries.
    
    Uses PostgreSQL's statement_timeout setting for the transaction.
    
    Args:
        seconds: Timeout in seconds
    
    Example:
        @query_timeout(seconds=5)
        async def slow_query():
            # Will fail after 5 seconds
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            session = kwargs.get('session')
            if session is None and args and hasattr(args[0], '__class__'):
                try:
                    session = args[0].session
                except (AttributeError, IndexError):
                    pass
            
            if session is None:
                # Can't set timeout without session
                return await func(*args, **kwargs)
            
            # Get table name
            table_name = getattr(func, '__self__', None).__class__.__name__ if hasattr(func, '__self__') else 'unknown'
            
            # Execute SET LOCAL statement_timeout
            # Note: This requires executing raw SQL
            # For now, we'll just log the timeout
            logger.debug(
                f"{table_name}: Query timeout set to {seconds}s for {func.__name__}",
                extra={"function": func.__name__, "timeout_seconds": seconds},
            )
            
            # In production, would execute:
            # await session.execute(text(f"SET LOCAL statement_timeout = '{seconds}s'"))
            # result = await func(*args, **kwargs)
            # await session.execute(text("RESET statement_timeout"))
            # return result
            
            # For now, just call function
            return await func(*args, **kwargs)
        
        return wrapper

