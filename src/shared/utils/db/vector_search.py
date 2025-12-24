"""Enhanced vector search helpers for pgvector."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import cast

# pgvector support will be available at runtime
# from pgvector.sqlalchemy import Vector

from src.shared.models.base import Base


logger = logging.getLogger(__name__)


class EnhancedVectorSearchMixin:
    """Mixin for enhanced vector similarity search with filtering."""
    
    async def vector_similarity_search_filtered(
        self,
        query_embedding: List[float],
        filters: Optional[Dict[str, Any]] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> List[Any]:
        """Vector similarity search with optional filters.
        
        Args:
            query_embedding: Query vector (list of floats)
            filters: Dict of field name -> value to filter results
            date_range: Tuple of (start_date, end_date) to filter by date
            limit: Maximum number of results
            threshold: Minimum similarity threshold (cosine similarity)
        
        Returns:
            List of model instances ordered by similarity (highest first)
        
        Example:
            # Search for similar items, filter by category
            results = await repo.vector_similarity_search_filtered(
                query_embedding=[0.1, 0.2, ...],
                filters={"category": "feature_engineering"},
                limit=20,
            )
            
            # Search with date range
            results = await repo.vector_similarity_search_filtered(
                query_embedding=[0.1, 0.2, ...],
                date_range=(datetime(2024, 1, 1), datetime.now()),
                limit=10,
            )
        """
        model = self.model
        table = model.__table__
        
        # Find vector column
        vector_column = None
        for col in table.columns:
            if col.name.endswith("embedding"):
                vector_column = col
                break
        
        if vector_column is None:
            logger.error(f"{self._model_name}: No embedding column found")
            raise ValueError(f"Model {model.__name__} has no embedding column")
        
        logger.debug(
            f"{self._model_name}: Vector search",
            extra={
                "embedding_dim": len(query_embedding),
                "filters": filters,
                "date_range": str(date_range) if date_range else None,
                "limit": limit,
                "threshold": threshold,
            },
        )
        
        try:
            # Build query with vector similarity
            # Note: This is a placeholder. Actual pgvector usage requires:
            # 1. pgvector extension installed in PostgreSQL
            # 2. Proper vector column type (VECTOR type in pgvector)
            #
            # When pgvector is available, the query would look like:
            # stmt = select(table).order_by(
            #     table.c.embedding.cosine_distance(query_embedding)
            # ).limit(limit)
            #
            # For now, we'll return empty and log a warning
            logger.warning(
                f"{self._model_name}: pgvector search requires pgvector extension",
                extra={
                    "model": model.__name__,
                    "vector_column": vector_column.name,
                },
            )
            
            # Placeholder: return all without vector search
            # In production, this would be:
            # stmt = select(table).order_by(vector_column.l2_distance(query_embedding))
            # if filters:
            #     conditions = []
            #     for key, value in filters.items():
            #         conditions.append(getattr(table.c, key) == value)
            #     stmt = stmt.where(and_(*conditions))
            # if date_range:
            #     start_date, end_date = date_range
            #     stmt = stmt.where(table.c.created_at >= start_date, table.c.created_at <= end_date)
            # stmt = stmt.limit(limit)
            # if threshold:
            #     stmt = stmt.where(table.c.distance <= threshold)
            # result = await self.session.execute(stmt)
            # return result.scalars().all()
            
            return []
        
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"{self._model_name}: Vector search failed",
                extra={
                    "filters": filters,
                    "date_range": str(date_range) if date_range else None,
                    "limit": limit,
                    "threshold": threshold,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def vector_similarity_search_paginated(
        self,
        query_embedding: List[float],
        page: int = 1,
        per_page: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Paginated vector similarity search.
        
        Args:
            query_embedding: Query vector
            page: Page number (1-indexed)
            per_page: Results per page
            filters: Optional filters (passed to vector_similarity_search_filtered)
        
        Returns:
            Dict with:
                - results: List of model instances
                - page: Current page
                - per_page: Results per page
                - total_pages: Total number of pages (estimated)
        
        Example:
            results = await repo.vector_similarity_search_paginated(
                query_embedding=[0.1, 0.2, ...],
                page=2,
                per_page=20,
            )
        """
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get results
        results = await self.vector_similarity_search_filtered(
            query_embedding=query_embedding,
            filters=filters,
            limit=per_page + offset,  # Get enough for pagination
        )
        
        # Paginate
        paginated_results = results[offset:offset + per_page]
        
        # Estimate total pages (rough estimate, would need total count)
        total_pages = (len(results) + per_page - 1) // per_page
        
        return {
            "results": paginated_results,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

