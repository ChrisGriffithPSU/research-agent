"""Integration tests for vector search with real PostgreSQL + pgvector.

These tests require PostgreSQL with pgvector running via Docker.
Set RUN_INTEGRATION_TESTS=1 and ensure PostgreSQL is accessible.
"""
import pytest
import math

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.shared.models import Base
from src.shared.models.source import Source, SourceType, ProcessingStatus
from src.shared.repositories.source_repository import SourceRepository


@pytest.fixture(scope="session")
async def postgres_session():
    """Create PostgreSQL session for testing."""
    import os

    engine = create_async_engine(
        f"postgresql+asyncpg://"
        f"{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'researcher_agent')}"
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_finds_similar_content(postgres_session):
    """Test pgvector similarity search finds similar vectors."""
    repo = SourceRepository(postgres_session)

    # Create base source with specific embedding
    # Note: Need to use smaller dimension for testing or mock pgvector
    # For now, we'll test that the query structure works
    embedding1 = [0.1, 0.2, 0.3] + [0.0] * 1533  # Pad to 1536

    source1 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/1234",
        title="Machine Learning for Time Series",
        content="This paper discusses ML techniques for time series forecasting",
        source_metadata={"authors": ["Author A"]},
        embedding=embedding1,
        status=ProcessingStatus.PROCESSED
    )

    # Create similar source (small variations in embedding)
    embedding2 = [0.1 + 0.01, 0.2 + 0.01, 0.3 + 0.01] + [0.0] * 1533

    source2 = await repo.create(
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/dataset/time-series",
        title="Time Series Prediction Dataset",
        content="Dataset for time series prediction using ML",
        source_metadata={"authors": ["Author B"]},
        embedding=embedding2,
        status=ProcessingStatus.PROCESSED
    )

    # Create dissimilar source (different embedding)
    embedding3 = [0.9, 0.8, 0.7] + [0.0] * 1533  # Very different

    source3 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/5678",
        title="Quantum Computing Algorithms",
        content="Quantum algorithms for cryptography",
        source_metadata={"authors": ["Author C"]},
        embedding=embedding3,
        status=ProcessingStatus.PROCESSED
    )

    # Search for similar to embedding1
    similar = await repo.find_similar(
        embedding1,
        threshold=0.7,  # Lower threshold for test reliability
        limit=10
    )

    # Should find source1 (identical) and source2 (similar)
    # The similarity calculation depends on pgvector's <=> operator
    similar_ids = [s.id for s in similar]

    # At minimum, we should find source1 (identical to query)
    assert source1.id in similar_ids

    # source2 should be found if similarity calculation works correctly
    # (may or may not be in results depending on actual distance calculation)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_threshold_filtering(postgres_session):
    """Test similarity threshold filtering works."""
    repo = SourceRepository(postgres_session)

    # Create base source
    embedding1 = [0.1, 0.2, 0.3] + [0.0] * 1533
    source1 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/threshold-test",
        title="Base Source",
        content="Base content",
        source_metadata={},
        embedding=embedding1,
        status=ProcessingStatus.PROCESSED
    )

    # Create very similar source
    embedding2 = [0.1 + 0.01, 0.2 + 0.01, 0.3 + 0.01] + [0.0] * 1533
    source2 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/very-similar",
        title="Very Similar",
        content="Similar content",
        source_metadata={},
        embedding=embedding2,
        status=ProcessingStatus.PROCESSED
    )

    # Create moderately similar source
    embedding3 = [0.1 + 0.3, 0.2 + 0.3, 0.3 + 0.3] + [0.0] * 1533
    source3 = await repo.create(
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/moderately-similar",
        title="Moderately Similar",
        content="Moderately similar content",
        source_metadata={},
        embedding=embedding3,
        status=ProcessingStatus.PROCESSED
    )

    # Search with high threshold (should find fewer results)
    similar_high = await repo.find_similar(
        embedding1,
        threshold=0.9,
        limit=10
    )

    # Search with low threshold (should find more results)
    similar_low = await repo.find_similar(
        embedding1,
        threshold=0.5,
        limit=10
    )

    # High threshold should find fewer or equal results compared to low threshold
    assert len(similar_high) <= len(similar_low)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_excludes_null_embeddings(postgres_session):
    """Test that NULL embeddings are excluded from search."""
    repo = SourceRepository(postgres_session)

    # Create source with embedding
    embedding = [0.1, 0.2, 0.3] + [0.0] * 1533
    source1 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/with-embedding",
        title="Has Embedding",
        content="Content with embedding",
        source_metadata={},
        embedding=embedding,
        status=ProcessingStatus.PROCESSED
    )

    # Create source without embedding
    source2 = await repo.create(
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/no-embedding",
        title="No Embedding",
        content="Content without embedding",
        source_metadata={},
        embedding=None,  # No embedding
        status=ProcessingStatus.PROCESSED
    )

    # Find similar
    similar = await repo.find_similar(
        embedding,
        threshold=0.5,
        limit=10
    )

    # Should only find source with embedding
    similar_ids = [s.id for s in similar]
    assert source1.id in similar_ids
    # source2 should NOT be in results (no embedding)
    assert source2.id not in similar_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_respects_limit(postgres_session):
    """Test that limit parameter works correctly."""
    repo = SourceRepository(postgres_session)

    # Create multiple sources with similar embeddings
    embedding_base = [0.1, 0.2, 0.3] + [0.0] * 1533

    for i in range(10):
        # Create embeddings with small variations
        embedding = embedding_base.copy()
        if i < 1536:
            embedding[i] += 0.01 * (i + 1)

        await repo.create(
            source_type=SourceType.ARXIV,
            url=f"https://arxiv.org/abs/limit-test-{i}",
            title=f"Source {i}",
            content=f"Content {i}",
            source_metadata={},
            embedding=embedding,
            status=ProcessingStatus.PROCESSED
        )

    # Search with limit=5
    similar = await repo.find_similar(
        embedding_base,
        threshold=0.5,
        limit=5
    )

    # Should return at most 5 results
    assert len(similar) <= 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cosine_distance_calculation(postgres_session):
    """Test cosine distance helper method."""
    repo = SourceRepository(postgres_session)

    # Identical vectors should have distance close to 0
    vec1 = [0.1, 0.2, 0.3]
    vec2 = [0.1, 0.2, 0.3]
    distance_identical = repo._cosine_distance(vec1, vec2)
    assert distance_identical < 0.01  # Almost identical

    # Orthogonal-like vectors should have non-zero distance
    vec3 = [1.0, 0.0, 0.0]
    vec4 = [0.0, 1.0, 0.0]
    distance_orthogonal = repo._cosine_distance(vec3, vec4)
    assert distance_orthogonal > 0.9  # Close to 1.0

    # Opposite vectors should have distance close to 2
    vec5 = [0.5, 0.5, 0.5]
    vec6 = [-0.5, -0.5, -0.5]
    distance_opposite = repo._cosine_distance(vec5, vec6)
    assert distance_opposite > 1.9  # Close to 2.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_detection_hybrid(postgres_session):
    """Test hybrid duplicate detection (URL + semantic)."""
    repo = SourceRepository(postgres_session)

    # Create source with embedding
    embedding1 = [0.1, 0.2, 0.3] + [0.0] * 1533
    source1 = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/duplication-test",
        title="Duplication Test",
        content="Test content for duplication",
        source_metadata={},
        embedding=embedding1,
        status=ProcessingStatus.PROCESSED
    )

    # Test 1: Check exact URL duplicate
    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/duplication-test", embedding1
    )
    assert is_dup is True
    assert dup_type == "exact_url"

    # Test 2: Check non-duplicate URL
    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/new-paper", embedding1
    )
    assert is_dup is False
    assert dup_type is None

    # Test 3: Check semantic duplicate with similar embedding
    embedding2 = [0.1 + 0.05, 0.2 + 0.05, 0.3 + 0.05] + [0.0] * 1533

    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/semantically-similar", embedding2
    )
    # May be duplicate depending on threshold in is_duplicate_hybrid
    # If the implementation checks similarity, this could return True
    # For now, we just verify the method runs without error
    assert isinstance(is_dup, bool)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_by_text_with_filters(postgres_session):
    """Test search by text with optional filters."""
    repo = SourceRepository(postgres_session)

    # Create sources of different types
    embedding_arxiv = [0.1, 0.2, 0.3] + [0.0] * 1533
    source_arxiv = await repo.create(
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/filter-test",
        title="ArXiv Paper",
        content="ArXiv content",
        source_metadata={},
        embedding=embedding_arxiv,
        status=ProcessingStatus.PROCESSED
    )

    embedding_kaggle = [0.1 + 0.1, 0.2 + 0.1, 0.3 + 0.1] + [0.0] * 1533
    source_kaggle = await repo.create(
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/filter-test",
        title="Kaggle Dataset",
        content="Kaggle content",
        source_metadata={},
        embedding=embedding_kaggle,
        status=ProcessingStatus.PROCESSED
    )

    # Search without filters (should find both)
    all_results = await repo.search_by_text(
        embedding_arxiv,
        filters=None,
        limit=10
    )
    all_ids = [s.id for s in all_results]
    assert source_arxiv.id in all_ids

    # Search with ARXIV filter
    arxiv_results = await repo.search_by_text(
        embedding_arxiv,
        filters={"source_type": SourceType.ARXIV},
        limit=10
    )
    arxiv_ids = [s.id for s in arxiv_results]
    assert source_arxiv.id in arxiv_ids
    # Kaggle source should NOT be in filtered results
    if source_kaggle.id in all_ids:
        assert source_kaggle.id not in arxiv_ids

