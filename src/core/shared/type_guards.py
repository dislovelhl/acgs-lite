"""
Type Guards and Type Narrowing Utilities for ACGS-2

This module provides TypeGuard functions for runtime type checking
and type narrowing in security-critical code paths.

Constitutional Hash: cdd01ef066bc6cf2

Usage:
    from src.core.shared.type_guards import is_json_dict, is_non_empty_str

    if is_json_dict(data):
        # data is now narrowed to JSONDict
        value = data.get("key")
"""

from typing import TypeGuard

from .types import JSONDict, JSONValue

# Constitutional hash for module verification
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ============================================================================
# JSON Type Guards
# ============================================================================


def is_json_dict(value: object) -> TypeGuard[JSONDict]:
    """Type guard for JSONDict (dict[str, object]).

    Args:
        value: Value to check

    Returns:
        True if value is a dict with string keys
    """
    return isinstance(value, dict) and all(isinstance(k, str) for k in value.keys())


def is_json_value(value: object) -> TypeGuard[JSONValue]:
    """Type guard for valid JSON values.

    Args:
        value: Value to check

    Returns:
        True if value is a valid JSON type (str, int, float, bool, None, dict, list)
    """
    if value is None:
        return True
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, dict):
        return all(isinstance(k, str) for k in value.keys())
    return bool(isinstance(value, list))


def is_string_dict(value: object) -> TypeGuard[dict[str, str]]:
    """Type guard for dict[str, str].

    Args:
        value: Value to check

    Returns:
        True if value is a dict with string keys and string values
    """
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


# ============================================================================
# String Type Guards
# ============================================================================


def is_non_empty_str(value: object) -> TypeGuard[str]:
    """Type guard for non-empty strings.

    Args:
        value: Value to check

    Returns:
        True if value is a non-empty string
    """
    return isinstance(value, str) and len(value) > 0


def is_str(value: object) -> TypeGuard[str]:
    """Type guard for strings (including empty).

    Args:
        value: Value to check

    Returns:
        True if value is a string
    """
    return isinstance(value, str)


# ============================================================================
# List Type Guards
# ============================================================================


def is_str_list(value: object) -> TypeGuard[list[str]]:
    """Type guard for list of strings.

    Args:
        value: Value to check

    Returns:
        True if value is a list of strings
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_dict_list(value: object) -> TypeGuard[list[JSONDict]]:
    """Type guard for list of JSON dicts.

    Args:
        value: Value to check

    Returns:
        True if value is a list of dicts with string keys
    """
    return isinstance(value, list) and all(is_json_dict(item) for item in value)


# ============================================================================
# Numeric Type Guards
# ============================================================================


def is_positive_int(value: object) -> TypeGuard[int]:
    """Type guard for positive integers.

    Args:
        value: Value to check

    Returns:
        True if value is a positive integer
    """
    return isinstance(value, int) and value > 0


def is_non_negative_float(value: object) -> TypeGuard[float]:
    """Type guard for non-negative floats (including int).

    Args:
        value: Value to check

    Returns:
        True if value is a non-negative number
    """
    return isinstance(value, (int, float)) and value >= 0


def is_probability(value: object) -> TypeGuard[float]:
    """Type guard for probability values [0.0, 1.0].

    Args:
        value: Value to check

    Returns:
        True if value is a float in [0.0, 1.0]
    """
    return isinstance(value, (int, float)) and 0.0 <= value <= 1.0


# ============================================================================
# Security Context Type Guards
# ============================================================================


def is_security_context(value: object) -> TypeGuard[JSONDict]:
    """Type guard for security context dictionaries.

    Validates that the value has required security context fields.

    Args:
        value: Value to check

    Returns:
        True if value is a valid security context
    """
    if not is_json_dict(value):
        return False
    # Security contexts should have at least one identifying field
    return bool(
        value.get("user_id")
        or value.get("agent_id")
        or value.get("tenant_id")
        or value.get("session_id")
    )


def is_agent_context(value: object) -> TypeGuard[JSONDict]:
    """Type guard for agent context dictionaries.

    Validates that the value has agent-specific fields.

    Args:
        value: Value to check

    Returns:
        True if value is a valid agent context
    """
    if not is_json_dict(value):
        return False
    return "agent_id" in value


def is_policy_result(value: object) -> TypeGuard[JSONDict]:
    """Type guard for OPA policy evaluation results.

    Args:
        value: Value to check

    Returns:
        True if value looks like a policy result
    """
    if not is_json_dict(value):
        return False
    # Policy results typically have 'allowed', 'allow', or 'result' fields
    return "allowed" in value or "allow" in value or "result" in value


# ============================================================================
# Content Type Guards (for injection detection)
# ============================================================================


def is_content_with_text(value: object) -> TypeGuard[dict[str, str]]:
    """Type guard for content dict with 'text' field.

    Args:
        value: Value to check

    Returns:
        True if value is a dict with a 'text' string field
    """
    return is_json_dict(value) and isinstance(value.get("text"), str)


def is_message_content(value: object) -> TypeGuard[JSONDict]:
    """Type guard for message content structures.

    Args:
        value: Value to check

    Returns:
        True if value looks like message content
    """
    if not is_json_dict(value):
        return False
    # Message content typically has content, body, or data fields
    return "content" in value or "body" in value or "data" in value or "text" in value


# ============================================================================
# Optional Value Extraction (Safe Getters)
# ============================================================================


def get_str(d: JSONDict, key: str, default: str = "") -> str:
    """Safely get a string value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        String value or default
    """
    value = d.get(key)
    return value if isinstance(value, str) else default


def get_int(d: JSONDict, key: str, default: int = 0) -> int:
    """Safely get an int value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        Int value or default
    """
    value = d.get(key)
    return value if isinstance(value, int) else default


def get_float(d: JSONDict, key: str, default: float = 0.0) -> float:
    """Safely get a float value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        Float value or default
    """
    value = d.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def get_bool(d: JSONDict, key: str, default: bool = False) -> bool:
    """Safely get a bool value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        Bool value or default
    """
    value = d.get(key)
    return value if isinstance(value, bool) else default


def get_dict(d: JSONDict, key: str, default: JSONDict | None = None) -> JSONDict:
    """Safely get a dict value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        Dict value or default (empty dict if default is None)
    """
    value = d.get(key)
    if is_json_dict(value):
        return value
    return default if default is not None else {}


def get_list(d: JSONDict, key: str, default: list[JSONValue] | None = None) -> list[JSONValue]:
    """Safely get a list value from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        List value or default (empty list if default is None)
    """
    value = d.get(key)
    if isinstance(value, list):
        return value
    return default if default is not None else []


def get_str_list(d: JSONDict, key: str, default: list[str] | None = None) -> list[str]:
    """Safely get a list of strings from a dict.

    Args:
        d: Dictionary to get from
        key: Key to look up
        default: Default value if key missing or wrong type

    Returns:
        List of strings or default
    """
    value = d.get(key)
    if is_str_list(value):
        return value
    return default if default is not None else []


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "get_bool",
    "get_dict",
    "get_float",
    "get_int",
    "get_list",
    # Safe getters
    "get_str",
    "get_str_list",
    "is_agent_context",
    # Content type guards
    "is_content_with_text",
    "is_dict_list",
    # JSON type guards
    "is_json_dict",
    "is_json_value",
    "is_message_content",
    # String type guards
    "is_non_empty_str",
    "is_non_negative_float",
    "is_policy_result",
    # Numeric type guards
    "is_positive_int",
    "is_probability",
    # Security type guards
    "is_security_context",
    "is_str",
    # List type guards
    "is_str_list",
    "is_string_dict",
]
