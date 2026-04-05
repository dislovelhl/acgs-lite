"""
ACGS-2 Constitutional Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for constitutional hash validation and compliance testing.
"""

from dataclasses import dataclass

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


@dataclass
class HashValidationResult:
    """Result of constitutional hash validation."""

    is_valid: bool
    expected: str
    actual: str | None
    layer: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "expected": self.expected,
            "actual": self.actual,
            "layer": self.layer,
            "message": self.message,
        }


class ConstitutionalHashValidator:
    """
    Validator for constitutional hash compliance.

    Used in executable specifications to verify hash propagation
    across architectural layers.
    """

    def __init__(self, expected_hash: str = CONSTITUTIONAL_HASH):
        self.expected_hash = expected_hash
        self.validation_history: list[HashValidationResult] = []

    def validate(
        self,
        actual_hash: str | None,
        layer: str | None = None,
    ) -> HashValidationResult:
        """
        Validate a constitutional hash.

        Args:
            actual_hash: The hash to validate
            layer: Optional layer identifier for tracking

        Returns:
            HashValidationResult with validation details
        """
        if actual_hash is None:
            result = HashValidationResult(
                is_valid=False,
                expected=self.expected_hash,
                actual=None,
                layer=layer,
                message="Hash is None",
            )
        elif actual_hash != self.expected_hash:
            result = HashValidationResult(
                is_valid=False,
                expected=self.expected_hash,
                actual=actual_hash,
                layer=layer,
                message=f"Hash mismatch: expected {self.expected_hash}, got {actual_hash}",
            )
        else:
            result = HashValidationResult(
                is_valid=True,
                expected=self.expected_hash,
                actual=actual_hash,
                layer=layer,
                message="Valid constitutional hash",
            )

        self.validation_history.append(result)
        return result

    def validate_propagation(
        self,
        layer_hashes: dict[str, str | None],
    ) -> list[HashValidationResult]:
        """
        Validate hash propagation across multiple layers.

        Args:
            layer_hashes: Dict mapping layer names to their hashes

        Returns:
            List of validation results for each layer
        """
        results = []
        for layer, hash_val in layer_hashes.items():
            results.append(self.validate(hash_val, layer))
        return results

    def all_valid(self) -> bool:
        """Check if all validations in history passed."""
        return all(r.is_valid for r in self.validation_history)

    def get_failures(self) -> list[HashValidationResult]:
        """Get all failed validations."""
        return [r for r in self.validation_history if not r.is_valid]

    def reset(self) -> None:
        """Clear validation history."""
        self.validation_history.clear()


@pytest.fixture
def constitutional_hash() -> str:
    """
    Fixture providing the constitutional hash value.

    Use in tests that need the canonical hash:
        def test_hash_included(constitutional_hash):
            assert message.hash == constitutional_hash
    """
    return str(CONSTITUTIONAL_HASH)


@pytest.fixture
def hash_validator() -> ConstitutionalHashValidator:
    """
    Fixture providing a constitutional hash validator.

    Use in tests validating hash propagation:
        def test_hash_propagation(hash_validator):
            result = hash_validator.validate(message.hash, "L1")
            assert result.is_valid
    """
    return ConstitutionalHashValidator()
