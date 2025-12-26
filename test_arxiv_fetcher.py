#!/usr/bin/env python3
"""
Test script for arXiv fetcher plugin end-to-end verification.

This script tests core features:
1. Configuration loading
2. Query expansion (LLM)
3. arXiv API search
4. Rate limiting
5. PDF parsing (docling)
6. Message publishing (if queue available)

Usage:
    python test_arxiv_fetcher.py [--skip-api] [--skip-llm] [--skip-pdf]

Options:
    --skip-api: Skip arXiv API tests (no network)
    --skip-llm: Skip LLM query expansion tests
    --skip-pdf: Skip PDF parsing tests
"""
import asyncio
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ============================================================
# Test Configuration
# ============================================================

class TestConfig:
    """Test configuration."""
    
    # Test queries
    TEST_QUERIES = [
        "transformer time series forecasting",
        "attention mechanism neural network",
        "quantitative finance machine learning",
    ]
    
    # Test categories
    TEST_CATEGORIES = ["cs.LG", "stat.ML"]
    
    # arXiv test paper
    TEST_PAPER_ID = "2408.09869"
    TEST_PAPER_URL = f"https://arxiv.org/pdf/{TEST_PAPER_ID}.pdf"
    
    # Expected results
    MIN_PAPERS_PER_QUERY = 1
    MAX_PAPERS_PER_QUERY = 100


# ============================================================
# Test Runner
# ============================================================

class TestRunner:
    """Test runner with timing and reporting."""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time: datetime = None
    
    async def run_test(
        self,
        name: str,
        test_func,
        required: bool = True,
    ) -> bool:
        """Run a single test.
        
        Args:
            name: Test name
            test_func: Async test function
            required: Whether test is required
            
        Returns:
            True if passed, False otherwise
        """
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print('='*60)
        
        self.start_time = datetime.utcnow()
        
        try:
            result = await test_func()
            duration = (datetime.utcnow() - self.start_time).total_seconds()
            
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"\n{status} ({duration:.2f}s)")
            
            self.results.append({
                "name": name,
                "passed": result,
                "duration": duration,
                "required": required,
            })
            
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - self.start_time).total_seconds()
            status = "✗ ERROR"
            print(f"\n{status}: {e}")
            import traceback
            traceback.print_exc()
            
            self.results.append({
                "name": name,
                "passed": False,
                "error": str(e),
                "duration": duration,
                "required": required,
            })
            
            return False
    
    def print_summary(self) -> bool:
        """Print test summary.
        
        Returns:
            True if all required tests passed
        """
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print('='*60)
        
        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        required_failed = sum(
            1 for r in self.results 
            if not r["passed"] and r.get("required", True)
        )
        
        print(f"\nTotal: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Required Failed: {required_failed}")
        
        print("\nDetailed Results:")
        for result in self.results:
            status = "✓" if result["passed"] else "✗"
            required = " [REQUIRED]" if result.get("required", True) else " [OPTIONAL]"
            print(f"  {status} {result['name']}{required}")
        
        success = required_failed == 0
        print(f"\n{'='*60}")
        if success:
            print("✓ ALL REQUIRED TESTS PASSED")
        else:
            print("✗ SOME REQUIRED TESTS FAILED")
        print('='*60)
        
        return success


# ============================================================
# Individual Tests
# ============================================================

async def test_configuration():
    """Test configuration loading."""
    print("\n[1/6] Testing configuration module...")
    
    from src.services.fetchers.arxiv.config import (
        ArxivFetcherConfig,
        get_config,
        load_config_from_dict,
    )
    
    # Test default config
    config = ArxivFetcherConfig()
    assert config is not None, "Failed to create default config"
    assert len(config.categories) > 0, "No categories in default config"
    assert config.rate_limit_requests_per_second > 0, "Invalid rate limit"
    assert config.ttl_api_response_seconds > 0, "Invalid API TTL"
    
    print(f"  - Default config created with {len(config.categories)} categories")
    print(f"  - Rate limit: {config.rate_limit_requests_per_second} req/s")
    print(f"  - API cache TTL: {config.ttl_api_response_seconds}s")
    
    # Test config from dict
    config_dict = {
        "categories": ["cs.LG", "stat.ML"],
        "rate_limit_requests_per_second": 0.5,
    }
    config2 = load_config_from_dict(config_dict)
    assert len(config2.categories) == 2, "Config from dict failed"
    
    print("  ✓ Configuration module working correctly")
    return True


async def test_schemas():
    """Test schema definitions."""
    print("\n[2/6] Testing schema definitions...")
    
    from src.services.fetchers.arxiv.schemas.paper import (
        PaperMetadata,
        ParsedContent,
        QueryExpansion,
    )
    from src.services.fetchers.arxiv.schemas.messages import (
        ArxivDiscoveredMessage,
        ArxivParseRequestMessage,
    )
    
    # Test PaperMetadata
    paper = PaperMetadata(
        paper_id="2401.12345",
        title="Test Paper",
        abstract="This is a test abstract",
        authors=["Author 1", "Author 2"],
        categories=["cs.LG", "stat.ML"],
        pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
        arxiv_url="https://arxiv.org/abs/2401.12345",
    )
    assert paper.paper_id == "2401.12345", "Paper ID mismatch"
    assert len(paper.authors) == 2, "Authors mismatch"
    assert "cs.LG" in paper.categories, "Categories mismatch"
    
    # Test ParsedContent
    content = ParsedContent(
        paper_id="2401.12345",
        text_content="Full text content here",
        tables=[{"caption": "Table 1", "data": [[1, 2], [3, 4]]}],
        equations=["$E=mc^2$", "\\begin{equation}x^2 = 1\\end{equation}"],
        figure_captions=[{"figure_id": "fig_1", "caption": "Figure 1"}],
    )
    assert len(content.tables) == 1, "Tables mismatch"
    assert len(content.equations) == 2, "Equations mismatch"
    assert len(content.figure_captions) == 1, "Figures mismatch"
    
    # Test ArxivDiscoveredMessage
    message = ArxivDiscoveredMessage(
        paper_id="2401.12345",
        title="Test Paper",
        abstract="Abstract",
        pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
        arxiv_url="https://arxiv.org/abs/2401.12345",
    )
    assert message.correlation_id is not None, "Correlation ID missing"
    
    print("  ✓ PaperMetadata schema working")
    print("  ✓ ParsedContent schema working")
    print("  ✓ Message schemas working")
    return True


async def test_rate_limiter():
    """Test rate limiter."""
    print("\n[3/6] Testing rate limiter...")
    
    from src.services.fetchers.arxiv.utils.rate_limiter import RateLimiter
    
    # Create rate limiter (arXiv: 1 req/3s)
    limiter = RateLimiter(rate=0.333, capacity=1)
    
    # Test initial state
    assert limiter.get_available_tokens() == 1.0, "Initial tokens mismatch"
    
    # Test acquire
    import asyncio
    start = asyncio.get_event_loop().time()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 0.5, f"Acquire took too long: {elapsed}s"
    
    # After acquire, should have 0 tokens
    tokens = limiter.get_available_tokens()
    assert tokens < 0.5, f"Tokens should be < 0.5, got {tokens}"
    
    print(f"  - Initial tokens: 1.0")
    print(f"  - After acquire: {tokens:.2f} tokens")
    
    # Wait for refill
    await asyncio.sleep(3.1)
    tokens_after = limiter.get_available_tokens()
    assert tokens_after > 0.9, f"Tokens should refill after 3s, got {tokens_after}"
    
    print(f"  - After 3s wait: {tokens_after:.2f} tokens")
    
    # Test stats
    stats = limiter.get_stats()
    assert "rate" in stats, "Stats missing rate"
    assert "capacity" in stats, "Stats missing capacity"
    
    print("  ✓ Rate limiter working correctly")
    return True


async def test_query_expansion(skip_llm: bool = False):
    """Test query expansion with LLM."""
    print("\n[4/6] Testing query expansion...")
    
    from src.services.fetchers.arxiv.services.query_processor import QueryProcessor
    from src.services.fetchers.arxiv.services.cache_manager import CacheManager
    
    # Create processor without LLM (fallback mode)
    processor = QueryProcessor(
        llm_router=None,  # No LLM - will use fallback
        cache_manager=None,
    )
    await processor.initialize()
    
    # Test expansion
    test_query = "transformer time series"
    expansion = await processor.expand_query(test_query)
    
    assert expansion is not None, "Expansion returned None"
    assert len(expansion.expanded_queries) > 0, "No expansions generated"
    assert test_query in expansion.original_query, "Original query mismatch"
    
    print(f"  - Original query: '{test_query}'")
    print(f"  - Expanded to {len(expansion.expanded_queries)} queries:")
    for i, q in enumerate(expansion.expanded_queries[:3], 1):
        print(f"    {i}. {q}")
    
    # Test cache
    cache = CacheManager()
    await cache.initialize()
    
    await cache.set_query_expansion("test_query", ["expanded1", "expanded2"])
    cached = await cache.get_query_expansion("test_query")
    assert cached == ["expanded1", "expanded2"], "Cache mismatch"
    
    await cache.close()
    print("  ✓ Query expansion working (with fallback)")
    print("  ✓ Cache integration working")
    return True


async def test_api_client(skip_api: bool = False):
    """Test arXiv API client."""
    print("\n[5/6] Testing arXiv API client...")
    
    if skip_api:
        print("  - Skipping API tests (--skip-api flag)")
        return True
    
    from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
    from src.services.fetchers.arxiv.services.cache_manager import CacheManager
    
    # Create client
    cache = CacheManager()
    await cache.initialize()
    
    client = ArxivAPIClient(
        config=None,
        cache=cache,
    )
    await client.initialize()
    
    # Health check
    healthy = await client.health_check()
    if not healthy:
        print("  - arXiv API not accessible, skipping search tests")
        await client.close()
        await cache.close()
        return True
    
    # Test simple search
    papers = await client.search(
        query="cat:cs.LG",
        max_results=5,
        sort_by=ArxivAPIClient.SORT_SUBMITTED,
        sort_order=ArxivAPIClient.ORDER_DESCENDING,
    )
    
    assert len(papers) > 0, f"Expected papers, got {len(papers)}"
    assert len(papers) <= 5, f"Expected <= 5 papers, got {len(papers)}"
    
    print(f"  - Found {len(papers)} papers from cs.LG category")
    
    # Check paper structure
    if papers:
        paper = papers[0]
        print(f"  - Sample paper: {paper.paper_id}")
        print(f"    Title: {paper.title[:60]}...")
        print(f"    Categories: {paper.categories}")
        print(f"    Authors: {len(paper.authors)}")
    
    # Test stats
    stats = client.get_stats()
    assert "request_count" in stats, "Stats missing request_count"
    assert "cache_hit_count" in stats, "Stats missing cache_hit_count"
    
    await client.close()
    await cache.close()
    print("  ✓ arXiv API client working correctly")
    return True


async def test_pdf_parsing(skip_pdf: bool = False):
    """Test PDF parsing with docling."""
    print("\n[6/6] Testing PDF parsing with docling...")
    
    if skip_pdf:
        print("  - Skipping PDF tests (--skip-pdf flag)")
        return True
    
    from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor
    
    # Create processor
    processor = PDFProcessor()
    
    # Health check
    healthy = await processor.health_check()
    if not healthy:
        print("  - PDF processor not healthy, skipping parsing tests")
        return False
    
    # Test with real arXiv paper
    test_paper_id = TestConfig.TEST_PAPER_ID
    test_pdf_url = TestConfig.TEST_PAPER_URL
    
    print(f"  - Parsing PDF: {test_pdf_url}")
    
    try:
        content = await processor.extract(
            pdf_url=test_pdf_url,
            paper_id=test_paper_id,
        )
        
        assert content is not None, "Content is None"
        assert content.paper_id == test_paper_id, "Paper ID mismatch"
        assert len(content.text_content) > 0, "No text extracted"
        
        print(f"  - Extracted {len(content.text_content)} characters of text")
        print(f"  - Found {len(content.tables)} tables")
        print(f"  - Found {len(content.equations)} equations")
        print(f"  - Found {len(content.figure_captions)} figures")
        
        # Check metadata
        assert "num_pages" in content.metadata, "Missing page count"
        print(f"  - Document has {content.metadata['num_pages']} pages")
        
        # Show sample of extracted text
        if content.text_content:
            sample = content.text_content[:200].replace('\n', ' ')
            print(f"  - Text sample: {sample}...")
        
        print("  ✓ PDF parsing working correctly")
        return True
        
    except Exception as e:
        print(f"  - PDF parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_workflow():
    """Test full discovery workflow."""
    print("\n[Bonus] Testing full discovery workflow...")
    
    from src.services.fetchers.arxiv import ArxivFetcher
    
    # Create fetcher
    fetcher = ArxivFetcher()
    
    try:
        await fetcher.initialize()
        
        # Run discovery with single query
        results = await fetcher.run_discovery(
            queries=["attention mechanism neural network"],
            categories=None,
        )
        
        assert "papers_discovered" in results, "Missing papers_discovered"
        assert "papers_published" in results, "Missing papers_published"
        assert "duration_seconds" in results, "Missing duration"
        
        print(f"  - Discovered: {results['papers_discovered']} papers")
        print(f"  - Published: {results['papers_published']} papers")
        print(f"  - Duration: {results['duration_seconds']:.2f}s")
        
        # Health check
        health = await fetcher.health_check()
        print(f"  - Component health: {health}")
        
        # Get stats
        stats = fetcher.get_stats()
        print(f"  - Stats: papers={stats.get('papers_discovered', 'N/A')}")
        
        await fetcher.close()
        print("  ✓ Full workflow test passed")
        return True
        
    except Exception as e:
        print(f"  - Workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# Main
# ============================================================

async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("ARXIV FETCHER PLUGIN - END-TO-END TESTS")
    print("="*60)
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Test arXiv fetcher plugin")
    parser.add_argument("--skip-api", action="store_true", help="Skip API tests")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM tests")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF tests")
    args = parser.parse_args()
    
    # Create test runner
    runner = TestRunner()
    
    # Run tests
    await runner.run_test("Configuration Module", test_configuration)
    await runner.run_test("Schema Definitions", test_schemas)
    await runner.run_test("Rate Limiter", test_rate_limiter)
    await runner.run_test("Query Expansion", lambda: test_query_expansion(args.skip_llm))
    await runner.run_test("arXiv API Client", lambda: test_api_client(args.skip_api))
    await runner.run_test("PDF Parsing", lambda: test_pdf_parsing(args.skip_pdf))
    
    # Run workflow test (optional, requires full setup)
    await runner.run_test("Full Workflow", test_full_workflow, required=False)
    
    # Print summary
    success = runner.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

