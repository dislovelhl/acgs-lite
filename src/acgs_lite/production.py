"""Production profile validation for fail-closed ACGS deployments.

The validator is intentionally small and deterministic: it checks the deployment
inputs that must be true before a governed production service starts accepting
traffic. It does not create files, fetch remote configuration, or silently repair
unsafe settings.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from acgs_lite.constitution import Constitution
from acgs_lite.maci import MACIRole


class ProductionProfileError(ValueError):
    """Raised when a production profile is unsafe or incomplete."""


@dataclass(frozen=True)
class ProductionProfile:
    """Required startup controls for a production ACGS deployment.

    Attributes:
        enforce_maci: Must be ``True`` in production.
        maci_role: Explicit role used by governed production entrypoints.
        constitution_artifact_path: Active constitution YAML artifact.
        expected_artifact_sha256: Full SHA-256 of the active artifact bytes.
        expected_constitutional_hash: ACGS constitutional hash derived from parsed rules.
        backup_artifact_path: Local hot-backup constitution artifact.
        rollback_bundle_id: Previous known-good bundle/version identifier.
        audit_log_path: Optional audit log target; parent must be writable/creatable.
        rbac_enabled: Whether production control-plane RBAC is enabled.
        allow_advisory_only: Must remain ``False`` in production.
    """

    enforce_maci: bool
    maci_role: MACIRole | None
    constitution_artifact_path: str | Path
    expected_artifact_sha256: str
    expected_constitutional_hash: str
    backup_artifact_path: str | Path | None
    rollback_bundle_id: str
    audit_log_path: str | Path | None = None
    rbac_enabled: bool = False
    allow_advisory_only: bool = False


@dataclass(frozen=True)
class ProductionProfileValidation:
    """Successful production profile validation result."""

    constitution_artifact_path: Path
    artifact_sha256: str
    constitutional_hash: str
    backup_artifact_path: Path
    rollback_bundle_id: str
    audit_log_path: Path | None


def validate_production_profile(profile: ProductionProfile) -> ProductionProfileValidation:
    """Validate a production profile and fail closed on any unsafe setting.

    The validator checks MACI hard enforcement, advisory-mode exclusion,
    constitution artifact existence/parseability, full artifact SHA-256 pinning,
    constitutional-hash pinning, local hot backup, rollback target, audit path
    parent, and RBAC enablement. All validation errors are reported together to
    make release-gate output actionable.
    """

    errors: list[str] = []

    if not profile.enforce_maci:
        errors.append("Production profiles require enforce_maci=True")
    if profile.maci_role is None:
        errors.append("Production profiles require an explicit maci_role")
    if profile.allow_advisory_only:
        errors.append("Production profiles must not allow advisory-only MACI mode")
    if not profile.rbac_enabled:
        errors.append("RBAC must be enabled for production control-plane actions")
    if not profile.rollback_bundle_id:
        errors.append("rollback_bundle_id is required for production rollback")

    constitution_path = Path(profile.constitution_artifact_path)
    constitution_hash = ""
    artifact_sha256 = ""
    if not constitution_path.exists():
        errors.append(f"Constitution artifact not found: {constitution_path}")
    elif not constitution_path.is_file():
        errors.append(f"Constitution artifact is not a file: {constitution_path}")
    else:
        artifact_bytes = constitution_path.read_bytes()
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        if artifact_sha256 != profile.expected_artifact_sha256:
            errors.append(
                "Artifact SHA-256 mismatch: "
                f"expected {profile.expected_artifact_sha256}, got {artifact_sha256}"
            )
        try:
            constitution = Constitution.from_yaml(constitution_path)
            constitution_hash = constitution.hash
            if constitution_hash != profile.expected_constitutional_hash:
                errors.append(
                    "Constitutional hash mismatch: "
                    f"expected {profile.expected_constitutional_hash}, got {constitution_hash}"
                )
        except Exception as exc:  # noqa: BLE001 - startup gate should report parse failures
            errors.append(f"Constitution artifact failed validation: {exc}")

    backup_path: Path | None = None
    if profile.backup_artifact_path is None:
        errors.append("Backup constitution artifact is required for production rollback")
    else:
        backup_path = Path(profile.backup_artifact_path)
        if not backup_path.exists():
            errors.append(f"Backup constitution artifact not found: {backup_path}")
        elif not backup_path.is_file():
            errors.append(f"Backup constitution artifact is not a file: {backup_path}")

    audit_path: Path | None = None
    if profile.audit_log_path is not None:
        audit_path = Path(profile.audit_log_path)
        audit_parent = audit_path.parent
        if audit_parent.exists() and not audit_parent.is_dir():
            errors.append(f"Audit log parent is not a directory: {audit_parent}")

    if errors:
        raise ProductionProfileError("; ".join(errors))

    # Narrowing for type checkers; errors above guarantee backup_path exists.
    assert backup_path is not None
    return ProductionProfileValidation(
        constitution_artifact_path=constitution_path,
        artifact_sha256=artifact_sha256,
        constitutional_hash=constitution_hash,
        backup_artifact_path=backup_path,
        rollback_bundle_id=profile.rollback_bundle_id,
        audit_log_path=audit_path,
    )
