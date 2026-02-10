"""Unit tests for local artifact storage."""

from pathlib import Path

import pytest

from src.shared.storage.artifact_store import ArtifactStoreFactory, LocalArtifactStore


@pytest.mark.asyncio
async def test_store_retrieve_exists_delete_roundtrip(tmp_path: Path) -> None:
    store = LocalArtifactStore(base_dir=str(tmp_path))
    key = "job-1/results/out.json"
    payload = b'{"ok": true}'

    stored_path = await store.store(key, payload, content_type="application/json")
    assert Path(stored_path).exists()
    assert await store.exists(key) is True
    assert await store.retrieve(key) == payload

    deleted = await store.delete(key)
    assert deleted is True
    assert await store.exists(key) is False


@pytest.mark.asyncio
async def test_list_prefix_returns_sorted_relative_paths(tmp_path: Path) -> None:
    store = LocalArtifactStore(base_dir=str(tmp_path))
    await store.store("a/1.txt", b"1")
    await store.store("a/2.txt", b"2")
    await store.store("b/3.txt", b"3")

    assert await store.list_prefix("a") == ["a/1.txt", "a/2.txt"]
    assert await store.list_prefix("missing") == []


def test_factory_create_from_env_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACT_STORE_TYPE", "local")
    store = ArtifactStoreFactory.create_from_env()
    assert isinstance(store, LocalArtifactStore)
