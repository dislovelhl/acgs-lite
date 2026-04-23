"""Regression: strict=True + audit_metadata writes a durable audit entry.

T-06: in audit_mode='full', the Rust context+strict fast path was missing
the `_fast_records is not None` guard, so it silently bypassed
`_record_validation_audit` and dropped audit_metadata.
"""

from __future__ import annotations

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine


def _make_engine(strict: bool = True) -> tuple[GovernanceEngine, AuditLog]:
    rules = [
        Rule(
            id="NO-DELETE",
            text="Do not delete production data",
            severity=Severity.HIGH,
            patterns=("delete production",),
        ),
    ]
    constitution = Constitution(name="t6", rules=rules, hash="t6hash")
    audit = AuditLog()
    engine = GovernanceEngine(constitution, audit_log=audit, strict=strict)
    return engine, audit


class TestAuditMetadataWithStrictTrue:
    def test_full_mode_strict_true_no_context_writes_audit(self) -> None:
        engine, audit = _make_engine(strict=True)
        engine.validate(
            "deploy service",
            agent_id="agent-1",
            audit_metadata={"job": "release-42"},
        )
        entries = audit.entries
        assert len(entries) == 1
        assert entries[0].metadata.get("runtime_governance") == {"job": "release-42"}

    def test_full_mode_strict_true_with_context_writes_audit(self) -> None:
        """Bug T-06: Rust context fast path must NOT bypass durable audit in full mode."""
        engine, audit = _make_engine(strict=True)
        engine.validate(
            "deploy service",
            agent_id="agent-1",
            context={"action_detail": "rolling restart of api"},
            audit_metadata={"job": "release-42"},
        )
        entries = audit.entries
        assert len(entries) == 1, (
            f"Audit log empty in full mode: Rust fast path bypassed _record_validation_audit "
            f"(T-06). Entries: {entries}"
        )
        assert entries[0].metadata.get("runtime_governance") == {"job": "release-42"}
        assert entries[0].agent_id == "agent-1"

    def test_full_mode_strict_true_with_context_blocked_writes_audit(self) -> None:
        """Even when blocked, a durable audit row must exist before the raise."""
        import contextlib

        from acgs_lite.errors import ConstitutionalViolationError

        engine, audit = _make_engine(strict=True)
        with contextlib.suppress(ConstitutionalViolationError):
            engine.validate(
                "delete production now",
                agent_id="agent-1",
                context={"action_detail": "scheduled cleanup"},
                audit_metadata={"approver": "alice"},
            )
        entries = audit.entries
        assert len(entries) >= 1
        assert any(
            e.metadata.get("runtime_governance") == {"approver": "alice"} for e in entries
        )
