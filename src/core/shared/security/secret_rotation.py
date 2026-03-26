"""
ACGS-2 Secret Rotation Lifecycle Manager
Constitutional Hash: 608508a9bd224290

BACKWARD COMPATIBILITY SHIM
===========================
This module has been refactored into a modular structure.
All imports are re-exported from the new location for backward compatibility.

New structure:
- security/rotation/enums.py      - RotationTrigger, RotationStatus, SecretType
- security/rotation/models.py     - RotationPolicy, SecretVersion, RotationRecord, RotationResult
- security/rotation/backend.py    - SecretBackend, InMemorySecretBackend, VaultSecretBackend
- security/rotation/manager.py    - SecretRotationManager, get_rotation_manager, reset_rotation_manager
- security/rotation/__init__.py   - Re-exports all public symbols

Usage (unchanged):
    from src.core.shared.security.secret_rotation import (
        SecretRotationManager,
        RotationPolicy,
        RotationTrigger,
        get_rotation_manager,
    )

Or use the new location directly:
    from src.core.shared.security.rotation import (
        SecretRotationManager,
        RotationPolicy,
        RotationTrigger,
        get_rotation_manager,
    )

Expert Reference: Kelsey Hightower
Task: T004 - Secret Rotation Lifecycle
"""

# Re-export everything from the new modular structure
from src.core.shared.security.rotation import (
    CONSTITUTIONAL_HASH,
    DEFAULT_GRACE_PERIOD_HOURS,
    DEFAULT_MAX_VERSIONS,
    DEFAULT_ROLLBACK_WINDOW_HOURS,
    DEFAULT_ROTATION_INTERVAL_DAYS,
    InMemorySecretBackend,
    RotationPolicy,
    RotationRecord,
    RotationResult,
    RotationStatus,
    RotationTrigger,
    SecretBackend,
    SecretGenerator,
    SecretRotationManager,
    SecretType,
    SecretVersion,
    VaultSecretBackend,
    get_rotation_manager,
    reset_rotation_manager,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "DEFAULT_GRACE_PERIOD_HOURS",
    "DEFAULT_MAX_VERSIONS",
    "DEFAULT_ROLLBACK_WINDOW_HOURS",
    "DEFAULT_ROTATION_INTERVAL_DAYS",
    "InMemorySecretBackend",
    # Data classes
    "RotationPolicy",
    "RotationRecord",
    "RotationResult",
    "RotationStatus",
    # Enums
    "RotationTrigger",
    # Backends
    "SecretBackend",
    # Type alias
    "SecretGenerator",
    # Main classes
    "SecretRotationManager",
    "SecretType",
    "SecretVersion",
    "VaultSecretBackend",
    "get_rotation_manager",
    "reset_rotation_manager",
]
