"""Upsert operation helpers for SQLAlchemy repositories."""
import logging
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models.base import Base


logger = logging.getLogger(__name__)


class UpsertMixin:
    """Mixin for upsert (insert or update on conflict) operations."""
    
    async def upsert(
        self,
        id: Any,
        **kwargs,
    ) -> Any:
        """Upsert a single record (insert or update on conflict).
        
        Args:
            id: Primary key value
            **kwargs: Field values to insert/update
        
        Returns:
            Upserted model instance
        """
        model = self.model
        table = model.__table__
        primary_key_name = table.primary_key.columns[0].name
        
        logger.debug(
            f"{self._model_name}: Upserting {primary_key_name}={id}",
            extra={primary_key_name: id, "fields": list(kwargs.keys())},
        )
        
        try:
            # Check if exists
            existing = await self.session.get(model, id)
            
            if existing:
                # Update existing record
                for key, value in kwargs.items():
                    setattr(existing, key, value)
                
                logger.debug(
                    f"{self._model_name}: Updating existing record {primary_key_name}={id}",
                    extra={primary_key_name: id, "fields": list(kwargs.keys())},
                )
                
                # Refresh and return
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
            
            # Insert new record
            new_obj = model(id=id, **kwargs)
            self.session.add(new_obj)
            await self.session.flush()
            await self.session.refresh(new_obj)
            
            logger.debug(
                f"{self._model_name}: Inserted new record {primary_key_name}={id}",
                extra={primary_key_name: id},
            )
            
            return new_obj
        
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"{self._model_name}: Upsert failed for {primary_key_name}={id}",
                extra={primary_key_name: id, "error": str(e)},
                exc_info=True,
            )
            raise

