"""
Constitutional Hash Registry and Algorithm Agility Framework
Constitutional Hash: cdd01ef066bc6cf2

Provides versioned, algorithm-agile constitutional hash management for
ACGS-2 governance operations. Supports migration between hash algorithms
without breaking validation.

Target format: {algorithm}:{version}:{hash}
Example: sha256:v1:cdd01ef066bc6cf2
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import (
    ACGSBaseError,
    ConstitutionalViolationError,
    ResourceNotFoundError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Current production constitutional hash
LEGACY_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


class HashAlgorithm(StrEnum):
    """Supported constitutional hash algorithms."""

    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"
    SHA3_256 = "sha3-256"
    SHA3_384 = "sha3-384"
    SHA3_512 = "sha3-512"
    BLAKE2B = "blake2b"
    BLAKE2S = "blake2s"
    # Post-quantum ready (future)
    SPHINCS_256 = "sphincs-256"
    DILITHIUM = "dilithium"


class HashStatus(StrEnum):
    """Lifecycle status of a constitutional hash version."""

    ACTIVE = "active"  # Currently in use
    DEPRECATED = "deprecated"  # Still valid but discouraged
    SUNSET = "sunset"  # No longer valid after sunset_date
    RETIRED = "retired"  # No longer valid


@dataclass
class HashVersion:
    """Represents a single version of a constitutional hash."""

    algorithm: HashAlgorithm
    version: str
    hash_value: str
    status: HashStatus = HashStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deprecated_at: datetime | None = None
    sunset_date: datetime | None = None
    successor_version: str | None = None
    notes: str = ""

    def to_canonical(self) -> str:
        """Return the canonical versioned hash string."""
        return f"{self.algorithm.value}:{self.version}:{self.hash_value}"

    def is_valid(self) -> bool:
        """Check if this hash version is currently valid."""
        if self.status == HashStatus.RETIRED:
            return False
        if self.status == HashStatus.SUNSET and self.sunset_date:
            return datetime.now(UTC) < self.sunset_date
        return True

    @classmethod
    def from_canonical(cls, canonical: str) -> HashVersion:
        """Parse a canonical hash string into a HashVersion."""
        parts = canonical.split(":")
        if len(parts) != 3:
            raise ACGSValidationError(
                f"Invalid canonical hash format: {canonical}",
                error_code="HASH_INVALID_FORMAT",
            )

        algorithm, version, hash_value = parts
        try:
            algo = HashAlgorithm(algorithm)
        except ValueError:
            raise ACGSValidationError(
                f"Unknown hash algorithm: {algorithm}",
                error_code="HASH_UNKNOWN_ALGORITHM",
            ) from None

        return cls(algorithm=algo, version=version, hash_value=hash_value)


class ConstitutionalHashRegistry:
    """
    Manages constitutional hash versions with algorithm agility.

    Features:
    - Version management with deprecation and sunset dates
    - Algorithm upgrade paths without breaking validation
    - Migration tools for existing references
    - Backwards compatibility with legacy bare hashes
    """

    # Version format regex
    VERSION_PATTERN = re.compile(r"^([a-z0-9-]+):v(\d+):([a-f0-9]+)$")
    LEGACY_PATTERN = re.compile(r"^[a-f0-9]{16}$")

    def __init__(self) -> None:
        self._versions: dict[str, HashVersion] = {}
        self._active_version: str | None = None
        self._deprecation_hooks: list[Callable[[HashVersion], None]] = []

        # Register the current production hash as v1
        self._register_initial_versions()

    def _register_initial_versions(self) -> None:
        """Register the initial constitutional hash versions."""
        # Register legacy hash as sha256:v1
        v1 = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value=LEGACY_CONSTITUTIONAL_HASH,
            status=HashStatus.ACTIVE,
            notes="Initial production constitutional hash",
        )
        self._versions[v1.to_canonical()] = v1
        self._active_version = v1.to_canonical()

        logger.info(f"Registered initial constitutional hash: {v1.to_canonical()}")

    @property
    def active_version(self) -> HashVersion | None:
        """Get the currently active hash version."""
        if self._active_version:
            return self._versions.get(self._active_version)
        return None

    @property
    def active_hash(self) -> str:
        """Get the current active constitutional hash (canonical format)."""
        if self._active_version:
            return self._active_version
        return f"sha256:v1:{LEGACY_CONSTITUTIONAL_HASH}"

    @property
    def active_hash_value(self) -> str:
        """Get just the hash value portion of the active hash."""
        version = self.active_version
        if version:
            return version.hash_value
        return LEGACY_CONSTITUTIONAL_HASH

    def register_version(
        self,
        algorithm: HashAlgorithm,
        version: str,
        hash_value: str,
        status: HashStatus = HashStatus.ACTIVE,
        notes: str = "",
    ) -> HashVersion:
        """Register a new hash version."""
        hv = HashVersion(
            algorithm=algorithm,
            version=version,
            hash_value=hash_value,
            status=status,
            notes=notes,
        )
        canonical = hv.to_canonical()

        if canonical in self._versions:
            raise ACGSValidationError(
                f"Hash version already registered: {canonical}",
                error_code="HASH_VERSION_DUPLICATE",
            )

        self._versions[canonical] = hv
        logger.info(f"Registered new constitutional hash version: {canonical}")

        return hv

    def deprecate_version(
        self,
        canonical: str,
        sunset_date: datetime | None = None,
        successor: str | None = None,
    ) -> None:
        """Mark a hash version as deprecated."""
        if canonical not in self._versions:
            raise ResourceNotFoundError(
                f"Unknown hash version: {canonical}",
                error_code="HASH_VERSION_NOT_FOUND",
            )

        version = self._versions[canonical]
        version.status = HashStatus.DEPRECATED
        version.deprecated_at = datetime.now(UTC)
        version.sunset_date = sunset_date
        version.successor_version = successor

        logger.warning(
            f"Deprecated constitutional hash version: {canonical}"
            f"{f', sunset: {sunset_date.isoformat()}' if sunset_date else ''}"
        )

        # Notify deprecation hooks
        for hook in self._deprecation_hooks:
            try:
                hook(version)
            except Exception as e:
                logger.error(f"Deprecation hook failed: {e}")

    def retire_version(self, canonical: str) -> None:
        """Permanently retire a hash version (no longer valid)."""
        if canonical not in self._versions:
            raise ResourceNotFoundError(
                f"Unknown hash version: {canonical}",
                error_code="HASH_VERSION_NOT_FOUND",
            )

        version = self._versions[canonical]
        version.status = HashStatus.RETIRED

        logger.warning(f"Retired constitutional hash version: {canonical}")

    def set_active_version(self, canonical: str) -> None:
        """Set a new active hash version."""
        if canonical not in self._versions:
            raise ResourceNotFoundError(
                f"Unknown hash version: {canonical}",
                error_code="HASH_VERSION_NOT_FOUND",
            )

        version = self._versions[canonical]
        if not version.is_valid():
            raise ConstitutionalViolationError(
                f"Cannot activate invalid hash version: {canonical}",
                error_code="HASH_VERSION_INVALID",
            )

        self._active_version = canonical
        logger.info(f"Set active constitutional hash version: {canonical}")

    def validate_hash(
        self,
        hash_input: str,
        strict: bool = False,
        allow_legacy: bool = True,
    ) -> ValidationResult:
        """
        Validate a constitutional hash.

        Args:
            hash_input: Hash to validate (canonical or legacy format)
            strict: If True, only accept active versions (not deprecated)
            allow_legacy: If True, accept bare legacy hash format

        Returns:
            ValidationResult with validation details
        """
        result = ValidationResult()

        # Check if it's a canonical versioned hash
        if self.VERSION_PATTERN.match(hash_input):
            if hash_input not in self._versions:
                result.valid = False
                result.error = f"Unknown hash version: {hash_input}"
                return result

            version = self._versions[hash_input]

            if not version.is_valid():
                result.valid = False
                result.error = f"Hash version is no longer valid: {hash_input}"
                return result

            if strict and version.status != HashStatus.ACTIVE:
                result.valid = False
                result.error = f"Hash version is deprecated: {hash_input}"
                result.warnings.append(
                    f"Successor version: {version.successor_version}"
                    if version.successor_version
                    else "No successor version defined"
                )
                return result

            if version.status == HashStatus.DEPRECATED:
                result.warnings.append(
                    f"Hash version {hash_input} is deprecated"
                    + (
                        f", will sunset on {version.sunset_date.isoformat()}"
                        if version.sunset_date
                        else ""
                    )
                )

            result.valid = True
            result.version = version
            return result

        # Check if it's a legacy bare hash
        if self.LEGACY_PATTERN.match(hash_input) and allow_legacy:
            # Map to known version if exists
            for canonical, version in self._versions.items():
                if version.hash_value == hash_input:
                    result.valid = version.is_valid()
                    result.version = version
                    result.warnings.append(
                        f"Using legacy hash format. Consider upgrading to: {canonical}"
                    )
                    return result

            # Unknown legacy hash - compare against active
            active = self.active_version
            if active and active.hash_value == hash_input:
                result.valid = True
                result.version = active
                result.warnings.append(
                    f"Using legacy hash format. Consider upgrading to: {active.to_canonical()}"
                )
                return result

            result.valid = False
            result.error = f"Unknown constitutional hash: {hash_input}"
            return result

        result.valid = False
        result.error = f"Invalid hash format: {hash_input}"
        return result

    def matches_active(self, hash_input: str) -> bool:
        """Check if a hash matches the current active version."""
        result = self.validate_hash(hash_input)
        if not result.valid:
            return False

        active = self.active_version
        if not active:
            return False

        # Compare hash values (handles both canonical and legacy)
        if result.version:
            return result.version.hash_value == active.hash_value

        return False

    def normalize_hash(self, hash_input: str) -> str:
        """
        Normalize a hash to canonical format.

        Args:
            hash_input: Hash in any valid format

        Returns:
            Canonical versioned hash string

        Raises:
            ValueError: If hash is invalid
        """
        result = self.validate_hash(hash_input)
        if not result.valid:
            raise ConstitutionalViolationError(
                str(result.error),
                error_code="HASH_NORMALIZATION_FAILED",
            )

        if result.version:
            return result.version.to_canonical()

        raise ConstitutionalViolationError(
            f"Cannot normalize hash: {hash_input}",
            error_code="HASH_NORMALIZATION_FAILED",
        )

    def migrate_hash(self, old_hash: str, new_version: str) -> str:
        """
        Migrate a hash reference to a new version.

        This validates the old hash and returns the canonical form
        of the new target version.

        Args:
            old_hash: Current hash value to migrate
            new_version: Target version canonical string

        Returns:
            Canonical hash string of new version

        Raises:
            ValueError: If old hash is invalid or new version doesn't exist
        """
        # Validate old hash
        result = self.validate_hash(old_hash)
        if not result.valid:
            raise ConstitutionalViolationError(
                f"Cannot migrate invalid hash: {result.error}",
                error_code="HASH_MIGRATION_INVALID",
            )

        # Check new version exists
        if new_version not in self._versions:
            raise ResourceNotFoundError(
                f"Unknown target version: {new_version}",
                error_code="HASH_VERSION_NOT_FOUND",
            )

        new = self._versions[new_version]
        if not new.is_valid():
            raise ConstitutionalViolationError(
                f"Target version is not valid: {new_version}",
                error_code="HASH_VERSION_INVALID",
            )

        logger.info(f"Migrated hash from {old_hash} to {new.to_canonical()}")
        return new.to_canonical()

    def register_deprecation_hook(self, hook: Callable[[HashVersion], None]) -> None:
        """Register a callback for deprecation events."""
        self._deprecation_hooks.append(hook)

    def get_all_versions(self) -> list[HashVersion]:
        """Get all registered hash versions."""
        return list(self._versions.values())

    def get_valid_versions(self) -> list[HashVersion]:
        """Get all currently valid hash versions."""
        return [v for v in self._versions.values() if v.is_valid()]

    def compute_hash(
        self,
        data: bytes,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> str:
        """
        Compute a hash using the specified algorithm.

        Args:
            data: Data to hash
            algorithm: Hash algorithm to use

        Returns:
            Hex-encoded hash value
        """
        algo_map = {
            HashAlgorithm.SHA256: hashlib.sha256,
            HashAlgorithm.SHA384: hashlib.sha384,
            HashAlgorithm.SHA512: hashlib.sha512,
            HashAlgorithm.SHA3_256: hashlib.sha3_256,
            HashAlgorithm.SHA3_384: hashlib.sha3_384,
            HashAlgorithm.SHA3_512: hashlib.sha3_512,
            HashAlgorithm.BLAKE2B: lambda: hashlib.blake2b(),
            HashAlgorithm.BLAKE2S: lambda: hashlib.blake2s(),
        }

        if algorithm not in algo_map:
            raise ACGSValidationError(
                f"Unsupported algorithm: {algorithm}",
                error_code="HASH_UNSUPPORTED_ALGORITHM",
            )

        hasher = algo_map[algorithm]()
        hasher.update(data)
        return hasher.hexdigest()


class ValidationResult:
    """Result of a hash validation operation."""

    def __init__(self) -> None:
        self.valid: bool = False
        self.version: HashVersion | None = None
        self.error: str | None = None
        self.warnings: list[str] = []

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "valid": self.valid,
            "version": self.version.to_canonical() if self.version else None,
            "error": self.error,
            "warnings": self.warnings,
        }


class ConstitutionalHashError(ACGSBaseError):
    """Base exception for constitutional hash errors (Q-H4 migration)."""

    http_status_code = 400
    error_code = "HASH_ERROR"

    def __init__(
        self,
        message: str,
        code: str = "hash_error",
        hash_value: str | None = None,
        **kwargs,
    ):
        # Preserve backward-compatible attributes
        self.code = code
        self.hash_value = hash_value

        # Build details dict
        details = kwargs.pop("details", {}) or {}
        details.update({"code": code, "hash_value": hash_value})

        super().__init__(message, error_code=code, details=details, **kwargs)

    def to_dict(self) -> dict:
        """Include legacy top-level hash_value for backward compatibility."""
        result = super().to_dict()
        result["hash_value"] = self.hash_value
        return result


class HashVersionMismatchError(ConstitutionalHashError):
    """Raised when hash version doesn't match expected version (Q-H4 migration)."""

    http_status_code = 400
    error_code = "HASH_MISMATCH"

    def __init__(self, expected: str, actual: str, **kwargs):
        self.expected = expected
        self.actual = actual
        message = f"Constitutional hash mismatch: expected '{expected}', got '{actual}'"
        super().__init__(message, code="hash_mismatch", hash_value=actual, **kwargs)


class HashVersionDeprecatedError(ConstitutionalHashError):
    """Raised when using a deprecated hash version in strict mode (Q-H4 migration)."""

    http_status_code = 400
    error_code = "HASH_DEPRECATED"

    def __init__(self, version: str, sunset_date: datetime | None = None, **kwargs):
        self.sunset_date = sunset_date
        message = f"Constitutional hash version is deprecated: {version}"
        if sunset_date:
            message += f", will sunset on {sunset_date.isoformat()}"
        super().__init__(message, code="hash_deprecated", hash_value=version, **kwargs)


class HashVersionRetiredError(ConstitutionalHashError):
    """Raised when using a retired hash version (Q-H4 migration)."""

    http_status_code = 400
    error_code = "HASH_RETIRED"

    def __init__(self, version: str, **kwargs):
        message = f"Constitutional hash version is retired and no longer valid: {version}"
        super().__init__(message, code="hash_retired", hash_value=version, **kwargs)


# Global registry instance with thread-safe initialization
_registry: ConstitutionalHashRegistry | None = None
_registry_lock = threading.Lock()


def get_hash_registry() -> ConstitutionalHashRegistry:
    """Get the global constitutional hash registry (thread-safe)."""
    global _registry
    if _registry is None:
        with _registry_lock:
            # Double-checked locking pattern for thread safety
            if _registry is None:
                _registry = ConstitutionalHashRegistry()
    return _registry


def validate_constitutional_hash(
    hash_input: str,
    strict: bool = False,
    allow_legacy: bool = True,
) -> ValidationResult:
    """
    Validate a constitutional hash using the global registry.

    Args:
        hash_input: Hash to validate
        strict: If True, reject deprecated versions
        allow_legacy: If True, accept bare legacy format

    Returns:
        ValidationResult with validation details
    """
    return get_hash_registry().validate_hash(hash_input, strict, allow_legacy)


def get_active_constitutional_hash() -> str:
    """Get the current active constitutional hash (canonical format)."""
    return get_hash_registry().active_hash


def get_active_hash_value() -> str:
    """Get just the hash value of the active constitutional hash."""
    return get_hash_registry().active_hash_value


def normalize_constitutional_hash(hash_input: str) -> str:
    """Normalize a hash to canonical format."""
    return get_hash_registry().normalize_hash(hash_input)


def matches_active_constitutional_hash(hash_input: str) -> bool:
    """Check if a hash matches the current active version."""
    return get_hash_registry().matches_active(hash_input)


# Backwards compatibility: expose the legacy hash as CONSTITUTIONAL_HASH
CONSTITUTIONAL_HASH = LEGACY_CONSTITUTIONAL_HASH

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "LEGACY_CONSTITUTIONAL_HASH",
    # Exceptions
    "ConstitutionalHashError",
    "ConstitutionalHashRegistry",
    # Enums
    "HashAlgorithm",
    "HashStatus",
    # Classes
    "HashVersion",
    "HashVersionDeprecatedError",
    "HashVersionMismatchError",
    "HashVersionRetiredError",
    "ValidationResult",
    "get_active_constitutional_hash",
    "get_active_hash_value",
    # Functions
    "get_hash_registry",
    "matches_active_constitutional_hash",
    "normalize_constitutional_hash",
    "validate_constitutional_hash",
]
