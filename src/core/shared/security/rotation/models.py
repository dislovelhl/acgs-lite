"""
Secret Rotation Data Models
Constitutional Hash: 608508a9bd224290

Data classes and models for secret rotation lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime

from .enums import RotationStatus, RotationTrigger

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]

# Constitutional compliance

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Default configuration constants
DEFAULT_ROTATION_INTERVAL_DAYS = 90
DEFAULT_GRACE_PERIOD_HOURS = 4
DEFAULT_MAX_VERSIONS = 3
DEFAULT_ROLLBACK_WINDOW_HOURS = 24


@dataclass
class RotationPolicy:
    """
    Policy defining how a secret should be rotated.

    Attributes:
        rotation_interval_days: Days between automatic rotations
        grace_period_hours: Hours both old and new secrets are valid
        max_versions: Maximum number of versions to retain
        triggers: List of triggers that can initiate rotation
        notify_before_days: Days before expiry to send notification
        require_approval: Whether rotation requires human approval
        auto_rollback_on_failure: Automatically rollback on failure
        rollback_window_hours: Hours during which rollback is allowed
        validation_required: Whether to validate new secret before activation
    """

    rotation_interval_days: int = DEFAULT_ROTATION_INTERVAL_DAYS
    grace_period_hours: int = DEFAULT_GRACE_PERIOD_HOURS
    max_versions: int = DEFAULT_MAX_VERSIONS
    triggers: list[RotationTrigger] = field(
        default_factory=lambda: [RotationTrigger.TIME_BASED, RotationTrigger.ON_DEMAND]
    )
    notify_before_days: int = 7
    require_approval: bool = False
    auto_rollback_on_failure: bool = True
    rollback_window_hours: int = DEFAULT_ROLLBACK_WINDOW_HOURS
    validation_required: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "rotation_interval_days": self.rotation_interval_days,
            "grace_period_hours": self.grace_period_hours,
            "max_versions": self.max_versions,
            "triggers": [t.value for t in self.triggers],
            "notify_before_days": self.notify_before_days,
            "require_approval": self.require_approval,
            "auto_rollback_on_failure": self.auto_rollback_on_failure,
            "rollback_window_hours": self.rollback_window_hours,
            "validation_required": self.validation_required,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SecretVersion:
    """
    A specific version of a secret.

    Attributes:
        version_id: Unique version identifier
        created_at: When this version was created
        activated_at: When this version became active
        deactivated_at: When this version was deactivated
        expires_at: When this version expires (end of grace period)
        is_current: Whether this is the current active version
        is_previous: Whether this is the previous version (grace period)
        checksum: Hash of the secret value for integrity verification
        created_by: Who/what created this version
        rotation_trigger: What triggered this version creation
    """

    version_id: str
    created_at: datetime
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    expires_at: datetime | None = None
    is_current: bool = False
    is_previous: bool = False
    checksum: str = ""
    created_by: str = "system"
    rotation_trigger: RotationTrigger = RotationTrigger.ON_DEMAND
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "version_id": self.version_id,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "deactivated_at": self.deactivated_at.isoformat() if self.deactivated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_current": self.is_current,
            "is_previous": self.is_previous,
            "checksum": self.checksum,
            "created_by": self.created_by,
            "rotation_trigger": self.rotation_trigger.value,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class RotationRecord:
    """
    Record of a rotation operation.

    Attributes:
        rotation_id: Unique rotation identifier
        secret_name: Name of the secret being rotated
        status: Current status of the rotation
        trigger: What initiated the rotation
        started_at: When rotation started
        completed_at: When rotation completed
        previous_version_id: Version being replaced
        new_version_id: New version created
        error_message: Error message if rotation failed
        rollback_available: Whether rollback is still possible
        actor_id: Who initiated the rotation
        tenant_id: Tenant context for the rotation
    """

    rotation_id: str
    secret_name: str
    status: RotationStatus
    trigger: RotationTrigger
    started_at: datetime
    completed_at: datetime | None = None
    previous_version_id: str | None = None
    new_version_id: str | None = None
    error_message: str | None = None
    rollback_available: bool = True
    actor_id: str = "system"
    tenant_id: str = "system"
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "rotation_id": self.rotation_id,
            "secret_name": self.secret_name,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "previous_version_id": self.previous_version_id,
            "new_version_id": self.new_version_id,
            "error_message": self.error_message,
            "rollback_available": self.rollback_available,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class RotationResult:
    """
    Result of a rotation operation.

    Attributes:
        success: Whether rotation succeeded
        rotation_id: ID of the rotation operation
        secret_name: Name of the rotated secret
        new_version_id: ID of the new version (if successful)
        previous_version_id: ID of the previous version
        grace_period_ends: When the grace period ends
        error: Error message if rotation failed
        rollback_available: Whether rollback is available
    """

    success: bool
    rotation_id: str
    secret_name: str
    new_version_id: str | None = None
    previous_version_id: str | None = None
    grace_period_ends: datetime | None = None
    error: str | None = None
    rollback_available: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "rotation_id": self.rotation_id,
            "secret_name": self.secret_name,
            "new_version_id": self.new_version_id,
            "previous_version_id": self.previous_version_id,
            "grace_period_ends": (
                self.grace_period_ends.isoformat() if self.grace_period_ends else None
            ),
            "error": self.error,
            "rollback_available": self.rollback_available,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "DEFAULT_GRACE_PERIOD_HOURS",
    "DEFAULT_MAX_VERSIONS",
    "DEFAULT_ROLLBACK_WINDOW_HOURS",
    # Constants
    "DEFAULT_ROTATION_INTERVAL_DAYS",
    # Data classes
    "RotationPolicy",
    "RotationRecord",
    "RotationResult",
    "SecretVersion",
]
