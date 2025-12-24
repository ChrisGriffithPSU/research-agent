"""Batch operation helpers for SQLAlchemy repositories."""
import logging
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models.base import Base


logger = logging.getLogger(__name__)


class BatchInsertMixin:
    """Mixin for batch insert operations in repositories."""
    
    async def batch_create(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Any]:
        """Batch insert multiple records efficiently.
        
        Args:
            items: List of dictionaries with field values
        
        Returns:
            List of created model instances with IDs
        """
        if not items:
            logger.debug(f"{self._model_name}: Batch create empty")
            return []
        
        model = self.model
        table = model.__table__
        
        logger.debug(
            f"{self._model_name}: Batch creating {len(items)} items",
            extra={"batch_size": len(items), "table": table.name},
        )
        
        try:
            # Create insert statement with returning
            stmt = insert(table).values(items).returning(table)
            
            # Execute
            result = await self.session.execute(stmt)
            
            # Get created objects
            created = result.scalars().all()
            
            logger.info(
                f"{self._model_name}: Batch created {len(created)} items",
                extra={"created_count": len(created), "table": table.name},
            )
            
            return list(created)
        
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"{self._model_name}: Batch create failed",
                extra={"batch_size": len(items), "table": table.name, "error": str(e)},
                exc_info=True,
            )
            raise
    
    async def batch_create_or_ignore(
        self,
        items: List[Dict[str, Any]],
        conflict_columns: Optional[List[str]] = None,
    ) -> int:
        """Batch insert, ignore rows that violate unique constraints.
        
        Args:
            items: List of dictionaries with field values
            conflict_columns: Column(s) that define unique constraint.
                         If None, uses first column of primary key.
        
        Returns:
            Number of rows inserted
        """
        if not items:
            logger.debug(f"{self._model_name}: Batch create-or-ignore empty")
            return 0
        
        model = self.model
        table = model.__table__
        
        # Determine conflict column
        if not conflict_columns:
            conflict_columns = [table.primary_key.columns[0].name]
        
        logger.debug(
            f"{self._model_name}: Batch creating {len(items)} items (ignore conflicts)",
            extra={
                "batch_size": len(items),
                "table": table.name,
                "conflict_columns": conflict_columns,
            },
        )
        
        try:
            # Create insert statement with ON CONFLICT DO NOTHING
            stmt = (
                pg_insert(table)
                .values(items)
                .on_conflict_do_nothing(constraint=conflict_columns[0])
                .returning(table)
            )
            
            # Execute
            result = await self.session.execute(stmt)
            
            # Get inserted count
            inserted_count = len(result.scalars().all())
            
            # Calculate how many were ignored
            ignored_count = len(items) - inserted_count
            
            logger.info(
                f"{self._model_name}: Batch inserted {inserted_count} items, {ignored_count} ignored",
                extra={
                    "inserted_count": inserted_count,
                    "ignored_count": ignored_count,
                    "table": table.name,
                },
            )
            
            return inserted_count
        
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"{self._model_name}: Batch create-or-ignore failed",
                extra={
                    "batch_size": len(items),
                    "table": table.name,
                    "conflict_columns": conflict_columns,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise


class BatchUpsertMixin:
    """Mixin for batch upsert operations in repositories."""
    
    async def batch_upsert(
        self,
        items: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> List[Any]:
        """Batch upsert (insert or update on conflict).
        
        Args:
            items: List of dictionaries with field values
            conflict_columns: Column(s) that define unique constraint
            update_columns: Which columns to update on conflict.
                         If None, updates all columns except conflict_columns
        
        Returns:
            List of upserted model instances
        """
        if not items:
            logger.debug(f"{self._model_name}: Batch upsert empty")
            return []
        
        model = self.model
        table = model.__table__
        
        # Determine update columns
        if update_columns is None:
            # Update all columns except conflict columns
            update_columns = [
                col.name for col in table.columns
                if col.name not in conflict_columns
            ]
        
        logger.debug(
            f"{self._model_name}: Batch upserting {len(items)} items",
            extra={
                "batch_size": len(items),
                "table": table.name,
                "conflict_columns": conflict_columns,
                "update_columns": update_columns,
            },
        )
        
        try:
            # Create update dict: "column = excluded(column)" to only update specified columns
            update_dict = {col: excluded(col) for col in update_columns}
            
            # Create upsert statement
            stmt = (
                pg_insert(table)
                .values(items)
                .on_conflict_do_update(
                    constraint=conflict_columns[0],
                    set_=update_dict,
                )
                .returning(table)
            )
            
            # Execute
            result = await self.session.execute(stmt)
            
            # Get upserted objects
            upserted = result.scalars().all()
            
            logger.info(
                f"{self._model_name}: Batch upserted {len(upserted)} items",
                extra={"upserted_count": len(upserted), "table": table.name},
            )
            
            return list(upserted)
        
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"{self._model_name}: Batch upsert failed",
                extra={
                    "batch_size": len(items),
                    "table": table.name,
                    "conflict_columns": conflict_columns,
                    "update_columns": update_columns,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

