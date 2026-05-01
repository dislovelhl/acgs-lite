"""S_audit_chain — per-record audit-chain hash consistency.

v0 wraps the existing ``AuditLog.verify_chain()`` (whole-log) into a
binary stabilizer bit. Per-entry granularity is deferred to a follow-up;
the whole-log path already short-circuits on the first tampered entry,
which is sufficient for the F1 keystone PR.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..failure_modes import StabilizerOutcome, StabilizerResult


class AuditChainStabilizer:
    """``S_audit_chain`` — emit PASS if the audit chain verifies, FAIL on tamper."""

    id: ClassVar[str] = "S_audit_chain"

    __slots__ = ()

    def evaluate(self, *, audit_log: Any) -> StabilizerResult:
        """Run ``audit_log.verify_chain()`` and emit the corresponding bit.

        Evidence: the boolean result and the count of entries inspected.
        """
        # Duck-typed; any object exposing ``verify_chain()`` and ``entries``
        # works (the production type is ``acgs_lite.audit.AuditLog``).
        chain_valid = bool(audit_log.verify_chain())
        entry_count = len(getattr(audit_log, "entries", ()) or ())
        return StabilizerResult(
            stabilizer_id=self.id,
            outcome=StabilizerOutcome.PASS if chain_valid else StabilizerOutcome.FAIL,
            evidence={
                "chain_valid": chain_valid,
                "entry_count": entry_count,
            },
        )
