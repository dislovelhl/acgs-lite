from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from acgs_lite import (
    MACIRole,
    ProductionProfile,
    ProductionProfileError,
    validate_production_profile,
)

CONSTITUTION_YAML = """
name: production-test
version: 1.0.0
rules:
  - id: no-secret-exfiltration
    text: Do not exfiltrate secrets
    severity: critical
    keywords: [secret, exfiltrate]
"""


def _write_constitution(tmp_path: Path) -> Path:
    path = tmp_path / "constitution.yaml"
    path.write_text(CONSTITUTION_YAML, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_production_profile_accepts_pinned_fail_closed_profile(tmp_path: Path) -> None:
    constitution_path = _write_constitution(tmp_path)
    backup_path = tmp_path / "constitution.backup.yaml"
    backup_path.write_text(CONSTITUTION_YAML, encoding="utf-8")

    profile = ProductionProfile(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256=_sha256(constitution_path),
        expected_constitutional_hash="2a7aeefacec85b1f",
        backup_artifact_path=backup_path,
        rollback_bundle_id="constitution-v1",
        audit_log_path=tmp_path / "audit" / "production.jsonl",
        rbac_enabled=True,
    )

    result = validate_production_profile(profile)

    assert result.constitutional_hash == "2a7aeefacec85b1f"
    assert result.artifact_sha256 == _sha256(constitution_path)
    assert result.rollback_bundle_id == "constitution-v1"
    assert result.audit_log_path == tmp_path / "audit" / "production.jsonl"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"enforce_maci": False}, "enforce_maci=True"),
        ({"maci_role": None}, "maci_role"),
        ({"allow_advisory_only": True}, "advisory"),
        ({"constitution_artifact_path": Path("missing.yaml")}, "Constitution artifact not found"),
    ],
)
def test_validate_production_profile_rejects_unsafe_maci_and_missing_artifact(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    constitution_path = _write_constitution(tmp_path)
    backup_path = tmp_path / "constitution.backup.yaml"
    backup_path.write_text(CONSTITUTION_YAML, encoding="utf-8")
    values = dict(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256=_sha256(constitution_path),
        expected_constitutional_hash="2a7aeefacec85b1f",
        backup_artifact_path=backup_path,
        rollback_bundle_id="constitution-v1",
        rbac_enabled=True,
    )
    values.update(kwargs)

    with pytest.raises(ProductionProfileError, match=message):
        validate_production_profile(ProductionProfile(**values))


def test_validate_production_profile_rejects_hash_mismatch(tmp_path: Path) -> None:
    constitution_path = _write_constitution(tmp_path)
    backup_path = tmp_path / "constitution.backup.yaml"
    backup_path.write_text(CONSTITUTION_YAML, encoding="utf-8")

    profile = ProductionProfile(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256="0" * 64,
        expected_constitutional_hash="2a7aeefacec85b1f",
        backup_artifact_path=backup_path,
        rollback_bundle_id="constitution-v1",
        rbac_enabled=True,
    )

    with pytest.raises(ProductionProfileError, match="Artifact SHA-256 mismatch"):
        validate_production_profile(profile)


def test_validate_production_profile_rejects_constitutional_hash_mismatch(tmp_path: Path) -> None:
    constitution_path = _write_constitution(tmp_path)
    backup_path = tmp_path / "constitution.backup.yaml"
    backup_path.write_text(CONSTITUTION_YAML, encoding="utf-8")

    profile = ProductionProfile(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256=_sha256(constitution_path),
        expected_constitutional_hash="wronghash",
        backup_artifact_path=backup_path,
        rollback_bundle_id="constitution-v1",
        rbac_enabled=True,
    )

    with pytest.raises(ProductionProfileError, match="Constitutional hash mismatch"):
        validate_production_profile(profile)


def test_validate_production_profile_requires_backup_rollback_and_rbac(tmp_path: Path) -> None:
    constitution_path = _write_constitution(tmp_path)

    profile = ProductionProfile(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256=_sha256(constitution_path),
        expected_constitutional_hash="2a7aeefacec85b1f",
        backup_artifact_path=None,
        rollback_bundle_id="",
        rbac_enabled=False,
    )

    with pytest.raises(ProductionProfileError) as exc:
        validate_production_profile(profile)

    message = str(exc.value)
    assert "Backup constitution artifact is required" in message
    assert "rollback_bundle_id is required" in message
    assert "RBAC must be enabled" in message
