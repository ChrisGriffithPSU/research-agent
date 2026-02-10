"""Paper Triage Agent worker.

Uses LLM to determine if a paper should be processed further
based on its abstract. Defaults to requesting full text unless
clearly irrelevant.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.shared.llm.openai_client import OpenAIClient
from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import (
    PaperTriageRequest,
    PaperTriageDecision,
    FullTextRequest,
    NotificationRequest,
)
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore


logger = logging.getLogger(__name__)


class PaperTriageWorker(BaseWorker):
    """Worker that triages papers using LLM.

    Analyzes paper abstracts to determine if full text should be fetched.
    Defaults to REQUEST_FULL_TEXT unless clearly irrelevant.

    Example:
        llm = OpenAIClient()
        consumer = MessageConsumer(connection)
        publisher = MessagePublisher(connection)

        worker = PaperTriageWorker(llm, consumer, publisher)
        await worker.start()
    """

    # Load system prompt from file
    SYSTEM_PROMPT = (
        Path(__file__).parent.parent.parent
        / "shared"
        / "llm"
        / "prompts"
        / "paper-ingestion-triage-agent.txt"
    )

    def __init__(
        self,
        llm_client: OpenAIClient,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: Optional[LocalArtifactStore] = None,
        config: Optional[WorkerConfig] = None,
    ):
        """Initialize paper triage worker.

        Args:
            llm_client: LLM client for triage decisions
            message_consumer: Message consumer for input queue
            message_publisher: Publisher for output messages
            artifact_store: Artifact storage
            config: Worker configuration
        """
        config = config or WorkerConfig(
            queue_name="paper.triage.request",
            dlq_name="paper.triage.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.llm = llm_client
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
            # Return minimal prompt as fallback
            return (
                "You are a paper triage agent. Decide if a paper's full text "
                "should be fetched. Return JSON with 'decision' field set to "
                "either 'REQUEST_FULL_TEXT' or 'REJECT_PAPER'."
            )

    def get_message_type(self):
        """Get expected message type."""
        return PaperTriageRequest

    async def process(self, message: PaperTriageRequest) -> None:
        """Process a paper triage request.

        Args:
            message: Triage request with paper metadata
        """
        logger.info(f"Triaging paper: {message.paper_id}")

        # Prepare input for LLM
        llm_input = self._prepare_llm_input(message)

        # Get triage decision from LLM
        decision = await self._get_triage_decision(llm_input)

        # Create and publish decision message
        triage_decision = PaperTriageDecision(
            work_id=message.work_id,
            parent_work_id=message.parent_work_id,
            paper_id=message.paper_id,
            decision=decision["decision"],
            confidence=decision["confidence_0_to_1"],
            reasoning=decision.get("primary_reasoning", {}),
            cross_domain_opportunities=decision.get("cross_domain_opportunities", []),
            notes_for_concept_stage=decision.get("notes_for_concept_stage", []),
        )

        # Publish decision
        await self.publish("paper.triage.decision", triage_decision)

        # If requesting full text, also publish full text request
        if decision["decision"] == "REQUEST_FULL_TEXT":
            full_text_request = FullTextRequest(
                work_id=message.work_id,
                parent_work_id=message.work_id,
                paper_id=message.paper_id,
                pdf_url=message.pdf_url,
                triage_decision=decision,
            )
            await self.publish("paper.fulltext.request", full_text_request)
            logger.info(f"Requested full text for: {message.paper_id}")
        else:
            logger.info(f"Rejected paper: {message.paper_id}")

    def _prepare_llm_input(self, message: PaperTriageRequest) -> str:
        """Prepare LLM input from message.

        Args:
            message: Paper triage request

        Returns:
            JSON string for LLM
        """
        input_data = {
            "paper_id": message.paper_id,
            "title": message.title,
            "authors": message.authors,
            "abstract": message.abstract,
            "source": "arxiv",
            "domain_hint": ", ".join(message.categories[:3]),
        }

        return json.dumps(input_data, indent=2)

    async def _get_triage_decision(self, llm_input: str) -> Dict[str, Any]:
        """Get triage decision from LLM.

        Args:
            llm_input: JSON input for LLM

        Returns:
            Parsed decision dict
        """
        try:
            response = await self.llm.complete(
                prompt=llm_input,
                system=self._system_prompt,
                temperature=0.3,  # Low temperature for consistent decisions
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            # Parse JSON response
            decision = json.loads(response.content)

            # Validate required fields
            if "decision" not in decision:
                raise ValueError("Missing 'decision' field in LLM response")

            if "confidence_0_to_1" not in decision:
                decision["confidence_0_to_1"] = 0.5

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Default to requesting full text on parse error
            return {
                "decision": "REQUEST_FULL_TEXT",
                "confidence_0_to_1": 0.5,
                "primary_reasoning": {
                    "system_modeled": "Parse error - defaulting to inclusion",
                    "dynamical_properties_detected": [],
                    "stochastic_elements_detected": [],
                    "event_driven_or_temporal_elements": [],
                    "latent_or_hidden_state_elements": [],
                },
                "cross_domain_opportunities": [],
                "rejection_justification": None,
                "notes_for_concept_stage": ["Parse error occurred - manual review recommended"],
            }

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Default to requesting full text on error
            return {
                "decision": "REQUEST_FULL_TEXT",
                "confidence_0_to_1": 0.5,
                "primary_reasoning": {
                    "system_modeled": "Error - defaulting to inclusion",
                    "dynamical_properties_detected": [],
                    "stochastic_elements_detected": [],
                    "event_driven_or_temporal_elements": [],
                    "latent_or_hidden_state_elements": [],
                },
                "cross_domain_opportunities": [],
                "rejection_justification": None,
                "notes_for_concept_stage": [f"Error occurred: {str(e)}"],
            }

    async def health_check(self) -> bool:
        """Check worker health."""
        return await self.llm.health_check()
