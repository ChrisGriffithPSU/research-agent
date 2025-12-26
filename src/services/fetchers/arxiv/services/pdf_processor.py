"""PDF content processor using docling.

Uses PDF URLs directly - no disk download needed.
Caches parsed content (not PDF files).
Integrates with existing cache infrastructure.
"""
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import ParsedContent
from src.services.fetchers.arxiv.services.cache_manager import CacheManager
from src.services.fetchers.arxiv.exceptions import (
    PDFDownloadError,
    PDFParseError,
    PDFSizeError,
)


logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF content processor using docling.
    
    Uses PDF URLs directly - docling handles HTTP download internally.
    Caches parsed content in Redis.
    
    Features:
    - Text extraction
    - Table extraction
    - Equation extraction (LaTeX)
    - Figure caption extraction
    - Caching of parsed content
    
    Attributes:
        converter: docling DocumentConverter
        cache_manager: Cache manager for parsed content
        config: ArXiv fetcher configuration
    """
    
    def __init__(
        self,
        cache_manager: Optional[CacheManager] = None,
        config: Optional[ArxivFetcherConfig] = None,
    ):
        """Initialize PDF processor.
        
        Args:
            cache_manager: Cache manager for parsed content
            config: ArXiv fetcher configuration
        """
        self.cache_manager = cache_manager
        self.config = config or ArxivFetcherConfig()
        
        # Configure docling for comprehensive extraction
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # Extract text from scanned PDFs
        pipeline_options.do_table_structure = True  # Extract tables
        pipeline_options.table_structure_options.do_cell_matching = True
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: pipeline_options,
            }
        )
        
        # Statistics
        self._processed_count = 0
        self._error_count = 0
        self._cache_hit_count = 0
    
    async def extract(
        self,
        pdf_url: str,
        paper_id: str,
    ) -> ParsedContent:
        """Process paper PDF and extract content.
        
        Args:
            pdf_url: URL to PDF (https://arxiv.org/pdf/{id}.pdf)
            paper_id: arXiv ID (e.g., "2401.12345")
            
        Returns:
            ParsedContent with extracted text, tables, equations, captions
            
        Raises:
            PDFDownloadError: If PDF download fails
            PDFParseError: If PDF parsing fails
            PDFSizeError: If PDF exceeds size limit
        """
        # Check cache first
        if self.cache_manager:
            cached = await self.cache_manager.get_parsed_content(paper_id)
            if cached:
                logger.info(f"Cache hit for parsed content: {paper_id}")
                self._cache_hit_count += 1
                return ParsedContent(
                    paper_id=paper_id,
                    **cached,
                )
        
        # Process with docling (URL passed directly)
        logger.info(f"Processing PDF: {pdf_url}")
        
        try:
            import time
            start_time = time.time()
            
            # docling handles URL download internally
            result = self.converter.convert(pdf_url)
            
            # Export to structured dict
            doc_dict = result.document.export_to_dict()
            
            # Extract content from docling output
            parsed = self._extract_from_docling(paper_id, doc_dict)
            
            # Add processing metadata
            parsed.metadata["processing_time_seconds"] = time.time() - start_time
            parsed.metadata["processed_at"] = datetime.utcnow().isoformat()
            parsed.metadata["pdf_url"] = pdf_url
            
            # Cache the parsed result
            if self.cache_manager:
                await self.cache_manager.set_parsed_content(
                    paper_id,
                    parsed.__dict__,
                )
            
            self._processed_count += 1
            logger.info(
                f"Processed {paper_id} in {parsed.metadata.get('processing_time_seconds', 0):.2f}s"
            )
            
            return parsed
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process PDF {pdf_url}: {e}")
            
            # Check for specific error types
            error_str = str(e).lower()
            if "timeout" in error_str or "timed out" in error_str:
                raise PDFParseError(
                    message=f"PDF parsing timed out: {e}",
                    paper_id=paper_id,
                    pdf_url=pdf_url,
                    parse_stage="timeout",
                )
            elif "size" in error_str or "too large" in error_str:
                raise PDFSizeError(
                    pdf_url=pdf_url,
                    paper_id=paper_id,
                    size_bytes=0,  # Unknown without downloading
                    max_size_bytes=self.config.max_pdf_size_mb * 1024 * 1024,
                )
            else:
                raise PDFParseError(
                    message=f"Failed to parse PDF: {e}",
                    paper_id=paper_id,
                    pdf_url=pdf_url,
                    parse_stage="extraction",
                )
    
    def _extract_from_docling(
        self,
        paper_id: str,
        doc_dict: dict,
    ) -> ParsedContent:
        """Extract structured content from docling output.
        
        Args:
            paper_id: arXiv ID
            doc_dict: docling export_to_dict() result
            
        Returns:
            ParsedContent dataclass
        """
        # Extract text content
        text_content = self._extract_text(doc_dict)
        
        # Extract tables
        tables = self._extract_tables(doc_dict)
        
        # Extract figures/captions
        figures = self._extract_figures(doc_dict)
        
        # Extract equations (from text)
        equations = self._extract_equations(text_content)
        
        # Extract metadata
        metadata = {
            "num_pages": doc_dict.get("meta", {}).get("pages", 0),
            "file_size": doc_dict.get("meta", {}).get("file_size", 0),
            "ocr_used": doc_dict.get("meta", {}).get("ocr", False),
            "docling_version": doc_dict.get("meta", {}).get("version", "unknown"),
        }
        
        return ParsedContent(
            paper_id=paper_id,
            text_content=text_content,
            tables=tables,
            equations=equations,
            figure_captions=figures,
            metadata=metadata,
        )
    
    def _extract_text(self, doc_dict: dict) -> str:
        """Extract text content from docling output.
        
        Args:
            doc_dict: docling export_to_dict() result
            
        Returns:
            Extracted text content
        """
        text_parts = []
        
        # Try different docling output formats
        if "text" in doc_dict:
            return doc_dict["text"]
        
        # Newer docling versions use "body"
        if "body" in doc_dict:
            body = doc_dict["body"]
            if isinstance(body, list):
                for item in body:
                    text_parts.append(self._extract_text_from_item(item))
            elif isinstance(body, dict):
                text_parts.append(self._extract_text_from_item(body))
        
        # Try "elements" (another docling format)
        if "elements" in doc_dict:
            for element in doc_dict["elements"]:
                if element.get("type") in ["paragraph", "text", "heading"]:
                    text_parts.append(element.get("text", ""))
        
        return "\n\n".join(text_parts)
    
    def _extract_text_from_item(self, item: dict) -> str:
        """Extract text from a docling body item.
        
        Args:
            item: Body item dict
            
        Returns:
            Extracted text
        """
        text_parts = []
        
        text = item.get("text") or item.get("content", "")
        if text:
            text_parts.append(text)
        
        # Handle nested content
        children = item.get("children") or item.get("content", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    text_parts.append(self._extract_text_from_item(child))
                elif isinstance(child, str):
                    text_parts.append(child)
        
        return "\n\n".join(text_parts)
    
    def _extract_tables(self, doc_dict: dict) -> List[Dict[str, Any]]:
        """Extract tables from docling output.
        
        Args:
            doc_dict: docling export_to_dict() result
            
        Returns:
            List of extracted tables
        """
        tables = []
        
        # Try "tables" key
        if "tables" in doc_dict:
            for table in doc_dict["tables"]:
                tables.append(self._format_table(table))
        
        # Try "elements" for inline tables
        if "elements" in doc_dict:
            for element in doc_dict["elements"]:
                if element.get("type") == "table":
                    tables.append(self._format_table(element))
        
        return tables
    
    def _format_table(self, table: dict) -> Dict[str, Any]:
        """Format a table for storage.
        
        Args:
            table: Table dict from docling
            
        Returns:
            Formatted table dict
        """
        return {
            "caption": table.get("caption", ""),
            "data": table.get("data", []),
            "row_count": len(table.get("data", [])),
            "col_count": len(table.get("data", [0])) if table.get("data") else 0,
            "page_number": table.get("page_no", 0),
        }
    
    def _extract_figures(self, doc_dict: dict) -> List[Dict[str, str]]:
        """Extract figure captions from docling output.
        
        Args:
            doc_dict: docling export_to_dict() result
            
        Returns:
            List of figure dicts
        """
        figures = []
        
        # Try "pictures" key
        if "pictures" in doc_dict:
            for i, pic in enumerate(doc_dict["pictures"]):
                figures.append({
                    "figure_id": f"fig_{i+1}",
                    "caption": pic.get("caption", ""),
                    "page": str(pic.get("page_no", 0)),
                    "alt_text": pic.get("alt_text", ""),
                })
        
        # Try "figures" key
        if "figures" in doc_dict:
            for i, fig in enumerate(doc_dict["figures"]):
                figures.append({
                    "figure_id": fig.get("id", f"fig_{i+1}"),
                    "caption": fig.get("caption", ""),
                    "page": str(fig.get("page_no", 0)),
                })
        
        # Try "elements" for inline figures
        if "elements" in doc_dict:
            for i, element in enumerate(doc_dict["elements"]):
                if element.get("type") == "figure":
                    figures.append({
                        "figure_id": element.get("id", f"fig_{i+1}"),
                        "caption": element.get("caption", ""),
                        "page": str(element.get("page_no", 0)),
                    })
        
        return figures
    
    def _extract_equations(self, text: str) -> List[str]:
        """Extract LaTeX equations from text content.
        
        Looks for:
        - Inline: $...$ or \(...\)
        - Block: $$...$$ or \[...\]
        - LaTeX environments: \begin{equation}...\end{equation}
        
        Args:
            text: Text content to search
            
        Returns:
            List of extracted equations
        """
        equations = []
        
        # Inline equations: $...$
        inline = re.findall(r'\$([^$]+)\$', text)
        equations.extend([e.strip() for e in inline if e.strip()])
        
        # Block equations: \[...\]
        block = re.findall(r'\\\[(.*?)\\\]', text, re.DOTALL)
        equations.extend([e.strip() for e in block if e.strip()])
        
        # LaTeX environments
        env_eq = re.findall(
            r'\\begin\{equation\}(.*?)\\end\{equation\}',
            text,
            re.DOTALL
        )
        equations.extend([e.strip() for e in env_eq if e.strip()])
        
        env_align = re.findall(
            r'\\begin\{align\}(.*?)\\end\{align\}',
            text,
            re.DOTALL
        )
        equations.extend([e.strip() for e in env_align if e.strip()])
        
        env_multline = re.findall(
            r'\\begin\{multline\}(.*?)\\end\{multline\}',
            text,
            re.DOTALL
        )
        equations.extend([e.strip() for e in env_multline if e.strip()])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_equations = []
        for eq in equations:
            if eq not in seen:
                seen.add(eq)
                unique_equations.append(eq)
        
        return unique_equations
    
    async def extract_batch(
        self,
        papers: List[Dict[str, str]],
    ) -> List[ParsedContent]:
        """Extract content from multiple PDFs.
        
        Args:
            papers: List of dicts with paper_id and pdf_url
            
        Returns:
            List of ParsedContent
        """
        results = []
        
        for paper in papers:
            try:
                parsed = await self.extract(
                    pdf_url=paper["pdf_url"],
                    paper_id=paper["paper_id"],
                )
                results.append(parsed)
            except Exception as e:
                logger.error(
                    f"Failed to extract {paper.get('paper_id', 'unknown')}: {e}"
                )
                continue
        
        return results
    
    async def health_check(self) -> bool:
        """Check if PDF processor is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple check - can we access docling?
            return self.converter is not None
        except Exception as e:
            logger.warning(f"PDF processor health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics.
        
        Returns:
            Dict with processing stats
        """
        return {
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "cache_hit_count": self._cache_hit_count,
            "success_rate": (
                self._processed_count / (self._processed_count + self._error_count)
                if (self._processed_count + self._error_count) > 0 else 0
            ),
        }
    
    def __repr__(self) -> str:
        return (
            f"PDFProcessor("
            f"processed={self._processed_count}, "
            f"errors={self._error_count}, "
            f"cache_hits={self._cache_hit_count})"
        )

