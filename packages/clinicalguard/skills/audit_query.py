"""ClinicalGuard: query_audit_trail skill.

Queries the in-process AuditLog by audit_id or time range.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any

from acgs_lite.audit import AuditLog


def query_audit_trail(
    audit_log: AuditLog,
    *,
    audit_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Query the tamper-evident audit trail.

    Args:
        audit_log: The live AuditLog instance.
        audit_id:  If provided, return the single entry with this id.
        limit:     Max entries to return when no audit_id given (default 20).

    Returns dict with:
        found:             bool
        entries:           list[dict]
        chain_valid:       bool
        total_entries:     int
        constitutional_hash: str (from most recent entry, if any)
    """
    chain_valid = audit_log.verify_chain()
    total = len(audit_log)

    if audit_id:
        matches = [e for e in audit_log.entries if e.id == audit_id]
        if not matches:
            return {
                "found": False,
                "entries": [],
                "chain_valid": chain_valid,
                "total_entries": total,
                "constitutional_hash": "",
                "error": f"No entry found with audit_id={audit_id!r}",
            }
        entries = [matches[0].to_dict()]
        const_hash = matches[0].constitutional_hash
    else:
        recent = audit_log.entries[-limit:] if audit_log.entries else []
        entries = [e.to_dict() for e in recent]
        const_hash = recent[-1].constitutional_hash if recent else ""

    return {
        "found": True,
        "entries": entries,
        "chain_valid": chain_valid,
        "total_entries": total,
        "constitutional_hash": const_hash,
    }
