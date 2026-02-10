"""Concept Generator Agent worker.

Uses LLM to extract concept objects from full paper text.
Produces structured concept objects following the spec schema.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.shared.llm.openai_client import OpenAIClient
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    ConceptGenerationRequest,
    ConceptsGenerated,
    ConceptObject,
    NotificationRequest,
)
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore


logger = logging.getLogger(__name__)


class ConceptGeneratorWorker(BaseWorker):
    """Worker that generates concept objects from papers.

    Analyzes full paper text to extract domain-agnostic concept objects
    that capture deep, generalizable structures.

    Example:
        llm = OpenAIClient()
        consumer = MessageConsumer(connection)
        publisher = MessagePublisher(connection)

        worker = ConceptGeneratorWorker(llm, consumer, publisher)
        await worker.start()
    """

    # Load system prompt from file
    SYSTEM_PROMPT = (
        Path(__file__).parent.parent.parent
        / "shared"
        / "llm"
        / "prompts"
        / "concept-object-generator.txt"
    )

    def __init__(
        self,
        llm_client: OpenAIClient,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: Optional[LocalArtifactStore] = None,
        config: Optional[WorkerConfig] = None,
        max_concepts: int = 5,
    ):
        """Initialize concept generator worker.

        Args:
            llm_client: LLM client for concept generation
            message_consumer: Message consumer for input queue
            message_publisher: Publisher for output messages
            artifact_store: Artifact storage
            config: Worker configuration
            max_concepts: Maximum concepts to generate per paper
        """
        config = config or WorkerConfig(
            queue_name="paper.concepts.request",
            dlq_name="paper.concepts.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.llm = llm_client
        self.max_concepts = max_concepts
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load system prompt from file.

        Returns:
            System prompt text
        """
        try:
            return self.SYSTEM_PROMPT.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return (
                "You are a concept generator. Extract deep, domain-agnostic "
                "concept objects from research papers. Return valid JSON with "
                "concept_objects array."
            )

    def get_message_type(self):
        """Get expected message type."""
        return ConceptGenerationRequest

    async def process(self, message: ConceptGenerationRequest) -> None:
        """Process a concept generation request.

        Args:
            message: Request with paper text and metadata
        """
        logger.info(f"Generating concepts for paper: {message.paper_id}")

        # Prepare input for LLM
        llm_input = self._prepare_llm_input(message)

        # Get concepts from LLM
        concepts_data = await self._generate_concepts(llm_input)

        # Parse concept objects
        concept_objects = self._parse_concepts(concepts_data, message.paper_id)

        # Store concepts.json artifact
        concepts_json = json.dumps(concepts_data, indent=2)
        artifact_key = f"{message.paper_id}/concepts/concepts.json"
        artifact_path = await self.store_artifact(
            key=artifact_key,
            data=concepts_json.encode("utf-8"),
            content_type="application/json",
        )

        # Create and publish result
        result = ConceptsGenerated(
            work_id=message.work_id,
            parent_work_id=message.parent_work_id,
            paper_id=message.paper_id,
            concept_objects=concept_objects,
            concepts_json_path=artifact_path,
            artifact_refs=[artifact_path],
            meta={
                "requested_count": self.max_concepts,
                "produced_count": len(concept_objects),
                "title": message.title,
            },
        )

        await self.publish("concepts.generated", result)

        logger.info(f"Generated {len(concept_objects)} concepts for: {message.paper_id}")

    def _prepare_llm_input(self, message: ConceptGenerationRequest) -> str:
        """Prepare LLM input from message.

        Args:
            message: Concept generation request

        Returns:
            JSON string for LLM
        """
        # Truncate full text if too long (leave room for prompt)
        max_text_length = 15000
        full_text = message.full_text
        if len(full_text) > max_text_length:
            logger.warning(
                f"Truncating paper {message.paper_id} from "
                f"{len(full_text)} to {max_text_length} chars"
            )
            full_text = full_text[:max_text_length] + "\n\n[...truncated]"

        input_data = {
            "paper_id": message.paper_id,
            "source": "arxiv",
            "title": message.title,
            "authors": message.authors,
            "abstract": message.abstract,
            "full_text": full_text,
            "sections": message.sections,
            "requested_concept_count": self.max_concepts,
            "domain_hints": message.categories,
            "constraints": {
                "max_concepts": self.max_concepts,
                "prefer_math_structures": True,
                "ban_feature_language": True,
            },
        }

        return json.dumps(input_data, indent=2)

    async def _generate_concepts(self, llm_input: str) -> Dict[str, Any]:
        """Generate concepts using LLM.

        Args:
            llm_input: JSON input for LLM

        Returns:
            Parsed concepts dict
        """
        try:
            response = await self.llm.complete(
                prompt=llm_input,
                system=self._system_prompt,
                temperature=0.4,  # Slightly higher for creativity
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            # Parse JSON response
            result = json.loads(response.content)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Return minimal valid structure
            return {
                "paper_id": "unknown",
                "concept_objects": [],
                "meta": {
                    "error": f"Parse error: {str(e)}",
                },
            }

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_concepts(
        self,
        concepts_data: Dict[str, Any],
        paper_id: str,
    ) -> List[ConceptObject]:
        """Parse concept objects from LLM response.

        Args:
            concepts_data: Raw concepts data from LLM
            paper_id: Paper ID for context

        Returns:
            List of validated ConceptObject instances
        """
        concepts = []

        raw_concepts = concepts_data.get("concept_objects", [])
        if not raw_concepts:
            logger.warning(f"No concepts generated for paper: {paper_id}")
            return concepts

        for i, raw_concept in enumerate(raw_concepts):
            try:
                # Ensure required fields exist
                if "concept_id" not in raw_concept:
                    raw_concept["concept_id"] = f"{paper_id}_concept_{i}"

                if "concept_name" not in raw_concept:
                    raw_concept["concept_name"] = f"Concept {i + 1}"

                concept = ConceptObject(**raw_concept)
                concepts.append(concept)

            except Exception as e:
                logger.warning(f"Failed to parse concept {i} for {paper_id}: {e}")
                continue

        return concepts

    async def health_check(self) -> bool:
        """Check worker health."""
        return await self.llm.health_check()
