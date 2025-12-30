"""Notebook data classes for Kaggle fetcher.

Defines data structures for notebook metadata, content, and parsed content.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class NotebookSource(str, Enum):
    """Source of notebook discovery."""
    COMPETITION = "competition"
    TAG = "tag"
    QUERY = "query"


class CellType(str, Enum):
    """Type of notebook cell."""
    CODE = "code"
    MARKDOWN = "markdown"


class NotebookMetadata(BaseModel):
    """Immutable notebook metadata from Kaggle.

    Attributes:
        notebook_id: Kaggle notebook ID (e.g., 'username/notebook-slug')
        title: Notebook title
        authors: List of author names
        competition_slug: Competition slug if from competition
        tags: Tags associated with the notebook
        votes: Number of votes/thumbs up
        total_views: Number of views
        total_comments: Number of comments
        created_at: Creation timestamp
        updated_at: Last update timestamp
        notebook_path: kagglehub path to download
        language: Programming language
        source: How the notebook was discovered (competition, tag, query)
        source_query: Query that found this notebook (if applicable)
        relevance_score: Optional relevance score from intelligence layer
    """
    notebook_id: str = Field(
        ...,
        description="Kaggle notebook ID (e.g., 'username/notebook-slug')"
    )
    title: str = Field(..., description="Notebook title")
    authors: List[str] = Field(
        default_factory=list,
        description="Author names"
    )
    competition_slug: Optional[str] = Field(
        None,
        description="Competition slug if from competition"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags associated with the notebook"
    )
    votes: int = Field(
        default=0,
        ge=0,
        description="Number of votes/thumbs up"
    )
    total_views: int = Field(
        default=0,
        ge=0,
        description="Number of views"
    )
    total_comments: int = Field(
        default=0,
        ge=0,
        description="Number of comments"
    )
    created_at: Optional[str] = Field(
        None,
        description="Creation timestamp"
    )
    updated_at: Optional[str] = Field(
        None,
        description="Last update timestamp"
    )
    notebook_path: str = Field(
        ...,
        description="kagglehub path to download"
    )
    language: str = Field(
        default="python",
        description="Programming language"
    )
    source: NotebookSource = Field(
        default=NotebookSource.QUERY,
        description="How the notebook was discovered"
    )
    source_query: str = Field(
        default="",
        description="Query that found this notebook"
    )
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance score"
    )

    def __hash__(self):
        """Make hashable for deduplication."""
        return hash(self.notebook_id)

    def __eq__(self, other):
        """Equality based on notebook ID."""
        if isinstance(other, NotebookMetadata):
            return self.notebook_id == other.notebook_id
        return False

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Output(BaseModel):
    """Cell output from notebook.

    Attributes:
        output_type: Type of output (execute_result, stream, error, display_data)
        data: Output data dictionary
        metadata: Output metadata
        execution_count: Execution count if available
    """
    output_type: str = Field(
        ...,
        description="Type of output (execute_result, stream, error, display_data)"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Output data dictionary"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Output metadata"
    )
    execution_count: Optional[int] = Field(
        None,
        description="Execution count if available"
    )


class CodeCell(BaseModel):
    """Code cell from notebook.

    Attributes:
        index: Cell index in the notebook
        source: Cell source code
        outputs: List of cell outputs
        execution_count: Execution count if available
        metadata: Cell metadata
    """
    index: int = Field(..., description="Cell index in the notebook")
    source: str = Field(..., description="Cell source code")
    outputs: List[Output] = Field(
        default_factory=list,
        description="List of cell outputs"
    )
    execution_count: Optional[int] = Field(
        None,
        description="Execution count if available"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cell metadata"
    )


class MarkdownCell(BaseModel):
    """Markdown cell from notebook.

    Attributes:
        index: Cell index in the notebook
        source: Markdown source content
        headings: Extracted headings from the markdown
    """
    index: int = Field(..., description="Cell index in the notebook")
    source: str = Field(..., description="Markdown source content")
    headings: List[str] = Field(
        default_factory=list,
        description="Extracted headings from the markdown"
    )


class CodeAnalysis(BaseModel):
    """Analysis of Python code cell using AST.

    Attributes:
        imports: List of imported modules
        functions: List of function names with signatures
        classes: List of class names
        line_count: Number of lines of code
        has_plotting: Whether the cell contains plotting code
        has_ml_library: Whether the cell uses ML libraries
    """
    imports: List[str] = Field(
        default_factory=list,
        description="List of imported modules"
    )
    functions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of function names with signatures"
    )
    classes: List[str] = Field(
        default_factory=list,
        description="List of class names"
    )
    line_count: int = Field(
        default=0,
        description="Number of lines of code"
    )
    has_plotting: bool = Field(
        default=False,
        description="Whether the cell contains plotting code"
    )
    has_ml_library: bool = Field(
        default=False,
        description="Whether the cell uses ML libraries"
    )


class NotebookContent(BaseModel):
    """Raw notebook content from Kaggle (JSON structure).

    Attributes:
        notebook_path: kagglehub path to the notebook
        nbformat_version: Notebook format version
        metadata: Notebook metadata
        cells: List of cells as raw dictionaries
        nbformat: Notebook format version (legacy field)
    """
    notebook_path: str = Field(
        ...,
        description="kagglehub path to the notebook"
    )
    nbformat_version: Optional[str] = Field(
        None,
        description="Notebook format version"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Notebook metadata"
    )
    cells: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of cells as raw dictionaries"
    )
    nbformat: Optional[int] = Field(
        None,
        description="Notebook format version (legacy field)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ParsedNotebook(BaseModel):
    """Parsed notebook content with structured cells.

    Attributes:
        notebook_path: kagglehub path to the notebook
        title: Notebook title
        authors: Author names
        competition_slug: Competition slug if applicable
        tags: Tags associated with the notebook
        votes: Number of votes
        code_cells: List of parsed code cells
        markdown_cells: List of parsed markdown cells
        raw_content: Original notebook content for reference
        metadata: Additional metadata from parsing
    """
    notebook_path: str = Field(
        ...,
        description="kagglehub path to the notebook"
    )
    title: str = Field(..., description="Notebook title")
    authors: List[str] = Field(
        default_factory=list,
        description="Author names"
    )
    competition_slug: Optional[str] = Field(
        None,
        description="Competition slug if applicable"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags associated with the notebook"
    )
    votes: int = Field(
        default=0,
        description="Number of votes"
    )
    code_cells: List[CodeCell] = Field(
        default_factory=list,
        description="Parsed code cells"
    )
    markdown_cells: List[MarkdownCell] = Field(
        default_factory=list,
        description="Parsed markdown cells"
    )
    raw_content: NotebookContent = Field(
        ...,
        description="Original notebook content for reference"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from parsing"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CompetitionMetadata(BaseModel):
    """Competition metadata from Kaggle.

    Attributes:
        competition_slug: Competition slug/identifier
        title: Competition title
        category: Competition category
        organization: Organizing entity
        deadline: Competition deadline
        total_teams: Number of participating teams
        description: Competition description
    """
    competition_slug: str = Field(..., description="Competition slug/identifier")
    title: str = Field(..., description="Competition title")
    category: str = Field(default="", description="Competition category")
    organization: str = Field(default="", description="Organizing entity")
    deadline: Optional[str] = Field(None, description="Competition deadline")
    total_teams: int = Field(default=0, description="Number of participating teams")
    description: str = Field(default="", description="Competition description")


__all__ = [
    "NotebookSource",
    "CellType",
    "NotebookMetadata",
    "Output",
    "CodeCell",
    "MarkdownCell",
    "CodeAnalysis",
    "NotebookContent",
    "ParsedNotebook",
    "CompetitionMetadata",
]

