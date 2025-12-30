"""Model data classes for HuggingFace fetcher.

Design Principles (from code-quality.mdc):
- Single Responsibility: Each class has one purpose
- Immutable data: Value objects that represent snapshots
- Fail fast: Pydantic validators reject invalid data at boundary
- No external dependencies: Pure data transfer objects
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import re


class ModelSource(str, Enum):
    """Source of model discovery."""
    QUERY = "query"
    TASK = "task"
    TRENDING = "trending"


class TaskTag(str, Enum):
    """HuggingFace task tags relevant to quantitative trading research."""
    TIME_SERIES_FORECASTING = "time-series-forecasting"
    TABULAR_REGRESSION = "tabular-regression"
    TABULAR_CLASSIFICATION = "tabular-classification"
    REINFORCEMENT_LEARNING = "reinforcement-learning"
    TEXT_GENERATION = "text-generation"
    TEXT_CLASSIFICATION = "text-classification"
    SEQUENCE_CLASSIFICATION = "sequence-classification"
    TOKEN_CLASSIFICATION = "token-classification"
    QUESTION_ANSWERING = "question-answering"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    IMAGE_CLASSIFICATION = "image-classification"
    OBJECT_DETECTION = "object-detection"


class ModelMetadata(BaseModel):
    """Immutable model metadata from HuggingFace.
    
    This is a VALUE OBJECT - it represents a snapshot of model data.
    Once created, it should not be mutated.
    
    Attributes:
        model_id: HuggingFace model ID (e.g., 'amazon/chronos-t5-base')
        name: Display name (last component of model_id)
        downloads: Total download count
        likes: Number of likes
        tags: List of tags including task tags and metadata
        pipeline_tag: Suggested pipeline tag (e.g., 'text-generation')
        license: Model license (e.g., 'apache-2.0')
        library_name: Library used (e.g., 'transformers', 'pytorch')
        language: Programming languages (e.g., ['python', 'rust'])
        created_at: Creation timestamp
        last_modified: Last modification timestamp
        url: URL to model page
        revision: Current revision hash
        siblings: List of files in the repository
        arxiv_ids: List of arXiv paper IDs linked to this model
        source: How the model was discovered (query, task, trending)
        source_query: Query that found this model (if applicable)
        relevance_score: Optional relevance score from intelligence layer
    """
    model_id: str = Field(..., description="HuggingFace model ID (org/model-name)", min_length=1)
    name: str = Field(..., description="Model display name", min_length=1)
    downloads: int = Field(default=0, ge=0, description="Total download count")
    likes: int = Field(default=0, ge=0, description="Number of likes")
    tags: List[str] = Field(default_factory=list, description="All tags")
    pipeline_tag: Optional[str] = Field(None, description="Suggested pipeline tag")
    license: Optional[str] = Field(None, description="Model license")
    library_name: Optional[str] = Field(None, description="Library used")
    language: List[str] = Field(default_factory=list, description="Programming languages")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    last_modified: Optional[str] = Field(None, description="Last modification timestamp")
    url: str = Field(default="", description="URL to model page")
    revision: Optional[str] = Field(None, description="Current revision hash")
    siblings: List[str] = Field(default_factory=list, description="Files in repository")
    arxiv_ids: List[str] = Field(default_factory=list, description="Linked arXiv papers")
    source: ModelSource = Field(
        default=ModelSource.QUERY,
        description="How the model was discovered"
    )
    source_query: str = Field(default="", description="Query that found this model")
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score"
    )

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        """Validate model_id format."""
        if not re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Invalid model_id format: {v}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str, info) -> str:
        """Validate URL format, constructing from model_id if empty."""
        if v:
            return v
        model_id = info.data.get("model_id", "")
        return f"https://huggingface.co/{model_id}"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str, info) -> str:
        """Validate name, extracting from model_id if empty."""
        if v:
            return v
        model_id = info.data.get("model_id", "")
        return model_id.split("/")[-1] if "/" in model_id else model_id

    @model_validator(mode="after")
    def validate_arxiv_ids(self) -> "ModelMetadata":
        """Ensure arxiv_ids are valid format."""
        valid_ids = []
        for arxiv_id in self.arxiv_ids:
            if re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
                valid_ids.append(arxiv_id)
            elif re.match(r"^arxiv:\d{4}\.\d{4,5}$", arxiv_id):
                valid_ids.append(arxiv_id.replace("arxiv:", ""))
        self.arxiv_ids = valid_ids
        return self

    def __hash__(self) -> int:
        """Make hashable for deduplication (immutable value object)."""
        return hash(self.model_id)

    def __eq__(self, other: object) -> bool:
        """Equality based on model ID (value object semantics)."""
        if isinstance(other, ModelMetadata):
            return self.model_id == other.model_id
        return False

    model_config = {
        "frozen": True,  # Immutable value object
        "str_json_mode": "json",
    }


class ModelCardMetadata(BaseModel):
    """Parsed YAML frontmatter from model card.
    
    Attributes:
        language: Model language(s)
        license: Model license
        library_name: Library used
        tags: Tags from frontmatter
        datasets: Datasets used in training
        metrics: Evaluation metrics
        base_model: Parent model if fine-tuned
        model_name: Human-readable model name
        pipeline_tag: Pipeline tag
    """
    language: List[str] = Field(default_factory=list)
    license: Optional[str] = None
    library_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    datasets: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)
    base_model: Optional[str] = None
    model_name: Optional[str] = None
    pipeline_tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (pure function)."""
        return {
            "language": self.language,
            "license": self.license,
            "library_name": self.library_name,
            "tags": self.tags,
            "datasets": self.datasets,
            "metrics": self.metrics,
            "base_model": self.base_model,
            "model_name": self.model_name,
            "pipeline_tag": self.pipeline_tag,
        }

    model_config = {"frozen": True}


class ModelCardContent(BaseModel):
    """Parsed model card content optimized for LLM consumption.
    
    This is a VALUE OBJECT - immutable parsed representation.
    
    Attributes:
        model_id: HuggingFace model ID
        metadata: Parsed YAML frontmatter
        markdown_content: Raw markdown body
        description: Model description section
        training_details: Training information section
        usage: How to use the model
        limitations: Known limitations and weaknesses
        code_blocks: Extracted code examples
        tables: Extracted tables with benchmark results
        metadata_dict: Full metadata dictionary (raw)
    """
    model_id: str = Field(..., description="HuggingFace model ID", min_length=1)
    metadata: ModelCardMetadata = Field(
        default_factory=ModelCardMetadata,
        description="Parsed YAML frontmatter"
    )
    markdown_content: str = Field(default="", description="Raw markdown body")
    description: str = Field(default="", description="Model description")
    training_details: str = Field(default="", description="Training information")
    usage: str = Field(default="", description="Usage instructions")
    limitations: str = Field(default="", description="Limitations and weaknesses")
    code_blocks: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Extracted code examples with language"
    )
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables with captions and data"
    )
    metadata_dict: Dict[str, Any] = Field(
        default_factory=dict,
        description="Full metadata dictionary"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching (pure function)."""
        return {
            "model_id": self.model_id,
            "metadata": self.metadata.to_dict(),
            "markdown_content": self.markdown_content,
            "description": self.description,
            "training_details": self.training_details,
            "usage": self.usage,
            "limitations": self.limitations,
            "code_blocks": self.code_blocks,
            "tables": self.tables,
            "metadata_dict": self.metadata_dict,
        }

    def to_xml(self) -> str:
        """Convert to XML format for LLM consumption (pure function)."""
        lines = [
            "<model_card>",
            f"  <model_id>{self.model_id}</model_id>",
            "  <description>",
            self.description or "No description available",
            "  </description>",
            "  <usage>",
            self.usage or "No usage instructions available",
            "  </usage>",
            "  <limitations>",
            self.limitations or "No limitations documented",
            "  </limitations>",
        ]
        
        if self.code_blocks:
            lines.append("  <code_blocks>")
            for i, block in enumerate(self.code_blocks):
                lang = block.get("language", "text")
                code = block.get("code", "")
                lines.append(f'    <code_block index="{i}" language="{lang}">')
                lines.append(f"      <![CDATA[{code}]]>")
                lines.append("    </code_block>")
            lines.append("  </code_blocks>")
        
        if self.tables:
            lines.append("  <tables>")
            for i, table in enumerate(self.tables):
                lines.append(f'    <table index="{i}">')
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                lines.append(f"      <headers>{', '.join(headers)}</headers>")
                for row in rows:
                    lines.append(f"      <row>{', '.join(row)}</row>")
                lines.append("    </table>")
            lines.append("  </tables>")
        
        lines.append("</model_card>")
        return "\n".join(lines)

    model_config = {"frozen": True}
