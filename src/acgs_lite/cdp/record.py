"""CDPRecordV1 — Constitutional Decision Provenance record schema.

Composes PolicyDecisionV1 + AuditEventV1 fields into a single immutable,
chain-linked provenance artifact.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_CANONICAL_HASH = "608508a9bd224290"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MACIStep:
    """One link in the MACI chain — a single agent's governance action."""

    agent_id: str
    role: str  # proposer | validator | executor | observer
    action: str
    outcome: str  # allow | deny | conditional | abstain | error
    timestamp: str = field(default_factory=_utcnow)
    reasoning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "action": self.action,
            "outcome": self.outcome,
            "timestamp": self.timestamp,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }


@dataclass
class ComplianceEvidenceRef:
    """Reference to a compliance artifact for a specific framework article."""

    framework_id: str  # e.g. "eu_ai_act", "hipaa", "gdpr", "igaming"
    article_ref: str  # e.g. "Art.14", "§164.502", "SR-4.2"
    evidence: str  # human-readable description of evidence
    compliant: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "article_ref": self.article_ref,
            "evidence": self.evidence,
            "compliant": self.compliant,
            "metadata": self.metadata,
        }


@dataclass
class InterventionOutcome:
    """Result of an intervention action triggered by the CDP record."""

    action: str  # block | throttle | notify | escalate | cool_off | log_only
    triggered: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "triggered": self.triggered,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class CDPRecordV1:
    """Constitutional Decision Provenance record — v1.

    Immutable, chain-linked record of a single governance decision.
    The ``cdp_hash`` field is derived deterministically from all other fields
    (excluding itself and ``prev_cdp_hash``) via sorted-key SHA-256.

    Invariants:
    - ``constitutional_hash`` must equal ``608508a9bd224290`` (INV-004)
    - ``input_hash`` is a SHA-256 digest of the raw input — never the raw input (AD-2)
    - ``cdp_hash`` is deterministic: same inputs → same hash across platforms
    """

    # Identity
    cdp_id: str
    tenant_id: str = "default"
    constitutional_hash: str = _CANONICAL_HASH

    # Privacy — input stored only as a hash (AD-2)
    input_hash: str = ""  # SHA-256 of raw input

    # MACI chain
    maci_chain: list[MACIStep] = field(default_factory=list)

    # Decision summary (mirrors PolicyDecisionV1 key fields)
    verdict: str = "allow"  # allow | deny | conditional | abstain | error
    decision_source: str = "constitutional"
    policy_id: str = ""
    subject_id: str = ""
    action: str = ""
    reasoning: str = ""
    matched_rules: list[str] = field(default_factory=list)
    violated_rules: list[str] = field(default_factory=list)
    confidence_score: float = 1.0
    risk_score: float = 0.0
    evaluation_duration_ms: float | None = None

    # Compliance evidence
    compliance_frameworks: list[str] = field(default_factory=list)
    compliance_evidence: list[ComplianceEvidenceRef] = field(default_factory=list)

    # Runtime obligations (Phase 2 — populated by RuntimeComplianceChecker)
    # Stored as plain dicts to avoid importing the compliance module from cdp/
    runtime_obligations: list[dict[str, Any]] = field(default_factory=list)

    # Intervention
    intervention: InterventionOutcome | None = None

    # Correlation
    correlation_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None

    # Chain linking
    prev_cdp_hash: str = "genesis"

    # Timestamps
    created_at: str = field(default_factory=_utcnow)

    # Computed at assembly — see assemble_cdp_record()
    cdp_hash: str = ""

    def _compute_hash(self) -> str:
        """Deterministic SHA-256 of the record content (excluding cdp_hash itself)."""
        payload: dict[str, Any] = {
            "cdp_id": self.cdp_id,
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
            "input_hash": self.input_hash,
            "maci_chain": [s.to_dict() for s in self.maci_chain],
            "verdict": self.verdict,
            "decision_source": self.decision_source,
            "policy_id": self.policy_id,
            "subject_id": self.subject_id,
            "action": self.action,
            "reasoning": self.reasoning,
            "matched_rules": self.matched_rules,
            "violated_rules": self.violated_rules,
            "confidence_score": self.confidence_score,
            "risk_score": self.risk_score,
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "compliance_frameworks": self.compliance_frameworks,
            "compliance_evidence": [e.to_dict() for e in self.compliance_evidence],
            "runtime_obligations": self.runtime_obligations,
            "intervention": self.intervention.to_dict() if self.intervention else None,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "prev_cdp_hash": self.prev_cdp_hash,
            "created_at": self.created_at,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def finalize(self) -> None:
        """Compute and set cdp_hash. Call once before persisting."""
        self.cdp_hash = self._compute_hash()

    def verify(self) -> bool:
        """Return True if cdp_hash matches current record content."""
        return self.cdp_hash == self._compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cdp_id": self.cdp_id,
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
            "input_hash": self.input_hash,
            "maci_chain": [s.to_dict() for s in self.maci_chain],
            "verdict": self.verdict,
            "decision_source": self.decision_source,
            "policy_id": self.policy_id,
            "subject_id": self.subject_id,
            "action": self.action,
            "reasoning": self.reasoning,
            "matched_rules": self.matched_rules,
            "violated_rules": self.violated_rules,
            "confidence_score": self.confidence_score,
            "risk_score": self.risk_score,
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "compliance_frameworks": self.compliance_frameworks,
            "compliance_evidence": [e.to_dict() for e in self.compliance_evidence],
            "runtime_obligations": self.runtime_obligations,
            "intervention": self.intervention.to_dict() if self.intervention else None,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "prev_cdp_hash": self.prev_cdp_hash,
            "created_at": self.created_at,
            "cdp_hash": self.cdp_hash,
        }
