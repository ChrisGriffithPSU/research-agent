#!/usr/bin/env python3
"""
Test suite demonstrating dependency injection for arXiv fetcher.

This file shows how to test the arXiv fetcher components in isolation
using the new dependency injection patterns.

Run with: python test_dependency_injection.py
"""
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# ==================== Test Fixtures ====================

class TestConfig:
    """Test configuration."""
    
    TEST_QUERIES = [
        "transformer time series forecasting",
        "attention mechanism neural network",
    ]
    
    TEST_CATEGORIES = ["cs.LG", "stat.ML"]
    
    TEST_PAPER_ID = "2401.12345"


class MockCacheBackend:
    """In-memory cache for testing."""
    
    def __init__(self):
        self._storage: Dict[str, bytes] = {}
    
    async def initialize(self):
        pass
    
    async def get(self, key: str) -> bytes:
        return self._storage.get(key)
    
    async def set(self, key: str, value: bytes, ttl_seconds: int = None):
        self._storage[key] = value
    
    async def delete(self, key: str):
        self._storage.pop(key, None)
    
    async def exists(self, key: str) -> bool:
        return key in self._storage
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        return {k: v for k, v in self._storage.items() if k in keys}
    
    async def delete_pattern(self, pattern: str):
        # Simple implementation
        pass
    
    async def close(self):
        self._storage.clear()


class MockLLMRouter:
    """Mock LLM router for testing."""
    
    def __init__(self, responses: Dict[str, List[str]] = None):
        self._responses = responses or {
            "transformer": '["all:transformer", "all:attention mechanism"]',
            "attention": '["all:attention", "all:transformer"]',
            "default": '["all:test"]',
        }
        self._call_count = 0
    
    async def complete(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.7,
        **kwargs,
    ) -> 'MockLLMResponse':
        self._call_count += 1
        
        # Return mock response based on prompt content
        content = self._responses.get("default")
        if "transformer" in prompt.lower():
            content = self._responses.get("transformer")
        elif "attention" in prompt.lower():
            content = self._responses.get("attention")
        
        return MockLLMResponse(
            content=content,
            model="mock-model",
            provider="mock",
        )
    
    async def generate_embedding(self, text: str, **kwargs) -> List[float]:
        return [0.1] * 10
    
    async def health_check_all(self) -> Dict[str, bool]:
        return {"mock": True}
    
    def add_provider(self, name, client):
        pass


class MockLLMResponse:
    def __init__(self, content: str, model: str, provider: str):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = {}
        self.cost = 0.001


class MockMessagePublisher:
    """Mock message publisher for testing."""
    
    def __init__(self):
        self._published: List[Dict[str, Any]] = []
    
    async def publish(self, message, routing_key: str, **kwargs):
        self._published.append({
            "message": message,
            "routing_key": routing_key,
        })
    
    async def health_check(self) -> bool:
        return True
    
    async def close(self):
        pass
    
    def get_published(self) -> List[Dict[str, Any]]:
        return list(self._published)
    
    def clear(self):
        self._published.clear()


# ==================== Async Test Helper ====================

def async_test(coro):
    """Decorator to run async test functions."""
    def wrapper(*args, **kwargs):
        asyncio.get_event_loop().run_until_complete(coro(*args, **kwargs))
    return wrapper


# ==================== Test Classes ====================

class TestCacheManager:
    """Test CacheManager with mock backend."""
    
    @async_test
    async def test_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        from src.services.fetchers.arxiv.services.cache_manager import CacheManager
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        cache = MockCacheBackend()
        manager = CacheManager(
            cache_backend=cache,
            config=ArxivFetcherConfig(),
        )
        
        result = await manager.get_api_response("test_query")
        
        assert result is None
    
    @async_test
    async def test_cache_hit_returns_data(self):
        """Test that cache hit returns data."""
        import json
        from src.services.fetchers.arxiv.services.cache_manager import CacheManager
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        cache = MockCacheBackend()
        manager = CacheManager(
            cache_backend=cache,
            config=ArxivFetcherConfig(),
        )
        
        # Set cached data
        test_data = {"papers": [], "fetched_at": "2024-01-01"}
        cache._storage["arxiv:api:key123"] = json.dumps(test_data).encode()
        
        result = await manager.get_api_response("test_query")
        
        assert result is not None
        assert result["papers"] == []


class TestQueryProcessor:
    """Test QueryProcessor with mock LLM."""
    
    @async_test
    async def test_expand_query_with_fallback(self):
        """Test that fallback expansion works without LLM."""
        from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        # No LLM router - should use fallback
        processor = QueryProcessor(
            llm_router=None,
            cache_manager=None,
            config=ArxivFetcherConfig(max_query_expansions=3),
        )
        
        expansion = await processor.expand_query("neural network")
        
        assert expansion.original_query == "neural network"
        assert len(expansion.expanded_queries) > 0
        assert "all:neural network" in expansion.expanded_queries
    
    @async_test
    async def test_expand_query_with_mock_llm(self):
        """Test that query expansion works with mock LLM."""
        from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        mock_router = MockLLMRouter()
        
        processor = QueryProcessor(
            llm_router=mock_router,
            cache_manager=None,
            config=ArxivFetcherConfig(max_query_expansions=3),
        )
        
        expansion = await processor.expand_query("transformer attention")
        
        assert expansion.original_query == "transformer attention"
        assert len(expansion.expanded_queries) > 0
        assert mock_router._call_count > 0
    
    def test_parse_expansions_filters_short_queries(self):
        """Test that very short queries are filtered out."""
        from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        processor = QueryProcessor(
            llm_router=None,
            config=ArxivFetcherConfig(),
        )
        
        expansions = processor._parse_expansions('["a", "ab", "abc", "test"]')
        
        assert "a" not in expansions
        assert "ab" not in expansions
        assert "abc" in expansions
        assert "test" in expansions


class TestArxivAPIClient:
    """Test ArxivAPIClient with mock HTTP client."""
    
    def test_build_search_url(self):
        """Test URL building without HTTP calls."""
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        client = ArxivAPIClient(
            http_client=None,
            rate_limiter=None,
            config=ArxivFetcherConfig(),
        )
        
        url = client._build_search_url(
            query="transformer",
            max_results=10,
            start_index=0,
            sort_by="relevance",
            sort_order="descending",
        )
        
        assert "search_query=transformer" in url
        assert "max_results=10" in url
        assert "sortBy=relevance" in url
        assert "sortOrder=descending" in url
    
    def test_build_search_url_respects_limit(self):
        """Test that max_results is capped at 2000."""
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        client = ArxivAPIClient(config=ArxivFetcherConfig())
        
        url = client._build_search_url(
            query="test",
            max_results=5000,  # Exceeds arXiv limit
            start_index=0,
            sort_by="relevance",
            sort_order="descending",
        )
        
        assert "max_results=2000" in url
        assert "max_results=5000" not in url
    
    def test_parse_atom_response_empty(self):
        """Test parsing empty ATOM response."""
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        
        client = ArxivAPIClient()
        
        empty_xml = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>"""
        
        papers = client._parse_atom_response(empty_xml)
        
        assert len(papers) == 0
    
    def test_parse_atom_response_single_entry(self):
        """Test parsing single paper entry."""
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        
        client = ArxivAPIClient()
        
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>http://arxiv.org/abs/2401.12345v1</id>
            <title>Test Paper</title>
            <summary>Abstract here</summary>
            <published>2024-01-15T10:30:00Z</published>
            <author><name>Author Name</name></author>
            <category term="cs.LG"/>
            <link rel="alternate" href="http://arxiv.org/abs/2401.12345"/>
            <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1.pdf"/>
          </entry>
        </feed>"""
        
        papers = client._parse_atom_response(xml, source_query="test")
        
        assert len(papers) == 1
        assert papers[0].paper_id == "2401.12345"
        assert papers[0].version == "v1"
        assert papers[0].title == "Test Paper"
        assert "Author Name" in papers[0].authors
        assert "cs.LG" in papers[0].categories
        assert "2401.12345.pdf" in papers[0].pdf_url


class TestArxivPublisher:
    """Test ArxivMessagePublisher with mock publisher."""
    
    @async_test
    async def test_publish_discovered_with_mock(self):
        """Test publishing with mock publisher."""
        from src.services.fetchers.arxiv.services.publisher import ArxivMessagePublisher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        from src.services.fetchers.arxiv.schemas.paper import PaperMetadata
        
        mock_pub = MockMessagePublisher()
        
        publisher = ArxivMessagePublisher(
            message_publisher=mock_pub,
            config=ArxivFetcherConfig(),
        )
        
        papers = [
            PaperMetadata(
                paper_id="2401.12345",
                title="Test Paper",
                abstract="Abstract",
                authors=["Author"],
                categories=["cs.LG"],
                pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
            )
        ]
        
        count = await publisher.publish_discovered(papers)
        
        assert count == 1
        assert len(mock_pub.get_published()) == 1
        
        # Verify message structure
        published = mock_pub.get_published()[0]
        assert published["routing_key"] == "arxiv.discovered"
        assert published["message"].paper_id == "2401.12345"
    
    @async_test
    async def test_health_check_returns_true(self):
        """Test health check with mock publisher."""
        from src.services.fetchers.arxiv.services.publisher import ArxivMessagePublisher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        mock_pub = MockMessagePublisher()
        
        publisher = ArxivMessagePublisher(
            message_publisher=mock_pub,
            config=ArxivFetcherConfig(),
        )
        
        result = await publisher.health_check()
        
        assert result is True


class TestArxivFetcher:
    """Test ArxivFetcher orchestrator with all mocks."""
    
    @async_test
    async def test_fetcher_initialization(self):
        """Test fetcher initialization with mocks."""
        from src.services.fetchers.arxiv.services.fetcher import ArxivFetcher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        
        fetcher = ArxivFetcher(
            config=ArxivFetcherConfig(),
            cache=MockCacheBackend(),
            query_processor=None,
            api_client=ArxivAPIClient(),
            publisher=None,
        )
        
        assert fetcher.is_initialized is False
        
        await fetcher.initialize()
        
        assert fetcher.is_initialized is True
    
    def test_deduplicate_papers(self):
        """Test paper deduplication logic."""
        from src.services.fetchers.arxiv.services.fetcher import ArxivFetcher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        from src.services.fetchers.arxiv.schemas.paper import PaperMetadata
        
        fetcher = ArxivFetcher(config=ArxivFetcherConfig())
        
        papers = [
            PaperMetadata(paper_id="2401.10001", title="Paper 1"),
            PaperMetadata(paper_id="2401.10001", title="Paper 1 Duplicate"),
            PaperMetadata(paper_id="2401.10002", title="Paper 2"),
        ]
        
        unique = fetcher._deduplicate_papers(papers)
        
        assert len(unique) == 2
        assert unique[0].paper_id == "2401.10001"
        assert unique[1].paper_id == "2401.10002"
    
    def test_get_stats(self):
        """Test statistics collection."""
        from src.services.fetchers.arxiv.services.fetcher import ArxivFetcher
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
        
        fetcher = ArxivFetcher(
            config=ArxivFetcherConfig(),
            api_client=ArxivAPIClient(),
        )
        
        stats = fetcher.get_stats()
        
        assert "papers_discovered" in stats
        assert "papers_published" in stats
        assert "queries_processed" in stats
        assert "initialized" in stats


class TestIntegration:
    """Integration tests with partial mocks."""
    
    @async_test
    async def test_query_processor_with_cache(self):
        """Test query processor using in-memory cache."""
        import json
        from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
        from src.services.fetchers.arxiv.services.cache_manager import CacheManager
        from src.services.fetchers.arxiv.config import ArxivFetcherConfig
        
        cache = MockCacheBackend()
        cache_manager = CacheManager(
            cache_backend=cache,
            config=ArxivFetcherConfig(),
        )
        
        # Pre-populate cache
        await cache_manager.set_query_expansion("cached_query", ["all:cached"])
        
        processor = QueryProcessor(
            llm_router=None,
            cache_manager=cache_manager,
            config=ArxivFetcherConfig(),
        )
        
        # First call - should cache
        expansion1 = await processor.expand_query("cached_query")
        
        # Second call - should hit cache
        expansion2 = await processor.expand_query("cached_query")
        
        assert expansion1.cache_hit is False
        assert expansion2.cache_hit is True
        assert expansion1.expanded_queries == expansion2.expanded_queries


# ==================== Test Runner ====================

def run_tests():
    """Run all tests and report results."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run arXiv fetcher dependency injection tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    test_classes = [
        TestCacheManager,
        TestQueryProcessor,
        TestArxivAPIClient,
        TestArxivPublisher,
        TestArxivFetcher,
        TestIntegration,
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    
    for test_class in test_classes:
        if args.verbose:
            print(f"\n{'='*60}")
            print(f"Running: {test_class.__name__}")
            print('='*60)
        
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        
        for method_name in methods:
            total_tests += 1
            method = getattr(instance, method_name)
            
            try:
                if args.verbose:
                    print(f"  {method_name}... ", end="")
                
                # Run the test (it may be decorated with @async_test)
                method()
                
                passed_tests += 1
                if args.verbose:
                    print("PASSED")
                    
            except Exception as e:
                failed_tests += 1
                if args.verbose:
                    print(f"FAILED: {e}")
                else:
                    print(f"{test_class.__name__}.{method_name}: {e}")
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    print(f"Total: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    
    success = failed_tests == 0
    print(f"\n{'='*60}")
    if success:
        print("ALL TESTS PASSED")
    else:
        print(f"{failed_tests} TESTS FAILED")
    print('='*60)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(run_tests())
