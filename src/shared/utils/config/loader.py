"""Config loader orchestrator - loads, merges, and validates configs."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from src.shared.utils.config.locator import find_config_path
from src.shared.utils.config.yaml_loader import YAMLLoader
from src.shared.utils.config.substitutor import EnvSubstitutor
from src.shared.utils.config.merger import ConfigMerger, ListMergeStrategy
from src.shared.exceptions.config import ConfigNotFoundError, ConfigValidationError


logger = logging.getLogger(__name__)


class ConfigLoader:
    """Orchestrates config loading, merging, and validation.
    
    Pipeline:
    1. Find config files (base + environment)
    2. Load YAML files
    3. Substitute environment variables
    4. Merge configs (base → environment)
    5. Validate against Pydantic schema
    6. Return validated model
    
    Example:
        loader = ConfigLoader()
        llm_config = loader.load_config("llm", env="dev", schema=LLMConfig)
    """
    
    def __init__(
        self,
        config_dir: Optional[str] = None,
        environments: Optional[List[str]] = None,
    ):
        """Initialize config loader.
        
        Args:
            config_dir: Path to config directory
            environments: List of environment names to search
        """
        self.config_dir = config_dir
        self.environments = environments
        self.yaml_loader = YAMLLoader()
        self.substitutor = EnvSubstitutor()
        self.merger = ConfigMerger()
        
        logger.debug(
            f"ConfigLoader initialized",
            extra={
                "config_dir": config_dir or "default",
                "environments": environments or ["base", "dev", "prod"],
            },
        )
    
    def load_raw_config(
        self,
        config_name: str,
        env: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load config without validation.
        
        Args:
            config_name: Name of config (e.g., "llm", "sources")
            env: Environment name (dev, prod). If None, tries all.
        
        Returns:
            Raw dictionary (merged, substituted)
        
        Raises:
            ConfigNotFoundError: Config files not found
        """
        # Find config paths
        try:
            base_path = find_config_path(config_name, env="base", config_dir=self.config_dir)
        except ConfigNotFoundError:
            # If base not found, still try to find env
            base_path = None
            logger.warning(
                f"Base config not found: {config_name}",
                extra={"config_name": config_name},
            )
        
        try:
            env_path = find_config_path(config_name, env=env, config_dir=self.config_dir, environments=self.environments) if env else None
        except ConfigNotFoundError:
            env_path = None
            logger.warning(
                f"Environment config not found: {config_name}, env={env}",
                extra={"config_name": config_name, "env": env},
            )
        
        if not base_path and not env_path:
            raise ConfigNotFoundError(
                config_name=config_name,
                searched_paths=[f"config/{e}/{config_name}.yaml" for e in self.environments] if self.environments else ["base", "dev", "prod"],
            )
        
        # Load configs
        configs_to_merge = []
        
        if base_path:
            base_config = self.yaml_loader.load(base_path)
            configs_to_merge.append(base_config)
            logger.debug(
                f"Loaded base config: {base_path}",
                extra={"config_name": config_name, "path": str(base_path), "keys": len(base_config)},
            )
        
        if env_path:
            env_config = self.yaml_loader.load(env_path)
            configs_to_merge.append(env_config)
            logger.debug(
                f"Loaded environment config: {env_path}",
                extra={"config_name": config_name, "env": env, "path": str(env_path), "keys": len(env_config)},
            )
        
        # Merge configs (later configs override earlier)
        if len(configs_to_merge) == 1:
            merged_config = configs_to_merge[0]
        elif len(configs_to_merge) > 1:
            merged_config = self.merger.merge_multiple(*configs_to_merge)
        else:
            merged_config = {}
        
        # Substitute environment variables
        substituted_config = self.substitutor.substitute(merged_config)
        
        logger.info(
            f"Config loaded: {config_name}",
            extra={
                "config_name": config_name,
                "env": env,
                "final_keys": len(substituted_config),
            },
        )
        
        return substituted_config
    
    def load_config(
        self,
        config_name: str,
        env: Optional[str] = None,
        schema: Type[BaseModel],
        list_merge_strategy: ListMergeStrategy = ListMergeStrategy.REPLACE,
    ) -> BaseModel:
        """Load and validate config.
        
        Args:
            config_name: Name of config
            env: Environment name
            schema: Pydantic model for validation
            list_merge_strategy: How to merge lists (replace, extend, prepend)
        
        Returns:
            Validated Pydantic model instance
        
        Raises:
            ConfigNotFoundError: Config files not found
            ConfigValidationError: Config fails validation
        """
        # Configure list merge strategy
        self.merger.list_strategy = list_merge_strategy
        
        # Load raw config
        raw_config = self.load_raw_config(config_name, env=env)
        
        # Validate against schema
        try:
            validated_config = schema(**raw_config)
            logger.info(
                f"Config validated: {config_name}",
                extra={
                    "config_name": config_name,
                    "schema": schema.__name__,
                    "valid": True,
                },
            )
            return validated_config
        
        except ValidationError as e:
            logger.error(
                f"Config validation failed: {config_name}",
                extra={
                    "config_name": config_name,
                    "schema": schema.__name__,
                    "error_count": len(e.errors()),
                },
            )
            raise ConfigValidationError(
                message=f"Configuration validation failed for {config_name}",
                field_errors={err["loc"][-1] if err["loc"] else "root": err["msg"] for err in e.errors()},
                original_error=e,
            )


def load_config(
    config_name: str,
    env: Optional[str] = None,
    schema: Optional[Type[BaseModel]] = None,
    config_dir: Optional[str] = None,
) -> Any:
    """Convenience function to load config.
    
    Args:
        config_name: Name of config
        env: Environment name
        schema: Pydantic model (optional, if None returns raw dict)
        config_dir: Path to config directory
    
    Returns:
        Validated Pydantic model or raw dict
    
    Example:
        # Returns LLMConfig model
        llm_config = load_config("llm", env="dev", schema=LLMConfig)
        
        # Returns raw dict
        llm_dict = load_config("llm", env="dev")
    """
    loader = ConfigLoader(config_dir=config_dir)
    return loader.load_config(config_name, env=env, schema=schema)

