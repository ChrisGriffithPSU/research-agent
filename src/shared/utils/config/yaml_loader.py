"""YAML file loader."""
import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.shared.exceptions.config import ConfigParseError


logger = logging.getLogger(__name__)


class YAMLLoader:
    """Loads YAML files into Python dictionaries."""
    
    def __init__(self):
        """Initialize YAML loader."""
        pass
    
    def load(self, path: Path) -> Dict[str, Any]:
        """Load YAML file into dictionary.
        
        Args:
            path: Path to YAML file
        
        Returns:
            Parsed YAML as dictionary
        
        Raises:
            ConfigParseError: If YAML syntax is invalid
        """
        try:
            logger.debug(f"Loading YAML file: {path}", extra={"path": str(path)})
            
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                
                if data is None:
                    logger.debug(f"YAML file is empty: {path}", extra={"path": str(path)})
                    return {}
                
                if not isinstance(data, dict):
                    logger.error(
                        f"YAML file must contain a dictionary: {path}",
                        extra={"path": str(path), "type": type(data).__name__},
                    )
                    raise ConfigParseError(
                        message=f"YAML must contain dictionary, got {type(data).__name__}",
                        config_file=str(path),
                    )
                
                logger.info(
                    f"YAML file loaded successfully: {path}",
                    extra={"path": str(path), "keys": list(data.keys())},
                )
                
                return data
        
        except yaml.YAMLError as e:
            logger.error(
                f"YAML parse error in {path}: {e}",
                extra={"path": str(path), "error": str(e)},
                exc_info=True,
            )
            
            # Extract line and column if available
            line_number = getattr(e, "problem_mark", {}).line if hasattr(e, "problem_mark") else None
            column_number = getattr(e, "problem_mark", {}).column if hasattr(e, "problem_mark") else None
            
            raise ConfigParseError(
                message=f"Failed to parse YAML file: {e}",
                config_file=str(path),
                line_number=line_number,
                column_number=column_number,
                original_error=e,
            )
        
        except IOError as e:
            logger.error(
                f"Failed to read file {path}: {e}",
                extra={"path": str(path), "error": str(e)},
                exc_info=True,
            )
            raise ConfigParseError(
                message=f"Failed to read config file: {e}",
                config_file=str(path),
                original_error=e,
            )
    
    def load_multiple(self, paths: List[Path]) -> Dict[str, Any]:
        """Load and merge multiple YAML files.
        
        Args:
            paths: List of YAML file paths (merged in order, later wins)
        
        Returns:
            Merged dictionary
        """
        if not paths:
            return {}
        
        merged = {}
        
        for path in paths:
            data = self.load(path)
            merged.update(data)
        
        return merged

