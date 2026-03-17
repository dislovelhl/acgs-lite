"""API key authentication for public /v1/ endpoints.
Constitutional Hash: cdd01ef066bc6cf2
"""

import hashlib
import hmac
import os
import time
from collections.abc import Callable

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from enhanced_agent_bus.observability.structured_logging import get_logger

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = get_logger(__name__)
# Dedicated constant so test key is never inlined in production key sets
_ENVIRONMENT_VAR = "ENVIRONMENT"
_RUNTIME_ENVIRONMENT_VAR = "AGENT_RUNTIME_ENVIRONMENT"
_PRODUCTION_ENV = "production"
_TEST_FLAG_VAR = "ACGS_ALLOW_TEST_API_KEY"
_TEST_CONTEXT_VAR = "PYTEST_CURRENT_TEST"
_API_KEYS_VAR = "ACGS_API_KEYS"  # pragma: allowlist secret

# TTL-based cache: allows runtime key revocation within _CACHE_TTL seconds
_CACHE_TTL = 60  # seconds
_cached_keys: frozenset[str] = frozenset()
_cache_timestamp: float = 0.0
_revoked_keys: set[str] = set()


def _key_fingerprint(api_key: str) -> str:
    """Return a non-reversible short fingerprint for audit logs."""
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    return digest[:12]


def _is_test_context() -> bool:
    return bool(os.environ.get(_TEST_CONTEXT_VAR))


def _is_production_environment() -> bool:
    """Return True when NOT in an explicit development/test environment.

    Fail-closed: unset ENVIRONMENT is treated as production.
    Only explicit development/test/ci values enable dev mode.
    """
    env = (
        (os.environ.get(_RUNTIME_ENVIRONMENT_VAR) or os.environ.get(_ENVIRONMENT_VAR, ""))
        .strip()
        .lower()
    )
    return env not in ("development", "dev", "test", "testing", "ci")


def _is_test_key_explicitly_allowed() -> bool:
    """Return True when test key opt-in flag is enabled."""
    return os.environ.get(_TEST_FLAG_VAR, "").lower() == "true"


def _allow_test_api_key() -> bool:
    """Return True when the test API key should be accepted.

    Conditions (ALL must hold):
      1. We are NOT in production, AND
      2. Either running under pytest OR the explicit opt-in flag is set.
    """
    if _is_production_environment():
        return False
    return _is_test_context() or _is_test_key_explicitly_allowed()


def _load_env_api_keys() -> set[str]:
    """Load API keys from environment variable.

    Filters out keys shorter than 32 characters with warning log.
    """
    env_keys = os.environ.get(_API_KEYS_VAR, "")
    keys = set()
    for key in env_keys.split(","):
        stripped = key.strip()
        if not stripped:
            continue
        if len(stripped) < 32:
            logger.warning(
                "Ignoring API key shorter than 32 characters",
                extra={"key_fingerprint": _key_fingerprint(stripped) if stripped else "empty"},
            )
            continue
        keys.add(stripped)
    return keys


def _get_valid_keys() -> frozenset[str]:
    """Get valid API keys from environment with TTL-based caching.

    Cache expires after _CACHE_TTL seconds, allowing runtime key revocation
    without requiring a full application restart.
    """
    global _cached_keys, _cache_timestamp

    now = time.monotonic()
    if now - _cache_timestamp < _CACHE_TTL and _cached_keys:
        return _cached_keys

    keys = _load_env_api_keys()
    if _revoked_keys:
        keys = {
            key
            for key in keys
            if not any(hmac.compare_digest(key, revoked) for revoked in _revoked_keys)
        }

    _cached_keys = frozenset(keys)
    _cache_timestamp = now
    logger.debug(
        "API key set refreshed from environment",
        extra={
            "active_key_count": len(_cached_keys),
            "revoked_key_count": len(_revoked_keys),
        },
    )
    return _cached_keys


def reset_valid_keys() -> None:
    """Reset cached keys and in-process revocation state."""
    global _cached_keys, _cache_timestamp
    _cached_keys = frozenset()
    _cache_timestamp = 0.0
    _revoked_keys.clear()
    logger.info("API key cache and revocation state reset")


def revoke_api_key(api_key: str) -> None:
    """Immediately revoke an API key in-process.

    This bypasses cache TTL delays for emergency revocation until
    configuration source-of-truth is updated and reloaded.
    """
    if not api_key:
        return
    _revoked_keys.add(api_key)
    global _cached_keys
    if _cached_keys:
        _cached_keys = frozenset(
            key for key in _cached_keys if not hmac.compare_digest(key, api_key)
        )
    logger.warning(
        "API key revoked in process memory",
        extra={"api_key_fingerprint": _key_fingerprint(api_key)},
    )


_cached_get_account: Callable[[str], dict | None] | None = None


def _is_signup_key(api_key: str) -> bool:
    """Check if the key was issued via /v1/signup."""
    global _cached_get_account
    if _cached_get_account is None:
        try:
            from .routes.signup import get_account

            _cached_get_account = get_account
        except ImportError:
            return False
    return _cached_get_account(api_key) is not None


def _is_known_api_key(api_key: str) -> bool:
    """Return True when API key is accepted by static or signup store.

    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    if any(hmac.compare_digest(api_key, revoked) for revoked in _revoked_keys):
        return False

    # Check against static keys using constant-time comparison
    valid_keys = _get_valid_keys()
    for valid_key in valid_keys:
        if hmac.compare_digest(api_key, valid_key):
            return True

    # Check against signup keys
    return _is_signup_key(api_key)


async def require_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """Validate API key from X-API-Key header."""
    # Strip whitespace before validation to reject whitespace-only strings
    if api_key:
        api_key = api_key.strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not _is_known_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
