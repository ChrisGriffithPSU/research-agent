"""Tests for OpenAI-compatible client wrapper.

Structure:
- Unit tests: config/init behavior (no API calls)
- Integration tests: real API calls against the configured endpoint
- Structured output tests: JSON schema enforcement and Pydantic validation

All integration tests are provider-agnostic — they use the OpenAI Chat
Completions API spec (response_format, json_schema). They happen to run
against whatever CUSTOM_LLM_BASE_URL points to (OpenRouter by default).
"""

from __future__ import annotations

import json
import os

import pytest
from pydantic import BaseModel, Field

from src.shared.exceptions.llm import LLMError, LLMProviderError
from src.shared.llm import openai_client as module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"


def _get_api_key() -> str:
    """Read the API key from env. Integration tests skip if missing."""
    key = os.getenv("CUSTOM_LLM_API_KEY", "")
    return key


def _make_client(**overrides) -> module.OpenAIClient:
    """Build a client with explicit values so it doesn't read env for
    base_url/model. Override anything via kwargs."""
    defaults = {
        "base_url": os.getenv("CUSTOM_LLM_BASE_URL", DEFAULT_BASE),
        "api_key": _get_api_key(),
        "model": os.getenv("CUSTOM_LLM_MODEL", DEFAULT_MODEL),
        "max_retries": 1,
        "timeout_seconds": 90.0,
    }
    defaults.update(overrides)
    return module.OpenAIClient(**defaults)


# ---------------------------------------------------------------------------
# Pydantic models used by structured output tests
# ---------------------------------------------------------------------------


class SimpleModel(BaseModel):
    """Simple schema: two required fields, one optional."""

    name: str
    count: int
    tag: str = "default"


class NestedChild(BaseModel):
    value: int
    label: str


class NestedParent(BaseModel):
    title: str
    children: list[NestedChild]


class EnumChoice(BaseModel):
    """Schema with constrained string values."""

    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


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
# Integration tests (real API calls)
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
    """Health check should succeed with valid credentials."""
    client = _make_client()
    assert await client.health_check() is True


# ---------------------------------------------------------------------------
# JSON mode tests (json_object — provider tells model to output JSON)
# ---------------------------------------------------------------------------


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_object_mode_returns_parseable_json() -> None:
    """response_format json_object should return valid JSON.

    Note: openrouter/free routes to random models, so we don't assert
    exact field values — just that the response is valid JSON.
    """
    client = _make_client()
    response = await client.complete(
        prompt='Return a JSON object with a "status" key.',
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    # Some free models return empty content for json_object mode.
    # If we got content, it must be valid JSON.
    if response.content.strip():
        parsed = json.loads(response.content)
        assert isinstance(parsed, dict)


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_object_mode_with_nested_schema() -> None:
    """json_object mode should handle nested structures when the model supports it."""
    client = _make_client()
    try:
        response = await client.complete(
            prompt=(
                'Return JSON: {"title": "Test", "children": '
                '[{"value": 1, "label": "a"}, {"value": 2, "label": "b"}]}'
            ),
            temperature=0.0,
            response_format={"type": "json_object"},
        )
    except LLMProviderError:
        # Some free models (e.g. gemma-3n) reject json_object mode. Skip.
        pytest.skip("Provider doesn't support json_object response_format")
    if not response.content.strip():
        pytest.skip("Model returned empty content")
    parsed = json.loads(response.content)
    assert isinstance(parsed, dict)


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_object_content_is_only_json() -> None:
    """json_object mode should return ONLY JSON — no markdown fences, no prose."""
    client = _make_client()
    response = await client.complete(
        prompt='Return JSON: {"answer": 42}',
        system="You are a JSON API.",
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    # Should parse without error — no trailing text or markdown fences
    parsed = json.loads(response.content)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Structured output tests (json_schema — API enforces the schema)
# These test the OpenAI API spec's json_schema response_format.
# ---------------------------------------------------------------------------


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_schema_enforces_required_fields() -> None:
    """json_schema mode should enforce required fields."""
    client = _make_client()
    response = await client.complete(
        prompt='Create a person named "Alice" with count 5.',
        system="Generate data matching the requested schema exactly.",
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "SimpleModel",
                "strict": True,
                "schema": SimpleModel.model_json_schema(),
            },
        },
    )
    parsed = json.loads(response.content)
    assert "name" in parsed
    assert "count" in parsed
    assert isinstance(parsed["count"], int)


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_schema_with_nested_objects() -> None:
    """json_schema mode should handle nested object schemas."""
    client = _make_client()
    schema = NestedParent.model_json_schema()
    response = await client.complete(
        prompt=(
            'Create a parent titled "Project X" with two children: '
            '(value=10, label="alpha") and (value=20, label="beta").'
        ),
        system="Generate data matching the requested schema exactly.",
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "NestedParent",
                "strict": True,
                "schema": schema,
            },
        },
    )
    parsed = json.loads(response.content)
    assert parsed["title"] == "Project X"
    assert len(parsed["children"]) == 2
    assert parsed["children"][0]["value"] == 10


# ---------------------------------------------------------------------------
# complete_structured() tests (Pydantic model in, validated model out)
# ---------------------------------------------------------------------------


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_simple_model() -> None:
    """complete_structured should return a validated Pydantic instance."""
    client = _make_client()
    instance, response = await client.complete_structured(
        model_class=SimpleModel,
        prompt='Create a person named "Bob" with count 3 and tag "test".',
        system="Generate data matching the requested schema exactly.",
    )
    assert isinstance(instance, SimpleModel)
    assert instance.name == "Bob"
    assert instance.count == 3
    assert instance.tag == "test"
    assert isinstance(response, module.LLMResponse)


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_nested_model() -> None:
    """complete_structured should handle nested Pydantic models."""
    client = _make_client()
    instance, response = await client.complete_structured(
        model_class=NestedParent,
        prompt=('Create a parent titled "Experiment" with one child: (value=42, label="control").'),
        system="Generate data matching the requested schema exactly.",
    )
    assert isinstance(instance, NestedParent)
    assert instance.title == "Experiment"
    assert len(instance.children) == 1
    assert instance.children[0].value == 42
    assert instance.children[0].label == "control"


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_with_confidence_score() -> None:
    """complete_structured should validate field constraints."""
    client = _make_client()
    instance, _ = await client.complete_structured(
        model_class=EnumChoice,
        prompt='Decide "yes" with 0.95 confidence because the data is clear.',
        system="You evaluate evidence and return structured decisions.",
    )
    assert isinstance(instance, EnumChoice)
    assert instance.decision  # non-empty string
    assert 0.0 <= instance.confidence <= 1.0
    assert len(instance.reasoning) > 0


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_fallback_to_json_object() -> None:
    """If json_schema isn't supported, fallback to json_object + validation."""
    client = _make_client()
    # This tests the fallback path — the free model may or may not support
    # json_schema, but complete_structured should work either way.
    instance, response = await client.complete_structured(
        model_class=SimpleModel,
        prompt='Create: name="test", count=1.',
        system="Return JSON with keys: name (string), count (integer).",
    )
    assert isinstance(instance, SimpleModel)
    assert instance.name == "test"
    assert instance.count == 1


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_response_is_valid_json() -> None:
    """The raw response content should always be parseable JSON."""
    client = _make_client()
    instance, response = await client.complete_structured(
        model_class=SimpleModel,
        prompt='Create: name="verify", count=99.',
        system="Return JSON.",
    )
    raw = json.loads(response.content)
    assert isinstance(raw, dict)
    assert raw["name"] == "verify"
    assert raw["count"] == 99


# ---------------------------------------------------------------------------
# Reasoning tests (provider-specific extra_body, not part of OpenAI spec)
# ---------------------------------------------------------------------------


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_with_reasoning() -> None:
    """Reasoning mode via extra_body should return content."""
    client = _make_client()
    response = await client.complete(
        prompt="How many r's are in the word 'strawberry'?",
        temperature=0.0,
        extra_body={"reasoning": {"enabled": True}},
    )
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    assert hasattr(response, "reasoning_details")


@_skip_no_key
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_with_reasoning() -> None:
    """Passing back reasoning_details for continued reasoning."""
    client = _make_client()

    response1 = await client.complete(
        prompt="How many r's are in the word 'strawberry'?",
        temperature=0.0,
        extra_body={"reasoning": {"enabled": True}},
    )

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
