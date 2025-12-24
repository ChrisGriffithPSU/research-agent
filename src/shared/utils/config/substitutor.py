"""Environment variable substitution in configuration."""
import logging
import os
import re
from typing import Any, Dict

from src.shared.exceptions.config import EnvVarNotFoundError, EnvVarSubstitutionError


logger = logging.getLogger(__name__)

# Pattern to match ${VAR_NAME} or ${VAR:-default} or ${VAR=default} or ${VAR:?error}
ENV_PATTERN = re.compile(r'\\$\\{([^}:]+)\\}')

# Pattern to detect escaped variables: \${VAR}
ESCAPE_PATTERN = re.compile(r'\\\\$\\{([^}]+)\\}')


class EnvSubstitutor:
    """Substitutes environment variables in configuration.
    
    Supports:
    - Simple substitution: ${VAR_NAME} → env var value
    - Default value: ${VAR_NAME:-default} → default if missing
    - Error message: ${VAR_NAME:?error} → raises error if missing
    - Escaping: \${VAR} → literal ${VAR}
    
    Default value formats:
    - ${VAR:-default} (dash)
    - ${VAR=default} (equals)
    - Same as first match wins
    """
    
    def __init__(self):
        """Initialize environment substitutor."""
        pass
    
    def substitute(self, config: Any) -> Any:
        """Recursively substitute environment variables in config.
        
        Args:
            config: Configuration (dict, list, or scalar)
        
        Returns:
            Config with all ${VAR} patterns replaced with env var values
        """
        if isinstance(config, str):
            return self._substitute_in_string(config)
        elif isinstance(config, dict):
            return {k: self.substitute(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self.substitute(item) for item in config]
        else:
            return config  # Numbers, booleans, None unchanged
    
    def _substitute_in_string(self, value: str) -> str:
        """Substitute environment variables in a string.
        
        Handles:
        1. Remove escape sequences (\${VAR} → ${VAR})
        2. Find all ${VAR:...} patterns
        3. For each pattern:
           - Extract expression (VAR:-default, etc.)
           - Evaluate and substitute
        """
        # Step 1: Remove escape sequences
        unescaped = ESCAPE_PATTERN.sub(r'${\1}', value)
        
        # Step 2: Find all patterns and substitute
        def replace_match(match: re.Match) -> str:
            expression = match.group(1)
            return self._evaluate_expression(expression)
        
        result = ENV_PATTERN.sub(replace_match, unescaped)
        
        return result
    
    def _evaluate_expression(self, expression: str) -> str:
        """Evaluate environment variable expression.
        
        Supported formats:
        - VAR: Get env var, raise if missing
        - VAR:-default: Get env var, use default if missing
        - VAR=default: Get env var, use default if missing
        - VAR:?error: Get env var, raise error message if missing
        """
        # Check for default value (:- or =)
        if ':-' in expression:
            var_name, default_value = expression.split(':-', 1)
            return self._get_env_var(var_name, default=default_value)
        elif '=' in expression and ':' not in expression:
            var_name, default_value = expression.split('=', 1)
            return self._get_env_var(var_name, default=default_value)
        elif ':?' in expression:
            var_name, error_msg = expression.split(':?', 1)
            return self._get_env_var(var_name, error_message=error_msg)
        else:
            # Simple variable name, no default
            return self._get_env_var(expression)
    
    def _get_env_var(
        self,
        var_name: str,
        default: str = None,
        error_message: str = None,
    ) -> str:
        """Get environment variable with optional default or error.
        
        Args:
            var_name: Environment variable name
            default: Default value if var not found
            error_message: Error message if var not found and no default
        
        Returns:
            Environment variable value or default
        
        Raises:
            EnvVarNotFoundError: If var not found and no default
        """
        if var_name in os.environ:
            value = os.environ[var_name]
            logger.debug(
                f"Env var found: {var_name}",
                extra={"var_name": var_name, "value": f"{value[:20]}..."},
            )
            return value
        
        # Var not found
        if default is not None:
            logger.debug(
                f"Env var not found, using default: {var_name}",
                extra={"var_name": var_name, "default": f"{default[:20]}..."},
            )
            return default
        
        if error_message is not None:
            logger.error(
                f"Required env var missing: {var_name}",
                extra={"var_name": var_name, "error_message": error_message},
            )
            raise EnvVarNotFoundError(
                message=error_message or f"Environment variable '{var_name}' not found",
                var_name=var_name,
            suggestions=[
                    f"Set {var_name} in environment or .env file",
                    f"Or provide default: ${{{var_name}:-your_default}}}",
                ],
            )
        
        logger.error(
            f"Env var not found (no default): {var_name}",
            extra={"var_name": var_name},
        )
        raise EnvVarNotFoundError(
            message=f"Environment variable '{var_name}' not found",
            var_name=var_name,
            suggestions=[
                f"Set {var_name} in environment or .env file",
                f"Or provide default: ${{{var_name}:-your_default}}}",
            ],
        )

