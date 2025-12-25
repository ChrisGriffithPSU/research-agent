"""Ollama LLM client implementation."""

import time
from typing import Any, Dict, List, Optional
import ollama
from ollama import AsyncClient

from .base import BaseLLMClient, LLMProvider, LLMResponse


class OllamaClient(BaseLLMClient):
    """Ollama client for local/self-hosted LLMs."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 120):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL (localhost:11434 if SSH tunneled)
            timeout: Request timeout in seconds (Ollama can be slow)
        """
        super().__init__(LLMProvider.OLLAMA)
        self.base_url = base_url
        self.timeout = timeout
        self.client = AsyncClient(host=base_url, timeout=timeout)

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using Ollama."""
        start_time = time.time()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        options = {
            "temperature": temperature,
        }
        if max_tokens:
            options["num_predict"] = max_tokens

        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
                options=options,
                **kwargs
            )

            latency = time.time() - start_time
            content = response["message"]["content"]

            # Ollama usage tracking (tokens)
            usage = {
                "prompt_tokens": response.get("prompt_eval_count", 0),
                "completion_tokens": response.get("eval_count", 0),
                "total_tokens": response.get("prompt_eval_count", 0) + response.get("eval_count", 0),
            }

            # Ollama is free/self-hosted, so cost is 0
            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider,
                usage=usage,
                cost=0.0,
                latency=latency,
            )

        except Exception as e:
            raise RuntimeError(f"Ollama completion failed: {str(e)}")

    async def generate_embedding(
        self,
        text: str,
        model: str = "nomic-embed-text",
        **kwargs: Any,
    ) -> List[float]:
        """Generate embeddings using Ollama."""
        try:
            response = await self.client.embeddings(
                model=model,
                prompt=text,
                **kwargs
            )
            return response["embedding"]

        except Exception as e:
            raise RuntimeError(f"Ollama embedding generation failed: {str(e)}")

    async def health_check(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            # List available models as a health check
            response = await self.client.list()
            return True
        except Exception:
            return False

    async def get_available_models(self) -> List[str]:
        """Get list of models available on Ollama server (async)."""
        import asyncio
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Use async client instead of sync
            response = await self.client.list()
            return [model["name"] for model in response.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    async def pull_model(self, model: str) -> bool:
        """
        Pull a model from Ollama registry if not already available.

        Args:
            model: Model name to pull (e.g., "llama3.1:70b")

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.client.pull(model)
            return True
        except Exception:
            return False
