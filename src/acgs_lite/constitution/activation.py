"""Runtime activation contract for constitution bundles.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ActivationRecord(BaseModel):
    """Immutable record written when a bundle becomes ACTIVE."""

    model_config = ConfigDict(validate_assignment=True)

    bundle_id: str
    version: int
    tenant_id: str
    constitutional_hash: str
    activated_by: str
    activated_at: datetime = Field(default_factory=_utcnow)
    parent_bundle_id: str | None = None
    rollback_to_bundle_id: str | None = None
    signature: str

    @classmethod
    def from_bundle(
        cls,
        bundle: ConstitutionBundle,
        *,
        signature: str,
        rollback_to_bundle_id: str | None = None,
    ) -> ActivationRecord:
        """Build an activation record from an ACTIVE bundle."""

        if bundle.status != BundleStatus.ACTIVE:
            raise ValueError("ActivationRecord can only be created from an ACTIVE bundle")
        if bundle.activated_by is None:
            raise ValueError("ACTIVE bundle is missing activated_by")
        return cls(
            bundle_id=bundle.bundle_id,
            version=bundle.version,
            tenant_id=bundle.tenant_id,
            constitutional_hash=bundle.constitutional_hash,
            activated_by=bundle.activated_by,
            activated_at=bundle.activated_at or _utcnow(),
            parent_bundle_id=bundle.parent_bundle_id,
            rollback_to_bundle_id=rollback_to_bundle_id or bundle.parent_bundle_id,
            signature=signature,
        )


__all__ = ["ActivationRecord"]
