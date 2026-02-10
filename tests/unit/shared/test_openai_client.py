"""Unit tests for OpenAI-compatible client wrapper."""

from __future__ import annotations

import types

import pytest

from src.shared.exceptions.llm import LLMError, LLMProviderError
from src.shared.llm import openai_client as module


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


@pytest.mark.asyncio
async def test_complete_returns_wrapped_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeCompletions:
        async def create(self, **kwargs):
            usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
            message = types.SimpleNamespace(content="ok")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice], usage=usage)

    class _FakeModels:
        async def list(self):
            return []

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())
            self.models = _FakeModels()

    monkeypatch.setattr(module, "AsyncOpenAI", _FakeClient)
    client = module.OpenAIClient(base_url="https://example", api_key="k", model="m")
    resp = await client.complete(prompt="hello", system="sys", temperature=0.1)
    assert resp.content == "ok"
    assert resp.usage["total_tokens"] == 3
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_complete_wraps_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("provider down")

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())
            self.models = types.SimpleNamespace(list=lambda: [])

    monkeypatch.setattr(module, "AsyncOpenAI", _FakeClient)
    client = module.OpenAIClient(base_url="https://example", api_key="k", model="m")
    with pytest.raises(LLMProviderError):
        await client.complete(prompt="hello")
