"""Shim for src.core.shared.json_utils."""
from __future__ import annotations

try:
    from src.core.shared.json_utils import *  # noqa: F403
    from src.core.shared.json_utils import dump_bytes, dump_compact, dump_pretty, dumps, loads
except ImportError:
    import json
    from typing import Any

    def dumps(obj: Any, *, default: Any = None, option: Any = None, **kwargs: Any) -> str:
        try:
            import orjson
            if default:
                return orjson.dumps(obj, default=default, option=option).decode("utf-8")
            return orjson.dumps(obj, option=option).decode("utf-8")
        except (ImportError, TypeError, ValueError):
            return json.dumps(obj, default=default or str, **kwargs)

    def loads(s: str | bytes, **kwargs: Any) -> Any:
        try:
            import orjson
            if isinstance(s, str):
                s = s.encode("utf-8")
            return orjson.loads(s)
        except ImportError:
            if isinstance(s, bytes):
                s = s.decode("utf-8")
            return json.loads(s, **kwargs)

    def dump_bytes(obj: Any) -> bytes:
        try:
            import orjson
            return orjson.dumps(obj)
        except ImportError:
            return json.dumps(obj, default=str).encode("utf-8")

    def dump_compact(obj: Any) -> str:
        try:
            import orjson
            return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS).decode("utf-8")
        except ImportError:
            return json.dumps(obj, separators=(",", ":"), default=str)

    def dump_pretty(obj: Any, indent: int = 2) -> str:
        return json.dumps(obj, indent=indent, default=str)
