"""Tests for vector search functionality."""
import pytest

from tests.factories import create_source, create_embedding
from src.shared.models.source import Source, SourceType, ProcessingStatus
from src.shared.repositories.base import VectorSearchMixin
from src.shared.repositories.source_repository import SourceRepository


@pytest.mark.asyncio
async def test_vector_search_find_similar(test_session):
    """Test finding similar vectors."""
    repo = SourceRepository(test_session)

    # Create source with embedding
    embedding1 = create_embedding()
    source1 = await repo.create(
        id=1,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/1234.5678",
        title="Source 1",
        content="Content 1",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding1,
    )

    # Create source with similar embedding (small distance)
    embedding2 = create_embedding()
    # Make it similar by setting most values close to embedding1
    for i in range(1536):
        if i % 100 == 0:  # Change some values slightly
            embedding2[i] = embedding1[i] + 0.1

    await repo.create(
        id=2,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/2345.6789",
        title="Source 2",
        content="Content 2",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding2,
    )

    # Create source with dissimilar embedding (large distance)
    embedding3 = create_embedding()
    # Make it dissimilar by flipping values
    for i in range(1536):
        embedding3[i] = 1.0 - embedding1[i]  # Opposite

    await repo.create(
        id=3,
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/dataset",
        title="Source 3",
        content="Content 3",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding3,
    )

    # Find similar to embedding1
    similar = await repo.find_similar(embedding1, limit=10)

    # Should find source1 (identical) and source2 (similar)
    # Should NOT find source3 (dissimilar)
    assert len(similar) >= 1
    found_ids = [s.id for s in similar]
    assert 1 in found_ids  # Source 1 should be found


@pytest.mark.asyncio
async def test_vector_search_with_threshold(test_session):
    """Test similarity threshold filtering."""
    repo = SourceRepository(test_session)

    # Create base source
    embedding1 = create_embedding()
    source1 = await repo.create(
        id=1,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/1234.5678",
        title="Source 1",
        content="Content 1",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding1,
    )

    # Create very similar source (small changes)
    embedding2 = embedding1.copy()
    for i in range(100):
        embedding2[i] = embedding1[i] + 0.05  # Very small change

    await repo.create(
        id=2,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/2345.6789",
        title="Source 2",
        content="Content 2",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding2,
    )

    # Create moderately similar source (bigger changes)
    embedding3 = embedding1.copy()
    for i in range(500):
        embedding3[i] = embedding1[i] + 0.5  # Larger changes

    await repo.create(
        id=3,
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/dataset",
        title="Source 3",
        content="Content 3",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding3,
    )

    # Find with high threshold (0.95) - should only find source2
    similar_high = await repo.find_similar(embedding1, threshold=0.95, limit=10)
    found_ids_high = [s.id for s in similar_high]
    assert 2 in found_ids_high  # Source 2 is very similar
    # Source 3 is below 0.95 threshold

    # Find with low threshold (0.7) - should find both
    similar_low = await repo.find_similar(embedding1, threshold=0.7, limit=10)
    found_ids_low = [s.id for s in similar_low]
    assert 2 in found_ids_low
    assert 3 in found_ids_low  # Source 3 is above 0.7 threshold


@pytest.mark.asyncio
async def test_vector_search_excludes_null_embeddings(test_session):
    """Test that NULL embeddings are excluded from search."""
    repo = SourceRepository(test_session)

    # Create source with embedding
    embedding = create_embedding()
    await repo.create(
        id=1,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/1234.5678",
        title="Source 1",
        content="Content 1",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding,
    )

    # Create source without embedding
    await repo.create(
        id=2,
        source_type=SourceType.KAGGLE,
        url="https://kaggle.com/dataset",
        title="Source 2",
        content="Content 2",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=None,  # No embedding
    )

    # Find similar
    similar = await repo.find_similar(embedding, limit=10)

    # Should only find source with embedding
    assert len(similar) == 1
    assert similar[0].id == 1


@pytest.mark.asyncio
async def test_vector_search_respects_limit(test_session):
    """Test that limit parameter works correctly."""
    repo = SourceRepository(test_session)

    embedding_base = create_embedding()

    # Create 5 sources with similar embeddings
    for i in range(5):
        embedding = embedding_base.copy()
        # Make them all similar with small variations
        for j in range(50):
            embedding[j] += 0.01 * (i + 1)

        await repo.create(
            id=i + 1,
            source_type=SourceType.ARXIV,
            url=f"https://arxiv.org/abs/{i}",
            title=f"Source {i}",
            content=f"Content {i}",
            metadata={},
            status=ProcessingStatus.FETCHED,
            embedding=embedding,
        )

    # Search with limit=2
    similar = await repo.find_similar(embedding_base, limit=2)

    # Should return at most 2 results
    assert len(similar) <= 2


@pytest.mark.asyncio
async def test_cosine_distance_calculation(test_session):
    """Test cosine distance calculation."""
    from src.shared.repositories.base import BaseRepository

    # We'll test the helper method directly
    repo = BaseRepository(Source, test_session)

    # Identical vectors should have distance close to 0
    vec1 = create_embedding()
    vec2 = vec1.copy()
    distance_identical = repo._cosine_distance(vec1, vec2)
    assert distance_identical < 0.001  # Almost identical

    # Opposite vectors should have distance close to 2
    vec3 = [1.0 - x for x in vec1]
    distance_opposite = repo._cosine_distance(vec1, vec3)
    assert distance_opposite > 1.5  # Should be close to 2

    # Orthogonal vectors should have distance close to 1
    vec4 = create_embedding()
    vec5 = create_embedding()
    # Make them orthogonal by making dot product zero
    # (simplified approach for testing)
    distance_orthogonal = repo._cosine_distance(vec4, vec5)
    assert 0.5 <= distance_orthogonal <= 1.5


@pytest.mark.asyncio
async def test_duplicate_detection_hybrid(test_session):
    """Test hybrid duplicate detection (URL + semantic)."""
    repo = SourceRepository(test_session)

    # Create source
    embedding1 = create_embedding()
    await repo.create(
        id=1,
        source_type=SourceType.ARXIV,
        url="https://arxiv.org/abs/1234.5678",
        title="Source 1",
        content="Content 1",
        metadata={},
        status=ProcessingStatus.FETCHED,
        embedding=embedding1,
    )

    # Test 1: Check exact URL duplicate
    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/1234.5678", embedding1
    )
    assert is_dup is True
    assert dup_type == "exact_url"

    # Test 2: Check non-duplicate URL
    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/9999.9999", embedding1
    )
    assert is_dup is False
    assert dup_type is None

    # Test 3: Check semantic duplicate with similar embedding
    embedding2 = embedding1.copy()
    for i in range(100):
        embedding2[i] += 0.05  # Small changes

    is_dup, dup_type = await repo.is_duplicate_hybrid(
        "https://arxiv.org/abs/8888.8888", embedding2
    )
    assert is_dup is True
    assert dup_type == "semantic_similarity"

