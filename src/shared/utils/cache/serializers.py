"""Cache serialization strategies."""
import json
import logging
from typing import Any

# Pickle will be imported when needed
# import pickle


logger = logging.getLogger(__name__)


class Serializer:
    """Base class for cache serializers.
    
    Defines interface for converting between Python objects and cache-storable format.
    """
    
    def serialize(self, value: Any) -> bytes:
        """Serialize value to bytes.
        
        Args:
            value: Python object to serialize
        
        Returns:
            Serialized bytes
        
        Raises:
            CacheSerializationError: If serialization fails
        """
        raise NotImplementedError("Subclasses must implement serialize()")
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to Python object.
        
        Args:
            data: Serialized bytes
        
        Returns:
            Deserialized Python object
        
        Raises:
            CacheSerializationError: If deserialization fails
        """
        raise NotImplementedError("Subclasses must implement deserialize()")


class JSONSerializer(Serializer):
    """JSON-based serializer for cache values.
    
    Supports:
    - Dicts
    - Lists
    - Strings, ints, floats, bools
    - None
    - Datetime objects (ISO format strings)
    
    Does NOT support:
    - Custom classes (use PickleSerializer)
    - Circular references
    """
    
    def serialize(self, value: Any) -> bytes:
        """Serialize value to JSON bytes."""
        if value is None:
            return b"null"
        
        try:
            # Use default=str for datetime and other non-JSON types
            json_str = json.dumps(value, default=str)
            return json_str.encode("utf-8")
        
        except TypeError as e:
            logger.error(f"JSON serialization failed: {e}", exc_info=True)
            raise TypeError(f"Value is not JSON-serializable: {e}")
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize JSON bytes to Python object."""
        try:
            json_str = data.decode("utf-8")
            return json.loads(json_str)
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON deserialization failed: {e}", exc_info=True)
            raise ValueError(f"Invalid JSON data: {e}")


class PickleSerializer(Serializer):
    """Pickle-based serializer for cache values.
    
    Supports:
    - Any Python object
    - Custom classes
    - Circular references
    
    Security Warning:
    - Pickle can execute arbitrary code on deserialization
    - Only use with trusted data sources
    """
    
    def serialize(self, value: Any) -> bytes:
        """Serialize value using pickle."""
        try:
            import pickle
            return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        
        except Exception as e:
            logger.error(f"Pickle serialization failed: {e}", exc_info=True)
            raise TypeError(f"Failed to serialize with pickle: {e}")
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize pickle bytes to Python object."""
        try:
            import pickle
            return pickle.loads(data)
        
        except Exception as e:
            logger.error(f"Pickle deserialization failed: {e}", exc_info=True)
            raise ValueError(f"Invalid pickle data: {e}")


class StringSerializer(Serializer):
    """Simple string serializer for text values.

    Useful for caching simple strings without JSON overhead.
    """
    
    def serialize(self, value: Any) -> bytes:
        """Serialize value to bytes (UTF-8)."""
        if not isinstance(value, str):
            logger.warning(f"StringSerializer received non-string value: {type(value)}")
            value = str(value)
        
        return value.encode("utf-8")
    
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to string."""
        try:
            return data.decode("utf-8")
        
        except UnicodeDecodeError as e:
            logger.error(f"UTF-8 deserialization failed: {e}", exc_info=True)
            raise ValueError(f"Invalid UTF-8 data: {e}")


def get_serializer(serializer_type: str = "json") -> Serializer:
    """Factory function to get serializer by type.
    
    Args:
        serializer_type: Type of serializer ("json", "pickle", "string")
    
    Returns:
        Serializer instance
    
    Example:
        serializer = get_serializer("json")  # Returns JSONSerializer
        serializer = get_serializer("pickle")  # Returns PickleSerializer
    """
    serializers = {
        "json": JSONSerializer(),
        "pickle": PickleSerializer(),
        "string": StringSerializer(),
    }
    
    if serializer_type not in serializers:
        logger.warning(f"Unknown serializer type: {serializer_type}, using json")
        serializer_type = "json"
    
    return serializers[serializer_type]

