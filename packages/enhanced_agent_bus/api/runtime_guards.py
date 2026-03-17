"""Runtime environment guards for production-vs-sandbox API behavior."""

from __future__ import annotations

import os

from fastapi import HTTPException

SANDBOX_ENVIRONMENTS = frozenset(
    {"development", "dev", "test", "testing", "local", "ci", "sandbox"}
)


def current_environment() -> str:
    """Return the normalized runtime environment name."""
    return os.environ.get("ENVIRONMENT", "").strip().lower()


def is_sandbox_environment() -> bool:
    """Return True when non-authoritative sandbox behavior is allowed."""
    return current_environment() in SANDBOX_ENVIRONMENTS


def require_sandbox_endpoint(endpoint_name: str, detail: str) -> None:
    """Reject non-authoritative endpoints outside sandbox/development environments."""
    if is_sandbox_environment():
        return

    raise HTTPException(
        status_code=503,
        detail=(f"{endpoint_name} is disabled outside sandbox/development environments: {detail}"),
    )
