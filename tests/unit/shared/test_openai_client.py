"""Tests for OpenAI-compatible client wrapper.

Structure:
- Unit tests: config/init behavior (no API calls)
- Integration tests: real API calls against OpenRouter free model
"""

from __future__ import annotations

import json
import os

import pytest

from src.shared.exceptions.llm import LLMError, LLMProviderError
from src.shared.llm import openai_client as module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openrouter/free"


def _get_api_key() -> str:
    """Read the API key from env. Integration tests skip if missing."""
    key = os.getenv("CUSTOM_LLM_API_KEY", "")
    return key


def _make_client(**overrides) -> module.OpenAIClient:
    """Build a client pointed at OpenRouter. Passes explicit values so
    the client doesn't try to read env vars for base_url/model."""
    defaults = {
        "base_url": OPENROUTER_BASE,
        "api_key": _get_api_key(),
        "model": OPENROUTER_MODEL,
        "max_retries": 1,
        "timeout_seconds": 60.0,
    }
    defaults.update(overrides)
    return module.OpenAIClient(**defaults)


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------


def test_init_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOM_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_LLM_TRIAGE_API_KEY", raising=False)
    with pytest.raises(LLMError):
        module.OpenAIClient(base_url="https://example", api_key="", model="m")


def test_profile_specific_env_overrides_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_LLM_API_KEY", "global-key")
    monkeypatch.setenv("CUSTOM_LLM_MODEL", "global-model")
    monkeypatch.setenv("CUSTOM_LLM_TRIAGE_MODEL", "triage-model")
    client = module.OpenAIClient(profile="triage")
    assert client.model == "triage-model"


def test_profile_specific_key_falls_back_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_LLM_API_KEY", "global-key")
    monkeypatch.delenv("CUSTOM_LLM_CONCEPT_GEN_API_KEY", raising=False)
    client = module.OpenAIClient(profile="concept_gen")
    assert client.api_key == "global-key"


# ---------------------------------------------------------------------------
# Integration tests (real API calls to OpenRouter)
# ---------------------------------------------------------------------------

_skip_no_key = pytest.mark.skipif(
    not _get_api_key(),
    reason="CUSTOM_LLM_API_KEY not set — skipping integration tests",
)


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_basic_completion_returns_content() -> None:
    """A simple prompt should return a non-empty string."""
    client = _make_client()
    response = await client.complete(
        prompt='Reply with exactly the word "pong" and nothing else.',
        temperature=0.0,
    )
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    assert response.latency_ms is not None
    assert response.latency_ms > 0


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_with_system_prompt() -> None:
    """System prompt should influence the response."""
    client = _make_client()
    response = await client.complete(
        prompt="What is 2+2? Reply with just the number.",
        system="You are a calculator. Only respond with numbers.",
        temperature=0.0,
    )
    assert isinstance(response.content, str)
    assert "4" in response.content


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_with_json_response_format() -> None:
    """response_format json_object should return valid JSON."""
    client = _make_client()
    response = await client.complete(
        prompt='Return a JSON object with one key "status" set to "ok".',
        system="You are a JSON API. Only return valid JSON.",
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.content)
    assert parsed["status"] == "ok"


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_with_reasoning() -> None:
    """Reasoning mode should return reasoning_details on the response."""
    client = _make_client()
    response = await client.complete(
        prompt="How many r's are in the word 'strawberry'?",
        temperature=0.0,
        extra_body={"reasoning": {"enabled": True}},
    )
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    # reasoning_details should be present (may be None for some models,
    # but the attribute should exist)
    assert hasattr(response, "reasoning_details")


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_with_reasoning() -> None:
    """Passing back reasoning_details should work for continued reasoning."""
    client = _make_client()

    # First turn
    response1 = await client.complete(
        prompt="How many r's are in the word 'strawberry'?",
        temperature=0.0,
        extra_body={"reasoning": {"enabled": True}},
    )
    assert isinstance(response1.content, str)

    # Second turn — pass back the assistant message with reasoning_details
    messages = [
        {"role": "user", "content": "How many r's are in the word 'strawberry'?"},
        {
            "role": "assistant",
            "content": response1.content,
            "reasoning_details": response1.reasoning_details,
        },
        {"role": "user", "content": "Are you sure? Think carefully."},
    ]
    response2 = await client.complete(
        messages=messages,
        temperature=0.0,
        extra_body={"reasoning": {"enabled": True}},
    )
    assert isinstance(response2.content, str)
    assert len(response2.content.strip()) > 0


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_usage_metrics_populated() -> None:
    """Response should include token usage metrics."""
    client = _make_client()
    response = await client.complete(
        prompt='Say "hello".',
        temperature=0.0,
    )
    assert response.usage is not None
    assert "total_tokens" in response.usage
    assert response.usage["total_tokens"] > 0


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_api_key_raises_provider_error() -> None:
    """A bad API key should raise LLMProviderError, not crash."""
    client = _make_client(api_key="sk-invalid-key-12345")
    with pytest.raises(LLMProviderError):
        await client.complete(prompt="hello")


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_with_valid_credentials() -> None:
    """Health check should succeed with valid credentials.

    Note: OpenRouter's /models endpoint is public, so even invalid keys
    may return True. This test just verifies the happy path works.
    """
    client = _make_client()
    assert await client.health_check() is True
