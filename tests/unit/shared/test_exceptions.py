"""Unit tests for shared exception hierarchy."""

from src.shared.exceptions import (
    CircuitOpenError,
    DatabaseError,
    LLMProviderError,
    RepositoryConflictError,
    RepositoryNotFoundError,
    ResearchAgentError,
)


def test_research_agent_error_to_dict_contains_contract_fields() -> None:
    err = ResearchAgentError("boom", error_code="X_TEST", details={"x": 1})
    as_dict = err.to_dict()
    assert as_dict["error_code"] == "X_TEST"
    assert as_dict["message"] == "boom"
    assert as_dict["details"] == {"x": 1}
    assert as_dict["exception_type"] == "ResearchAgentError"


def test_database_specialized_exceptions_have_specific_codes() -> None:
    not_found = RepositoryNotFoundError()
    conflict = RepositoryConflictError()
    assert isinstance(not_found, DatabaseError)
    assert isinstance(conflict, DatabaseError)
    assert not_found.error_code == "REPOSITORY_NOT_FOUND"
    assert conflict.error_code == "REPOSITORY_CONFLICT"


def test_llm_provider_error_preserves_provider_and_model() -> None:
    err = LLMProviderError("failed", provider="openai", model="gpt-test", provider_code="429")
    rendered = str(err)
    assert "failed" in rendered
    assert "openai" in rendered
    assert "gpt-test" in rendered
    assert err.details["provider_code"] == "429"


def test_circuit_open_error_includes_circuit_name() -> None:
    err = CircuitOpenError(circuit_name="llm-primary")
    assert err.error_code == "CIRCUIT_OPEN"
    assert err.details["circuit_name"] == "llm-primary"
