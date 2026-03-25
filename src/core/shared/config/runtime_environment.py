"""Runtime environment resolution helpers.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
from collections.abc import Sequence

_RUNTIME_ENVIRONMENT_VARIABLES = (
    "AGENT_RUNTIME_ENVIRONMENT",
    "APP_ENV",
    "ENVIRONMENT",
    "ENV",
)


def _normalize_runtime_environment(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def resolve_runtime_environment(
    configured_env: str | None = None,
    *,
    default: str = "development",
    extra_env_vars: Sequence[str] = (),
) -> str:
    """Resolve the runtime environment with explicit env vars ahead of defaults.

    ``settings.env`` comes from ``APP_ENV`` but defaults to ``development`` when
    unset, so callers should not treat it as authoritative before checking the
    runtime environment variables themselves.
    """

    for env_var in _RUNTIME_ENVIRONMENT_VARIABLES:
        normalized = _normalize_runtime_environment(os.getenv(env_var))
        if normalized is not None:
            return normalized

    for env_var in extra_env_vars:
        normalized = _normalize_runtime_environment(os.getenv(env_var))
        if normalized is not None:
            return normalized

    configured = _normalize_runtime_environment(configured_env)
    if configured is not None:
        return configured

    fallback = _normalize_runtime_environment(default)
    return fallback or "development"
