"""
ACGS-2 High-Performance JSON Utilities
Constitutional Hash: 608508a9bd224290

Provides optimized JSON serialization using orjson for maximum performance.
Includes fallbacks for environments where orjson is not available.
"""

import json

try:
    from src.core.shared.types import JSONDict, JSONValue
except ImportError:
    JSONValue = object
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]

try:
    import orjson

    # Use orjson for maximum performance
    def dumps(obj: JSONValue, *, default=None, option=None, **kwargs) -> str:
        """Fast JSON serialization using orjson."""
        try:
            if default:
                return orjson.dumps(obj, default=default, option=option).decode("utf-8")
            return orjson.dumps(obj, option=option).decode("utf-8")
        except (TypeError, ValueError):
            # Fallback to standard json for complex objects
            return json.dumps(obj, default=str, **kwargs)

    def loads(s: str | bytes, **kwargs) -> JSONValue:
        """Fast JSON deserialization using orjson."""
        try:
            if isinstance(s, str):
                s = s.encode("utf-8")
            return orjson.loads(s)
        except (orjson.JSONDecodeError, UnicodeDecodeError):
            # Fallback to standard json
            if isinstance(s, bytes):
                s = s.decode("utf-8")
            return json.loads(s, **kwargs)

except ImportError:
    # Fallback to standard library json
    def dumps(obj: JSONValue, *, default=None, option=None, **kwargs) -> str:
        """Standard JSON serialization when orjson unavailable."""
        return json.dumps(obj, default=default or str, **kwargs)

    def loads(s: str | bytes, **kwargs) -> JSONValue:
        """Standard JSON deserialization when orjson unavailable."""
        if isinstance(s, bytes):
            s = s.decode("utf-8")
        return json.loads(s, **kwargs)


# Convenience functions for common use cases
def dump_bytes(obj: JSONValue) -> bytes:
    """Serialize to JSON bytes (orjson optimized)."""
    try:
        import orjson

        return orjson.dumps(obj)
    except ImportError:
        return json.dumps(obj, default=str).encode("utf-8")


def dump_compact(obj: JSONValue) -> str:
    """Serialize to compact JSON string (no whitespace)."""
    try:
        import orjson

        return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS).decode("utf-8")
    except ImportError:
        return json.dumps(obj, separators=(",", ":"), default=str)


def dump_pretty(obj: JSONValue, indent: int = 2) -> str:
    """Serialize to pretty-printed JSON string."""
    return json.dumps(obj, indent=indent, default=str)
