"""exp181: GovernanceContract — bilateral agent governance agreements.

Formalizes interaction commitments between agents as enforceable contracts
with terms, obligations, expiration, breach detection, and dispute resolution.

Usage:
    registry = ContractRegistry()
    contract = registry.create_contract(
        party_a="agent-alpha",
        party_b="agent-beta",
        terms=[
            ContractTerm(
                term_id="T1",
                description="Agent-alpha must not share PII received from agent-beta",
                category="data_protection",
                severity=Severity.CRITICAL,
            ),
            ContractTerm(
                term_id="T2",
                description="Response latency must not exceed 500ms",
                category="sla",
                severity=Severity.MEDIUM,
                measurable=True,
                threshold=500.0,
            ),
        ],
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )

    # Check compliance
    breach = contract.report_breach("T1", reported_by="agent-beta", evidence="PII in response")
    assert contract.status == ContractStatus.DISPUTED

    # Resolve
    contract.resolve_dispute(breach.breach_id, resolution="warning", resolved_by="governance-admin")
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ContractStatus(Enum):
    """Lifecycle states for a governance contract."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    DISPUTED = "disputed"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class BreachSeverity(Enum):
    """Severity classification for contract breaches."""

    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class DisputeResolution(Enum):
    """Outcome of a dispute resolution process."""

    DISMISSED = "dismissed"
    WARNING = "warning"
    REMEDIATION_REQUIRED = "remediation_required"
    CONTRACT_SUSPENDED = "contract_suspended"
    CONTRACT_TERMINATED = "contract_terminated"


@dataclass
class ContractTerm:
    """A single term in a governance contract."""

    term_id: str
    description: str
    category: str
    severity: str = "medium"
    measurable: bool = False
    threshold: float | None = None
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "term_id": self.term_id,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
        }
        if self.measurable:
            d["measurable"] = True
            if self.threshold is not None:
                d["threshold"] = self.threshold
            if self.unit is not None:
                d["unit"] = self.unit
        return d


@dataclass
class BreachRecord:
    """Record of a contract term breach."""

    breach_id: str
    contract_id: str
    term_id: str
    reported_by: str
    evidence: str
    severity: BreachSeverity
    timestamp: datetime
    resolved: bool = False
    resolution: DisputeResolution | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "breach_id": self.breach_id,
            "contract_id": self.contract_id,
            "term_id": self.term_id,
            "reported_by": self.reported_by,
            "evidence": self.evidence,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
        }
        if self.resolved:
            d["resolution"] = self.resolution.value if self.resolution else None
            d["resolved_by"] = self.resolved_by
            d["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
            d["resolution_notes"] = self.resolution_notes
        return d


@dataclass
class GovernanceContract:
    """A bilateral governance agreement between two agents.

    Contracts formalize interaction commitments with enforceable terms,
    breach reporting, and dispute resolution.
    """

    contract_id: str
    party_a: str
    party_b: str
    terms: list[ContractTerm]
    created_at: datetime
    expires_at: datetime | None = None
    status: ContractStatus = ContractStatus.DRAFT
    breaches: list[BreachRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    _history: list[dict[str, Any]] = field(default_factory=list)

    def _record_event(self, event: str, **kwargs: Any) -> None:
        self._history.append(
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            }
        )

    def propose(self, proposed_by: str) -> None:
        """Move contract from DRAFT to PROPOSED."""
        if self.status != ContractStatus.DRAFT:
            msg = f"Can only propose from DRAFT, current: {self.status.value}"
            raise ValueError(msg)
        if proposed_by not in (self.party_a, self.party_b):
            msg = f"Only contract parties can propose: {proposed_by}"
            raise ValueError(msg)
        self.status = ContractStatus.PROPOSED
        self._record_event("proposed", by=proposed_by)

    def accept(self, accepted_by: str) -> None:
        """Accept a proposed contract, making it ACTIVE."""
        if self.status != ContractStatus.PROPOSED:
            msg = f"Can only accept from PROPOSED, current: {self.status.value}"
            raise ValueError(msg)
        if accepted_by not in (self.party_a, self.party_b):
            msg = f"Only contract parties can accept: {accepted_by}"
            raise ValueError(msg)
        last_proposal = next((e for e in reversed(self._history) if e["event"] == "proposed"), None)
        if last_proposal and last_proposal.get("by") == accepted_by:
            msg = "Cannot accept your own proposal (MACI separation)"
            raise ValueError(msg)
        self.status = ContractStatus.ACTIVE
        self._record_event("accepted", by=accepted_by)

    def is_active(self) -> bool:
        """Check if the contract is currently active and not expired."""
        if self.status != ContractStatus.ACTIVE:
            return False
        if self.expires_at is not None:
            return datetime.now(timezone.utc) < self.expires_at
        return True

    def check_expiry(self) -> bool:
        """Check and update expiry status. Returns True if expired."""
        if (
            self.expires_at is not None
            and self.status == ContractStatus.ACTIVE
            and datetime.now(timezone.utc) >= self.expires_at
        ):
            self.status = ContractStatus.EXPIRED
            self._record_event("expired")
            return True
        return False

    def report_breach(
        self,
        term_id: str,
        reported_by: str,
        evidence: str,
        severity: BreachSeverity | None = None,
    ) -> BreachRecord:
        """Report a breach of a contract term."""
        if self.status not in (ContractStatus.ACTIVE, ContractStatus.DISPUTED):
            msg = f"Can only report breaches on ACTIVE/DISPUTED contracts: {self.status.value}"
            raise ValueError(msg)
        term = next((t for t in self.terms if t.term_id == term_id), None)
        if term is None:
            msg = f"Unknown term: {term_id}"
            raise ValueError(msg)
        if reported_by not in (self.party_a, self.party_b):
            msg = f"Only contract parties can report breaches: {reported_by}"
            raise ValueError(msg)

        if severity is None:
            sev_map = {
                "critical": BreachSeverity.CRITICAL,
                "high": BreachSeverity.MAJOR,
                "medium": BreachSeverity.MODERATE,
                "low": BreachSeverity.MINOR,
            }
            severity = sev_map.get(term.severity, BreachSeverity.MODERATE)

        breach = BreachRecord(
            breach_id=uuid.uuid4().hex[:12],
            contract_id=self.contract_id,
            term_id=term_id,
            reported_by=reported_by,
            evidence=evidence,
            severity=severity,
            timestamp=datetime.now(timezone.utc),
        )
        self.breaches.append(breach)
        self.status = ContractStatus.DISPUTED
        self._record_event(
            "breach_reported",
            breach_id=breach.breach_id,
            term_id=term_id,
            by=reported_by,
            severity=severity.value,
        )
        return breach

    def resolve_dispute(
        self,
        breach_id: str,
        resolution: str,
        resolved_by: str,
        notes: str = "",
    ) -> None:
        """Resolve a breach dispute."""
        breach = next((b for b in self.breaches if b.breach_id == breach_id), None)
        if breach is None:
            msg = f"Unknown breach: {breach_id}"
            raise ValueError(msg)
        if breach.resolved:
            msg = f"Breach {breach_id} already resolved"
            raise ValueError(msg)

        resolution_enum = DisputeResolution(resolution)
        breach.resolved = True
        breach.resolution = resolution_enum
        breach.resolved_by = resolved_by
        breach.resolved_at = datetime.now(timezone.utc)
        breach.resolution_notes = notes

        self._record_event(
            "dispute_resolved",
            breach_id=breach_id,
            resolution=resolution,
            by=resolved_by,
        )

        if resolution_enum == DisputeResolution.CONTRACT_SUSPENDED:
            self.status = ContractStatus.SUSPENDED
        elif resolution_enum == DisputeResolution.CONTRACT_TERMINATED:
            self.status = ContractStatus.TERMINATED
        else:
            unresolved = [b for b in self.breaches if not b.resolved]
            if not unresolved:
                self.status = ContractStatus.ACTIVE

    def terminate(self, terminated_by: str, reason: str = "") -> None:
        """Terminate the contract."""
        if self.status in (ContractStatus.TERMINATED, ContractStatus.EXPIRED):
            msg = f"Contract already {self.status.value}"
            raise ValueError(msg)
        self.status = ContractStatus.TERMINATED
        self._record_event("terminated", by=terminated_by, reason=reason)

    def suspend(self, suspended_by: str, reason: str = "") -> None:
        """Suspend the contract pending review."""
        if self.status != ContractStatus.ACTIVE:
            msg = f"Can only suspend ACTIVE contracts: {self.status.value}"
            raise ValueError(msg)
        self.status = ContractStatus.SUSPENDED
        self._record_event("suspended", by=suspended_by, reason=reason)

    def reinstate(self, reinstated_by: str) -> None:
        """Reinstate a suspended contract."""
        if self.status != ContractStatus.SUSPENDED:
            msg = f"Can only reinstate SUSPENDED contracts: {self.status.value}"
            raise ValueError(msg)
        self.status = ContractStatus.ACTIVE
        self._record_event("reinstated", by=reinstated_by)

    def compliance_score(self) -> float:
        """Calculate contract compliance as a ratio of unbreached terms."""
        if not self.terms:
            return 1.0
        breached_terms = {b.term_id for b in self.breaches if not b.resolved}
        compliant = sum(1 for t in self.terms if t.term_id not in breached_terms)
        return compliant / len(self.terms)

    def integrity_hash(self) -> str:
        """Compute a SHA-256 hash of the contract for tamper detection."""
        content = f"{self.contract_id}|{self.party_a}|{self.party_b}|{len(self.terms)}|" + "|".join(
            f"{t.term_id}:{t.description}:{t.severity}" for t in self.terms
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def history(self) -> list[dict[str, Any]]:
        """Return the full event history of this contract."""
        return list(self._history)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "party_a": self.party_a,
            "party_b": self.party_b,
            "status": self.status.value,
            "terms": [t.to_dict() for t in self.terms],
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "breaches": [b.to_dict() for b in self.breaches],
            "compliance_score": self.compliance_score(),
            "integrity_hash": self.integrity_hash(),
            "metadata": self.metadata,
        }


class ContractRegistry:
    """Registry for managing governance contracts between agents.

    Provides contract lifecycle management, querying, and compliance reporting.
    """

    __slots__ = ("_contracts", "_by_party")

    def __init__(self) -> None:
        self._contracts: dict[str, GovernanceContract] = {}
        self._by_party: dict[str, list[str]] = {}

    def create_contract(
        self,
        party_a: str,
        party_b: str,
        terms: list[ContractTerm],
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GovernanceContract:
        """Create a new governance contract in DRAFT status."""
        if party_a == party_b:
            msg = "Contract parties must be different agents"
            raise ValueError(msg)
        contract_id = uuid.uuid4().hex[:12]
        contract = GovernanceContract(
            contract_id=contract_id,
            party_a=party_a,
            party_b=party_b,
            terms=terms,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            metadata=metadata or {},
        )
        contract._record_event("created", party_a=party_a, party_b=party_b)
        self._contracts[contract_id] = contract
        self._by_party.setdefault(party_a, []).append(contract_id)
        self._by_party.setdefault(party_b, []).append(contract_id)
        return contract

    def get_contract(self, contract_id: str) -> GovernanceContract | None:
        return self._contracts.get(contract_id)

    def contracts_for_agent(
        self,
        agent_id: str,
        status: ContractStatus | None = None,
    ) -> list[GovernanceContract]:
        """Get all contracts involving an agent, optionally filtered by status."""
        ids = self._by_party.get(agent_id, [])
        contracts = [self._contracts[cid] for cid in ids if cid in self._contracts]
        if status is not None:
            contracts = [c for c in contracts if c.status == status]
        return contracts

    def active_contracts_between(self, agent_a: str, agent_b: str) -> list[GovernanceContract]:
        """Find active contracts between two specific agents."""
        a_ids = set(self._by_party.get(agent_a, []))
        b_ids = set(self._by_party.get(agent_b, []))
        shared = a_ids & b_ids
        return [
            self._contracts[cid]
            for cid in shared
            if cid in self._contracts and self._contracts[cid].is_active()
        ]

    def check_all_expiry(self) -> list[str]:
        """Check all contracts for expiry. Returns list of newly expired contract IDs."""
        expired: list[str] = []
        for cid, contract in self._contracts.items():
            if contract.check_expiry():
                expired.append(cid)
        return expired

    def compliance_report(self) -> dict[str, Any]:
        """Generate a compliance report across all contracts."""
        active = [c for c in self._contracts.values() if c.status == ContractStatus.ACTIVE]
        disputed = [c for c in self._contracts.values() if c.status == ContractStatus.DISPUTED]
        total_breaches = sum(len(c.breaches) for c in self._contracts.values())
        unresolved = sum(
            sum(1 for b in c.breaches if not b.resolved) for c in self._contracts.values()
        )
        avg_compliance = sum(c.compliance_score() for c in active) / len(active) if active else 1.0
        return {
            "total_contracts": len(self._contracts),
            "active": len(active),
            "disputed": len(disputed),
            "total_breaches": total_breaches,
            "unresolved_breaches": unresolved,
            "avg_compliance_score": round(avg_compliance, 4),
        }

    def __len__(self) -> int:
        return len(self._contracts)
