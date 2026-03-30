"""Redaction helpers for flywheel dataset export."""

from __future__ import annotations

import re
from typing import Any

REDACTED_TOKEN = "[REDACTED]"
_SENSITIVE_KEY_FRAGMENTS = (
    "email",
    "phone",
    "ip",
    "address",
    "user_id",
    "authenticated_user_id",
    "name",
    "title",
    "description",
    "comment",
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def redact_for_dataset_export(value: Any) -> Any:
    """Recursively redact obvious PII before dataset export."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_TOKEN if item not in (None, "") else item
            else:
                redacted[key] = redact_for_dataset_export(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_dataset_export(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_dataset_export(item) for item in value)
    if isinstance(value, str):
        return _EMAIL_PATTERN.sub(REDACTED_TOKEN, _IPV4_PATTERN.sub(REDACTED_TOKEN, value))
    return value


def contains_unredacted_pii(value: Any) -> bool:
    """Detect obvious email and IPv4 leakage after redaction."""
    if isinstance(value, dict):
        return any(contains_unredacted_pii(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(contains_unredacted_pii(item) for item in value)
    if isinstance(value, str):
        return bool(_EMAIL_PATTERN.search(value) or _IPV4_PATTERN.search(value))
    return False


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower()
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


__all__ = ["REDACTED_TOKEN", "contains_unredacted_pii", "redact_for_dataset_export"]
