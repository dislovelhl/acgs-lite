"""
Secret Rotation Enums
Constitutional Hash: cdd01ef066bc6cf2

Enum definitions for secret rotation lifecycle management.
"""

from enum import StrEnum


class RotationTrigger(StrEnum):
    """Triggers that can initiate secret rotation."""

    TIME_BASED = "time_based"  # Automatic time-based rotation
    ON_DEMAND = "on_demand"  # Manual trigger via API
    COMPROMISE_DETECTED = "compromise_detected"  # Security event trigger
    POLICY_CHANGE = "policy_change"  # Policy update trigger
    DEPENDENCY_ROTATION = "dependency_rotation"  # Cascading from related secret
    SCHEDULED = "scheduled"  # Cron-based schedule
    STARTUP = "startup"  # Rotate on service startup


class RotationStatus(StrEnum):
    """Status of a secret rotation operation."""

    PENDING = "pending"  # Rotation scheduled but not started
    IN_PROGRESS = "in_progress"  # Rotation currently executing
    GRACE_PERIOD = "grace_period"  # New secret active, old still valid
    COMPLETED = "completed"  # Rotation fully complete
    FAILED = "failed"  # Rotation failed
    ROLLED_BACK = "rolled_back"  # Rotation was rolled back


class SecretType(StrEnum):
    """Types of secrets supported for rotation."""

    API_KEY = "api_key"
    JWT_SIGNING_KEY = "jwt_signing_key"
    ENCRYPTION_KEY = "encryption_key"
    DATABASE_PASSWORD = "database_password"  # noqa: S105 - secret type label
    SERVICE_ACCOUNT = "service_account"
    OAUTH_CLIENT_SECRET = "oauth_client_secret"  # noqa: S105 - secret type label
    WEBHOOK_SECRET = "webhook_secret"  # noqa: S105 - secret type label
    GENERIC = "generic"


__all__ = [
    "RotationStatus",
    "RotationTrigger",
    "SecretType",
]
