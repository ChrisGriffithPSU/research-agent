"""Unit tests for arXiv API client parsing and search behavior."""

from __future__ import annotations

import pytest

from src.services.fetchers.arxiv.services.api_client import ArxivAPIClient
from src.shared.testing.mocks import MockHTTPClient, MockHTTPResponse


SAMPLE_ATOM = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:arxiv=\"http://arxiv.org/schemas/atom\">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v2</id>
    <updated>2024-01-02T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title> Test Title </title>
    <summary> Test abstract </summary>
    <author><name>Jane Doe</name></author>
    <category term=\"cs.LG\"/>
    <link rel=\"alternate\" href=\"https://arxiv.org/abs/2401.12345\"/>
    <link title=\"pdf\" href=\"https://arxiv.org/pdf/2401.12345.pdf\"/>
  </entry>
</feed>
"""


def test_build_search_url_contains_query_and_limit() -> None:
    client = ArxivAPIClient(http_client=MockHTTPClient())
    url = client._build_search_url(
        "cat:cs.LG", max_results=25, start_index=0, sort_by="relevance", sort_order="descending"
    )
    assert "search_query=cat:cs.LG" in url
    assert "max_results=25" in url


def test_parse_atom_response_extracts_expected_fields() -> None:
    client = ArxivAPIClient(http_client=MockHTTPClient())
    papers = client._parse_atom_response(SAMPLE_ATOM, source_query="cat:cs.LG")
    assert len(papers) == 1
    paper = papers[0]
    assert paper.paper_id == "2401.12345"
    assert paper.version == "v2"
    assert paper.title == "Test Title"
    assert "Jane Doe" in paper.authors
    assert paper.pdf_url.endswith(".pdf")


@pytest.mark.asyncio
async def test_search_uses_http_client_and_parses_payload() -> None:
    response = MockHTTPResponse(status_code=200, content=SAMPLE_ATOM.encode("utf-8"))
    http_client = MockHTTPClient(
        responses={
            "http://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=1&sortBy=relevance&sortOrder=descending": response
        }
    )
    client = ArxivAPIClient(http_client=http_client)
    papers = await client.search("cat:cs.LG", max_results=1)
    assert len(papers) == 1
    assert papers[0].paper_id == "2401.12345"
