"""Centralized type definitions for enhanced_agent_bus.

Constitutional Hash: 608508a9bd224290

This module provides all common type aliases used throughout the enhanced_agent_bus
package, eliminating duplicate definitions and ensuring type consistency.
"""

import sys
from collections.abc import Callable
from typing import TypeAlias, TypeVar

# Ensure module aliasing across package import paths
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.types", _module)
    sys.modules.setdefault("enhanced_agent_bus.bus_types", _module)
    sys.modules.setdefault("core.enhanced_agent_bus.types", _module)

# JSON types - for working with JSON-compatible data structures
# Using object instead of recursive self-reference to avoid Pydantic model_rebuild
# issues on Python 3.13+ (recursive TypeAlias not resolved at validation time)
JSONValue: TypeAlias = str | int | float | bool | None | dict[str, object] | list[object]
JSONDict: TypeAlias = dict[str, object]

# Domain types - semantic aliases for common patterns
SecurityContext: TypeAlias = JSONDict
MetadataDict: TypeAlias = JSONDict
PerformanceMetrics: TypeAlias = dict[str, float]
MessagePayload: TypeAlias = JSONDict

# Callback and handler types
CallbackType: TypeAlias = Callable[..., object]
AsyncCallbackType: TypeAlias = Callable[..., object]  # For async callbacks

# Type variables for generic programming
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# Re-export for convenience
__all__ = [
    "AsyncCallbackType",
    "CallbackType",
    "JSONDict",
    "JSONValue",
    "K",
    "MessagePayload",
    "MetadataDict",
    "PerformanceMetrics",
    "SecurityContext",
    "T",
    "V",
]
