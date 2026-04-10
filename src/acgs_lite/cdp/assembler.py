"""CDP assembler — pure function for building CDPRecordV1 from governance context.

Validates constitutional hash invariant, computes input_hash (never stores raw
input — AD-2), builds the MACI chain from audit entries, chains to the previous
record, and finalizes the hash.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from acgs_lite.cdp.record import (
    CDPRecordV1,
    ComplianceEvidenceRef,
    InterventionOutcome,
    MACIStep,
)

_CANONICAL_HASH = "608508a9bd224290"


def _hash_input(raw_input: str) -> str:
    """Return SHA-256 hex digest of raw_input (full, not truncated)."""
    return hashlib.sha256(raw_input.encode()).hexdigest()


def assemble_cdp_record(
    *,
    raw_input: str,
    agent_id: str,
    constitutional_hash: str,
    verdict: str = "allow",
    decision_source: str = "constitutional",
    policy_id: str = "",
    subject_id: str = "",
    action: str = "",
    reasoning: str = "",
    matched_rules: list[str] | None = None,
    violated_rules: list[str] | None = None,
    confidence_score: float = 1.0,
    risk_score: float = 0.0,
    evaluation_duration_ms: float | None = None,
    compliance_frameworks: list[str] | None = None,
    compliance_evidence: list[ComplianceEvidenceRef] | None = None,
    runtime_obligations: list[Any] | None = None,
    maci_chain: list[MACIStep] | None = None,
    intervention: InterventionOutcome | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    tenant_id: str = "default",
    prev_cdp_hash: str = "genesis",
    cdp_id: str | None = None,
    created_at: str | None = None,
    audit_entries: list[Any] | None = None,
) -> CDPRecordV1:
    """Assemble a CDPRecordV1 from governance context.

    This is a pure function: the same inputs always produce the same cdp_hash.
    ``raw_input`` is hashed immediately and the original string is not stored.

    Args:
        raw_input: The original agent input — stored only as a SHA-256 hash.
        agent_id: ID of the governing agent.
        constitutional_hash: Must match the canonical hash (608508a9bd224290).
        verdict: Policy decision outcome.
        decision_source: Which policy engine produced the decision.
        policy_id: ID of the evaluated policy.
        subject_id: Subject being evaluated (defaults to agent_id).
        action: Action being governed.
        reasoning: Human-readable decision explanation.
        matched_rules: Policy rules that matched.
        violated_rules: Policy rules that were violated.
        confidence_score: Decision confidence (0.0–1.0).
        risk_score: Risk assessment (0.0–1.0).
        evaluation_duration_ms: How long the evaluation took.
        compliance_frameworks: Applicable frameworks (eu_ai_act, hipaa, etc.).
        compliance_evidence: Per-article compliance evidence refs.
        maci_chain: Ordered list of MACI agent steps.
        intervention: Intervention outcome (if any).
        correlation_id: Distributed tracing ID.
        request_id: HTTP request ID.
        session_id: Session identifier.
        tenant_id: Multi-tenant identifier.
        prev_cdp_hash: Hash of previous CDP record (or "genesis").
        cdp_id: Explicit record ID (auto-generated if None).
        audit_entries: AuditEntry objects to fold into the MACI chain.

    Returns:
        Finalized CDPRecordV1 with cdp_hash set.

    Raises:
        ValueError: If constitutional_hash does not match canonical value.
    """
    if constitutional_hash != _CANONICAL_HASH:
        raise ValueError(
            f"Constitutional hash mismatch: expected {_CANONICAL_HASH!r}, "
            f"got {constitutional_hash!r} — INV-004 violated"
        )

    record_id = cdp_id or f"cdp-{uuid.uuid4().hex}"
    input_hash = _hash_input(raw_input)
    effective_subject_id = subject_id or agent_id

    # Build MACI chain from explicit steps or fold in audit entries
    chain: list[MACIStep] = list(maci_chain or [])
    if audit_entries:
        for entry in audit_entries:
            entry_type = getattr(entry, "type", "")
            entry_action = getattr(entry, "action", "")
            entry_valid = getattr(entry, "valid", True)
            if entry_type in ("validation", "maci_check", "output_retry"):
                chain.append(
                    MACIStep(
                        agent_id=getattr(entry, "agent_id", agent_id),
                        role=_infer_role(entry_type),
                        action=entry_action or entry_type,
                        outcome="allow" if entry_valid else "deny",
                        timestamp=getattr(entry, "timestamp", ""),
                        reasoning=", ".join(getattr(entry, "violations", [])),
                        metadata=getattr(entry, "metadata", {}),
                    )
                )

    # Add a proposer step for the governing agent if chain is empty
    if not chain:
        step_kwargs: dict[str, Any] = {
            "agent_id": agent_id,
            "role": "proposer",
            "action": action or "execute",
            "outcome": verdict,
            "reasoning": reasoning,
        }
        if created_at is not None:
            step_kwargs["timestamp"] = created_at
        chain.append(MACIStep(**step_kwargs))

    record_kwargs: dict[str, Any] = {
        "cdp_id": record_id,
        "tenant_id": tenant_id,
        "constitutional_hash": constitutional_hash,
        "input_hash": input_hash,
        "maci_chain": chain,
        "verdict": verdict,
        "decision_source": decision_source,
        "policy_id": policy_id,
        "subject_id": effective_subject_id,
        "action": action,
        "reasoning": reasoning,
        "matched_rules": list(matched_rules or []),
        "violated_rules": list(violated_rules or []),
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "evaluation_duration_ms": evaluation_duration_ms,
        "compliance_frameworks": list(compliance_frameworks or []),
        "compliance_evidence": list(compliance_evidence or []),
        "runtime_obligations": _serialize_obligations(runtime_obligations),
        "intervention": intervention,
        "correlation_id": correlation_id,
        "request_id": request_id,
        "session_id": session_id,
        "prev_cdp_hash": prev_cdp_hash,
    }
    if created_at is not None:
        record_kwargs["created_at"] = created_at
    record = CDPRecordV1(**record_kwargs)
    record.finalize()
    return record


def _serialize_obligations(obligations: list[Any] | None) -> list[dict[str, Any]]:
    """Convert RuntimeObligation objects (or plain dicts) to plain dicts for storage."""
    if not obligations:
        return []
    result: list[dict[str, Any]] = []
    for ob in obligations:
        if isinstance(ob, dict):
            result.append(ob)
        elif hasattr(ob, "to_dict"):
            result.append(ob.to_dict())
    return result


def _infer_role(entry_type: str) -> str:
    """Map audit entry type to MACI role."""
    mapping = {
        "validation": "validator",
        "maci_check": "validator",
        "output_retry": "executor",
        "override": "observer",
    }
    return mapping.get(entry_type, "executor")
