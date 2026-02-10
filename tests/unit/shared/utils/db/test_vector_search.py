"""Unit tests for vector search mixin helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.shared.utils.db.vector_search import EnhancedVectorSearchMixin


@dataclass
class _Column:
    name: str


class _Table:
    def __init__(self, columns):
        self.columns = columns


class _ModelWithEmbedding:
    __name__ = "WithEmbedding"
    __table__ = _Table([_Column("id"), _Column("feature_embedding")])


class _ModelWithoutEmbedding:
    __name__ = "NoEmbedding"
    __table__ = _Table([_Column("id"), _Column("value")])


class _Repo(EnhancedVectorSearchMixin):
    def __init__(self, model):
        self.model = model
        self._model_name = model.__name__

        class _S:
            async def rollback(self):
                return None

        self.session = _S()


@pytest.mark.asyncio
async def test_filtered_search_requires_embedding_column() -> None:
    repo = _Repo(_ModelWithoutEmbedding)
    with pytest.raises(ValueError):
        await repo.vector_similarity_search_filtered([0.1, 0.2])


@pytest.mark.asyncio
async def test_filtered_search_returns_empty_placeholder_list() -> None:
    repo = _Repo(_ModelWithEmbedding)
    result = await repo.vector_similarity_search_filtered([0.1, 0.2], limit=5)
    assert result == []


@pytest.mark.asyncio
async def test_paginated_search_slices_results() -> None:
    class _PagedRepo(_Repo):
        async def vector_similarity_search_filtered(
            self, query_embedding, filters=None, limit=10, threshold=None, date_range=None
        ):
            return list(range(20))

    repo = _PagedRepo(_ModelWithEmbedding)
    page = await repo.vector_similarity_search_paginated([0.1], page=2, per_page=5)
    assert page["results"] == [5, 6, 7, 8, 9]
    assert page["page"] == 2
