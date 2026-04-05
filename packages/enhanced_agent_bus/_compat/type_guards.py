"""Shim for src.core.shared.type_guards."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.type_guards import *  # noqa: F403
    from src.core.shared.type_guards import (
        get_bool,
        get_dict,
        get_float,
        get_int,
        get_list,
        get_str,
        get_str_list,
        is_json_dict,
        is_json_value,
        is_str,
        is_str_list,
    )
except ImportError:

    def is_str(value: Any) -> bool:
        return isinstance(value, str)

    def is_str_list(value: Any) -> bool:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)

    def is_json_dict(value: Any) -> bool:
        return isinstance(value, dict) and all(isinstance(k, str) for k in value)

    def is_json_value(value: Any) -> bool:
        return isinstance(value, (str, int, float, bool, type(None), dict, list))

    def get_str(data: dict, key: str, default: str = "") -> str:
        v = data.get(key, default)
        return v if isinstance(v, str) else default

    def get_int(data: dict, key: str, default: int = 0) -> int:
        v = data.get(key, default)
        return v if isinstance(v, int) and not isinstance(v, bool) else default

    def get_float(data: dict, key: str, default: float = 0.0) -> float:
        v = data.get(key, default)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default

    def get_bool(data: dict, key: str, default: bool = False) -> bool:
        v = data.get(key, default)
        return v if isinstance(v, bool) else default

    def get_dict(data: dict, key: str, default: dict | None = None) -> dict:
        v = data.get(key, default or {})
        return v if isinstance(v, dict) else (default or {})

    def get_list(data: dict, key: str, default: list | None = None) -> list:
        v = data.get(key, default or [])
        return v if isinstance(v, list) else (default or [])

    def get_str_list(data: dict, key: str, default: list | None = None) -> list[str]:
        v = data.get(key, default or [])
        if isinstance(v, list):
            return [str(x) for x in v]
        return default or []

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

    def is_json_primitive(value: Any) -> bool:
        return isinstance(value, (str, int, float, bool, type(None)))

    def ensure_str(value: Any, default: str = "") -> str:
        return value if isinstance(value, str) else default

    def ensure_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
