"""
ACGS-2 Deliberation Layer - Audit Signature Utilities
Constitutional Hash: 608508a9bd224290

HMAC-SHA256 signature functions for audit record immutability verification.
"""

import hashlib
import hmac
import json

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
AUDIT_SIGNATURE_OPERATION_ERRORS = (
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)


def sign_audit_record(payload: JSONDict, secret_key: str) -> str:
    """
    Sign an audit record payload using HMAC-SHA256.

    Args:
        payload: Audit record payload dictionary (must be JSON-serializable)
        secret_key: Secret key for HMAC signing

    Returns:
        Hexadecimal HMAC-SHA256 signature string
    """
    try:
        # Serialize payload to JSON with sorted keys for deterministic hashing
        json_str = json.dumps(payload, sort_keys=True, default=str)

        # Create HMAC signature
        signature = hmac.new(
            secret_key.encode("utf-8"), json_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return signature
    except AUDIT_SIGNATURE_OPERATION_ERRORS as e:
        logger.error(f"Failed to sign audit record: {e}")
        return ""


def verify_signature(payload: JSONDict, signature: str, secret_key: str) -> bool:
    """
    Verify an audit record signature.

    Args:
        payload: Audit record payload dictionary
        signature: Expected HMAC-SHA256 signature (hex string)
        secret_key: Secret key used for signing

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        expected_signature = sign_audit_record(payload, secret_key)
        return hmac.compare_digest(expected_signature, signature)
    except AUDIT_SIGNATURE_OPERATION_ERRORS as e:
        logger.error(f"Failed to verify signature: {e}")
        return False
