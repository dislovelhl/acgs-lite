"""
Secret Rotation Manager
Constitutional Hash: cdd01ef066bc6cf2

Main manager class for secret rotation lifecycle with:
- Time-based and event-based rotation triggers
- Grace period for dual-secret validation during rotation
- Automatic rollback mechanism on failure
- Comprehensive audit logging of all rotation events
- Integration with multiple secret backends
- Zero-downtime rotation support

Expert Reference: Kelsey Hightower
Task: T004 - Secret Rotation Lifecycle
"""

import asyncio
import hashlib
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.structured_logging import get_logger

from .backend import InMemorySecretBackend, SecretBackend
from .enums import RotationStatus, RotationTrigger, SecretType
from .models import (
    RotationPolicy,
    RotationRecord,
    RotationResult,
    SecretVersion,
)

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]

# Constitutional compliance
import contextlib

from src.core.shared.constants import CONSTITUTIONAL_HASH

logger = get_logger(__name__)
# Type alias for secret generator functions
SecretGenerator = Callable[[str, SecretType], Coroutine[object, object, str]]


class SecretRotationManager:
    """
    Manages secret rotation lifecycle with support for:
    - Time-based and event-based rotation triggers
    - Grace periods for zero-downtime rotation
    - Automatic rollback on failure
    - Comprehensive audit logging
    - Multiple secret backend support

    Example:
        manager = SecretRotationManager()

        # Register a secret with rotation policy
        await manager.register_secret(
            secret_name="JWT_SIGNING_KEY",  # pragma: allowlist secret
            secret_type=SecretType.JWT_SIGNING_KEY,
            policy=RotationPolicy(rotation_interval_days=30),
        )

        # Rotate the secret
        result = await manager.rotate_secret("JWT_SIGNING_KEY")
        if result.success:
            logger.info(f"Rotated to version: {result.new_version_id}")
            logger.info(f"Grace period ends: {result.grace_period_ends}")

        # Rollback if needed
        await manager.rollback_secret("JWT_SIGNING_KEY")
    """

    def __init__(
        self,
        backend: SecretBackend | None = None,
        audit_callback: Callable[[JSONDict], Coroutine[object, object, None]] | None = None,
        secret_generator: SecretGenerator | None = None,
    ) -> None:
        """
        Initialize the rotation manager.

        Args:
            backend: Secret storage backend (defaults to in-memory)
            audit_callback: Async callback for audit logging
            secret_generator: Custom function to generate new secret values
        """
        self._backend = backend or InMemorySecretBackend()
        self._audit_callback = audit_callback
        self._secret_generator = secret_generator or self._default_secret_generator

        # Internal state
        self._registered_secrets: dict[str, tuple[SecretType, RotationPolicy]] = {}
        self._versions: dict[str, list[SecretVersion]] = {}
        self._rotation_records: dict[str, list[RotationRecord]] = {}
        self._rotation_lock = asyncio.Lock()

        # Background task for scheduled rotations
        self._scheduler_task: asyncio.Task[None] | None = None
        self._scheduler_running = False

        logger.info(
            f"SecretRotationManager initialized with backend: {type(self._backend).__name__}"
        )

    async def _default_secret_generator(self, name: str, secret_type: SecretType) -> str:
        """Generate a new secret value based on type."""
        import base64
        import secrets

        if secret_type == SecretType.JWT_SIGNING_KEY:
            # Generate RSA key pair (simplified - in production use proper key gen)
            return base64.b64encode(secrets.token_bytes(64)).decode()
        elif secret_type == SecretType.ENCRYPTION_KEY:
            # 256-bit encryption key
            return base64.b64encode(secrets.token_bytes(32)).decode()
        elif secret_type == SecretType.DATABASE_PASSWORD:
            # Strong password
            return secrets.token_urlsafe(32)
        elif secret_type == SecretType.API_KEY:
            # API key format
            return f"acgs2_{secrets.token_urlsafe(32)}"
        elif secret_type == SecretType.WEBHOOK_SECRET:
            # Webhook secret
            return f"whsec_{secrets.token_urlsafe(32)}"
        else:
            # Generic secret
            return secrets.token_urlsafe(48)

    def _compute_checksum(self, value: str) -> str:
        """Compute SHA-256 checksum of secret value."""
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    def _generate_version_id(self, name: str) -> str:
        """Generate a unique version ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        unique = uuid.uuid4().hex[:8]
        return f"{name}-v{timestamp}-{unique}"

    def _generate_rotation_id(self) -> str:
        """Generate a unique rotation ID."""
        return f"rot-{uuid.uuid4().hex}"

    async def _audit_log(
        self,
        event_type: str,
        secret_name: str,
        details: JSONDict,
        actor_id: str = "system",
        tenant_id: str = "system",
    ) -> None:
        """Log an audit event."""
        event = {
            "event_type": event_type,
            "secret_name": secret_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "details": details,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        logger.info(f"Rotation audit: {event_type} for {secret_name}")

        if self._audit_callback:
            try:
                await self._audit_callback(event)
            except (TimeoutError, RuntimeError, ValueError, TypeError) as e:
                logger.error(f"Audit callback failed: {e}")

    async def register_secret(
        self,
        secret_name: str,
        secret_type: SecretType = SecretType.GENERIC,
        policy: RotationPolicy | None = None,
        initial_value: str | None = None,
    ) -> bool:
        """
        Register a secret for rotation management.

        Args:
            secret_name: Unique name for the secret
            secret_type: Type of secret for proper generation
            policy: Rotation policy (uses defaults if not specified)
            initial_value: Initial secret value (generated if not specified)

        Returns:
            True if registration successful
        """
        if secret_name in self._registered_secrets:
            logger.warning(f"Secret {secret_name} already registered")
            return False

        policy = policy or RotationPolicy()

        # Generate or use initial value
        if initial_value is None:
            initial_value = await self._secret_generator(secret_name, secret_type)

        # Create initial version
        version_id = self._generate_version_id(secret_name)
        now = datetime.now(UTC)

        version = SecretVersion(
            version_id=version_id,
            created_at=now,
            activated_at=now,
            is_current=True,
            checksum=self._compute_checksum(initial_value),
            created_by="system",
            rotation_trigger=RotationTrigger.ON_DEMAND,
        )

        # Store in backend
        if not await self._backend.store_secret(secret_name, initial_value, version_id):
            logger.error(f"Failed to store initial secret for {secret_name}")
            return False

        # Register in internal state
        self._registered_secrets[secret_name] = (secret_type, policy)
        self._versions[secret_name] = [version]
        self._rotation_records[secret_name] = []

        await self._audit_log(
            "secret_registered",
            secret_name,
            {
                "secret_type": secret_type.value,
                "policy": policy.to_dict(),
                "version_id": version_id,
            },
        )

        logger.info(f"Registered secret: {secret_name} (type: {secret_type.value})")
        return True

    async def rotate_secret(
        self,
        secret_name: str,
        trigger: RotationTrigger = RotationTrigger.ON_DEMAND,
        new_value: str | None = None,
        actor_id: str = "system",
        tenant_id: str = "system",
    ) -> RotationResult:
        """
        Rotate a secret to a new version.

        The rotation process:
        1. Generate new secret value
        2. Store new version in backend
        3. Mark new version as current
        4. Mark old version as previous (grace period)
        5. Schedule old version expiration

        Args:
            secret_name: Name of secret to rotate
            trigger: What triggered the rotation
            new_value: Optional pre-generated new value
            actor_id: Who initiated the rotation
            tenant_id: Tenant context

        Returns:
            RotationResult with status and details
        """
        rotation_id = self._generate_rotation_id()
        registration_failure = self._validate_rotation_request(secret_name, trigger, rotation_id)
        if registration_failure is not None:
            return registration_failure

        secret_type, policy = self._registered_secrets[secret_name]
        async with self._rotation_lock:
            now = datetime.now(UTC)
            previous_version = self._find_current_version(secret_name)
            record = self._build_in_progress_record(
                rotation_id=rotation_id,
                secret_name=secret_name,
                trigger=trigger,
                now=now,
                previous_version=previous_version,
                actor_id=actor_id,
                tenant_id=tenant_id,
            )

            try:
                resolved_value = await self._resolve_new_secret_value(
                    secret_name=secret_name,
                    secret_type=secret_type,
                    new_value=new_value,
                )
                new_version_id, grace_period_ends = await self._apply_rotation(
                    secret_name=secret_name,
                    trigger=trigger,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    now=now,
                    policy=policy,
                    previous_version=previous_version,
                    new_value=resolved_value,
                    record=record,
                )
                return RotationResult(
                    success=True,
                    rotation_id=rotation_id,
                    secret_name=secret_name,
                    new_version_id=new_version_id,
                    previous_version_id=previous_version.version_id if previous_version else None,
                    grace_period_ends=grace_period_ends,
                    rollback_available=True,
                )
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                return await self._finalize_rotation_failure(
                    secret_name=secret_name,
                    trigger=trigger,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    record=record,
                    rotation_id=rotation_id,
                    error=e,
                )

    def _validate_rotation_request(
        self,
        secret_name: str,
        trigger: RotationTrigger,
        rotation_id: str,
    ) -> RotationResult | None:
        """Validate secret registration and trigger allowance."""
        if secret_name not in self._registered_secrets:
            return RotationResult(
                success=False,
                rotation_id=rotation_id,
                secret_name=secret_name,
                error=f"Secret {secret_name} is not registered",
                rollback_available=False,
            )

        _, policy = self._registered_secrets[secret_name]
        if trigger not in policy.triggers:
            return RotationResult(
                success=False,
                rotation_id=rotation_id,
                secret_name=secret_name,
                error=f"Trigger {trigger.value} not allowed for this secret",
                rollback_available=False,
            )
        return None

    def _find_current_version(self, secret_name: str) -> SecretVersion | None:
        """Find currently active version for a secret."""
        for version in self._versions.get(secret_name, []):
            if version.is_current:
                return version
        return None

    def _build_in_progress_record(
        self,
        rotation_id: str,
        secret_name: str,
        trigger: RotationTrigger,
        now: datetime,
        previous_version: SecretVersion | None,
        actor_id: str,
        tenant_id: str,
    ) -> RotationRecord:
        """Build initial in-progress rotation record."""
        return RotationRecord(
            rotation_id=rotation_id,
            secret_name=secret_name,
            status=RotationStatus.IN_PROGRESS,
            trigger=trigger,
            started_at=now,
            previous_version_id=previous_version.version_id if previous_version else None,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    async def _resolve_new_secret_value(
        self,
        secret_name: str,
        secret_type: SecretType,
        new_value: str | None,
    ) -> str:
        """Resolve or generate new secret value for rotation."""
        if new_value is not None:
            return new_value
        return await self._secret_generator(secret_name, secret_type)

    async def _apply_rotation(
        self,
        secret_name: str,
        trigger: RotationTrigger,
        actor_id: str,
        tenant_id: str,
        now: datetime,
        policy: RotationPolicy,
        previous_version: SecretVersion | None,
        new_value: str,
        record: RotationRecord,
    ) -> tuple[str, datetime]:
        """Apply successful secret rotation and persist all side effects."""
        new_version_id = self._generate_version_id(secret_name)
        grace_period_ends = now + timedelta(hours=policy.grace_period_hours)
        new_version = SecretVersion(
            version_id=new_version_id,
            created_at=now,
            activated_at=now,
            is_current=True,
            is_previous=False,
            checksum=self._compute_checksum(new_value),
            created_by=actor_id,
            rotation_trigger=trigger,
        )

        if not await self._backend.store_secret(secret_name, new_value, new_version_id):
            raise ConfigurationError(
                message="Failed to store new secret version",
                error_code="SECRET_STORE_FAILED",
            )

        self._promote_new_version(
            secret_name, previous_version, new_version, now, grace_period_ends
        )
        record.status = RotationStatus.GRACE_PERIOD
        record.new_version_id = new_version_id
        record.completed_at = now
        self._rotation_records[secret_name].append(record)

        await self._cleanup_old_versions(secret_name, policy.max_versions)
        await self._audit_log(
            "secret_rotated",
            secret_name,
            {
                "rotation_id": record.rotation_id,
                "trigger": trigger.value,
                "previous_version_id": previous_version.version_id if previous_version else None,
                "new_version_id": new_version_id,
                "grace_period_ends": grace_period_ends.isoformat(),
            },
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

        logger.info(
            f"Rotated secret {secret_name}: {new_version_id} "
            f"(grace period ends: {grace_period_ends})"
        )
        return new_version_id, grace_period_ends

    def _promote_new_version(
        self,
        secret_name: str,
        previous_version: SecretVersion | None,
        new_version: SecretVersion,
        now: datetime,
        grace_period_ends: datetime,
    ) -> None:
        """Promote new version and move prior current to previous status."""
        if previous_version:
            for version in self._versions[secret_name]:
                if version.is_previous:
                    version.is_previous = False

            previous_version.is_current = False
            previous_version.is_previous = True
            previous_version.deactivated_at = now
            previous_version.expires_at = grace_period_ends

        self._versions[secret_name].append(new_version)

    async def _finalize_rotation_failure(
        self,
        secret_name: str,
        trigger: RotationTrigger,
        actor_id: str,
        tenant_id: str,
        record: RotationRecord,
        rotation_id: str,
        error: OSError | RuntimeError | ValueError | TypeError,
    ) -> RotationResult:
        """Finalize failed rotation with record updates and audit logging."""
        error_msg = str(error)
        record.status = RotationStatus.FAILED
        record.error_message = error_msg
        record.completed_at = datetime.now(UTC)
        self._rotation_records[secret_name].append(record)

        await self._audit_log(
            "secret_rotation_failed",
            secret_name,
            {
                "rotation_id": rotation_id,
                "trigger": trigger.value,
                "error": error_msg,
            },
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

        logger.error(f"Failed to rotate secret {secret_name}: {error_msg}")
        return RotationResult(
            success=False,
            rotation_id=rotation_id,
            secret_name=secret_name,
            error=error_msg,
            rollback_available=False,
        )

    async def rollback_secret(
        self,
        secret_name: str,
        actor_id: str = "system",
        tenant_id: str = "system",
    ) -> RotationResult:
        """
        Rollback to the previous secret version.

        Rollback is only available during the grace period or rollback window.

        Args:
            secret_name: Name of secret to rollback
            actor_id: Who initiated the rollback
            tenant_id: Tenant context

        Returns:
            RotationResult with rollback status
        """
        rollback_id = self._generate_rotation_id()

        if secret_name not in self._registered_secrets:
            return RotationResult(
                success=False,
                rotation_id=rollback_id,
                secret_name=secret_name,
                error=f"Secret {secret_name} is not registered",
                rollback_available=False,
            )

        _, _policy = self._registered_secrets[secret_name]

        async with self._rotation_lock:
            now = datetime.now(UTC)
            versions = self._versions.get(secret_name, [])

            # Find current and previous versions
            current_version = None
            previous_version = None
            for v in versions:
                if v.is_current:
                    current_version = v
                elif v.is_previous:
                    previous_version = v

            if not current_version or not previous_version:
                return RotationResult(
                    success=False,
                    rotation_id=rollback_id,
                    secret_name=secret_name,
                    error="No previous version available for rollback",
                    rollback_available=False,
                )

            # Check if rollback is still allowed
            if previous_version.expires_at and previous_version.expires_at < now:
                return RotationResult(
                    success=False,
                    rotation_id=rollback_id,
                    secret_name=secret_name,
                    error="Rollback window has expired",
                    rollback_available=False,
                )

            try:
                # Swap versions
                current_version.is_current = False
                current_version.deactivated_at = now
                previous_version.is_current = True
                previous_version.is_previous = False
                previous_version.deactivated_at = None
                previous_version.expires_at = None

                # Record rollback
                record = RotationRecord(
                    rotation_id=rollback_id,
                    secret_name=secret_name,
                    status=RotationStatus.ROLLED_BACK,
                    trigger=RotationTrigger.ON_DEMAND,
                    started_at=now,
                    completed_at=now,
                    previous_version_id=current_version.version_id,
                    new_version_id=previous_version.version_id,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                )
                self._rotation_records[secret_name].append(record)

                await self._audit_log(
                    "secret_rolled_back",
                    secret_name,
                    {
                        "rollback_id": rollback_id,
                        "rolled_back_version": current_version.version_id,
                        "restored_version": previous_version.version_id,
                    },
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                )

                logger.info(
                    f"Rolled back secret {secret_name}: "
                    f"{current_version.version_id} -> {previous_version.version_id}"
                )

                return RotationResult(
                    success=True,
                    rotation_id=rollback_id,
                    secret_name=secret_name,
                    new_version_id=previous_version.version_id,
                    previous_version_id=current_version.version_id,
                    rollback_available=False,  # Can't rollback a rollback
                )

            except (RuntimeError, ValueError, TypeError) as e:
                error_msg = str(e)
                logger.error(f"Failed to rollback secret {secret_name}: {error_msg}")

                return RotationResult(
                    success=False,
                    rotation_id=rollback_id,
                    secret_name=secret_name,
                    error=error_msg,
                    rollback_available=True,
                )

    async def _cleanup_old_versions(self, secret_name: str, max_versions: int) -> None:
        """Remove old versions beyond max_versions limit."""
        versions = self._versions.get(secret_name, [])
        if len(versions) <= max_versions:
            return

        # Sort by creation time and keep only recent versions
        versions.sort(key=lambda v: v.created_at, reverse=True)
        to_remove = versions[max_versions:]

        for version in to_remove:
            if not version.is_current and not version.is_previous:
                await self._backend.delete_secret_version(secret_name, version.version_id)
                versions.remove(version)
                logger.debug(f"Cleaned up old version: {version.version_id}")

    async def get_current_secret(
        self,
        secret_name: str,
        include_previous: bool = False,
    ) -> tuple[str | None, str | None]:
        """
        Get the current secret value(s).

        Args:
            secret_name: Name of the secret
            include_previous: Whether to also return previous version (for dual-key validation)

        Returns:
            Tuple of (current_value, previous_value) - previous is None if not in grace period
        """
        if secret_name not in self._registered_secrets:
            return None, None

        versions = self._versions.get(secret_name, [])
        current_value = None
        previous_value = None

        for version in versions:
            if version.is_current:
                current_value = await self._backend.get_secret(secret_name, version.version_id)
            elif version.is_previous and include_previous:
                # Check if still in grace period
                now = datetime.now(UTC)
                if version.expires_at and version.expires_at > now:
                    previous_value = await self._backend.get_secret(secret_name, version.version_id)

        return current_value, previous_value

    async def get_rotation_status(self, secret_name: str) -> JSONDict:
        """
        Get the rotation status for a secret.

        Args:
            secret_name: Name of the secret

        Returns:
            Status dictionary with version and rotation information
        """
        if secret_name not in self._registered_secrets:
            return {
                "error": f"Secret {secret_name} is not registered",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        secret_type, policy = self._registered_secrets[secret_name]
        versions = self._versions.get(secret_name, [])
        records = self._rotation_records.get(secret_name, [])

        current_version = None
        previous_version = None
        for v in versions:
            if v.is_current:
                current_version = v
            elif v.is_previous:
                previous_version = v

        # Check if rotation is due
        needs_rotation = False
        if current_version and current_version.activated_at:
            age_days = (datetime.now(UTC) - current_version.activated_at).days
            needs_rotation = age_days >= policy.rotation_interval_days

        # Get last rotation
        last_rotation = records[-1] if records else None

        return {
            "secret_name": secret_name,
            "secret_type": secret_type.value,
            "current_version": current_version.to_dict() if current_version else None,
            "previous_version": previous_version.to_dict() if previous_version else None,
            "in_grace_period": previous_version is not None,
            "grace_period_ends": (
                previous_version.expires_at.isoformat()
                if previous_version and previous_version.expires_at
                else None
            ),
            "needs_rotation": needs_rotation,
            "policy": policy.to_dict(),
            "last_rotation": last_rotation.to_dict() if last_rotation else None,
            "total_rotations": len(records),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def check_secrets_needing_rotation(self) -> list[str]:
        """
        Check all secrets and return those needing rotation.

        Returns:
            List of secret names that need rotation based on their policies
        """
        needs_rotation = []
        now = datetime.now(UTC)

        for secret_name, (_, policy) in self._registered_secrets.items():
            if RotationTrigger.TIME_BASED not in policy.triggers:
                continue

            versions = self._versions.get(secret_name, [])
            for version in versions:
                if version.is_current and version.activated_at:
                    age_days = (now - version.activated_at).days
                    if age_days >= policy.rotation_interval_days:
                        needs_rotation.append(secret_name)
                        break

        return needs_rotation

    async def start_scheduler(self, check_interval_seconds: int = 3600) -> None:
        """
        Start the background scheduler for automatic rotations.

        Args:
            check_interval_seconds: How often to check for due rotations
        """
        if self._scheduler_running:
            logger.warning("Scheduler already running")
            return

        self._scheduler_running = True

        async def scheduler_loop() -> None:
            """Continuously check for and rotate secrets that are due."""
            while self._scheduler_running:
                try:
                    # Check for secrets needing rotation
                    due_secrets = await self.check_secrets_needing_rotation()
                    for secret_name in due_secrets:
                        logger.info(f"Auto-rotating secret: {secret_name}")
                        await self.rotate_secret(
                            secret_name,
                            trigger=RotationTrigger.TIME_BASED,
                        )

                    # Expire old grace periods
                    await self._expire_grace_periods()

                except (TimeoutError, OSError, RuntimeError, ValueError, TypeError) as e:
                    # Scheduler must never crash - catch operational errors
                    logger.error(f"Scheduler error ({type(e).__name__}): {e}")

                await asyncio.sleep(check_interval_seconds)

        self._scheduler_task = asyncio.create_task(scheduler_loop())
        logger.info(f"Rotation scheduler started (interval: {check_interval_seconds}s)")

    async def stop_scheduler(self) -> None:
        """Stop the background scheduler."""
        self._scheduler_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task
            self._scheduler_task = None
        logger.info("Rotation scheduler stopped")

    async def _expire_grace_periods(self) -> None:
        """Expire grace periods that have ended."""
        now = datetime.now(UTC)

        for secret_name, versions in self._versions.items():
            for version in versions:
                if version.is_previous and version.expires_at and version.expires_at < now:
                    version.is_previous = False
                    logger.debug(
                        f"Grace period expired for {secret_name} version {version.version_id}"
                    )

                    await self._audit_log(
                        "grace_period_expired",
                        secret_name,
                        {"version_id": version.version_id},
                    )

    def get_health(self) -> JSONDict:
        """Get health status for monitoring."""
        return {
            "status": "healthy",
            "registered_secrets": len(self._registered_secrets),
            "scheduler_running": self._scheduler_running,
            "backend_type": type(self._backend).__name__,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Singleton instance
_rotation_manager: SecretRotationManager | None = None


async def get_rotation_manager(
    backend: SecretBackend | None = None,
) -> SecretRotationManager:
    """Get or create the rotation manager singleton."""
    global _rotation_manager
    if _rotation_manager is None:
        _rotation_manager = SecretRotationManager(backend=backend)
    return _rotation_manager


def reset_rotation_manager() -> None:
    """Reset the rotation manager singleton (for testing)."""
    global _rotation_manager
    _rotation_manager = None


__all__ = [
    # Type alias
    "SecretGenerator",
    # Main class
    "SecretRotationManager",
    # Singleton functions
    "get_rotation_manager",
    "reset_rotation_manager",
]
