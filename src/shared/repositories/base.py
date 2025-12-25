"""Generic repository base class with common CRUD operations."""
import logging
from typing import Any, Generic, List, Optional, Type, TypeVar

# from pgvector.sqlalchemy import Vector
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions import (
    DatabaseError,
    RepositoryConflictError,
    RepositoryNotFoundError,
)
from src.shared.models.base import Base

logger = logging.getLogger(__name__)

# Generic type variable for model classes
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations.

    All repositories inherit from this to get standard CRUD functionality.
    Override methods as needed for specific query requirements.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Async session for database operations
        """
        self.model = model
        self.session = session
        self._model_name = model.__name__

    async def create(self, **kwargs) -> ModelType:
        """Create a new model instance.

        Args:
            **kwargs: Field values for model

        Returns:
            Created model instance with ID

        Raises:
            RepositoryConflictError: Constraint violation (duplicate, etc.)
            DatabaseError: Other database errors
        """
        logger.debug(
            f"{self._model_name}: Creating with params={self._sanitize_params(kwargs)}"
        )
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            logger.info(f"{self._model_name}: Created {instance}")
            return instance
        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"{self._model_name}: Integrity error during create: {e}")
            raise RepositoryConflictError(
                f"Failed to create {self._model_name}: constraint violation"
            ) from e
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"{self._model_name}: Database error during create: {e}")
            raise DatabaseError(
                f"Failed to create {self._model_name}: {e}"
            ) from e

    async def get(self, id: int) -> Optional[ModelType]:
        """Get model instance by ID.

        Args:
            id: Primary key ID

        Returns:
            Model instance or None if not found
        """
        logger.debug(f"{self._model_name}: Getting id={id}")
        try:
            result = await self.session.get(self.model, id)
            if result:
                logger.debug(f"{self._model_name}: Found id={id}")
            else:
                logger.debug(f"{self._model_name}: Not found id={id}")
            return result
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during get: {e}")
            raise DatabaseError(f"Failed to get {self._model_name} id={id}: {e}") from e

    async def get_or_404(self, id: int) -> ModelType:
        """Get model instance by ID, raise exception if not found.

        Args:
            id: Primary key ID

        Returns:
            Model instance

        Raises:
            RepositoryNotFoundError: If instance not found
        """
        instance = await self.get(id)
        if instance is None:
            logger.warning(f"{self._model_name}: Not found id={id}, raising 404")
            raise RepositoryNotFoundError(
                f"{self._model_name} with id={id} not found"
            )
        return instance

    async def get_all(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[ModelType]:
        """Get all model instances with optional pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of model instances
        """
        logger.debug(
            f"{self._model_name}: Getting all with limit={limit}, offset={offset}"
        )
        try:
            query = select(self.model)
            if limit is not None:
                query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)
            result = await self.session.execute(query)
            instances = list[ModelType](result.scalars().all())
            logger.debug(f"{self._model_name}: Found {len(instances)} instances")
            return instances
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during get_all: {e}")
            raise DatabaseError(
                f"Failed to get all {self._model_name}: {e}"
            ) from e

    async def update(self, id: int, **kwargs) -> ModelType:
        """Update model instance by ID.

        Args:
            id: Primary key ID
            **kwargs: Fields to update

        Returns:
            Updated model instance

        Raises:
            RepositoryNotFoundError: If instance not found
            DatabaseError: Other database errors
        """
        logger.debug(
            f"{self._model_name}: Updating id={id} with params={self._sanitize_params(kwargs)}"
        )
        try:
            stmt = (
                update(self.model)
                .where(self.model.id == id)
                .values(**kwargs)
                .returning(self.model)
            )
            result = await self.session.execute(stmt)
            instance = result.scalar_one_or_none()

            if instance is None:
                logger.warning(f"{self._model_name}: Not found for update id={id}")
                raise RepositoryNotFoundError(
                    f"{self._model_name} with id={id} not found"
                )

            logger.info(f"{self._model_name}: Updated id={id}")
            return instance
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"{self._model_name}: Database error during update: {e}")
            raise DatabaseError(
                f"Failed to update {self._model_name} id={id}: {e}"
            ) from e

    async def delete(self, id: int) -> bool:
        """Delete model instance by ID.

        Args:
            id: Primary key ID

        Returns:
            True if deleted, False if not found

        Raises:
            DatabaseError: Database errors
        """
        logger.debug(f"{self._model_name}: Deleting id={id}")
        try:
            instance = await self.get(id)
            if instance is None:
                logger.debug(f"{self._model_name}: Not found for delete id={id}")
                return False

            await self.session.delete(instance)
            logger.info(f"{self._model_name}: Deleted id={id}")
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"{self._model_name}: Database error during delete: {e}")
            raise DatabaseError(
                f"Failed to delete {self._model_name} id={id}: {e}"
            ) from e

    async def list_by_field(
        self, field_name: str, value: Any, limit: Optional[int] = None
    ) -> List[ModelType]:
        """List instances filtering by field value.

        Args:
            field_name: Name of field to filter on
            value: Value to match
            limit: Optional limit on results

        Returns:
            List of matching instances
        """
        logger.debug(
            f"{self._model_name}: Listing by {field_name}={self._sanitize_value(value)}"
        )
        try:
            field = getattr(self.model, field_name)
            query = select(self.model).where(field == value)
            if limit is not None:
                query = query.limit(limit)
            result = await self.session.execute(query)
            instances = list(result.scalars().all())
            logger.debug(f"{self._model_name}: Found {len(instances)} matches")
            return instances
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during list_by_field: {e}")
            raise DatabaseError(
                f"Failed to list {self._model_name} by {field_name}: {e}"
            ) from e

    async def count(self) -> int:
        """Count total number of instances using efficient SQL COUNT.

        Returns:
            Total count
        """
        logger.debug(f"{self._model_name}: Counting instances")
        try:
            # Use SQL COUNT(*) for efficiency
            query = select(func.count()).select_from(self.model)
            result = await self.session.execute(query)
            count = result.scalar() or 0
            logger.debug(f"{self._model_name}: Count={count}")
            return count
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during count: {e}")
            raise DatabaseError(
                f"Failed to count {self._model_name}: {e}"
            ) from e

    def _sanitize_params(self, params: dict) -> dict:
        """Sanitize parameters for logging (remove sensitive data)."""
        sanitized = {}
        sensitive_keys = {"password", "token", "api_key", "secret"}
        for key, value in params.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized

    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize single value for logging."""
        if isinstance(value, str) and len(value) > 100:
            return value[:100] + "..."
        return value


class VectorSearchMixin(Generic[ModelType]):
    """Mixin for repositories with vector similarity search.

    Provides methods for finding similar vectors using pgvector.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
        self._model_name = model.__name__

    async def find_similar(
        self,
        embedding: List[float],
        threshold: float = 0.85,
        limit: int = 10,
    ) -> List[ModelType]:
        """Find similar vectors using cosine similarity.

        Args:
            embedding: Query embedding (1536 dimensions)
            threshold: Minimum similarity (0-1, cosine similarity)
            limit: Maximum number of results

        Returns:
            List of model instances ordered by similarity (descending)
        """
        logger.debug(
            f"{self._model_name}: Finding similar vectors with threshold={threshold}, limit={limit}"
        )
        try:
            # Use cosine distance operator (<=>) with database-side filtering
            # Cosine distance: 0 = identical, 2 = opposite
            # Cosine similarity = 1 - (distance / 2)
            # For threshold filtering: distance <= 2 * (1 - threshold)
            max_distance = 2.0 * (1.0 - threshold)

            query = (
                select(self.model)
                .where(self.model.embedding.is_not(None))
                .where(self.model.embedding.op("<=>")(embedding) <= max_distance)
                .order_by(self.model.embedding.op("<=>")(embedding))
                .limit(limit)
            )

            result = await self.session.execute(query)
            instances = list(result.scalars().all())

            logger.debug(f"{self._model_name}: Found {len(instances)} similar vectors")
            return instances
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during find_similar: {e}")
            raise DatabaseError(
                f"Failed to find similar {self._model_name}: {e}"
            ) from e

    async def search_by_text(
        self,
        query_embedding: List[float],
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> List[ModelType]:
        """Search by text with optional filters.

        Args:
            query_embedding: Text query converted to embedding
            filters: Optional field filters (e.g., {"source_type": "arxiv"})
            limit: Maximum number of results

        Returns:
            List of model instances ordered by similarity
        """
        logger.debug(
            f"{self._model_name}: Searching by text with filters={filters}, limit={limit}"
        )
        try:
            query = select(self.model).where(self.model.embedding.is_not(None))

            # Apply filters
            if filters:
                for field_name, value in filters.items():
                    field = getattr(self.model, field_name)
                    query = query.where(field == value)

            # Order by similarity and limit
            query = query.order_by(self.model.embedding.op("<=>")(query_embedding)).limit(
                limit
            )

            result = await self.session.execute(query)
            instances = list(result.scalars().all())
            logger.debug(f"{self._model_name}: Search found {len(instances)} results")
            return instances
        except SQLAlchemyError as e:
            logger.error(f"{self._model_name}: Database error during search_by_text: {e}")
            raise DatabaseError(
                f"Failed to search {self._model_name}: {e}"
            ) from e

