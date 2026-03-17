"""
ACGS-2 Audit Data Encryption
Constitutional Hash: cdd01ef066bc6cf2

Provides envelope encryption for sensitive audit payloads.
"""

import base64
import json
import os
import sys

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.structured_logging import get_logger

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]

logger = get_logger(__name__)
_MASTER_KEY_CACHE: bytes | None = None


def _runtime_environment() -> str:
    return (
        (
            os.environ.get("AGENT_RUNTIME_ENVIRONMENT")
            or os.environ.get("ENVIRONMENT")
            or "development"
        )
        .strip()
        .lower()
    )


def _is_production_like_environment() -> bool:
    return _runtime_environment() not in {"development", "dev", "test", "testing", "local", "ci"}


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "on"}


def _allow_ephemeral_master_key() -> bool:
    if _is_production_like_environment():
        return False

    if _parse_bool_env(os.environ.get("ACGS2_ALLOW_EPHEMERAL_ENCRYPTION_KEY")):
        return True

    return bool(os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)


def _load_master_key() -> bytes:
    global _MASTER_KEY_CACHE

    if _MASTER_KEY_CACHE is not None:
        return _MASTER_KEY_CACHE

    configured_key = (os.environ.get("ACGS2_ENCRYPTION_KEY") or "").strip()
    if configured_key:
        try:
            decoded_key = base64.b64decode(configured_key)
        except (ValueError, TypeError) as exc:
            raise OSError("ACGS2_ENCRYPTION_KEY must be valid base64-encoded bytes") from exc

        if len(decoded_key) != 32:
            raise OSError("ACGS2_ENCRYPTION_KEY must decode to exactly 32 bytes")

        _MASTER_KEY_CACHE = decoded_key
        return decoded_key

    if _allow_ephemeral_master_key():
        import secrets

        _MASTER_KEY_CACHE = secrets.token_bytes(32)
        logger.warning(
            "Using auto-generated encryption key for non-production runtime (%s)",
            _runtime_environment(),
        )
        return _MASTER_KEY_CACHE

    raise OSError(
        "ACGS2_ENCRYPTION_KEY environment variable is required in production-like environments. "
        f"Current environment: {_runtime_environment()!r}. "
        "Generate with: python -c 'import secrets, base64; "
        "print(base64.b64encode(secrets.token_bytes(32)).decode())'"
    )


class EncryptionManager:
    """Manager for audit data encryption."""

    @staticmethod
    def encrypt_payload(payload: JSONDict) -> str:
        """
        Encrypt a payload using envelope encryption (AES-GCM).
        Returns a base64 encoded string containing IV + Tag + Ciphertext.
        """
        try:
            # Generate a random data key
            data_key = os.urandom(32)
            aesgcm = AESGCM(data_key)
            data_nonce = os.urandom(12)

            payload_bytes = json.dumps(payload).encode("utf-8")
            ciphertext = aesgcm.encrypt(data_nonce, payload_bytes, None)

            # Encrypt the data key with the master key (separate nonce)
            master_aesgcm = AESGCM(_load_master_key())
            key_nonce = os.urandom(12)
            encrypted_key = master_aesgcm.encrypt(key_nonce, data_key, None)

            # Combine: data_nonce (12) + key_nonce (12) + encrypted_key (48) + ciphertext
            combined = data_nonce + key_nonce + encrypted_key + ciphertext
            return base64.b64encode(combined).decode("utf-8")
        except (ValueError, TypeError, OSError) as e:
            logger.error(f"Payload encryption failed ({type(e).__name__}): {e}")
            raise ConfigurationError(
                "Encryption failure",
                error_code="ENCRYPTION_FAILED",
            ) from e

    @staticmethod
    def decrypt_payload(encrypted_str: str) -> JSONDict:
        """Decrypt an encrypted payload."""
        try:
            combined = base64.b64decode(encrypted_str)
            data_nonce = combined[:12]
            key_nonce = combined[12:24]
            # encrypted_key is 32 bytes + 16 bytes tag = 48 bytes
            encrypted_key = combined[24:72]
            ciphertext = combined[72:]

            # Decrypt data key
            master_aesgcm = AESGCM(_load_master_key())
            data_key = master_aesgcm.decrypt(key_nonce, encrypted_key, None)

            # Decrypt payload
            aesgcm = AESGCM(data_key)
            payload_bytes = aesgcm.decrypt(data_nonce, ciphertext, None)

            return json.loads(payload_bytes.decode("utf-8"))
        except (ValueError, TypeError, OSError, json.JSONDecodeError, InvalidTag) as e:
            logger.error(f"Payload decryption failed ({type(e).__name__}): {e}")
            raise ConfigurationError(
                "Decryption failure",
                error_code="DECRYPTION_FAILED",
            ) from e


__all__ = ["EncryptionManager"]
