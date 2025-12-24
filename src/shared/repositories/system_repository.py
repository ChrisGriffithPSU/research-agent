"""System state and metadata repositories."""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models.system import (
    FetcherStatus,
    FetcherState,
    ModelMetadata,
    PreferenceWeight,
    SearchQuery,
    SystemState,
)
from src.shared.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SystemStateRepository(BaseRepository[SystemState]):
    """Repository for system state key-value operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(SystemState, session)

    async def get_value(self, key: str) -> Optional[dict]:
        """Get system state value by key.

        Args:
            key: State key

        Returns:
            Value dict or None if not found
        """
        logger.debug(f"SystemStateRepository: Getting key={key}")
        state = await self.get_by_field("key", key)
        return state.value if state else None

    async def set_value(self, key: str, value: dict) -> SystemState:
        """Set system state value (create or update).

        Args:
            key: State key
            value: Value dict

        Returns:
            SystemState instance
        """
        logger.debug(f"SystemStateRepository: Setting key={key}")
        existing = await self.get_by_field("key", key)
        if existing:
            return await self.update(existing.id, value=value)
        else:
            return await self.create(key=key, value=value)

    async def list_all(self) -> List[SystemState]:
        """List all system state entries.

        Returns:
            List of all SystemState instances
        """
        logger.debug("SystemStateRepository: Listing all state")
        return await self.get_all()


class FetcherStateRepository(BaseRepository[FetcherState]):
    """Repository for fetcher state operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(FetcherState, session)

    async def get_by_name(
        self, fetcher_name: str
    ) -> Optional[FetcherState]:
        """Get fetcher state by name.

        Args:
            fetcher_name: Fetcher name (arxiv, kaggle, etc.)

        Returns:
            FetcherState instance or None if not found
        """
        logger.debug(
            f"FetcherStateRepository: Getting fetcher_name={fetcher_name}"
        )
        return await self.get_by_field("fetcher_name", fetcher_name)

    async def get_or_create(
        self, fetcher_name: str
    ) -> FetcherState:
        """Get or create fetcher state.

        Args:
            fetcher_name: Fetcher name

        Returns:
            FetcherState instance (existing or newly created)
        """
        logger.debug(
            f"FetcherStateRepository: Getting or creating fetcher_name={fetcher_name}"
        )
        state = await self.get_by_name(fetcher_name)
        if state is None:
            state = await self.create(
                fetcher_name=fetcher_name,
                status=FetcherStatus.ACTIVE,
                error_count=0,
                config={"enabled": True},
            )
            logger.info(
                f"FetcherStateRepository: Created state for {fetcher_name}"
            )
        return state

    async def update_last_fetch(
        self, fetcher_name: str, results_count: int
    ) -> FetcherState:
        """Update last fetch time and reset error count.

        Args:
            fetcher_name: Fetcher name
            results_count: Number of results fetched

        Returns:
            Updated FetcherState instance
        """
        logger.debug(
            f"FetcherStateRepository: Updating last fetch for {fetcher_name}"
        )
        from datetime import datetime, timezone

        state = await self.get_or_create(fetcher_name)
        state = await self.update(
            state.id,
            last_fetch_time=datetime.now(timezone.utc),
            status=FetcherStatus.ACTIVE,
            error_count=0,
        )
        # Update config with results count
        config = state.config.copy()
        config["last_results_count"] = results_count
        await self.update(state.id, config=config)
        return state

    async def increment_error(
        self, fetcher_name: str
    ) -> FetcherState:
        """Increment error count for fetcher.

        Args:
            fetcher_name: Fetcher name

        Returns:
            Updated FetcherState instance
        """
        logger.warning(
            f"FetcherStateRepository: Incrementing error for {fetcher_name}"
        )
        state = await self.get_or_create(fetcher_name)
        new_count = state.error_count + 1
        state = await self.update(state.id, error_count=new_count)

        # Check circuit breaker threshold (3 errors)
        if new_count >= 3:
            logger.error(
                f"FetcherStateRepository: Circuit breaker triggered for {fetcher_name}"
            )
            await self.update(state.id, status=FetcherStatus.ERROR)

        return state

    async def reset_errors(self, fetcher_name: str) -> FetcherState:
        """Reset error count for fetcher.

        Args:
            fetcher_name: Fetcher name

        Returns:
            Updated FetcherState instance
        """
        logger.info(f"FetcherStateRepository: Resetting errors for {fetcher_name}")
        state = await self.get_or_create(fetcher_name)
        return await self.update(state.id, error_count=0, status=FetcherStatus.ACTIVE)

    async def list_active(self) -> List[FetcherState]:
        """List active fetchers.

        Returns:
            List of FetcherState instances with status=ACTIVE
        """
        logger.debug("FetcherStateRepository: Listing active fetchers")
        return await self.list_by_field("status", FetcherStatus.ACTIVE)

    async def list_by_status(
        self, status: FetcherStatus
    ) -> List[FetcherState]:
        """List fetchers by status.

        Args:
            status: Fetcher status

        Returns:
            List of FetcherState instances
        """
        logger.debug(f"FetcherStateRepository: Listing by status={status}")
        return await self.list_by_field("status", status)


class SearchQueryRepository(BaseRepository[SearchQuery]):
    """Repository for search query operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(SearchQuery, session)

    async def is_duplicate(
        self, source: str, query_text: str
    ) -> bool:
        """Check if query already exists for source.

        Args:
            source: Source that generated query
            query_text: Query text

        Returns:
            True if duplicate, False otherwise
        """
        logger.debug(
            f"SearchQueryRepository: Checking duplicate source={source}, query={query_text[:50]}"
        )
        try:
            query = select(SearchQuery).where(
                SearchQuery.source == source,
                SearchQuery.query_text == query_text,
            )
            result = await self.session.execute(query)
            is_dup = result.scalar_one_or_none() is not None
            logger.debug(f"SearchQueryRepository: Query duplicate={is_dup}")
            return is_dup
        except Exception as e:
            logger.error(
                f"SearchQueryRepository: Error checking duplicate: {e}"
            )
            raise

    async def list_by_source(
        self, source: str, limit: int = 100
    ) -> List[SearchQuery]:
        """List queries by source.

        Args:
            source: Source name
            limit: Maximum number of results

        Returns:
            List of SearchQuery instances
        """
        logger.debug(f"SearchQueryRepository: Listing by source={source}")
        return await self.list_by_field("source", source, limit=limit)

    async def list_recent(
        self, limit: int = 50
    ) -> List[SearchQuery]:
        """List most recent queries across all sources.

        Args:
            limit: Maximum number of results

        Returns:
            List of SearchQuery instances (most recent first)
        """
        logger.debug("SearchQueryRepository: Listing recent queries")
        try:
            query = (
                select(SearchQuery)
                .order_by(SearchQuery.executed_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            queries = list(result.scalars().all())
            logger.debug(f"SearchQueryRepository: Found {len(queries)} recent queries")
            return queries
        except Exception as e:
            logger.error(f"SearchQueryRepository: Error listing recent queries: {e}")
            raise


class ModelMetadataRepository(BaseRepository[ModelMetadata]):
    """Repository for model metadata operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(ModelMetadata, session)

    async def get_latest(self) -> Optional[ModelMetadata]:
        """Get most recently trained model.

        Returns:
            ModelMetadata instance or None if no models exist
        """
        logger.debug("ModelMetadataRepository: Getting latest model")
        try:
            query = (
                select(ModelMetadata)
                .order_by(ModelMetadata.trained_at.desc())
                .limit(1)
            )
            result = await self.session.execute(query)
            model = result.scalar_one_or_none()
            if model:
                logger.debug(
                    f"ModelMetadataRepository: Found latest model version={model.version}"
                )
            else:
                logger.debug("ModelMetadataRepository: No models found")
            return model
        except Exception as e:
            logger.error(f"ModelMetadataRepository: Error getting latest model: {e}")
            raise

    async def get_by_version(
        self, version: str
    ) -> Optional[ModelMetadata]:
        """Get model by version.

        Args:
            version: Model version string

        Returns:
            ModelMetadata instance or None if not found
        """
        logger.debug(f"ModelMetadataRepository: Getting model version={version}")
        return await self.get_by_field("version", version)

    async def list_all(self, limit: int = 10) -> List[ModelMetadata]:
        """List all models (most recent first).

        Args:
            limit: Maximum number of results

        Returns:
            List of ModelMetadata instances
        """
        logger.debug("ModelMetadataRepository: Listing all models")
        try:
            query = (
                select(ModelMetadata)
                .order_by(ModelMetadata.trained_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            models = list(result.scalars().all())
            logger.debug(f"ModelMetadataRepository: Found {len(models)} models")
            return models
        except Exception as e:
            logger.error(f"ModelMetadataRepository: Error listing models: {e}")
            raise


class PreferenceWeightRepository(BaseRepository[PreferenceWeight]):
    """Repository for preference weight operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(PreferenceWeight, session)

    async def get_weight(self, dimension: str) -> Optional[float]:
        """Get preference weight for dimension.

        Args:
            dimension: Dimension identifier

        Returns:
            Weight value or None if not found
        """
        logger.debug(f"PreferenceWeightRepository: Getting weight for {dimension}")
        weight = await self.get_by_field("dimension", dimension)
        return weight.weight if weight else None

    async def set_weight(
        self, dimension: str, weight: float
    ) -> PreferenceWeight:
        """Set preference weight (create or update).

        Args:
            dimension: Dimension identifier
            weight: Weight value (-1.0 to 1.0)

        Returns:
            PreferenceWeight instance
        """
        logger.debug(f"PreferenceWeightRepository: Setting weight for {dimension} to {weight}")
        existing = await self.get_by_field("dimension", dimension)
        if existing:
            return await self.update(existing.id, weight=weight)
        else:
            return await self.create(dimension=dimension, weight=weight)

    async def list_all(self) -> List[PreferenceWeight]:
        """List all preference weights.

        Returns:
            List of all PreferenceWeight instances
        """
        logger.debug("PreferenceWeightRepository: Listing all weights")
        return await self.get_all()

    async def get_category_weights(self, category: str) -> List[PreferenceWeight]:
        """Get all weights for a category.

        Args:
            category: Category prefix (e.g., "category:", "source:")

        Returns:
            List of matching PreferenceWeight instances
        """
        logger.debug(f"PreferenceWeightRepository: Listing weights for {category}")
        try:
            query = select(PreferenceWeight).where(
                PreferenceWeight.dimension.startswith(category)
            )
            result = await self.session.execute(query)
            weights = list(result.scalars().all())
            logger.debug(f"PreferenceWeightRepository: Found {len(weights)} weights")
            return weights
        except Exception as e:
            logger.error(
                f"PreferenceWeightRepository: Error listing weights for {category}: {e}"
            )
            raise

    async def reset_weights(self) -> List[PreferenceWeight]:
        """Reset all weights to zero.

        Returns:
            List of reset PreferenceWeight instances
        """
        logger.info("PreferenceWeightRepository: Resetting all weights")
        try:
            # Get all weights
            weights = await self.list_all()

            # Reset each to zero
            for weight in weights:
                await self.update(weight.id, weight=0.0)

            logger.info(
                f"PreferenceWeightRepository: Reset {len(weights)} weights"
            )
            return weights
        except Exception as e:
            logger.error("PreferenceWeightRepository: Error resetting weights: {e}")
            raise

