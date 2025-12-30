"""Abstract interfaces for Kaggle fetcher plugin.

Defines contracts that components must honor.
Allows for different implementations (e.g., mock for testing).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class IKaggleAPI(ABC):
    """Interface for Kaggle API client.

    What changes: HTTP client implementation, retry logic, rate limiting strategy
    What must not change: Query execution, result parsing, pagination contract
    """

    @abstractmethod
    async def search_notebooks(
        self,
        query: str,
        max_results: int = 20,
        sort_by: str = "voteCount",
    ) -> List["NotebookMetadata"]:
        """Search notebooks on Kaggle.

        Args:
            query: Search query (supports tags: "tag:mytag")
            max_results: Maximum results to return
            sort_by: Sort field (voteCount, dateCreated, scoreDescending)

        Returns:
            List of notebook metadata
        """
        pass

    @abstractmethod
    async def get_competition_notebooks(
        self,
        competition_slug: str,
        max_notebooks: int = 10,
    ) -> List["NotebookMetadata"]:
        """Get top notebooks from a competition.

        Args:
            competition_slug: Competition identifier (e.g., "titanic")
            max_notebooks: Maximum notebooks to return

        Returns:
            List of notebook metadata sorted by votes
        """
        pass

    @abstractmethod
    async def download_notebook(
        self,
        notebook_path: str,
    ) -> "NotebookContent":
        """Download notebook content from Kaggle.

        Args:
            notebook_path: Kaggle notebook path (e.g., "username/notebook-slug")

        Returns:
            Full notebook content as JSON
        """
        pass

    @abstractmethod
    async def search_competitions(
        self,
        query: str,
    ) -> List["CompetitionMetadata"]:
        """Search competitions on Kaggle.

        Args:
            query: Search query for competitions

        Returns:
            List of competition metadata
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if Kaggle API is accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        pass


class INotebookParser(ABC):
    """Interface for notebook content parsing.

    What changes: Parser implementation, AST library, extraction logic
    What must not change: Output format (ParsedNotebook dataclass)
    """

    @abstractmethod
    async def parse(
        self,
        notebook_json: Dict[str, Any],
        notebook_path: str,
    ) -> "ParsedNotebook":
        """Parse full notebook content.

        Args:
            notebook_json: Raw notebook JSON from Kaggle
            notebook_path: Kaggle notebook path

        Returns:
            ParsedNotebook with structured content
        """
        pass

    @abstractmethod
    async def extract_cells(
        self,
        notebook_json: Dict[str, Any],
    ) -> List[Union["CodeCell", "MarkdownCell"]]:
        """Extract cells from notebook.

        Args:
            notebook_json: Raw notebook JSON

        Returns:
            List of cells (code or markdown)
        """
        pass

    @abstractmethod
    async def analyze_code_cell(
        self,
        source: str,
    ) -> "CodeAnalysis":
        """Analyze Python code cell using AST.

        Args:
            source: Python source code

        Returns:
            CodeAnalysis with imports, functions, classes
        """
        pass

    @abstractmethod
    async def extract_outputs(
        self,
        outputs: List[Dict[str, Any]],
    ) -> List["Output"]:
        """Extract and parse cell outputs.

        Args:
            outputs: Raw output data from notebook

        Returns:
            List of structured outputs
        """
        pass


# Forward references for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.fetchers.kaggle.schemas.notebook import (
        NotebookMetadata,
        NotebookContent,
        ParsedNotebook,
        CompetitionMetadata,
        CodeCell,
        MarkdownCell,
        CodeAnalysis,
        Output,
    )


__all__ = [
    "IKaggleAPI",
    "INotebookParser",
]

