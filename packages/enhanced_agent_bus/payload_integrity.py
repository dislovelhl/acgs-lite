"""
ACGS-2 Enhanced Agent Bus - Payload Integrity (OWASP AA05)
Constitutional Hash: 608508a9bd224290

HMAC-SHA256 payload signing and verification to prevent silent mutation
of AgentMessage payloads between creation and validation.

Uses the constitutional hash as the HMAC key derivation seed via SHA-256.
No external dependencies — stdlib hmac and hashlib only.
"""

import hashlib
import hmac
import json

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.structured_logging import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)


logger = get_logger(__name__)


def _derive_hmac_key(seed: str) -> bytes:
    """Derive a 32-byte HMAC key from a seed string using SHA-256.

    Args:
        seed: The seed string (typically the constitutional hash).

    Returns:
        32-byte key suitable for HMAC-SHA256.
    """
    return hashlib.sha256(seed.encode("utf-8")).digest()


# Module-level derived key — computed once from the constitutional hash.
_HMAC_KEY: bytes = _derive_hmac_key(CONSTITUTIONAL_HASH)


def _canonicalize_payload(payload: dict) -> bytes:
    """Produce a canonical byte representation of a payload dict.

    Uses JSON with sorted keys and no whitespace to ensure deterministic output.

    Args:
        payload: The payload dictionary to canonicalize.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict, key: bytes | None = None) -> str:
    """Produce an HMAC-SHA256 hex digest for a payload dictionary.

    Args:
        payload: The payload dictionary to sign.
        key: Optional HMAC key bytes. Defaults to the key derived from
            the constitutional hash.

    Returns:
        Hex-encoded HMAC-SHA256 digest string.
    """
    effective_key = key if key is not None else _HMAC_KEY
    canonical = _canonicalize_payload(payload)
    return hmac.new(effective_key, canonical, hashlib.sha256).hexdigest()


def verify_payload(payload: dict, hmac_hex: str, key: bytes | None = None) -> bool:
    """Verify an HMAC-SHA256 hex digest against a payload dictionary.

    Uses constant-time comparison via ``hmac.compare_digest`` to prevent
    timing attacks.

    Args:
        payload: The payload dictionary to verify.
        hmac_hex: The expected HMAC-SHA256 hex digest.
        key: Optional HMAC key bytes. Defaults to the key derived from
            the constitutional hash.

    Returns:
        True if the HMAC matches, False otherwise.
    """
    effective_key = key if key is not None else _HMAC_KEY
    canonical = _canonicalize_payload(payload)
    expected = hmac.new(effective_key, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, hmac_hex)


__all__ = [
    "sign_payload",
    "verify_payload",
]
