"""
ACGS-2 Retention Policy Engine
Constitutional Hash: cdd01ef066bc6cf2

Implements data retention lifecycle management:
- Policy definition and storage
- Scheduled enforcement job simulation
- Disposal handlers (delete, archive, anonymize, pseudonymize)
- Comprehensive audit logging
- Multi-tenant isolation
"""

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.core.shared.types import MetadataDict

from .data_classification import (
    CONSTITUTIONAL_HASH,
    DEFAULT_RETENTION_POLICIES,
    DataClassificationTier,
    DisposalMethod,
    PIICategory,
    RetentionPolicy,
)

# ============================================================================
# Types and Enums
# ============================================================================


class RetentionStatus(StrEnum):
    """Status of a retention record."""

    ACTIVE = "active"  # Within retention period
    PENDING_DISPOSAL = "pending_disposal"  # Retention expired, awaiting disposal
    DISPOSED = "disposed"  # Successfully disposed
    ARCHIVED = "archived"  # Moved to archive
    ANONYMIZED = "anonymized"  # PII removed
    HELD = "held"  # Legal hold prevents disposal
    ERROR = "error"  # Disposal failed


class RetentionActionType(StrEnum):
    """Types of retention actions."""

    CREATED = "created"
    EXTENDED = "extended"
    DISPOSED = "disposed"
    ARCHIVED = "archived"
    ANONYMIZED = "anonymized"
    HOLD_APPLIED = "hold_applied"
    HOLD_RELEASED = "hold_released"
    POLICY_CHANGED = "policy_changed"
    ERROR = "error"


# ============================================================================
# Models
# ============================================================================


class RetentionRecord(BaseModel):
    """Record of data subject to retention policy."""

    record_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique record identifier"
    )
    data_id: str = Field(..., description="ID of the data being retained")
    data_type: str = Field(..., description="Type/category of data")
    policy_id: str = Field(..., description="Applied retention policy ID")
    classification_tier: DataClassificationTier = Field(...)
    pii_categories: list[PIICategory] = Field(default_factory=list)
    status: RetentionStatus = Field(default=RetentionStatus.ACTIVE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retention_until: datetime = Field(..., description="Retention expiry date")
    disposed_at: datetime | None = Field(default=None)
    disposal_method: DisposalMethod | None = Field(default=None)
    legal_hold: bool = Field(default=False)
    legal_hold_reason: str | None = Field(default=None)
    tenant_id: str | None = Field(default=None)
    metadata: MetadataDict = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


class RetentionAction(BaseModel):
    """Audit log entry for retention actions."""

    action_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique action identifier"
    )
    record_id: str = Field(..., description="Affected retention record ID")
    action_type: RetentionActionType = Field(...)
    performed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    performed_by: str = Field(default="system", description="Actor performing action")
    previous_status: RetentionStatus | None = Field(default=None)
    new_status: RetentionStatus | None = Field(default=None)
    details: MetadataDict = Field(default_factory=dict)
    tenant_id: str | None = Field(default=None)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


class DisposalResult(BaseModel):
    """Result of a disposal operation."""

    record_id: str = Field(...)
    success: bool = Field(...)
    method: DisposalMethod = Field(...)
    disposed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bytes_disposed: int = Field(default=0)
    error_message: str | None = Field(default=None)
    audit_trail_hash: str = Field(default="")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class RetentionEnforcementReport(BaseModel):
    """Report of retention enforcement run."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    records_scanned: int = Field(default=0)
    records_expired: int = Field(default=0)
    records_disposed: int = Field(default=0)
    records_archived: int = Field(default=0)
    records_anonymized: int = Field(default=0)
    records_held: int = Field(default=0)
    records_errored: int = Field(default=0)
    disposal_results: list[DisposalResult] = Field(default_factory=list)
    duration_ms: float = Field(default=0.0)
    tenant_id: str | None = Field(default=None)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


# ============================================================================
# Storage Protocol
# ============================================================================


class RetentionStorageProtocol(Protocol):
    """Protocol for retention record storage backends."""

    async def save_record(self, record: RetentionRecord) -> None:
        """Save a retention record."""
        ...

    async def get_record(self, record_id: str) -> RetentionRecord | None:
        """Get a retention record by ID."""
        ...

    async def find_expired_records(
        self,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
        limit: int = 1000,
    ) -> list[RetentionRecord]:
        """Find records with expired retention periods."""
        ...

    async def update_record(self, record: RetentionRecord) -> None:
        """Update a retention record."""
        ...

    async def log_action(self, action: RetentionAction) -> None:
        """Log a retention action."""
        ...


# ============================================================================
# In-Memory Storage (for testing and development)
# ============================================================================


class InMemoryRetentionStorage:
    """In-memory implementation of retention storage."""

    def __init__(self):
        self.records: dict[str, RetentionRecord] = {}
        self.actions: list[RetentionAction] = []
        self.policies: dict[str, RetentionPolicy] = {
            p.policy_id: p for p in DEFAULT_RETENTION_POLICIES
        }

    async def save_record(self, record: RetentionRecord) -> None:
        """Persist a retention record in the in-memory store."""
        self.records[record.record_id] = record

    async def get_record(self, record_id: str) -> RetentionRecord | None:
        """Return the retention record for the given ID, or None if not found."""
        return self.records.get(record_id)

    async def find_expired_records(
        self,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
        limit: int = 1000,
    ) -> list[RetentionRecord]:
        """Return active records whose retention period has expired."""
        as_of = as_of or datetime.now(UTC)
        expired = []

        for record in self.records.values():
            if record.status != RetentionStatus.ACTIVE:
                continue
            if record.legal_hold:
                continue
            if tenant_id and record.tenant_id != tenant_id:
                continue
            if record.retention_until <= as_of:
                expired.append(record)
                if len(expired) >= limit:
                    break

        return expired

    async def update_record(self, record: RetentionRecord) -> None:
        """Update an existing retention record in the in-memory store."""
        self.records[record.record_id] = record

    async def log_action(self, action: RetentionAction) -> None:
        """Append a retention action to the audit log."""
        self.actions.append(action)

    async def get_actions(
        self,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[RetentionAction]:
        """Get retention actions, optionally filtered by record ID."""
        actions = self.actions
        if record_id:
            actions = [a for a in actions if a.record_id == record_id]
        return actions[-limit:]

    def get_policy(self, policy_id: str) -> RetentionPolicy | None:
        """Return the retention policy for the given ID, or None if not found."""
        return self.policies.get(policy_id)

    def add_policy(self, policy: RetentionPolicy) -> None:
        """Register a new retention policy in the in-memory store."""
        self.policies[policy.policy_id] = policy


# ============================================================================
# Disposal Handlers
# ============================================================================


class DisposalHandler(ABC):
    """Abstract base class for disposal handlers."""

    @abstractmethod
    async def dispose(
        self,
        record: RetentionRecord,
        data: object | None = None,
    ) -> DisposalResult:
        """Execute disposal for a retention record."""
        ...


class DeleteHandler(DisposalHandler):
    """Handler for permanent deletion."""

    async def dispose(
        self,
        record: RetentionRecord,
        data: object | None = None,
    ) -> DisposalResult:
        """Permanently delete data."""
        try:
            # In production, this would call data store deletion APIs
            audit_hash = hashlib.sha256(
                f"{record.record_id}:{record.data_id}:deleted".encode()
            ).hexdigest()[:32]

            return DisposalResult(
                record_id=record.record_id,
                success=True,
                method=DisposalMethod.DELETE,
                bytes_disposed=len(json.dumps(data)) if data else 0,
                audit_trail_hash=audit_hash,
            )
        except (TypeError, ValueError) as e:
            return DisposalResult(
                record_id=record.record_id,
                success=False,
                method=DisposalMethod.DELETE,
                error_message=str(e),
            )


class ArchiveHandler(DisposalHandler):
    """Handler for archiving to cold storage."""

    async def dispose(
        self,
        record: RetentionRecord,
        data: object | None = None,
    ) -> DisposalResult:
        """Archive data to cold storage."""
        try:
            # In production, this would move data to archive storage
            audit_hash = hashlib.sha256(
                f"{record.record_id}:{record.data_id}:archived".encode()
            ).hexdigest()[:32]

            return DisposalResult(
                record_id=record.record_id,
                success=True,
                method=DisposalMethod.ARCHIVE,
                bytes_disposed=len(json.dumps(data)) if data else 0,
                audit_trail_hash=audit_hash,
            )
        except (TypeError, ValueError) as e:
            return DisposalResult(
                record_id=record.record_id,
                success=False,
                method=DisposalMethod.ARCHIVE,
                error_message=str(e),
            )


class AnonymizeHandler(DisposalHandler):
    """Handler for anonymization (remove PII but keep analytics)."""

    async def dispose(
        self,
        record: RetentionRecord,
        data: object | None = None,
    ) -> DisposalResult:
        """Anonymize data by removing identifying information."""
        try:
            # In production, this would apply anonymization transformations
            audit_hash = hashlib.sha256(
                f"{record.record_id}:{record.data_id}:anonymized".encode()
            ).hexdigest()[:32]

            return DisposalResult(
                record_id=record.record_id,
                success=True,
                method=DisposalMethod.ANONYMIZE,
                bytes_disposed=0,  # Data not deleted, just transformed
                audit_trail_hash=audit_hash,
            )
        except (TypeError, ValueError) as e:
            return DisposalResult(
                record_id=record.record_id,
                success=False,
                method=DisposalMethod.ANONYMIZE,
                error_message=str(e),
            )


class PseudonymizeHandler(DisposalHandler):
    """Handler for pseudonymization (replace identifiers)."""

    async def dispose(
        self,
        record: RetentionRecord,
        data: object | None = None,
    ) -> DisposalResult:
        """Pseudonymize data by replacing identifiers with pseudonyms."""
        try:
            # In production, this would apply pseudonymization transformations
            audit_hash = hashlib.sha256(
                f"{record.record_id}:{record.data_id}:pseudonymized".encode()
            ).hexdigest()[:32]

            return DisposalResult(
                record_id=record.record_id,
                success=True,
                method=DisposalMethod.PSEUDONYMIZE,
                bytes_disposed=0,  # Data not deleted, just transformed
                audit_trail_hash=audit_hash,
            )
        except (TypeError, ValueError) as e:
            return DisposalResult(
                record_id=record.record_id,
                success=False,
                method=DisposalMethod.PSEUDONYMIZE,
                error_message=str(e),
            )


# ============================================================================
# Retention Policy Engine
# ============================================================================


class RetentionPolicyEngine:
    """
    Engine for managing data retention lifecycle.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        storage: InMemoryRetentionStorage | None = None,
        disposal_handlers: dict[DisposalMethod, DisposalHandler] | None = None,
    ):
        """
        Initialize retention policy engine.

        Args:
            storage: Storage backend for retention records
            disposal_handlers: Custom disposal handlers per method
        """
        self.storage = storage or InMemoryRetentionStorage()
        self.disposal_handlers = disposal_handlers or {
            DisposalMethod.DELETE: DeleteHandler(),
            DisposalMethod.ARCHIVE: ArchiveHandler(),
            DisposalMethod.ANONYMIZE: AnonymizeHandler(),
            DisposalMethod.PSEUDONYMIZE: PseudonymizeHandler(),
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def create_retention_record(
        self,
        data_id: str,
        data_type: str,
        policy_id: str,
        classification_tier: DataClassificationTier,
        pii_categories: list[PIICategory] | None = None,
        tenant_id: str | None = None,
        metadata: MetadataDict | None = None,
    ) -> RetentionRecord:
        """
        Create a new retention record for data.

        Args:
            data_id: ID of the data being tracked
            data_type: Type/category of data
            policy_id: Retention policy to apply
            classification_tier: Data classification tier
            pii_categories: Detected PII categories
            tenant_id: Tenant identifier
            metadata: Additional metadata

        Returns:
            Created RetentionRecord
        """
        policy = self.storage.get_policy(policy_id)
        if not policy:
            # Use default policy for tier
            for p in DEFAULT_RETENTION_POLICIES:
                if p.classification_tier == classification_tier:
                    policy = p
                    break

        if not policy:
            policy = DEFAULT_RETENTION_POLICIES[-1]  # Fallback to restricted

        # Calculate retention period
        if policy.retention_days == -1:
            retention_until = datetime.max.replace(tzinfo=UTC)
        else:
            retention_until = datetime.now(UTC) + timedelta(days=policy.retention_days)

        record = RetentionRecord(
            data_id=data_id,
            data_type=data_type,
            policy_id=policy.policy_id,
            classification_tier=classification_tier,
            pii_categories=pii_categories or [],
            retention_until=retention_until,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        await self.storage.save_record(record)

        # Log creation action
        await self.storage.log_action(
            RetentionAction(
                record_id=record.record_id,
                action_type=RetentionActionType.CREATED,
                new_status=RetentionStatus.ACTIVE,
                details={
                    "policy_id": policy.policy_id,
                    "retention_days": policy.retention_days,
                    "retention_until": retention_until.isoformat(),
                },
                tenant_id=tenant_id,
            )
        )

        return record

    async def extend_retention(
        self,
        record_id: str,
        additional_days: int,
        reason: str,
        performed_by: str = "system",
    ) -> RetentionRecord | None:
        """
        Extend retention period for a record.

        Args:
            record_id: Record to extend
            additional_days: Additional days to retain
            reason: Reason for extension
            performed_by: Actor performing the action

        Returns:
            Updated RetentionRecord or None if not found
        """
        record = await self.storage.get_record(record_id)
        if not record:
            return None

        old_retention = record.retention_until
        record.retention_until = record.retention_until + timedelta(days=additional_days)
        await self.storage.update_record(record)

        await self.storage.log_action(
            RetentionAction(
                record_id=record_id,
                action_type=RetentionActionType.EXTENDED,
                performed_by=performed_by,
                details={
                    "previous_retention_until": old_retention.isoformat(),
                    "new_retention_until": record.retention_until.isoformat(),
                    "additional_days": additional_days,
                    "reason": reason,
                },
                tenant_id=record.tenant_id,
            )
        )

        return record

    async def apply_legal_hold(
        self,
        record_id: str,
        reason: str,
        performed_by: str = "legal",
    ) -> RetentionRecord | None:
        """
        Apply legal hold to prevent disposal.

        Args:
            record_id: Record to hold
            reason: Legal hold reason
            performed_by: Actor applying hold

        Returns:
            Updated RetentionRecord or None if not found
        """
        record = await self.storage.get_record(record_id)
        if not record:
            return None

        record.legal_hold = True
        record.legal_hold_reason = reason
        await self.storage.update_record(record)

        await self.storage.log_action(
            RetentionAction(
                record_id=record_id,
                action_type=RetentionActionType.HOLD_APPLIED,
                performed_by=performed_by,
                details={"reason": reason},
                tenant_id=record.tenant_id,
            )
        )

        return record

    async def release_legal_hold(
        self,
        record_id: str,
        performed_by: str = "legal",
    ) -> RetentionRecord | None:
        """
        Release legal hold from a record.

        Args:
            record_id: Record to release
            performed_by: Actor releasing hold

        Returns:
            Updated RetentionRecord or None if not found
        """
        record = await self.storage.get_record(record_id)
        if not record:
            return None

        record.legal_hold = False
        record.legal_hold_reason = None
        await self.storage.update_record(record)

        await self.storage.log_action(
            RetentionAction(
                record_id=record_id,
                action_type=RetentionActionType.HOLD_RELEASED,
                performed_by=performed_by,
                tenant_id=record.tenant_id,
            )
        )

        return record

    async def dispose_record(
        self,
        record_id: str,
        method: DisposalMethod | None = None,
        data: object | None = None,
    ) -> DisposalResult:
        """
        Dispose of a retention record.

        Args:
            record_id: Record to dispose
            method: Disposal method (uses policy default if None)
            data: Actual data to dispose (optional)

        Returns:
            DisposalResult
        """
        record = await self.storage.get_record(record_id)
        if not record:
            return DisposalResult(
                record_id=record_id,
                success=False,
                method=method or DisposalMethod.DELETE,
                error_message="Record not found",
            )

        if record.legal_hold:
            return DisposalResult(
                record_id=record_id,
                success=False,
                method=method or DisposalMethod.DELETE,
                error_message="Record is under legal hold",
            )

        # Determine disposal method
        if method is None:
            policy = self.storage.get_policy(record.policy_id)
            method = policy.disposal_method if policy else DisposalMethod.DELETE

        # Get handler and execute disposal
        handler = self.disposal_handlers.get(method)
        if not handler:
            return DisposalResult(
                record_id=record_id,
                success=False,
                method=method,
                error_message=f"No handler for disposal method: {method}",
            )

        result = await handler.dispose(record, data)

        # Update record status
        previous_status = record.status
        if result.success:
            if method == DisposalMethod.DELETE:
                record.status = RetentionStatus.DISPOSED
            elif method == DisposalMethod.ARCHIVE:
                record.status = RetentionStatus.ARCHIVED
            elif method in (DisposalMethod.ANONYMIZE, DisposalMethod.PSEUDONYMIZE):
                record.status = RetentionStatus.ANONYMIZED
            record.disposed_at = result.disposed_at
            record.disposal_method = method
        else:
            record.status = RetentionStatus.ERROR

        await self.storage.update_record(record)

        # Log action
        action_type = {
            DisposalMethod.DELETE: RetentionActionType.DISPOSED,
            DisposalMethod.ARCHIVE: RetentionActionType.ARCHIVED,
            DisposalMethod.ANONYMIZE: RetentionActionType.ANONYMIZED,
            DisposalMethod.PSEUDONYMIZE: RetentionActionType.ANONYMIZED,
        }.get(method, RetentionActionType.DISPOSED)

        await self.storage.log_action(
            RetentionAction(
                record_id=record_id,
                action_type=action_type if result.success else RetentionActionType.ERROR,
                previous_status=previous_status,
                new_status=record.status,
                details={
                    "method": method.value if hasattr(method, "value") else str(method),
                    "success": result.success,
                    "error": result.error_message,
                    "audit_trail_hash": result.audit_trail_hash,
                },
                tenant_id=record.tenant_id,
            )
        )

        return result

    async def enforce_retention(
        self,
        tenant_id: str | None = None,
        batch_size: int = 100,
    ) -> RetentionEnforcementReport:
        """
        Enforce retention policies by disposing expired records.

        Args:
            tenant_id: Optional tenant filter
            batch_size: Number of records to process per batch

        Returns:
            RetentionEnforcementReport
        """
        start_time = datetime.now(UTC)

        report = RetentionEnforcementReport(
            tenant_id=tenant_id,
        )

        # Find expired records
        expired_records = await self.storage.find_expired_records(
            tenant_id=tenant_id,
            limit=batch_size,
        )

        report.records_scanned = len(expired_records)
        report.records_expired = len(expired_records)

        # Process each expired record
        for record in expired_records:
            if record.legal_hold:
                report.records_held += 1
                continue

            result = await self.dispose_record(record.record_id)
            report.disposal_results.append(result)

            if result.success:
                if result.method == DisposalMethod.DELETE:
                    report.records_disposed += 1
                elif result.method == DisposalMethod.ARCHIVE:
                    report.records_archived += 1
                elif result.method in (DisposalMethod.ANONYMIZE, DisposalMethod.PSEUDONYMIZE):
                    report.records_anonymized += 1
            else:
                report.records_errored += 1

        end_time = datetime.now(UTC)
        report.duration_ms = (end_time - start_time).total_seconds() * 1000

        return report

    async def get_record_history(
        self,
        record_id: str,
    ) -> list[RetentionAction]:
        """Get action history for a retention record."""
        return await self.storage.get_actions(record_id=record_id)


# ============================================================================
# Singleton Instance
# ============================================================================


_engine_instance: RetentionPolicyEngine | None = None


def get_retention_engine() -> RetentionPolicyEngine:
    """Get or create the singleton RetentionPolicyEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RetentionPolicyEngine()
    return _engine_instance


def reset_retention_engine() -> None:
    """Reset the singleton instance (for testing)."""
    global _engine_instance
    _engine_instance = None


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "AnonymizeHandler",
    "ArchiveHandler",
    "DeleteHandler",
    # Handlers
    "DisposalHandler",
    "DisposalResult",
    "InMemoryRetentionStorage",
    "PseudonymizeHandler",
    "RetentionAction",
    "RetentionActionType",
    "RetentionEnforcementReport",
    # Engine
    "RetentionPolicyEngine",
    # Models
    "RetentionRecord",
    # Enums
    "RetentionStatus",
    # Storage
    "RetentionStorageProtocol",
    "get_retention_engine",
    "reset_retention_engine",
]
