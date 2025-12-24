"""LLM Router for intelligent provider selection and failover."""

import logging
from typing import Any, Dict, List, Optional
from enum import Enum

from .base import BaseLLMClient, LLMProvider, LLMResponse
from .anthropic_client import AnthropicClient
from .openai_client import OpenAIClient
from .ollama_client import OllamaClient


logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of LLM tasks with different requirements."""
    EXTRACTION = "extraction"
    SYNTHESIS = "synthesis"
    CATEGORIZATION = "categorization"
    QUERY_GENERATION = "query_generation"
    EMBEDDING = "embedding"


class LLMRouter:
    """Intelligent LLM router for multi-provider support."""

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434",
        ollama_enabled: bool = False,
        cost_cap_daily: Optional[float] = None,
    ):
        self.providers: Dict[LLMProvider, Optional[BaseLLMClient]] = {}
        self.cost_tracker: Dict[LLMProvider, float] = {}
        self.cost_cap = cost_cap_daily

        if anthropic_api_key:
            self.providers[LLMProvider.ANTHROPIC] = AnthropicClient(anthropic_api_key)
            self.cost_tracker[LLMProvider.ANTHROPIC] = 0.0
            logger.info("Anthropic client initialized")

        if openai_api_key:
            self.providers[LLMProvider.OPENAI] = OpenAIClient(openai_api_key)
            self.cost_tracker[LLMProvider.OPENAI] = 0.0
            logger.info("OpenAI client initialized")

        if ollama_enabled:
            self.providers[LLMProvider.OLLAMA] = OllamaClient(ollama_base_url)
            self.cost_tracker[LLMProvider.OLLAMA] = 0.0
            logger.info(f"Ollama client initialized at {ollama_base_url}")

        self.routing_map = {
            TaskType.EXTRACTION: [LLMProvider.ANTHROPIC, LLMProvider.OLLAMA],
            TaskType.SYNTHESIS: [LLMProvider.ANTHROPIC, LLMProvider.OLLAMA],
            TaskType.CATEGORIZATION: [LLMProvider.ANTHROPIC, LLMProvider.OLLAMA],
            TaskType.QUERY_GENERATION: [LLMProvider.OLLAMA, LLMProvider.ANTHROPIC],
            TaskType.EMBEDDING: [LLMProvider.OPENAI, LLMProvider.OLLAMA],
        }

        self.model_map = {
            (LLMProvider.ANTHROPIC, TaskType.EXTRACTION): "claude-sonnet-4",
            (LLMProvider.ANTHROPIC, TaskType.SYNTHESIS): "claude-sonnet-4",
            (LLMProvider.ANTHROPIC, TaskType.CATEGORIZATION): "claude-sonnet-4",
            (LLMProvider.ANTHROPIC, TaskType.QUERY_GENERATION): "claude-haiku-3-5",
            (LLMProvider.OPENAI, TaskType.EMBEDDING): "text-embedding-3-small",
            (LLMProvider.OLLAMA, TaskType.EXTRACTION): "llama3.1:70b",
            (LLMProvider.OLLAMA, TaskType.SYNTHESIS): "llama3.1:70b",
            (LLMProvider.OLLAMA, TaskType.CATEGORIZATION): "llama3.1:8b",
            (LLMProvider.OLLAMA, TaskType.QUERY_GENERATION): "llama3.1:8b",
            (LLMProvider.OLLAMA, TaskType.EMBEDDING): "nomic-embed-text",
        }

    async def complete(
        self,
        prompt: str,
        task_type: TaskType,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        force_provider: Optional[LLMProvider] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if force_provider:
            provider_order = [force_provider]
        else:
            provider_order = self.routing_map.get(task_type, [LLMProvider.ANTHROPIC])

        for provider in provider_order:
            client = self.providers.get(provider)
            if not client:
                continue

            if self.cost_cap and self.cost_tracker.get(provider, 0) >= self.cost_cap:
                logger.warning(f"{provider} cost cap reached")
                continue

            model = self.model_map.get((provider, task_type))
            if not model:
                continue

            try:
                logger.info(f"Routing {task_type} to {provider} model={model}")
                response = await client.complete(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system,
                    **kwargs
                )
                if response.cost:
                    self.cost_tracker[provider] += response.cost
                return response
            except Exception as e:
                logger.error(f"{provider} failed: {e}")
                continue

        raise RuntimeError(f"All providers failed for {task_type}")

    async def generate_embedding(
        self,
        text: str,
        force_provider: Optional[LLMProvider] = None,
        **kwargs: Any,
    ) -> List[float]:
        if force_provider:
            provider_order = [force_provider]
        else:
            provider_order = self.routing_map[TaskType.EMBEDDING]

        for provider in provider_order:
            client = self.providers.get(provider)
            if not client:
                continue
            model = self.model_map.get((provider, TaskType.EMBEDDING))
            if not model:
                continue
            try:
                return await client.generate_embedding(text=text, model=model, **kwargs)
            except Exception as e:
                logger.error(f"{provider} embedding failed: {e}")
                continue

        raise RuntimeError("All embedding providers failed")

    async def health_check_all(self) -> Dict[LLMProvider, bool]:
        health_status = {}
        for provider, client in self.providers.items():
            if client:
                try:
                    health_status[provider] = await client.health_check()
                except Exception:
                    health_status[provider] = False
            else:
                health_status[provider] = False
        return health_status

    def get_cost_summary(self) -> Dict[str, Any]:
        return {
            "by_provider": dict(self.cost_tracker),
            "total": sum(self.cost_tracker.values()),
            "cap": self.cost_cap,
            "cap_reached": self.cost_cap and sum(self.cost_tracker.values()) >= self.cost_cap,
        }

    def reset_cost_tracker(self):
        for provider in self.cost_tracker:
            self.cost_tracker[provider] = 0.0
        logger.info("Cost tracker reset")
