# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Shared serialization helpers for governance validation payloads.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

_MAX_GOVERNANCE_PAYLOAD_CHARS = 10_000


def _truncate_payload(payload: str, *, max_chars: int) -> str:
    if len(payload) <= max_chars:
        return payload
    suffix = "… [truncated]"
    return payload[: max_chars - len(suffix)] + suffix


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return dict_method()
    if isinstance(value, set):
        return sorted(value, key=str)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (dict, list)):
        return value
    raw_dict = getattr(value, "__dict__", None)
    if isinstance(raw_dict, dict) and raw_dict:
        return raw_dict
    return value


def serialize_for_governance(value: Any, *, max_chars: int = _MAX_GOVERNANCE_PAYLOAD_CHARS) -> str:
    """Convert a value into a stable string payload for governance validation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _truncate_payload(value, max_chars=max_chars)

    jsonable = _to_jsonable(value)
    if jsonable is value and not isinstance(value, (dict, list, tuple, set)):
        return ""

    try:
        payload = json.dumps(jsonable, default=str, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload = str(jsonable)
    return _truncate_payload(payload, max_chars=max_chars)


def iter_governance_payloads(*values: Any, max_chars: int = _MAX_GOVERNANCE_PAYLOAD_CHARS) -> list[str]:
    """Collect non-empty governance payloads from positional or keyword values."""
    payloads: list[str] = []
    for value in values:
        payload = serialize_for_governance(value, max_chars=max_chars)
        if payload:
            payloads.append(payload)
    return payloads


__all__ = ["iter_governance_payloads", "serialize_for_governance"]
