# Constitutional Hash: cdd01ef066bc6cf2
"""JSON and data structure type aliases for ACGS-2."""

from typing import Any

# General JSON types - use these for JSON payloads, API responses, config files
JSONPrimitive = str | int | float | bool | None
JSONDict = dict[str, Any]  # Still requires object for deep recursion in standard typing
JSONList = list[Any]
JSONValue = JSONPrimitive | JSONDict | JSONList

# Recursive JSON types (supported in Python 3.11+)
JSONType = str | int | float | bool | None | dict[str, "JSONType"] | list["JSONType"]
RecursiveDict = dict[str, JSONType]
RecursiveList = list[JSONType]

# More specific JSON structures
NestedDict = JSONDict  # For deeply nested structures
StringDict = dict[str, str]  # For simple string-to-string mappings
MetadataDict = dict[str, JSONValue]  # For metadata fields
AttributeDict = dict[str, JSONValue]  # For attribute collections

__all__ = [
    "AttributeDict",
    "JSONDict",
    "JSONList",
    "JSONPrimitive",
    "JSONType",
    "JSONValue",
    "MetadataDict",
    "NestedDict",
    "RecursiveDict",
    "RecursiveList",
    "StringDict",
]
