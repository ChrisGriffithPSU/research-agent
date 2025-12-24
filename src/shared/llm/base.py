"""Base LLM client interface for multi-provider support."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class LLMResponse:
    """Standardized LLM response format."""
    
    def __init__(
        self,
        content: str,
        model: str,
        provider: LLMProvider,
        usage: Optional[Dict[str, int]] = None,
        cost: Optional[float] = None,
        latency: Optional[float] = None,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.cost = cost
        self.latency = latency

    def __repr__(self) -> str:
        return f"LLMResponse(provider={self.provider}, model={self.model}, content_length={len(self.content)})"


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The user prompt/message
            model: Model identifier
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            system: System prompt/instructions
            **kwargs: Provider-specific arguments

        Returns:
            LLMResponse object with standardized response
        """
        pass

    @abstractmethod
    async def generate_embedding(
        self,
        text: str,
        model: str,
        **kwargs: Any,
    ) -> List[float]:
        """
        Generate embeddings for the given text.

        Args:
            text: Input text to embed
            model: Embedding model identifier
            **kwargs: Provider-specific arguments

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the LLM provider is available and healthy.

        Returns:
            True if healthy, False otherwise
        """
        pass

    @abstractmethod
    def get_available_models(self) -> List[str]:
        """
        Get list of available models from this provider.

        Returns:
            List of model identifiers
        """
        pass
