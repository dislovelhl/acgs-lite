"""Shim for src.core.shared.type_guards."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.type_guards import *  # noqa: F403
except ImportError:

    def is_str(value: Any) -> bool:
        return isinstance(value, str)

    def is_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def is_float(value: Any) -> bool:
        return isinstance(value, float)

    def is_bool(value: Any) -> bool:
        return isinstance(value, bool)

    def is_dict(value: Any) -> bool:
        return isinstance(value, dict)

    def is_list(value: Any) -> bool:
        return isinstance(value, list)

    def is_none(value: Any) -> bool:
        return value is None

    def is_not_none(value: Any) -> bool:
        return value is not None

    def is_json_primitive(value: Any) -> bool:
        return isinstance(value, (str, int, float, bool, type(None)))

    def ensure_str(value: Any, default: str = "") -> str:
        return value if isinstance(value, str) else default

    def ensure_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
