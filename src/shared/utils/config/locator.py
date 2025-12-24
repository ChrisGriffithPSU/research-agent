"""Config file locator for finding config across environments."""
import os
from pathlib import Path
from typing import List, Optional

from src.shared.exceptions.config import ConfigNotFoundError


logger = logging.getLogger(__name__)


class ConfigLocator:
    """Locates configuration files in config directory.
    
    Search order:
    1. Environment-specific config: config/{env}/{config_name}.yaml
    2. Base config: config/base/{config_name}.yaml
    3. Current directory fallback: ./{config_name}.yaml
    """
    
    def __init__(
        self,
        config_dir: Optional[str] = None,
        environments: List[str] = None,
    ):
        """Initialize config locator.
        
        Args:
            config_dir: Path to config directory (default: ./config)
            environments: List of environment names (default: ["base", "dev", "prod"])
        """
        self.config_dir = Path(config_dir or "./config")
        self.environments = environments or ["base", "dev", "prod"]
        
        logger.debug(
            f"ConfigLocator initialized",
            extra={"config_dir": str(self.config_dir), "environments": self.environments},
        )
    
    def find_config_path(
        self,
        config_name: str,
        env: Optional[str] = None,
    ) -> Path:
        """Find configuration file for given name and environment.
        
        Args:
            config_name: Name of config (e.g., "llm", "sources")
            env: Environment name (dev, prod). If None, tries all.
        
        Returns:
            Path to first found config file
        
        Raises:
            ConfigNotFoundError: If config file not found
        """
        # Try environment-specific first if env provided
        if env:
            env_path = self.config_dir / env / f"{config_name}.yaml"
            if env_path.exists():
                logger.info(f"Found config at {env_path}", extra={"config_name": config_name, "env": env, "path": str(env_path)})
                return env_path
            logger.debug(
                f"Environment config not found: {env_path}",
                extra={"config_name": config_name, "env": env, "path": str(env_path)},
            )
        
        # Search for config in all environments
        searched_paths: List[Path] = []
        
        for environment in self.environments:
            config_path = self.config_dir / environment / f"{config_name}.yaml"
            searched_paths.append(config_path)
            
            if config_path.exists():
                logger.info(
                    f"Found config at {config_path}",
                    extra={
                        "config_name": config_name,
                        "environment": environment,
                        "path": str(config_path),
                    },
                )
                return config_path
        
        # Fallback to current directory
        cwd_path = Path.cwd() / f"{config_name}.yaml"
        searched_paths.append(cwd_path)
        
        if cwd_path.exists():
            logger.warning(
                f"Found config in current directory (not recommended): {cwd_path}",
                extra={"config_name": config_name, "path": str(cwd_path)},
            )
            return cwd_path
        
        # Not found anywhere
        searched_paths_str = [str(p) for p in searched_paths]
        
        logger.error(
            f"Config file not found: {config_name}",
            extra={
                "config_name": config_name,
                "searched_paths": searched_paths_str,
            },
        )
        
        raise ConfigNotFoundError(
            config_name=config_name,
            searched_paths=searched_paths_str,
        )


def find_config_path(config_name: str, env: Optional[str] = None) -> Path:
    """Convenience function to find config path.
    
    Args:
        config_name: Name of config
        env: Environment name (optional)
    
    Returns:
        Path to config file
    """
    locator = ConfigLocator()
    return locator.find_config_path(config_name, env=env)

