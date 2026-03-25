"""
ACGS-2 Secret Rotation Module
Constitutional Hash: 608508a9bd224290

Production-grade secret rotation with:
- Time-based and event-based rotation triggers
- Grace period for dual-secret validation during rotation
- Automatic rollback mechanism on failure
- Comprehensive audit logging of all rotation events
- Integration with Kubernetes secrets and HashiCorp Vault
- Zero-downtime rotation support

Expert Reference: Kelsey Hightower
Task: T004 - Secret Rotation Lifecycle

Usage:
    from src.core.shared.security.rotation import (
        SecretRotationManager,
        RotationPolicy,
        RotationTrigger,
        get_rotation_manager,
    )

    # Create rotation manager
    manager = SecretRotationManager()

    # Register a secret with rotation policy
    await manager.register_secret(
        secret_name="JWT_SIGNING_KEY",
        policy=RotationPolicy(
            rotation_interval_days=30,
            grace_period_hours=4,
            triggers=[RotationTrigger.TIME_BASED, RotationTrigger.ON_DEMAND],
        ),
    )

    # Trigger rotation
    result = await manager.rotate_secret("JWT_SIGNING_KEY")

    # Rollback if needed
    await manager.rollback_secret("JWT_SIGNING_KEY")
"""

# Re-export all public symbols for backward compatibility
from src.core.shared.constants import CONSTITUTIONAL_HASH

from .backend import InMemorySecretBackend, SecretBackend, VaultSecretBackend
from .enums import RotationStatus, RotationTrigger, SecretType
from .manager import (
    SecretGenerator,
    SecretRotationManager,
    get_rotation_manager,
    reset_rotation_manager,
)
from .models import (
    DEFAULT_GRACE_PERIOD_HOURS,
    DEFAULT_MAX_VERSIONS,
    DEFAULT_ROLLBACK_WINDOW_HOURS,
    DEFAULT_ROTATION_INTERVAL_DAYS,
    RotationPolicy,
    RotationRecord,
    RotationResult,
    SecretVersion,
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
