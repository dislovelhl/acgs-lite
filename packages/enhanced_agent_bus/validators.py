"""
ACGS-2 Enhanced Agent Bus - Validators
Constitutional Hash: 608508a9bd224290

Validation utilities for message and agent compliance.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field

try:
    from .models import AgentMessage, MessageStatus
except (ImportError, ValueError):
    from models import AgentMessage, MessageStatus  # type: ignore[import-untyped]
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from .models import PQCMetadata

# Import centralized constitutional hash from shared module
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        is_valid (bool): Whether the validation passed. Defaults to True.
        errors (list[str]): A list of error messages if validation failed.
        warnings (list[str]): A list of warning messages.
        metadata (JSONDict): Additional metadata associated with the validation.
        constitutional_hash (str): The constitutional hash `608508a9bd224290`.
        pqc_metadata (PQCMetadata | None): Post-quantum cryptography metadata including
            algorithm details and verification status. None if PQC is not enabled.
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    decision: str = "ALLOW"
    status: MessageStatus = MessageStatus.VALIDATED
    constitutional_hash: str = CONSTITUTIONAL_HASH
    pqc_metadata: "PQCMetadata" | None = None

    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(warning)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.is_valid:
            self.is_valid = False

    def to_dict(self) -> JSONDict:
        """Converts the validation result to a dictionary for serialization.

        Returns:
            JSONDict: A dictionary representation of the validation result.
        """
        result = {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "decision": self.decision,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Include PQC metadata if present
        if self.pqc_metadata:
            result["pqc_metadata"] = self.pqc_metadata.to_dict()

        return result


def validate_constitutional_hash(hash_value: str) -> ValidationResult:
    """Validate a constitutional hash.

    Uses constant-time comparison to prevent timing attacks.
    Error messages are sanitized to prevent hash exposure.
    """
    result = ValidationResult()

    # Ensure both values are strings for comparison
    if not isinstance(hash_value, str):
        result.add_error("Constitutional hash must be a string")
        return result

    # Use constant-time comparison to prevent timing attacks
    # hmac.compare_digest prevents attackers from inferring the hash
    # character-by-character through response time analysis
    try:
        is_match = hmac.compare_digest(
            hash_value.encode("utf-8"), CONSTITUTIONAL_HASH.encode("utf-8")
        )
    except UnicodeEncodeError:
        is_match = False

    if not is_match:
        # Sanitize error message: only show prefix to aid debugging
        # without exposing full hash values
        safe_provided = hash_value[:8] + "..." if len(hash_value) > 8 else hash_value
        result.add_error(f"Constitutional hash mismatch (provided: {safe_provided})")
    return result


def validate_message_content(content: JSONDict) -> ValidationResult:
    """Validate message content."""
    result = ValidationResult()

    if not isinstance(content, dict):
        result.add_error("Content must be a dictionary")
        return result

    # Check for required fields if specified
    if "action" in content and not content["action"]:
        result.add_warning("Empty action field")

    return result


def validate_payload_integrity(message: "AgentMessage") -> ValidationResult:
    """Validate payload integrity via HMAC-SHA256 (OWASP AA05).

    If the message carries a ``payload_hmac``, this function verifies it
    against the message's ``payload`` using the constitutional-hash-derived
    HMAC key.  Messages without a ``payload_hmac`` pass with a warning to
    preserve backwards compatibility.

    Args:
        message: The AgentMessage to validate.

    Returns:
        ValidationResult with integrity check outcome.
    """
    from .payload_integrity import verify_payload

    result = ValidationResult()

    if message.payload_hmac is None:
        result.add_warning("Message has no payload_hmac — integrity not verified (AA05)")
        return result

    if not verify_payload(message.payload, message.payload_hmac):
        result.add_error("Payload HMAC verification failed — possible message tampering (AA05)")
    return result


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ValidationResult",
    "validate_constitutional_hash",
    "validate_message_content",
    "validate_payload_integrity",
]
