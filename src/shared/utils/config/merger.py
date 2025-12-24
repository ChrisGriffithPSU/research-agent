"""Config merger for combining multiple config dictionaries."""
import logging
from enum import Enum
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class ListMergeStrategy(Enum):
    """Strategy for merging list values."""
    REPLACE = "replace"      # Override list completely
    EXTEND = "extend"        # Append override elements to base list
    PREPEND = "prepend"      # Prepend override elements to base list


class ConfigMerger:
    """Deep merges configuration dictionaries.
    
    Merge rules:
    - Dicts: Merged recursively
    - Lists: Merged based on ListMergeStrategy
    - Scalars (int, str, bool, etc.): Overridden by value
    
    Example:
        base = {"sources": ["arxiv", "kaggle"]}
        override = {"sources": ["web_search"], "models": {"claude": "sonnet"}}
        
        With REPLACE strategy:
            result = {"sources": ["web_search"], "models": {"claude": "sonnet"}}
        
        With EXTEND strategy:
            result = {"sources": ["arxiv", "kaggle", "web_search"], "models": {"claude": "sonnet"}}
    """
    
    def __init__(self, list_strategy: ListMergeStrategy = ListMergeStrategy.REPLACE):
        """Initialize config merger.
        
        Args:
            list_strategy: Strategy for merging lists
        """
        self.list_strategy = list_strategy
        
        logger.debug(
            f"ConfigMerger initialized",
            extra={"list_strategy": list_strategy.value},
        )
    
    def merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override into base config.
        
        Args:
            base: Base configuration (lower priority)
            override: Override configuration (higher priority)
        
        Returns:
            Merged configuration (new dict, inputs not modified)
        """
        if not base:
            return override.copy() if override else {}
        
        if not override:
            return base.copy()
        
        # Create new dict (don't modify inputs)
        result = base.copy()
        
        for key, override_value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(override_value, dict):
                # Both dicts: merge recursively
                result[key] = self.merge(result[key], override_value)
            elif key in result and isinstance(result[key], list) and isinstance(override_value, list):
                # Both lists: merge based on strategy
                result[key] = self._merge_lists(result[key], override_value)
            else:
                # Scalar or type mismatch: override
                result[key] = override_value
        
        logger.debug(
            f"Configs merged",
            extra={
                "base_keys": len(base),
                "override_keys": len(override),
                "result_keys": len(result),
                "list_strategy": self.list_strategy.value,
            },
        )
        
        return result
    
    def _merge_lists(self, base_list: List[Any], override_list: List[Any]) -> List[Any]:
        """Merge two lists based on configured strategy."""
        if self.list_strategy == ListMergeStrategy.REPLACE:
            return override_list.copy()
        elif self.list_strategy == ListMergeStrategy.EXTEND:
            return base_list + override_list
        elif self.list_strategy == ListMergeStrategy.PREPEND:
            return override_list + base_list
        else:
            raise ValueError(f"Unknown list strategy: {self.list_strategy}")
    
    def merge_multiple(
        self,
        *configs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge multiple configs in order (left to right, right wins).
        
        Args:
            *configs: Multiple configs to merge (merged left to right)
        
        Returns:
            Final merged config
        """
        if not configs:
            return {}
        
        result = configs[0].copy()
        
        for config in configs[1:]:
            result = self.merge(result, config)
        
        return result


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function for deep merging configs."""
    merger = ConfigMerger()
    return merger.merge(base, override)

