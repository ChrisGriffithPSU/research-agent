"""Query processor using LLM for fuzzy matching expansion.

Integrates with existing LLMRouter from src/shared/llm/router.py
Uses TaskType.QUERY_GENERATION for routing to appropriate model.
"""
import json
import re
import logging
from typing import List, Optional, Dict, Any

from src.shared.llm.router import LLMRouter, TaskType, LLMProvider
from src.shared.llm.base import LLMResponse

from src.services.fetchers.arxiv.config import ArxivFetcherConfig
from src.services.fetchers.arxiv.schemas.paper import QueryExpansion
from src.services.fetchers.arxiv.services.cache_manager import CacheManager
from src.services.fetchers.arxiv.exceptions import LLMError, QueryProcessingError


logger = logging.getLogger(__name__)


class QueryProcessor:
    """Query processor using LLM for fuzzy matching expansion.
    
    Integrates with existing LLMRouter from src/shared/llm/router.py
    Uses TaskType.QUERY_GENERATION for routing to appropriate model.
    
    Attributes:
        llm_router: LLMRouter instance for LLM calls
        cache_manager: CacheManager for caching expansions
        config: ArXiv fetcher configuration
        max_expansions: Maximum number of query variations
        temperature: LLM temperature for query generation
    """
    
    # Prompt template for query expansion
    QUERY_EXPANSION_PROMPT = """You are a research query assistant helping search arXiv for 
academic papers about quantitative finance and machine learning.

Generate {max_expansions} unique search query variations for the following research topic:
"{original_query}"

Requirements:
1. Include synonyms and related technical terms
2. Include common abbreviations (e.g., "NN" for "neural network")
3. Include related concepts and methodologies
4. Use arXiv search-friendly syntax (all: for full text search)
5. Each query should maximize recall while staying relevant

Output format (JSON array only, no other text):
["query 1", "query 2", "query 3"]

Example for "transformer time series":
["all:transformer time series", "all:attention mechanism forecasting", "all:temporal transformer prediction"]

Now generate {max_expansions} queries for: "{query}"
"""
    
    def __init__(
        self,
        llm_router: Optional[LLMRouter] = None,
        cache_manager: Optional[CacheManager] = None,
        config: Optional[ArxivFetcherConfig] = None,
    ):
        """Initialize query processor.
        
        Args:
            llm_router: LLMRouter instance (creates default if not provided)
            cache_manager: CacheManager for caching expansions
            config: ArXiv fetcher configuration
        """
        self.llm_router = llm_router
        self.cache_manager = cache_manager
        self.config = config or ArxivFetcherConfig()
        self.max_expansions = self.config.max_query_expansions
        self.temperature = self.config.llm_temperature
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the query processor.
        
        Creates default LLMRouter if not provided.
        """
        if self._initialized:
            return
            
        if self.llm_router is None:
            self.llm_router = LLMRouter(
                ollama_enabled=True,  # Prefer local Ollama
            )
            logger.info("Created default LLMRouter for query processing")
        
        self._initialized = True
        logger.info("QueryProcessor initialized")
    
    async def expand_query(self, raw_query: str) -> QueryExpansion:
        """Expand raw query into multiple search queries using LLM.
        
        Args:
            raw_query: Original query from orchestration
            
        Returns:
            QueryExpansion with expanded queries
            
        Raises:
            QueryProcessingError: If query expansion fails
        """
        if not self._initialized:
            await self.initialize()
        
        # Check cache first
        if self.cache_manager:
            cached = await self.cache_manager.get_query_expansion(raw_query)
            if cached:
                logger.info(f"Query expansion cache hit: {raw_query[:50]}...")
                return QueryExpansion(
                    original_query=raw_query,
                    expanded_queries=cached,
                    cache_hit=True,
                )
        
        # Generate expansions using LLM
        prompt = self.QUERY_EXPANSION_PROMPT.format(
            query=raw_query,
            max_expansions=self.max_expansions,
        )
        
        try:
            response = await self.llm_router.complete(
                prompt=prompt,
                task_type=TaskType.QUERY_GENERATION,
                temperature=self.temperature,
                max_tokens=512,
                force_provider=LLMProvider.OLLAMA,  # Prefer local
            )
            
            # Parse JSON response
            expansions = self._parse_expansions(response.content)
            
            if not expansions:
                logger.warning(
                    f"LLM returned empty expansions for: {raw_query[:50]}..."
                )
                expansions = self._fallback_expansions(raw_query)
            
            # Cache the result
            if self.cache_manager:
                await self.cache_manager.set_query_expansion(raw_query, expansions)
            
            logger.info(
                f"Generated {len(expansions)} query variations for: "
                f"{raw_query[:50]}..."
            )
            
            return QueryExpansion(
                original_query=raw_query,
                expanded_queries=expansions,
                cache_hit=False,
            )
            
        except LLMError:
            # Re-raise LLM errors
            raise
        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            
            # Try fallback before failing completely
            expansions = self._fallback_expansions(raw_query)
            if expansions:
                logger.info(f"Using fallback expansions for: {raw_query[:50]}...")
                return QueryExpansion(
                    original_query=raw_query,
                    expanded_queries=expansions,
                    cache_hit=False,
                )
            
            raise QueryProcessingError(
                message=f"Failed to expand query: {e}",
                query=raw_query,
                stage="expansion",
                original=e,
            )
    
    def _parse_expansions(self, response: str) -> List[str]:
        """Parse JSON array from LLM response.
        
        Args:
            response: LLM response text
            
        Returns:
            List of query strings
        """
        try:
            # Clean up response (remove markdown code blocks if present)
            response = response.strip()
            response = re.sub(r'^```json\s*', '', response)
            response = re.sub(r'\s*```$', '', response)
            response = response.strip()
            
            # Parse JSON
            expansions = json.loads(response)
            
            # Validate
            if isinstance(expansions, list) and len(expansions) > 0:
                # Filter and clean queries
                cleaned = []
                for q in expansions:
                    q = q.strip()
                    if q and len(q) > 3:  # Skip very short queries
                        cleaned.append(q)
                
                return cleaned[:self.max_expansions]
            
            return []
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse query expansions: {e}")
            logger.debug(f"Response was: {response[:200]}...")
            return []
    
    def _fallback_expansions(self, query: str) -> List[str]:
        """Generate simple expansions without LLM.
        
        Args:
            query: Original query
            
        Returns:
            List of expanded queries
        """
        # Simple keyword-based expansion
        keywords = query.lower().split()
        
        # Build variations
        variations = [
            f"all:{query}",  # Full query
            f"all:{' '.join(keywords)}",  # Just keywords
        ]
        
        # Add common transformations
        query_clean = re.sub(r'[^\w\s]', ' ', query)
        if query_clean.strip() != query:
            variations.append(f"all:{query_clean.strip()}")
        
        # Add query with specific field prefixes
        variations.append(f"all:{query}")
        variations.append(f-title:{query}")
        variations.append(f-abs:{query}")
        
        # Filter valid queries
        cleaned = []
        for q in variations:
            q = q.strip()
            if q and len(q) > 3:
                cleaned.append(q)
        
        return list(set(cleaned))[:self.max_expansions]
    
    async def expand_batch(
        self,
        queries: List[str],
    ) -> Dict[str, QueryExpansion]:
        """Expand multiple queries.
        
        Args:
            queries: List of queries to expand
            
        Returns:
            Dict mapping original query to QueryExpansion
        """
        results = {}
        
        for query in queries:
            try:
                expansion = await self.expand_query(query)
                results[query] = expansion
            except QueryProcessingError as e:
                logger.error(f"Failed to expand query '{query}': {e}")
                # Still include the original query as a fallback
                results[query] = QueryExpansion(
                    original_query=query,
                    expanded_queries=[query],  # Use original as fallback
                )
        
        return results
    
    async def health_check(self) -> bool:
        """Check if query processor is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._initialized:
            return False
            
        if self.llm_router is None:
            return False
        
        try:
            health = await self.llm_router.health_check_all()
            # Check if at least one provider is healthy
            return any(health.values())
        except Exception as e:
            logger.warning(f"Query processor health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get query processor statistics.
        
        Returns:
            Dict with stats
        """
        return {
            "initialized": self._initialized,
            "max_expansions": self.max_expansions,
            "temperature": self.temperature,
            "llm_provider": self.config.llm_provider,
            "llm_model": self.config.llm_model,
        }
    
    def __repr__(self) -> str:
        return (
            f"QueryProcessor("
            f"initialized={self._initialized}, "
            f"max_expansions={self.max_expansions}, "
            f"provider={self.config.llm_provider})"
        )

