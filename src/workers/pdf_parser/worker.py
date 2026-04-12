"""PDF Parser worker.

Fetches and parses PDF files from ArXiv.
Extracts text, tables, equations, and figure captions.
Non-LLM worker - uses docling for parsing.
"""

import logging

from src.services.fetchers.arxiv.schemas.paper import ParsedContent
from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    ConceptGenerationRequest,
    PaperFullTextRequest,
)

logger = logging.getLogger(__name__)


class PDFParserWorker(BaseWorker):
    """Worker that fetches and parses PDF files.

    Extracts structured content from PDFs including text,
    tables, equations, and figure captions.

    Example:
        consumer = MessageConsumer(connection)
        publisher = MessagePublisher(connection)

        worker = PDFParserWorker(consumer, publisher)
        await worker.start()
    """

    def __init__(
        self,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: LocalArtifactStore | None = None,
        config: WorkerConfig | None = None,
        pdf_processor: PDFProcessor | None = None,
    ):
        """Initialize PDF parser worker.

        Args:
            message_consumer: Message consumer for input queue
            message_publisher: Publisher for output messages
            artifact_store: Artifact storage
            config: Worker configuration
            pdf_processor: PDF processor instance
        """
        config = config or WorkerConfig(
            queue_name="paper.fulltext.request",
            dlq_name="paper.fulltext.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.pdf_processor = pdf_processor or PDFProcessor()

    def get_message_type(self):
        """Get expected message type."""
        return PaperFullTextRequest

    async def process(self, message: PaperFullTextRequest) -> None:
        """Process a full text request.

        Args:
            message: Request with paper metadata and PDF URL
        """
        logger.info(f"Parsing PDF for paper: {message.paper_id}")

        # Parse PDF
        parsed = await self._parse_pdf(message.pdf_url, message.paper_id)

        # Store parsed content artifact
        await self._store_parsed_content(parsed, message.paper_id)

        # Build and publish concept generation request
        concept_request = ConceptGenerationRequest(
            work_id=message.work_id,
            parent_work_id=message.work_id,
            paper_id=message.paper_id,
            title=message.title,
            abstract=message.abstract,
            authors=message.authors,
            full_text=parsed.text_content,
            sections=self._extract_sections(parsed),
            categories=message.categories,
            artifact_refs=[
                f"{message.paper_id}/parsed/full_text.txt",
            ],
        )

        await self.publish("paper.concepts.request", concept_request)

        logger.info(f"Parsed and published: {message.paper_id}")

    async def _parse_pdf(self, pdf_url: str, paper_id: str) -> ParsedContent:
        """Parse PDF from URL.

        Args:
            pdf_url: Direct PDF URL
            paper_id: Paper identifier

        Returns:
            Parsed content
        """
        try:
            return await self.pdf_processor.extract(pdf_url, paper_id)
        except Exception as e:
            logger.error(f"Failed to parse PDF {pdf_url}: {e}")
            raise

    async def _store_parsed_content(
        self,
        parsed: ParsedContent,
        paper_id: str,
    ) -> None:
        """Store parsed content artifacts.

        Args:
            parsed: Parsed content
            paper_id: Paper identifier
        """
        # Store full text
        full_text_key = f"{paper_id}/parsed/full_text.txt"
        await self.store_artifact(
            key=full_text_key,
            data=parsed.text_content.encode("utf-8"),
            content_type="text/plain",
        )

        # Store tables if any
        if parsed.tables:
            import json

            tables_key = f"{paper_id}/parsed/tables.json"
            await self.store_artifact(
                key=tables_key,
                data=json.dumps(parsed.tables, indent=2).encode("utf-8"),
                content_type="application/json",
            )

        # Store equations if any
        if parsed.equations:
            equations_key = f"{paper_id}/parsed/equations.txt"
            equations_text = "\n\n".join(parsed.equations)
            await self.store_artifact(
                key=equations_key,
                data=equations_text.encode("utf-8"),
                content_type="text/plain",
            )

    def _extract_sections(self, parsed: ParsedContent) -> list:
        """Extract sections from parsed content.

        Args:
            parsed: Parsed content

        Returns:
            List of section dicts
        """
        import re

        sections = []
        text = parsed.text_content

        # Common section patterns
        section_pattern = (
            r"(?:\n|^)(Abstract|Introduction|Background|Related Work|Methods?|"
            r"Methodology|Experiments?|Results?|Discussion|Conclusion|References)\s*\n"
        )

        matches = list(re.finditer(section_pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            section_name = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            section_text = text[start:end].strip()
            if section_text:
                sections.append(
                    {
                        "heading": section_name,
                        "text": section_text[:5000],
                    }
                )

        # If no sections found, treat whole text as one section
        if not sections and text:
            sections.append(
                {
                    "heading": "Full Text",
                    "text": text[:10000],
                }
            )

        return sections

    async def health_check(self) -> bool:
        """Check worker health."""
        return await self.pdf_processor.health_check()
