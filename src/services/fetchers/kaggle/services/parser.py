"""Notebook parser with AST support.

Parses notebook JSON into structured content with optional AST analysis.
"""
import ast
import logging
from typing import List, Dict, Any, Union, Optional

from src.services.fetchers.kaggle.config import KaggleFetcherConfig
from src.services.fetchers.kaggle.interfaces import INotebookParser
from src.services.fetchers.kaggle.schemas.notebook import (
    NotebookContent,
    ParsedNotebook,
    CodeCell,
    MarkdownCell,
    Output,
    CodeAnalysis,
    NotebookMetadata,
)
from src.services.fetchers.kaggle.exceptions import NotebookParseError


logger = logging.getLogger(__name__)


class NotebookParser(INotebookParser):
    """Parser for Kaggle notebooks with configurable AST analysis.

    Features:
    - Structural parsing of notebook JSON
    - Cell type detection (code, markdown)
    - Optional AST analysis of code cells
    - Output extraction (raw JSON)

    All dependencies are injected through the constructor.

    Example:
        # Production use with full AST analysis
        parser = NotebookParser(ast_depth=2)

        # Testing use with no AST
        parser = NotebookParser(ast_depth=0)

        # Use parser
        parsed = await parser.parse(notebook_json, "username/notebook-slug")

    Attributes:
        config: Kaggle fetcher configuration
        ast_depth: Level of AST analysis (0, 1, or 2)
    """

    # ML libraries for detection
    ML_LIBRARIES = {
        "sklearn", "tensorflow", "torch", "keras", "xgboost", "lightgbm",
        "catboost", "pandas", "numpy", "scipy", "statsmodels", "pmdarima",
        "prophet", " darts", "mlflow", "pytorch", "jax", "transformers",
        "datasets", "huggingface", "fastai", "pytorch_lightning",
    }

    # Plotting libraries for detection
    PLOTTING_LIBRARIES = {
        "matplotlib", "seaborn", "plotly", "bokeh", "altair", "ggplot",
        "pygal", "plotnine", "holoviews", "geoplot", "folium",
    }

    def __init__(
        self,
        ast_depth: int = 2,
        config: Optional[KaggleFetcherConfig] = None,
    ):
        """Initialize notebook parser.

        Args:
            ast_depth: AST parsing depth (0=no AST, 1=imports+functions, 2=full)
            config: Kaggle fetcher configuration
        """
        self.config = config or KaggleFetcherConfig()
        self.ast_depth = ast_depth or self.config.ast_depth

    async def parse(
        self,
        notebook_json: Dict[str, Any],
        notebook_path: str,
    ) -> ParsedNotebook:
        """Parse full notebook content.

        Args:
            notebook_json: Raw notebook JSON from Kaggle
            notebook_path: Kaggle notebook path

        Returns:
            ParsedNotebook with structured content

        Raises:
            NotebookParseError: If parsing fails
        """
        try:
            # Extract metadata from notebook
            metadata = notebook_json.get("metadata", {})
            title = self._extract_title(metadata, notebook_json)
            authors = self._extract_authors(metadata)

            # Extract cells
            code_cells, markdown_cells = await self.extract_cells(notebook_json)

            # Extract tags and votes if available
            tags = metadata.get("tags", [])
            # Note: Votes are typically in NotebookMetadata, not in the notebook itself

            # Create raw content for reference
            raw_content = NotebookContent(
                notebook_path=notebook_path,
                nbformat_version=notebook_json.get("nbformat_version"),
                metadata=metadata,
                cells=notebook_json.get("cells", []),
                nbformat=notebook_json.get("nbformat"),
            )

            # Build parsed notebook
            parsed = ParsedNotebook(
                notebook_path=notebook_path,
                title=title,
                authors=authors,
                tags=tags,
                code_cells=code_cells,
                markdown_cells=markdown_cells,
                raw_content=raw_content,
                metadata={
                    "nbformat_version": notebook_json.get("nbformat_version"),
                    "cells_count": len(notebook_json.get("cells", [])),
                    "code_cells_count": len(code_cells),
                    "markdown_cells_count": len(markdown_cells),
                },
            )

            logger.debug(f"Parsed notebook: {notebook_path} ({len(code_cells)} code cells)")
            return parsed

        except Exception as e:
            raise NotebookParseError(
                message=f"Failed to parse notebook: {e}",
                notebook_path=notebook_path,
                parse_stage="full_parse",
                original=e,
            )

    async def extract_cells(
        self,
        notebook_json: Dict[str, Any],
    ) -> tuple[List[CodeCell], List[MarkdownCell]]:
        """Extract cells from notebook.

        Args:
            notebook_json: Raw notebook JSON

        Returns:
            Tuple of (code_cells, markdown_cells)
        """
        code_cells = []
        markdown_cells = []

        cells = notebook_json.get("cells", [])

        for i, cell_data in enumerate(cells):
            cell_type = cell_data.get("cell_type", "code")

            if cell_type == "code":
                cell = await self._parse_code_cell(cell_data, i)
                code_cells.append(cell)
            elif cell_type == "markdown":
                cell = self._parse_markdown_cell(cell_data, i)
                markdown_cells.append(cell)

        return code_cells, markdown_cells

    async def analyze_code_cell(
        self,
        source: str,
    ) -> CodeAnalysis:
        """Analyze Python code cell using AST.

        Args:
            source: Python source code

        Returns:
            CodeAnalysis with imports, functions, classes
        """
        if self.ast_depth == 0:
            # No AST analysis requested
            return CodeAnalysis(
                line_count=len(source.splitlines()),
            )

        try:
            # Parse AST
            tree = ast.parse(source)

            # Extract imports
            imports = self._extract_imports(tree)

            # Extract functions (if depth >= 1)
            functions = []
            if self.ast_depth >= 1:
                functions = self._extract_functions(tree)

            # Extract classes (if depth >= 2)
            classes = []
            if self.ast_depth >= 2:
                classes = self._extract_classes(tree)

            # Detect libraries
            has_ml_library = bool(imports & self.ML_LIBRARIES)
            has_plotting = bool(imports & self.PLOTTING_LIBRARIES)

            return CodeAnalysis(
                imports=sorted(list(imports)),
                functions=functions,
                classes=classes,
                line_count=len(source.splitlines()),
                has_plotting=has_plotting,
                has_ml_library=has_ml_library,
            )

        except SyntaxError:
            # Invalid Python code - return basic analysis
            logger.debug(f"AST parse failed for code cell, returning basic analysis")
            return CodeAnalysis(
                line_count=len(source.splitlines()),
            )

    async def extract_outputs(
        self,
        outputs: List[Dict[str, Any]],
    ) -> List[Output]:
        """Extract and parse cell outputs.

        Args:
            outputs: Raw output data from notebook

        Returns:
            List of structured outputs (raw JSON as per user request)
        """
        parsed_outputs = []

        for i, output_data in enumerate(outputs):
            output = Output(
                output_type=output_data.get("output_type", "unknown"),
                data=output_data.get("data", {}),
                metadata=output_data.get("metadata", {}),
                execution_count=output_data.get("execution_count"),
            )
            parsed_outputs.append(output)

        return parsed_outputs

    async def _parse_code_cell(
        self,
        cell_data: Dict[str, Any],
        index: int,
    ) -> CodeCell:
        """Parse a code cell.

        Args:
            cell_data: Raw cell data
            index: Cell index

        Returns:
            CodeCell with parsed content
        """
        # Extract source
        source = cell_data.get("source", "")
        if isinstance(source, list):
            source = "".join(source)

        # Extract outputs if enabled
        outputs = []
        if self.config.extract_outputs:
            raw_outputs = cell_data.get("outputs", [])
            outputs = await self.extract_outputs(raw_outputs)

        # Extract execution count
        execution_count = cell_data.get("execution_count")

        # Analyze code if AST depth > 0
        analysis = None
        if self.ast_depth > 0 and source.strip():
            analysis = await self.analyze_code_cell(source)

        return CodeCell(
            index=index,
            source=source,
            outputs=outputs,
            execution_count=execution_count,
            metadata=cell_data.get("metadata", {}),
            analysis=analysis,
        )

    def _parse_markdown_cell(
        self,
        cell_data: Dict[str, Any],
        index: int,
    ) -> MarkdownCell:
        """Parse a markdown cell.

        Args:
            cell_data: Raw cell data
            index: Cell index

        Returns:
            MarkdownCell with parsed content
        """
        # Extract source
        source = cell_data.get("source", "")
        if isinstance(source, list):
            source = "".join(source)

        # Extract headings
        headings = self._extract_headings(source)

        return MarkdownCell(
            index=index,
            source=source,
            headings=headings,
        )

    def _extract_title(
        self,
        metadata: Dict[str, Any],
        notebook_json: Dict[str, Any],
    ) -> str:
        """Extract notebook title."""
        # Try metadata first
        title = metadata.get("title", "")
        if title:
            return title

        # Try first markdown cell
        for cell in notebook_json.get("cells", []):
            if cell.get("cell_type") == "markdown":
                source = cell.get("source", "")
                if isinstance(source, list):
                    source = "".join(source)
                # First line that's a heading or non-empty
                for line in source.split("\n"):
                    line = line.strip()
                    if line.startswith("#"):
                        return line.lstrip("#").strip()
                    elif line:
                        return line

        return "Untitled Notebook"

    def _extract_authors(self, metadata: Dict[str, Any]) -> List[str]:
        """Extract author names from metadata."""
        authors = []

        # Try different possible fields
        author_data = metadata.get("authors", metadata.get("author", []))

        if isinstance(author_data, list):
            for author in author_data:
                if isinstance(author, str):
                    authors.append(author)
                elif isinstance(author, dict):
                    name = author.get("name", author.get("username", ""))
                    if name:
                        authors.append(name)
        elif isinstance(author_data, str):
            authors.append(author_data)

        return authors

    def _extract_headings(self, source: str) -> List[str]:
        """Extract headings from markdown."""
        headings = []

        for line in source.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                heading = line.lstrip("#").strip()
                headings.append(heading)

        return headings

    def _extract_imports(self, tree: ast.AST) -> set:
        """Extract imported module names from AST."""
        imports = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    imports.add(module)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    imports.add(module)

        return imports

    def _extract_functions(self, tree: ast.AST) -> List[Dict[str, str]]:
        """Extract function definitions from AST."""
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_info = {
                    "name": node.name,
                    "line": str(node.lineno),
                }
                # Add arguments
                args = [arg.arg for arg in node.args.args]
                func_info["args"] = ",".join(args)
                functions.append(func_info)

        return functions

    def _extract_classes(self, tree: ast.AST) -> List[str]:
        """Extract class definitions from AST."""
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)

        return classes


__all__ = [
    "NotebookParser",
]

