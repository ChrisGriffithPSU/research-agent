"""Configuration-related exceptions."""
from typing import Optional


class ConfigError(Exception):
    """Base exception for configuration errors.
    
    Args:
        message: Human-readable error message
        config_file: Path to config file
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.config_file = config_file
        self.details = details or {}
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.config_file:
            parts.append(f"Config: {self.config_file}")
        return " | ".join(parts)


class ConfigNotFoundError(ConfigError):
    """Configuration file not found."""
    
    def __init__(
        self,
        message: str = "Configuration file not found",
        config_name: Optional[str] = None,
        searched_paths: Optional[list] = None,
    ):
        details = {}
        if config_name is not None:
            details["config_name"] = config_name
        if searched_paths is not None:
            details["searched_paths"] = searched_paths
        super().__init__(message, None, details)


class ConfigParseError(ConfigError):
    """Failed to parse configuration file."""
    
    def __init__(
        self,
        message: str = "Failed to parse config file",
        config_file: Optional[str] = None,
        line_number: Optional[int] = None,
        column_number: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if line_number is not None:
            details["line"] = line_number
        if column_number is not None:
            details["column"] = column_number
        super().__init__(message, config_file, details)
        self.original_error = original_error


class ConfigValidationError(ConfigError):
    """Configuration failed validation."""
    
    def __init__(
        self,
        message: str = "Configuration validation failed",
        config_file: Optional[str] = None,
        field_errors: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if field_errors is not None:
            details["field_errors"] = field_errors
        super().__init__(message, config_file, details)
        self.original_error = original_error


class ConfigMergeError(ConfigError):
    """Failed to merge configuration files."""
    
    def __init__(
        self,
        message: str = "Failed to merge configurations",
        config_files: Optional[list] = None,
        conflict_path: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if config_files is not None:
            details["config_files"] = config_files
        if conflict_path is not None:
            details["conflict_path"] = conflict_path
        super().__init__(message, None, details)
        self.original_error = original_error


class EnvVarNotFoundError(ConfigError):
    """Required environment variable not found."""
    
    def __init__(
        self,
        message: str = "Environment variable not found",
        var_name: Optional[str] = None,
        suggestions: Optional[list] = None,
    ):
        details = {}
        if var_name is not None:
            details["var_name"] = var_name
        if suggestions is not None:
            details["suggestions"] = suggestions
        super().__init__(message, None, details)


class EnvVarSubstitutionError(ConfigError):
    """Failed to substitute environment variable."""
    
    def __init__(
        self,
        message: str = "Environment variable substitution failed",
        var_name: Optional[str] = None,
        expression: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if var_name is not None:
            details["var_name"] = var_name
        if expression is not None:
            details["expression"] = expression
        super().__init__(message, None, details)
        self.original_error = original_error

