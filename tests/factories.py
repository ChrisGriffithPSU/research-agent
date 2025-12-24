"""Model factories for test data generation.

Provides helper functions to create model instances for testing.
"""
from datetime import date, datetime, timezone
from typing import List

from src.shared.models.digest import Digest, DigestItem, DigestStatus
from src.shared.models.feedback import Feedback
from src.shared.models.source import ProcessingStatus, Source, SourceType
from src.shared.models.system import (
    FetcherStatus,
    FetcherState,
    ModelMetadata,
    PreferenceWeight,
    SearchQuery,
    SystemState,
)
from src.shared.models.user import UserProfile


def create_user_profile(
    id: int = 1,
    email: str = "test@example.com",
    preferences: dict = None,
    learning_config: dict = None,
) -> UserProfile:
    """Create UserProfile instance for testing.

    Args:
        id: User ID
        email: Email address
        preferences: User preferences dict
        learning_config: Learning configuration dict

    Returns:
        UserProfile instance
    """
    if preferences is None:
        preferences = {
            "topics": ["transformers", "time_series"],
            "sources": ["arxiv", "kaggle"],
        }

    if learning_config is None:
        learning_config = {
            "feedback_weight": 0.7,
            "exploration_rate": 0.2,
        }

    return UserProfile(
        id=id,
        email=email,
        preferences=preferences,
        learning_config=learning_config,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_source(
    id: int = 1,
    source_type: SourceType = SourceType.ARXIV,
    url: str = "https://arxiv.org/abs/1234.5678",
    title: str = "Test Paper",
    content: str = "Test content",
    metadata: dict = None,
    embedding: List[float] = None,
    status: ProcessingStatus = ProcessingStatus.FETCHED,
    extracted_data: dict = None,
) -> Source:
    """Create Source instance for testing.

    Args:
        id: Source ID
        source_type: Source type enum
        url: Source URL
        title: Source title
        content: Source content text
        metadata: Source metadata dict
        embedding: Vector embedding (1536 dimensions)
        status: Processing status
        extracted_data: Extracted data from LLM

    Returns:
        Source instance
    """
    if metadata is None:
        metadata = {"authors": ["Test Author"], "published_date": "2024-01-01"}

    return Source(
        id=id,
        source_type=source_type,
        url=url,
        title=title,
        content=content,
        metadata=metadata,
        embedding=embedding,
        status=status,
        extracted_data=extracted_data,
        fetched_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc) if status == ProcessingStatus.PROCESSED else None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_embedding(dims: int = 1536) -> List[float]:
    """Create a random embedding vector for testing.

    Args:
        dims: Number of dimensions

    Returns:
        List of float values
    """
    import random

    return [random.random() for _ in range(dims)]


def create_digest(
    id: int = 1,
    user_id: int = 1,
    digest_date: date = None,
    status: DigestStatus = DigestStatus.READY,
) -> Digest:
    """Create Digest instance for testing.

    Args:
        id: Digest ID
        user_id: User ID
        digest_date: Digest date
        status: Digest status

    Returns:
        Digest instance
    """
    if digest_date is None:
        digest_date = date.today()

    return Digest(
        id=id,
        user_id=user_id,
        digest_date=digest_date,
        status=status,
        delivered_at=datetime.now(timezone.utc)
        if status == DigestStatus.DELIVERED
        else None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_digest_item(
    id: int = 1,
    digest_id: int = 1,
    source_id: int = 1,
    rank: int = 1,
    title: str = "Test Item",
    summary: str = "Test summary",
    reasoning: str = "Test reasoning",
    tags: List[str] = None,
    relevance_score: float = 0.8,
) -> DigestItem:
    """Create DigestItem instance for testing.

    Args:
        id: DigestItem ID
        digest_id: Parent Digest ID
        source_id: Parent Source ID
        rank: Rank within digest
        title: Item title
        summary: Item summary
        reasoning: LLM reasoning for inclusion
        tags: Item tags
        relevance_score: Relevance score (0-1)

    Returns:
        DigestItem instance
    """
    if tags is None:
        tags = ["feature_engineering", "transformers"]

    return DigestItem(
        id=id,
        digest_id=digest_id,
        source_id=source_id,
        rank=rank,
        title=title,
        summary=summary,
        reasoning=reasoning,
        tags=tags,
        relevance_score=relevance_score,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_feedback(
    id: int = 1,
    digest_item_id: int = 1,
    rating: int = 5,
    notes: str = "Great insight!",
    time_spent: float = 60.0,
    clicked_through: bool = True,
) -> Feedback:
    """Create Feedback instance for testing.

    Args:
        id: Feedback ID
        digest_item_id: Parent DigestItem ID
        rating: Rating value (-1 to 5)
        notes: User notes
        time_spent: Time spent reading (seconds)
        clicked_through: Whether user clicked through

    Returns:
        Feedback instance
    """
    return Feedback(
        id=id,
        digest_item_id=digest_item_id,
        rating=rating,
        notes=notes,
        time_spent=time_spent,
        clicked_through=clicked_through,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_system_state(
    key: str = "test_key", value: dict = None
) -> SystemState:
    """Create SystemState instance for testing.

    Args:
        key: State key
        value: State value dict

    Returns:
        SystemState instance
    """
    if value is None:
        value = {"test": "value"}

    return SystemState(
        key=key,
        value=value,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_fetcher_state(
    fetcher_name: str = "arxiv",
    status: FetcherStatus = FetcherStatus.ACTIVE,
    error_count: int = 0,
) -> FetcherState:
    """Create FetcherState instance for testing.

    Args:
        fetcher_name: Fetcher name
        status: Fetcher status
        error_count: Consecutive error count

    Returns:
        FetcherState instance
    """
    return FetcherState(
        fetcher_name=fetcher_name,
        last_fetch_time=datetime.now(timezone.utc),
        status=status,
        error_count=error_count,
        config={"enabled": True},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_search_query(
    id: int = 1,
    source: str = "arxiv",
    query_text: str = "test query",
    results_count: int = 10,
) -> SearchQuery:
    """Create SearchQuery instance for testing.

    Args:
        id: Query ID
        source: Source that generated query
        query_text: Query text
        results_count: Number of results

    Returns:
        SearchQuery instance
    """
    return SearchQuery(
        id=id,
        source=source,
        query_text=query_text,
        executed_at=datetime.now(timezone.utc),
        results_count=results_count,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_model_metadata(
    id: int = 1,
    version: str = "v1.0",
    training_samples: int = 100,
) -> ModelMetadata:
    """Create ModelMetadata instance for testing.

    Args:
        id: Metadata ID
        version: Model version
        training_samples: Number of training samples

    Returns:
        ModelMetadata instance
    """
    return ModelMetadata(
        id=id,
        version=version,
        trained_at=datetime.now(timezone.utc),
        training_samples=training_samples,
        performance_metrics={"accuracy": 0.85, "precision": 0.82},
        file_path="/app/models/test_model.pkl",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_preference_weight(
    dimension: str = "category:feature_engineering",
    weight: float = 0.5,
) -> PreferenceWeight:
    """Create PreferenceWeight instance for testing.

    Args:
        dimension: Dimension identifier
        weight: Weight value (-1.0 to 1.0)

    Returns:
        PreferenceWeight instance
    """
    return PreferenceWeight(
        dimension=dimension,
        weight=weight,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def create_multiple_sources(
    count: int = 10, **kwargs
) -> List[Source]:
    """Create multiple Source instances.

    Args:
        count: Number of sources to create
        **kwargs: Additional arguments for create_source

    Returns:
        List of Source instances
    """
    return [create_source(id=i + 1, **kwargs) for i in range(count)]


def create_multiple_digest_items(
    digest_id: int = 1, count: int = 10, **kwargs
) -> List[DigestItem]:
    """Create multiple DigestItem instances.

    Args:
        digest_id: Parent Digest ID
        count: Number of items to create
        **kwargs: Additional arguments for create_digest_item

    Returns:
        List of DigestItem instances
    """
    return [
        create_digest_item(
            id=i + 1,
            digest_id=digest_id,
            rank=i + 1,
            **kwargs,
        )
        for i in range(count)
    ]


def create_multiple_feedback(
    digest_item_ids: List[int], ratings: List[int] = None
) -> List[Feedback]:
    """Create multiple Feedback instances.

    Args:
        digest_item_ids: List of DigestItem IDs
        ratings: Optional list of ratings (defaults to 5s)

    Returns:
        List of Feedback instances
    """
    if ratings is None:
        ratings = [5] * len(digest_item_ids)

    return [
        create_feedback(id=i + 1, digest_item_id=item_id, rating=rating)
        for i, (item_id, rating) in enumerate(zip(digest_item_ids, ratings))
    ]

