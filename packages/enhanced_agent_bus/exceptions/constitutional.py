"""
ACGS-2 Enhanced Agent Bus - Constitutional Exceptions
Constitutional Hash: 608508a9bd224290
"""

from .base import ConstitutionalError


class ConstitutionalHashMismatchError(ConstitutionalError):
    """Raised when constitutional hash validation fails.

    Security Note: Hash values are sanitized in messages and serialization
    to prevent exposure in logs, error traces, and debugging output.
    """

    @staticmethod
    def _sanitize_hash(hash_value: str, max_visible: int = 8) -> str:
        """Sanitize hash for safe display in error messages."""
        if not hash_value or len(hash_value) <= max_visible:
            return hash_value
        return hash_value[:max_visible] + "..."

    def __init__(
        self,
        expected_hash: str,
        actual_hash: str,
        context: str | None = None,
    ) -> None:
        # Store original values for internal use only
        self._expected_hash = expected_hash
        self._actual_hash = actual_hash

        # Sanitized versions for safe exposure
        safe_expected = self._sanitize_hash(expected_hash)
        safe_actual = self._sanitize_hash(actual_hash)

        message = f"Constitutional hash mismatch: expected '{safe_expected}', got '{safe_actual}'"
        if context:
            message += f" (context: {context})"
        super().__init__(
            message=message,
            details={
                # Only expose sanitized hashes in serializable output
                "expected_hash_prefix": safe_expected,
                "actual_hash_prefix": safe_actual,
                "context": context,
            },
        )

    @property
    def expected_hash(self) -> str:
        """Return full expected hash for internal validation only."""
        return self._expected_hash

    @property
    def actual_hash(self) -> str:
        """Return full actual hash for internal validation only."""
        return self._actual_hash


class ConstitutionalValidationError(ConstitutionalError):
    """Raised when constitutional validation fails for any reason."""

    def __init__(
        self,
        validation_errors: list[str],
        agent_id: str | None = None,
        action_type: str | None = None,
    ) -> None:
        self.validation_errors = validation_errors
        self.agent_id = agent_id
        self.action_type = action_type
        message = f"Constitutional validation failed: {'; '.join(validation_errors)}"
        super().__init__(
            message=message,
            details={
                "validation_errors": validation_errors,
                "agent_id": agent_id,
                "action_type": action_type,
            },
        )


__all__ = [
    "ConstitutionalError",
    "ConstitutionalHashMismatchError",
    "ConstitutionalValidationError",
]
