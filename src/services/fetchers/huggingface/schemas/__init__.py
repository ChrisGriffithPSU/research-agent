"""Schemas for HuggingFace fetcher.

Exports all data classes for model metadata, model card content, and message schemas.
"""
from src.services.fetchers.huggingface.schemas.model import (
    ModelSource,
    TaskTag,
    ModelMetadata,
    ModelCardMetadata,
    ModelCardContent,
)
from src.services.fetchers.huggingface.schemas.messages import (
    HuggingFaceDiscoveredMessage,
    HuggingFaceParseRequestMessage,
    HuggingFaceDiscoveryBatch,
)

__all__ = [
    # Model schemas
    "ModelSource",
    "TaskTag",
    "ModelMetadata",
    "ModelCardMetadata",
    "ModelCardContent",
    # Message schemas
    "HuggingFaceDiscoveredMessage",
    "HuggingFaceParseRequestMessage",
    "HuggingFaceDiscoveryBatch",
]
