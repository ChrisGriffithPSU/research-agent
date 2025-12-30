"""Model card parser for HuggingFace.

Design Principles (from code-quality.mdc):
- Pure Function: parse(model_id, content) -> ModelCardContent (no side effects)
- No State: Parser is stateless, configuration is immutable
- Defensive Programming: Handle malformed input gracefully
- LLM-Optimized: Output structured for LLM consumption
- Error Handling: Return partial results on parse errors
"""
import re
import logging
from typing import List, Dict, Any, Optional, Pattern
from dataclasses import dataclass

from huggingface_hub import ModelCard

from ..exceptions import ModelCardParseError
from ..interfaces import IModelCardParser
from ..schemas.model import (
    ModelCardContent,
    ModelCardMetadata,
)


logger = logging.getLogger(__name__)


# Pre-compiled patterns for performance (immutable, module-level)
_SECTION_PATTERNS: Dict[str, Pattern[str]] = {
    "description": re.compile(
        r"^#{1,3}\s*(?:description|about|summary|overview|intro)",
        re.IGNORECASE | re.MULTILINE
    ),
    "usage": re.compile(
        r"^#{1,3}\s*(?:usage|how to use|using|installation|quickstart|get started)",
        re.IGNORECASE | re.MULTILINE
    ),
    "training": re.compile(
        r"^#{1,3}\s*(?:training|train|training details|training procedure|training code)",
        re.IGNORECASE | re.MULTILINE
    ),
    "limitations": re.compile(
        r"^#{1,3}\s*(?:limitations|caveats|known issues|warnings|shortcomings)",
        re.IGNORECASE | re.MULTILINE
    ),
    "evaluation": re.compile(
        r"^#{1,3}\s*(?:evaluation|benchmarks|results|performance|metrics)",
        re.IGNORECASE | re.MULTILINE
    ),
    "model_details": re.compile(
        r"^#{1,3}\s*(?:model details|model information|architecture|model card)",
        re.IGNORECASE | re.MULTILINE
    ),
    "citation": re.compile(
        r"^#{1,3}\s*(?:citation|cite|reference)",
        re.IGNORECASE | re.MULTILINE
    ),
}

_CODE_BLOCK_PATTERN: Pattern[str] = re.compile(
    r"```(\w*)\n([\s\S]*?)```",
    re.MULTILINE
)

_TABLE_PATTERN: Pattern[str] = re.compile(
    r"\|[^\n]*\|\n\|[-:|]+\|\n((?:\|[^\n]*\|\n)*)",
    re.MULTILINE
)

_YAML_FRONTMATTER_PATTERN: Pattern[str] = re.compile(
    r"^---\n[\s\S]*?\n---\n",
    re.MULTILINE
)


@dataclass
class ParseResult:
    """Result of parsing a section."""
    title: str
    content: str
    level: int  # Header level (1 for #, 2 for ##, etc.)


class Parser(IModelCardParser):
    """Parser for HuggingFace model cards.
    
    Responsibilities:
    - Parse model card markdown into structured format
    - Extract YAML frontmatter
    - Extract code blocks and tables
    - Identify key sections (description, usage, training, etc.)
    - Format output for LLM consumption
    
    This is a STATELESS parser - no mutable instance variables.
    All configuration should be passed as parameters if needed.
    
    Design:
    - Pure function: parse() transforms input to output
    - No side effects in core logic
    - Deterministic output for given input
    - Graceful degradation on errors
    """
    
    def __init__(self) -> None:
        """Initialize the model card parser.
        
        No state is stored - this is a stateless parser.
        """
        logger.debug(
            "Parser initialized",
            extra={"event": "parser_init"}
        )
    
    def parse(
        self,
        model_id: str,
        card_content: str,
    ) -> ModelCardContent:
        """Parse model card content into structured format.
        
        This is a PURE FUNCTION - no side effects.
        
        Args:
            model_id: HuggingFace model ID
            card_content: Raw markdown content
            
        Returns:
            ModelCardContent with parsed sections
            
        Raises:
            ModelCardParseError: If parsing completely fails
        """
        if not card_content or not card_content.strip():
            logger.debug(
                f"Empty model card for {model_id}",
                extra={
                    "event": "parser_empty",
                    "model_id": model_id,
                }
            )
            return ModelCardContent(model_id=model_id)
        
        try:
            # Parse with huggingface_hub's ModelCard
            card = ModelCard(card_content)
            
            # Extract metadata from YAML frontmatter
            metadata = self._parse_metadata(card)
            
            # Extract sections from markdown
            sections = self._extract_sections(card_content)
            
            # Extract code blocks
            code_blocks = self._extract_code_blocks(card_content)
            
            # Extract tables
            tables = self._extract_tables(card_content)
            
            # Build content
            content = ModelCardContent(
                model_id=model_id,
                metadata=metadata,
                markdown_content=card_content,
                description=sections.get("description", ""),
                training_details=sections.get("training", ""),
                usage=sections.get("usage", ""),
                limitations=sections.get("limitations", ""),
                code_blocks=code_blocks,
                tables=tables,
                metadata_dict=card.data.to_dict() if card.data else {},
            )
            
            logger.debug(
                f"Parsed model card for {model_id}",
                extra={
                    "event": "parser_success",
                    "model_id": model_id,
                    "description_length": len(content.description),
                    "code_blocks_count": len(content.code_blocks),
                    "tables_count": len(content.tables),
                }
            )
            
            return content
            
        except Exception as e:
            logger.error(
                f"Failed to parse model card for {model_id}: {e}",
                extra={
                    "event": "parser_error",
                    "model_id": model_id,
                    "error": str(e),
                }
            )
            raise ModelCardParseError(
                model_id=model_id,
                message=str(e),
                original=e,
            )
    
    def _parse_metadata(self, card: ModelCard) -> ModelCardMetadata:
        """Parse YAML frontmatter from model card.
        
        Pure data transformation - no side effects.
        
        Args:
            card: ModelCard object from huggingface_hub
            
        Returns:
            ModelCardMetadata with extracted fields
        """
        data = card.data.to_dict() if card.data else {}
        
        return ModelCardMetadata(
            language=data.get("language", []),
            license=data.get("license"),
            library_name=data.get("library_name"),
            tags=data.get("tags", []),
            datasets=data.get("datasets", []),
            metrics=data.get("metrics", []),
            base_model=data.get("base_model"),
            model_name=data.get("model_name"),
            pipeline_tag=data.get("pipeline_tag"),
        )
    
    def _extract_sections(self, content: str) -> Dict[str, str]:
        """Extract named sections from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Dictionary mapping section names to content
        """
        sections: Dict[str, str] = {}
        lines = content.split("\n")
        
        current_section: Optional[str] = None
        current_content: List[str] = []
        
        for line in lines:
            # Check if this line is a header
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            
            if header_match:
                header_level = len(header_match.group(1))
                header_text = header_match.group(2).strip().lower()
                
                # Check if this header matches any known section
                matched = False
                for section_name, pattern in _SECTION_PATTERNS.items():
                    if pattern.search(line):
                        # Save previous section
                        if current_section and current_content:
                            sections[current_section] = "\n".join(
                                current_content
                            ).strip()
                        
                        current_section = section_name
                        current_content = []
                        matched = True
                        break
                
                # Unknown header - save current section if exists
                if not matched:
                    if current_section and current_content:
                        sections[current_section] = "\n".join(
                            current_content
                        ).strip()
                    current_section = None
                    current_content = []
            elif current_section:
                current_content.append(line)
        
        # Save last section
        if current_section and current_content:
            sections[current_section] = "\n".join(current_content).strip()
        
        # If no description section found, use first paragraph
        if "description" not in sections:
            first_para = self._extract_first_paragraph(content)
            if first_para:
                sections["description"] = first_para
        
        return sections
    
    def _extract_first_paragraph(self, content: str) -> str:
        """Extract first paragraph from content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            First paragraph text
        """
        # Skip YAML frontmatter
        content = _YAML_FRONTMATTER_PATTERN.sub("", content)
        
        # Find first non-empty, non-header paragraph
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        
        return ""
    
    def _extract_code_blocks(self, content: str) -> List[Dict[str, str]]:
        """Extract code blocks from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            List of code blocks with language and content
        """
        code_blocks: List[Dict[str, str]] = []
        
        for match in _CODE_BLOCK_PATTERN.finditer(content):
            language = match.group(1) or "text"
            code = match.group(2).strip()
            
            code_blocks.append({
                "language": language,
                "code": code,
            })
        
        return code_blocks
    
    def _extract_tables(self, content: str) -> List[Dict[str, Any]]:
        """Extract tables from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            List of tables with headers and rows
        """
        tables: List[Dict[str, Any]] = []
        
        # Find all table sections
        table_sections = _TABLE_PATTERN.findall(content)
        
        for section in table_sections:
            try:
                rows = [
                    [cell.strip() for cell in line.strip("| ").split("|")]
                    for line in section.strip().split("\n")
                    if line.strip()
                ]
                
                if len(rows) < 2:
                    continue
                
                # First row is headers
                headers = rows[0]
                
                # Rest are data rows
                data_rows = rows[1:]
                
                tables.append({
                    "headers": headers,
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": len(headers),
                })
            except Exception as e:
                logger.debug(
                    f"Failed to parse table: {e}",
                    extra={"event": "table_parse_error", "error": str(e)}
                )
                continue
        
        return tables
    
    def health_check(self) -> bool:
        """Check if parser is healthy.
        
        Returns:
            True if parser is healthy, False otherwise
        """
        try:
            # Test parsing a simple model card
            test_content = """
---
language: en
license: mit
---

# Test Model

## Description
This is a test model.
"""
            result = self.parse("test/model", test_content)
            return result.model_id == "test/model"
        except Exception as e:
            logger.error(
                f"Parser health check failed: {e}",
                extra={"event": "parser_health_check_error", "error": str(e)}
            )
            return False
    
    def __repr__(self) -> str:
        return "Parser(stateless)"


# Alias for backwards compatibility
ModelCardParser = Parser

