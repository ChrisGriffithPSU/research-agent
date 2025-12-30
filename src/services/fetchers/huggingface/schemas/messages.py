"""Message schemas for HuggingFace fetcher.

Defines message types for model discovery workflow:
- huggingface.discovered: Models with metadata only (Discovery Phase)
- huggingface.parse_request: Request to parse specific model card (Parsing Phase)

Each message includes correlation_id for tracing through the pipeline.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from uuid import uuid4

from src.services.fetchers.huggingface.schemas.model import ModelMetadata


class HuggingFaceDiscoveredMessage(BaseModel):
    """Message for discovered models (Phase 1: Discovery).
    
    Published to: huggingface.discovered queue
    Consumed by: Intelligence Layer (for filtering)
    
    Contains metadata only - NO model card content.
    Intelligence layer decides which models to parse.
    
    Attributes:
        correlation_id: Unique ID to trace message through pipeline
        created_at: Timestamp when discovered
        models: List of discovered model metadata
        query: Original search query
        task_filter: Task filter applied (if any)
        total_count: Total models found in this batch
    """
    
    # Correlation for tracing through pipeline
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID to trace message through pipeline"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Timestamp when discovered"
    )
    
    # Core content
    models: List[ModelMetadata] = Field(
        ...,
        description="Discovered model metadata"
    )
    query: str = Field(
        ...,
        description="Original search query"
    )
    task_filter: Optional[str] = Field(
        None,
        description="Task filter applied (e.g., 'time-series-forecasting')"
    )
    total_count: int = Field(
        ...,
        ge=0,
        description="Total models found in this batch"
    )
    
    @model_validator(mode="after")
    def validate_total_count(self) -> "HuggingFaceDiscoveredMessage":
        """Ensure total_count matches models list length."""
        if self.total_count != len(self.models):
            raise ValueError(
                f"total_count ({self.total_count}) does not match "
                f"models length ({len(self.models)})"
            )
        return self
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        frozen = True


class HuggingFaceParseRequestMessage(BaseModel):
    """Message requesting model card parsing (Phase 2: On-demand).
    
    Published by: Intelligence Layer (when model is "interesting")
    Consumed by: Model Card Parser Service
    
    Contains just enough info to identify and parse the model card.
    
    Attributes:
        correlation_id: Correlation ID for this request
        original_correlation_id: Original discovery correlation ID
        created_at: When the request was created
        model_id: HuggingFace model ID to parse
        priority: Parse priority (1=highest, 10=lowest)
        relevance_score: LLM-assigned relevance score
        intelligence_notes: Optional notes from intelligence layer
    """
    
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for this request"
    )
    original_correlation_id: str = Field(
        ...,
        description="Correlation ID from original HuggingFaceDiscoveredMessage"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="When the request was created"
    )
    
    # Identification
    model_id: str = Field(
        ...,
        description="HuggingFace model ID to parse",
        min_length=1
    )
    
    # Priority (optional, for scheduling)
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Parse priority (1=highest, 10=lowest)"
    )
    
    # Context from intelligence layer
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score"
    )
    intelligence_notes: Optional[str] = Field(
        None,
        description="Optional notes from intelligence layer"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        frozen = True


class HuggingFaceDiscoveryBatch(BaseModel):
    """Batch of discovered models for efficient processing.
    
    Attributes:
        correlation_id: Batch correlation ID
        models: List of discovered models
        query: The query that generated these models
        task_filter: Task filter applied
        total_found: Total models found before batching
        batch_number: Batch number for large result sets
        total_batches: Total batches for this query
    """
    
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Batch correlation ID"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="When the batch was created"
    )
    models: List[ModelMetadata] = Field(
        default_factory=list,
        description="List of discovered models"
    )
    query: str = Field(
        default="",
        description="The query that generated these models"
    )
    task_filter: Optional[str] = Field(
        None,
        description="Task filter applied"
    )
    total_found: int = Field(
        default=0,
        description="Total models found before batching"
    )
    batch_number: int = Field(
        default=1,
        description="Batch number"
    )
    total_batches: int = Field(
        default=1,
        description="Total batches"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        frozen = True

