"""Artifact storage implementations.

Provides abstraction over file/object storage for experiment artifacts.
Supports local filesystem (default) with swappable backend for S3/Object storage.
"""

import os
from pathlib import Path

from src.shared.interfaces import IArtifactStore


class LocalArtifactStore(IArtifactStore):
    """Local filesystem implementation of artifact storage.

    Stores artifacts in a configurable base directory with
    hierarchical organization by work_id and type.

    Environment Variables:
        ARTIFACTS_BASE_DIR: Base directory for artifacts (default: ./artifacts)

    Example:
        store = LocalArtifactStore()
        path = await store.store(
            key="work-123/concepts/concepts.json",
            data=json_bytes,
            content_type="application/json"
        )
        # Returns: /path/to/artifacts/work-123/concepts/concepts.json
    """

    def __init__(self, base_dir: str | None = None):
        """Initialize local artifact store.

        Args:
            base_dir: Base directory path (falls back to env var)
        """
        self.base_dir = Path(base_dir or os.getenv("ARTIFACTS_BASE_DIR", "./artifacts"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def store(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        """Store artifact in local filesystem.

        Args:
            key: Relative path for the artifact (e.g., "work-123/results.json")
            data: Binary data to store
            content_type: MIME type (stored as metadata comment)

        Returns:
            Absolute path to stored artifact
        """
        file_path = self.base_dir / key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(data)

        # Store content type as extended attribute if supported
        if content_type:
            try:
                import xattr

                xattr.setxattr(str(file_path), b"user.content_type", content_type.encode())
            except ImportError:
                # xattr not available, skip metadata storage
                pass

        return str(file_path)

    async def retrieve(self, key: str) -> bytes | None:
        """Retrieve artifact from local filesystem.

        Args:
            key: Relative path for the artifact

        Returns:
            Binary data or None if not found
        """
        file_path = self.base_dir / key

        if not file_path.exists():
            return None

        with open(file_path, "rb") as f:
            return f.read()

    async def exists(self, key: str) -> bool:
        """Check if artifact exists.

        Args:
            key: Relative path for the artifact

        Returns:
            True if file exists, False otherwise
        """
        return (self.base_dir / key).exists()

    async def delete(self, key: str) -> bool:
        """Delete artifact.

        Args:
            key: Relative path for the artifact

        Returns:
            True if deleted, False if not found
        """
        file_path = self.base_dir / key

        if not file_path.exists():
            return False

        file_path.unlink()
        return True

    async def list_prefix(self, prefix: str) -> list[str]:
        """List artifacts with given prefix.

        Args:
            prefix: Path prefix to filter by

        Returns:
            List of relative artifact keys
        """
        prefix_path = self.base_dir / prefix

        if not prefix_path.exists():
            return []

        if prefix_path.is_file():
            return [prefix]

        artifacts = []
        for item in prefix_path.rglob("*"):
            if item.is_file():
                # Get relative path from base_dir
                rel_path = item.relative_to(self.base_dir)
                artifacts.append(str(rel_path).replace(os.sep, "/"))

        return sorted(artifacts)

    def get_absolute_path(self, key: str) -> str:
        """Get absolute path for a key.

        Args:
            key: Relative path

        Returns:
            Absolute path
        """
        return str(self.base_dir / key)


class ArtifactStoreFactory:
    """Factory for creating artifact store instances.

    Supports dependency injection and easy backend switching.
    """

    @staticmethod
    def create_local(base_dir: str | None = None) -> LocalArtifactStore:
        """Create local filesystem artifact store.

        Args:
            base_dir: Base directory (uses env var if not provided)

        Returns:
            LocalArtifactStore instance
        """
        return LocalArtifactStore(base_dir)

    @staticmethod
    def create_from_env() -> IArtifactStore:
        """Create artifact store from environment configuration.

        Reads ARTIFACT_STORE_TYPE environment variable:
        - "local" (default): Local filesystem storage
        - Future: "s3", "gcs", etc.

        Returns:
            Configured IArtifactStore implementation
        """
        store_type = os.getenv("ARTIFACT_STORE_TYPE", "local")

        if store_type == "local":
            return LocalArtifactStore()
        else:
            raise ValueError(f"Unsupported artifact store type: {store_type}")
