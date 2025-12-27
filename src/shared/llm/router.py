"""Refactored LLM router with dependency injection.

Provides a clean interface for LLM operations with injectable provider dependencies.
"""
import logging
from typing import Any, Dict, List, Optional

from src.shared.interfaces import (
    ILLMClient,
    LLMResponse,
)
from enum import Enum


logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of LLM tasks with different routing requirements.
    
    Each task type has different quality and cost requirements,
    which affects how requests are routed to providers.
    """
    EXTRACTION = "extraction"
    SYNTHESIS = "synthesis"
    CATEGORIZATION = "categorization"
    QUERY_GENERATION = "query_generation"
    EMBEDDING = "embedding"


class LLMRouter:
    """LLM router with injectable provider dependencies.
    
    Routes LLM requests to appropriate providers based on task type.
    Handles failover and load balancing.
    
    All dependencies are injected through the constructor.
    No internal creation of external clients.
    
    Example:
        # Production use with real providers
        router = LLMRouter(
            providers={
                "anthropic": AnthropicClient(api_key="..."),
                "ollama": OllamaClient(base_url="http://localhost:11434"),
                "openai": OpenAIClient(api_key="..."),
            },
            routing_map={
                TaskType.EXTRACTION: ["anthropic", "ollama"],
                TaskType.SYNTHESIS: ["anthropic", "ollama"],
                TaskType.CATEGORIZATION: ["anthropic", "ollama"],
                TaskType.QUERY_GENERATION: ["ollama", "anthropic"],
                TaskType.EMBEDDING: ["openai", "ollama"],
            },
        )
        
        # Testing use with mocks
        from src.shared.testing.mocks import MockLLMClient, MockLLMRouter
        router = MockLLMRouter()
        
        # Use router
        response = await router.complete(
            prompt="Extract the main points from this text...",
            task_type=TaskType.EXTRACTION,
            temperature=0.3,
        )
    
    Attributes:
        _providers: Dict of provider name -> ILLMClient
        _cost_tracker: Dict of provider name -> total cost
        _cost_cap: Optional daily cost cap
        _routing_map: TaskType -> list of provider names (priority order)
        _model_map: (provider, task_type) -> model name
    """
    
    def __init__(
        self,
        providers: Optional[Dict[str, ILLMClient]] = None,
        routing_map: Optional[Dict[TaskType, List[str]]] = None,
        model_map: Optional[Dict[tuple, str]] = None,
        cost_cap: Optional[float] = None,
    ):
        """Initialize LLM router.
        
        Args:
            providers: Dict of provider_name -> ILLMClient implementation
            routing_map: TaskType -> list of provider names (priority order)
            model_map: (provider, task_type) -> model name
            cost_cap: Optional daily cost cap per provider
        """
        self._providers = providers or {}
        self._cost_tracker: Dict[str, float] = {p: 0.0 for p in self._providers}
        self._cost_cap = cost_cap
        
        # Default routing map (can be overridden)
        self._routing_map = routing_map or {
            TaskType.EXTRACTION: ["anthropic", "ollama"],
            TaskType.SYNTHESIS: ["anthropic", "ollama"],
            TaskType.CATEGORIZATION: ["anthropic", "ollama"],
            TaskType.QUERY_GENERATION: ["ollama", "anthropic"],
            TaskType.EMBEDDING: ["openai", "ollama"],
        }
        
        # Default model map (can be overridden)
        self._model_map = model_map or {
            ("anthropic", TaskType.EXTRACTION): "claude-sonnet-4",
            ("anthropic", TaskType.SYNTHESIS): "claude-sonnet-4",
            ("anthropic", TaskType.CATEGORIZATION): "claude-sonnet-4",
            ("anthropic", TaskType.QUERY_GENERATION): "claude-haiku-3-5",
            ("openai", TaskType.EMBEDDING): "text-embedding-3-small",
            ("ollama", TaskType.EXTRACTION): "llama3.1:70b",
            ("ollama", TaskType.SYNTHESIS): "llama3.1:70b",
            ("ollama", TaskType.CATEGORIZATION): "llama3.1:8b",
            ("ollama", TaskType.QUERY_GENERATION): "llama3.1:8b",
            ("ollama", TaskType.EMBEDDING): "nomic-embed-text",
        }
    
    def add_provider(self, name: str, client: ILLMClient) -> None:
        """Add a provider after initialization.
        
        Args:
            name: Provider name
            client: ILLMClient implementation
        """
        self._providers[name] = client
        self._cost_tracker[name] = 0.0
    
    def remove_provider(self, name: str) -> Optional[ILLMClient]:
        """Remove a provider.
        
        Args:
            name: Provider name to remove
            
        Returns:
            The removed client or None if not found
        """
        client = self._providers.pop(name, None)
        if name in self._cost_tracker:
            del self._cost_tracker[name]
        return client
    
    def get_provider(self, name: str) -> Optional[ILLMClient]:
        """Get a provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            ILLMClient or None if not found
        """
        return self._providers.get(name)
    
    async def complete(
        self,
        prompt: str,
        task_type: TaskType,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """Complete a prompt using appropriate provider.
        
        Routes the request based on task type and available providers.
        Handles failover between providers.
        
        Args:
            prompt: User prompt
            task_type: Type of task (determines routing)
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            system: System prompt
            force_provider: Override routing with specific provider
            **kwargs: Additional provider-specific args
            
        Returns:
            LLMResponse with generated content
            
        Raises:
            RuntimeError: If all providers fail
        """
        if force_provider:
            provider_order = [force_provider]
        else:
            provider_order = self._routing_map.get(task_type, ["anthropic"])
        
        last_error = None
        
        for provider_name in provider_order:
            provider = self._providers.get(provider_name)
            if not provider:
                logger.debug(f"Provider {provider_name} not available")
                continue
            
            # Check cost cap
            if self._cost_cap and self._cost_tracker.get(provider_name, 0) >= self._cost_cap:
                logger.warning(f"{provider_name} cost cap reached")
                continue
            
            model = self._model_map.get((provider_name, task_type))
            if not model:
                logger.debug(f"No model configured for {provider_name}/{task_type}")
                continue
            
            try:
                logger.info(f"Routing {task_type} to {provider_name} model={model}")
                response = await provider.complete(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system,
                    **kwargs,
                )
                
                if response.cost:
                    self._cost_tracker[provider_name] += response.cost
                
                return response
                
            except Exception as e:
                logger.error(f"{provider_name} failed: {e}")
                last_error = e
                continue
        
        if last_error:
            raise RuntimeError(f"All providers failed for {task_type}") from last_error
        raise RuntimeError(f"No providers available for {task_type}")
    
    async def generate_embedding(
        self,
        text: str,
        force_provider: Optional[str] = None,
        **kwargs,
    ) -> List[float]:
        """Generate embedding for text.
        
        Routes to appropriate embedding provider.
        
        Args:
            text: Text to embed
            force_provider: Override routing
            **kwargs: Additional args
            
        Returns:
            List of embedding values
            
        Raises:
            RuntimeError: If all providers fail
        """
        provider_order = [force_provider] if force_provider \
            else self._routing_map.get(TaskType.EMBEDDING, ["openai"])
        
        last_error = None
        
        for provider_name in provider_order:
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            
            model = self._model_map.get((provider_name, TaskType.EMBEDDING))
            if not model:
                continue
            
            try:
                return await provider.generate_embedding(text=text, model=model, **kwargs)
            except Exception as e:
                logger.error(f"{provider_name} embedding failed: {e}")
                last_error = e
                continue
        
        if last_error:
            raise RuntimeError("All embedding providers failed") from last_error
        raise RuntimeError("No embedding providers available")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers.
        
        Returns:
            Dict mapping provider name to health status
        """
        health = {}
        for name, provider in self._providers.items():
            try:
                health[name] = await provider.health_check()
            except Exception:
                health[name] = False
        return health
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary.
        
        Returns:
            Dict with cost information by provider
        """
        return {
            "by_provider": dict(self._cost_tracker),
            "total": sum(self._cost_tracker.values()),
            "cap": self._cost_cap,
            "cap_reached": (
                self._cost_cap and
                sum(self._cost_tracker.values()) >= self._cost_cap
            ),
        }
    
    def reset_cost_tracker(self) -> None:
        """Reset cost tracking.
        
        Sets all provider costs to zero.
        """
        for provider in self._cost_tracker:
            self._cost_tracker[provider] = 0.0
        logger.info("Cost tracker reset")
    
    def get_routing_map(self) -> Dict[TaskType, List[str]]:
        """Get the current routing map.
        
        Returns:
            Copy of the routing map
        """
        return dict(self._routing_map)
    
    def set_routing_map(self, routing_map: Dict[TaskType, List[str]]) -> None:
        """Set a new routing map.
        
        Args:
            routing_map: New routing configuration
        """
        self._routing_map = routing_map
    
    @property
    def providers(self) -> Dict[str, ILLMClient]:
        """Get all providers."""
        return self._providers
    
    @property
    def available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self._providers.keys())


class LLMRouterFactory:
    """Factory for creating LLMRouter instances.
    
    Provides convenient methods for creating routers with common configurations.
    """
    
    @staticmethod
    def create_with_providers(
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434",
        ollama_enabled: bool = False,
        cost_cap: Optional[float] = None,
    ) -> LLMRouter:
        """Create LLMRouter with real provider clients.
        
        Args:
            anthropic_api_key: Anthropic API key
            openai_api_key: OpenAI API key
            ollama_base_url: Ollama base URL
            ollama_enabled: Whether to enable Ollama
            cost_cap: Optional daily cost cap
            
        Returns:
            Configured LLMRouter with real clients
        """
        from src.shared.llm.anthropic_client import AnthropicClient
        from src.shared.llm.openai_client import OpenAIClient
        from src.shared.llm.ollama_client import OllamaClient
        
        providers: Dict[str, ILLMClient] = {}
        
        if anthropic_api_key:
            try:
                providers["anthropic"] = AnthropicClient(anthropic_api_key)
            except ImportError as e:
                logger.warning(f"Anthropic client unavailable: {e}")
        
        if openai_api_key:
            try:
                providers["openai"] = OpenAIClient(openai_api_key)
            except ImportError as e:
                logger.warning(f"OpenAI client unavailable: {e}")
        
        if ollama_enabled:
            try:
                providers["ollama"] = OllamaClient(ollama_base_url)
            except Exception as e:
                logger.warning(f"Ollama client unavailable: {e}")
        
        return LLMRouter(
            providers=providers,
            cost_cap=cost_cap,
        )
    
    @staticmethod
    def create_mock(
        responses: Optional[Dict[tuple, str]] = None,
    ) -> 'MockLLMRouter':
        """Create LLMRouter with mock clients for testing.
        
        Args:
            responses: Predefined responses for testing
            
        Returns:
            LLMRouter with MockLLMClient instances
        """
        from src.shared.testing.mocks import MockLLMRouter
        
        return MockLLMRouter(
            providers={
                "anthropic": MockLLMClient(name="anthropic", responses=responses),
                "openai": MockLLMClient(name="openai", responses=responses),
                "ollama": MockLLMClient(name="ollama", responses=responses),
            }
        )
    
    @staticmethod
    def create_empty() -> LLMRouter:
        """Create empty LLMRouter (no providers).
        
        Useful when you want to add providers manually.
        
        Returns:
            Empty LLMRouter
        """
        return LLMRouter(providers={})


# Remove the old global singleton and get_publisher function
# The new pattern uses explicit dependency injection


__all__ = [
    "LLMRouter",
    "LLMRouterFactory",
    "TaskType",
]
