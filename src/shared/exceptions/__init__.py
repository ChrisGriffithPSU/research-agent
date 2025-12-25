"""Custom exceptions for the application."""

from src.shared.exceptions.base import (
    ResearchAgentError,
    CircuitOpenError,
)

from src.shared.exceptions.database import (
    ConnectionPoolExhaustedError,
    DatabaseError,
    DuplicateDetectionError,
    RepositoryConflictError,
    RepositoryNotFoundError,
)

from src.shared.exceptions.http import (
    HTTPError,
    ValidationError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError as HTTPNotFoundError,
    ConflictError,
    RateLimitError,
    InternalServerError,
    ServiceUnavailableError,
)

from src.shared.exceptions.llm import (
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMInvalidResponseError,
    AllLLMProvidersFailedError,
)

from src.shared.exceptions.external_api import (
    ExternalAPIError,
    APITimeoutError,
    APIConnectionError,
    APIAuthError,
    APIRateLimitError,
    APIServerError,
    APIInvalidResponseError,
    APIClientError,
)

from src.shared.exceptions.config import (
    ConfigError,
    ConfigNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    ConfigMergeError,
    EnvVarNotFoundError,
    EnvVarSubstitutionError,
)

from src.shared.exceptions.cache import (
    CacheError,
    CacheConnectionError,
    CacheTimeoutError,
    CacheSerializationError,
    CacheKeyError,
    CacheCapacityError,
    CacheQuotaExceededError,
)

__all__ = [
    # Base exceptions
    "ResearchAgentError",
    "CircuitOpenError",
    "DatabaseError",
    # Repository exceptions
    "RepositoryNotFoundError",
    "RepositoryConflictError",
    "DuplicateDetectionError",
    # Connection exceptions
    "ConnectionPoolExhaustedError",
    # HTTP exceptions
    "HTTPError",
    "ValidationError",
    "AuthenticationError",
    "PermissionDeniedError",
    "HTTPNotFoundError",
    "ConflictError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    # LLM exceptions
    "LLMError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMProviderError",
    "LLMQuotaExceededError",
    "LLMInvalidResponseError",
    "AllLLMProvidersFailedError",
    # External API exceptions
    "ExternalAPIError",
    "APITimeoutError",
    "APIConnectionError",
    "APIAuthError",
    "APIRateLimitError",
    "APIServerError",
    "APIInvalidResponseError",
    "APIClientError",
    # Configuration exceptions
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigParseError",
    "ConfigValidationError",
    "ConfigMergeError",
    "EnvVarNotFoundError",
    "EnvVarSubstitutionError",
    # Cache exceptions
    "CacheError",
    "CacheConnectionError",
    "CacheTimeoutError",
    "CacheSerializationError",
    "CacheKeyError",
    "CacheCapacityError",
    "CacheQuotaExceededError",
]

