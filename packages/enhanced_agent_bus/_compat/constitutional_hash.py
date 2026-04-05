"""Shim for src.core.shared.constitutional_hash."""

from __future__ import annotations

try:
    from src.core.shared.constitutional_hash import *  # noqa: F403
except ImportError:
    CANONICAL_HASH = "608508a9bd224290"

    def validate_constitutional_hash(h: str) -> bool:
        """Return True if *h* matches the canonical hash."""
        return h == CANONICAL_HASH

    def get_constitutional_hash() -> str:
        return CANONICAL_HASH

    def get_constitutional_hash_versioned() -> str:
        return f"sha256:v1:{CANONICAL_HASH}"
