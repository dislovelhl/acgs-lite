"""Rule Codifier — Phase 3.3.

Scans the PrecedentStore for clusters of similar precedents that have
reached consensus, then proposes them as new constitutional rules.
No rule is activated without explicit Governor approval.

Pipeline:
  1. Cluster precedents by 7-vector cosine similarity
  2. Filter clusters by size and validator agreement
  3. Generate YAML rule text from cluster centroid + majority judgment
  4. Require Governor approval (pending state)
  5. Activate: append rule to constitution → new constitutional hash

This is rule writing, not model training. Every generated rule is:
  • Explicit — plain-language text, fully auditable
  • Versioned — produces a new constitutional hash on activation
  • Governed — SN Owner must call approve() before activation
  • Reversible — revoke() marks the rule inactive

Example output YAML (matching Q&A doc §5 Mechanism 3):
  - id: HEALTH-SEC-047
    text: "Healthcare data access requests with both security and fairness
           vectors above 0.60 require explicit consent verification"
    severity: high
    source: precedent_codification
    precedent_cluster: ESC-HEALTH-SEC
    case_count: 53
    validator_agreement: 0.94

Roadmap: 08-subnet-implementation-roadmap.md § Phase 3.3
Q&A:     07-subnet-concept-qa-responses.md § 5 Mechanism 3
"""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from constitutional_swarm.bittensor.precedent_store import PrecedentRecord

_DIMENSIONS = (
    "safety", "security", "privacy",
    "fairness", "reliability", "transparency", "efficiency",
)


# ---------------------------------------------------------------------------
# Rule candidate state
# ---------------------------------------------------------------------------


class RuleCandidateStatus(Enum):
    PENDING   = "pending"     # awaiting Governor approval
    APPROVED  = "approved"    # Governor approved, not yet activated
    ACTIVE    = "active"      # activated, has a new constitutional hash
    REJECTED  = "rejected"    # Governor rejected
    REVOKED   = "revoked"     # was active, Governor revoked


# ---------------------------------------------------------------------------
# Cluster (input to codification)
# ---------------------------------------------------------------------------


@dataclass
class PrecedentCluster:
    """A group of similar precedents that might be codified into a rule."""

    cluster_id: str
    precedent_ids: list[str]
    centroid_vector: dict[str, float]        # mean of all impact vectors
    dominant_dimensions: list[str]           # dims with centroid score > 0.5
    majority_judgment: str                   # most common judgment text
    validator_agreement: float               # mean validator_grade
    escalation_type: str
    domain_hint: str = ""
    formed_at: float = field(default_factory=time.time)

    @property
    def size(self) -> int:
        return len(self.precedent_ids)

    @property
    def is_stable(self) -> bool:
        """True when agreement is high enough to propose a rule."""
        return self.validator_agreement >= 0.70

    def summary(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "size": self.size,
            "validator_agreement": round(self.validator_agreement, 3),
            "dominant_dimensions": self.dominant_dimensions,
            "escalation_type": self.escalation_type,
            "majority_judgment": self.majority_judgment[:80] + "...",
        }


# ---------------------------------------------------------------------------
# Rule candidate (output of codification, pending approval)
# ---------------------------------------------------------------------------


@dataclass
class RuleCandidate:
    """A proposed constitutional rule awaiting Governor approval."""

    candidate_id: str
    cluster_id: str
    rule_id: str               # e.g. "PREC-SEC-001"
    rule_text: str
    severity: str              # critical | high | medium | low
    keywords: list[str]
    source_precedent_ids: list[str]
    validator_agreement: float
    dominant_dimensions: list[str]
    escalation_type: str
    status: RuleCandidateStatus
    proposed_at: float
    approved_at: float | None = None
    activated_at: float | None = None
    constitutional_hash_before: str = ""
    constitutional_hash_after: str = ""
    rejection_reason: str = ""
    revocation_reason: str = ""

    def to_yaml_block(self) -> str:
        """Generate the YAML rule block for insertion into a constitution file."""
        keywords_str = "\n".join(f"      - {k}" for k in self.keywords)
        return (
            f"  - id: {self.rule_id}\n"
            f"    text: \"{self.rule_text}\"\n"
            f"    severity: {self.severity}\n"
            f"    hardcoded: false\n"
            f"    source: precedent_codification\n"
            f"    precedent_cluster: {self.cluster_id}\n"
            f"    case_count: {len(self.source_precedent_ids)}\n"
            f"    validator_agreement: {self.validator_agreement:.2f}\n"
            f"    keywords:\n{keywords_str}\n"
        )

    def summary(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rule_id": self.rule_id,
            "status": self.status.value,
            "severity": self.severity,
            "validator_agreement": round(self.validator_agreement, 3),
            "case_count": len(self.source_precedent_ids),
            "dominant_dimensions": self.dominant_dimensions,
        }


# ---------------------------------------------------------------------------
# Main codifier
# ---------------------------------------------------------------------------


class RuleCodifier:
    """Scans PrecedentStore for consensus clusters and proposes new rules.

    Usage::

        codifier = RuleCodifier(
            constitutional_hash="608508a9bd224290",
            min_cluster_size=5,          # lower for testing; 50 in prod
            min_validator_agreement=0.90,
            similarity_threshold=0.80,
        )

        # Find candidate clusters
        clusters = codifier.find_clusters(active_precedents)

        # Generate rule proposals from qualifying clusters
        candidates = codifier.propose_rules(clusters)

        # Governor reviews and approves
        for c in candidates:
            print(c.to_yaml_block())
            codifier.approve(c.candidate_id)

        # Activate (appends to constitution YAML, produces new hash)
        new_hash = codifier.activate(c.candidate_id, constitution_yaml)
    """

    def __init__(
        self,
        constitutional_hash: str,
        min_cluster_size: int = 50,
        min_validator_agreement: float = 0.90,
        similarity_threshold: float = 0.80,
        rule_id_prefix: str = "PREC",
    ) -> None:
        self._constitutional_hash = constitutional_hash
        self._min_size = min_cluster_size
        self._min_agreement = min_validator_agreement
        self._sim_threshold = similarity_threshold
        self._rule_prefix = rule_id_prefix
        self._candidates: dict[str, RuleCandidate] = {}
        self._rule_counter: int = 0
        self._activated_rules: list[RuleCandidate] = []

    @property
    def constitutional_hash(self) -> str:
        return self._constitutional_hash

    @property
    def pending_candidates(self) -> list[RuleCandidate]:
        return [c for c in self._candidates.values()
                if c.status == RuleCandidateStatus.PENDING]

    @property
    def active_rules(self) -> list[RuleCandidate]:
        return list(self._activated_rules)

    # ------------------------------------------------------------------
    # Step 1: Cluster precedents
    # ------------------------------------------------------------------

    def find_clusters(
        self,
        precedents: list[PrecedentRecord],
        domain: str = "",
    ) -> list[PrecedentCluster]:
        """Group active precedents into similarity clusters.

        Uses greedy agglomerative clustering:
          For each unassigned precedent, if it's within similarity_threshold
          of an existing cluster centroid, add it. Otherwise start a new cluster.

        Args:
            precedents: active PrecedentRecord objects
            domain: optional hint embedded in cluster metadata

        Returns:
            list of PrecedentCluster (all sizes, pre-filtered)
        """
        active = [p for p in precedents if p.is_active]
        if not active:
            return []

        clusters: list[dict] = []

        for rec in active:
            vec = rec.impact_vector
            best_idx = -1
            best_sim = -1.0

            for i, cl in enumerate(clusters):
                sim = _cosine(vec, cl["centroid"])
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i

            if best_idx >= 0 and best_sim >= self._sim_threshold:
                clusters[best_idx]["members"].append(rec)
                # Update centroid (running mean)
                n = len(clusters[best_idx]["members"])
                for d in _DIMENSIONS:
                    clusters[best_idx]["centroid"][d] = (
                        clusters[best_idx]["centroid"][d] * (n - 1) / n
                        + vec.get(d, 0.0) / n
                    )
            else:
                clusters.append({
                    "centroid": {d: vec.get(d, 0.0) for d in _DIMENSIONS},
                    "members": [rec],
                })

        result: list[PrecedentCluster] = []
        for cl in clusters:
            members: list[PrecedentRecord] = cl["members"]
            centroid: dict[str, float] = cl["centroid"]

            dominant = [d for d in _DIMENSIONS if centroid.get(d, 0.0) >= 0.5]
            avg_grade = sum(m.validator_grade for m in members) / len(members)
            esc_types = [m.escalation_type.value for m in members]
            majority_etype = max(set(esc_types), key=esc_types.count)

            # Majority judgment: most common judgment text (first 100 chars as key)
            judgment_keys = [m.judgment[:100] for m in members]
            majority_j = max(set(judgment_keys), key=judgment_keys.count)
            # Recover full text
            for m in members:
                if m.judgment[:100] == majority_j:
                    majority_j = m.judgment
                    break

            result.append(PrecedentCluster(
                cluster_id=uuid.uuid4().hex[:8],
                precedent_ids=[m.precedent_id for m in members],
                centroid_vector=centroid,
                dominant_dimensions=dominant,
                majority_judgment=majority_j,
                validator_agreement=avg_grade,
                escalation_type=majority_etype,
                domain_hint=domain,
            ))

        return result

    # ------------------------------------------------------------------
    # Step 2: Propose rules from qualifying clusters
    # ------------------------------------------------------------------

    def propose_rules(
        self,
        clusters: list[PrecedentCluster],
    ) -> list[RuleCandidate]:
        """Generate RuleCandidate proposals from clusters that meet thresholds.

        Only clusters with size ≥ min_cluster_size AND
        validator_agreement ≥ min_validator_agreement are proposed.

        Returns:
            list of RuleCandidate in PENDING state
        """
        proposed: list[RuleCandidate] = []

        for cluster in clusters:
            if cluster.size < self._min_size:
                continue
            if cluster.validator_agreement < self._min_agreement:
                continue

            candidate = self._generate_candidate(cluster)
            self._candidates[candidate.candidate_id] = candidate
            proposed.append(candidate)

        return proposed

    # ------------------------------------------------------------------
    # Steps 3-5: Governor approval workflow
    # ------------------------------------------------------------------

    def approve(self, candidate_id: str) -> RuleCandidate:
        """Governor approves a pending rule candidate.

        Raises KeyError if not found, ValueError if not in PENDING state.
        """
        c = self._get_candidate(candidate_id, RuleCandidateStatus.PENDING)
        import dataclasses
        updated = dataclasses.replace(
            c,
            status=RuleCandidateStatus.APPROVED,
            approved_at=time.time(),
        )
        self._candidates[candidate_id] = updated
        return updated

    def reject(self, candidate_id: str, reason: str = "") -> RuleCandidate:
        """Governor rejects a pending rule candidate."""
        c = self._get_candidate(candidate_id, RuleCandidateStatus.PENDING)
        import dataclasses
        updated = dataclasses.replace(
            c,
            status=RuleCandidateStatus.REJECTED,
            rejection_reason=reason,
        )
        self._candidates[candidate_id] = updated
        return updated

    def activate(
        self,
        candidate_id: str,
        constitution_yaml: str,
    ) -> tuple[RuleCandidate, str]:
        """Activate an approved rule: append it to constitution YAML.

        Returns (updated_candidate, new_constitution_yaml).
        The new YAML contains the rule appended to the rules list.
        A new constitutional hash is computed from the new YAML.

        Raises ValueError if candidate is not in APPROVED state.
        """
        c = self._get_candidate(candidate_id, RuleCandidateStatus.APPROVED)
        new_yaml = _append_rule_to_yaml(constitution_yaml, c.to_yaml_block())
        new_hash = hashlib.sha256(new_yaml.encode()).hexdigest()[:16]

        import dataclasses
        activated = dataclasses.replace(
            c,
            status=RuleCandidateStatus.ACTIVE,
            activated_at=time.time(),
            constitutional_hash_before=self._constitutional_hash,
            constitutional_hash_after=new_hash,
        )
        self._candidates[candidate_id] = activated
        self._activated_rules.append(activated)
        self._constitutional_hash = new_hash
        return activated, new_yaml

    def revoke(
        self,
        candidate_id: str,
        reason: str = "",
    ) -> RuleCandidate:
        """Governor revokes an active rule (marks it inactive, no hash change).

        The constitutional hash does NOT change on revocation — a new
        constitution YAML must be provided and re-activated to remove the rule.
        """
        c = self._get_candidate(candidate_id, RuleCandidateStatus.ACTIVE)
        import dataclasses
        revoked = dataclasses.replace(
            c,
            status=RuleCandidateStatus.REVOKED,
            revocation_reason=reason,
        )
        self._candidates[candidate_id] = revoked
        self._activated_rules = [
            r for r in self._activated_rules if r.candidate_id != candidate_id
        ]
        return revoked

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def all_candidates(self) -> list[RuleCandidate]:
        return list(self._candidates.values())

    def summary(self) -> dict[str, Any]:
        counts = {s.value: 0 for s in RuleCandidateStatus}
        for c in self._candidates.values():
            counts[c.status.value] += 1
        return {
            "constitutional_hash": self._constitutional_hash,
            "total_candidates": len(self._candidates),
            "active_rules": len(self._activated_rules),
            "status_counts": counts,
            "thresholds": {
                "min_cluster_size": self._min_size,
                "min_validator_agreement": self._min_agreement,
                "similarity_threshold": self._sim_threshold,
            },
        }

    def _generate_candidate(self, cluster: PrecedentCluster) -> RuleCandidate:
        self._rule_counter += 1
        dims = "-".join(d[:3].upper() for d in cluster.dominant_dimensions[:2])
        rule_id = f"{self._rule_prefix}-{dims}-{self._rule_counter:03d}"

        severity = _infer_severity(cluster.dominant_dimensions)
        rule_text = _generate_rule_text(cluster)
        keywords = _extract_keywords(cluster)

        return RuleCandidate(
            candidate_id=uuid.uuid4().hex[:8],
            cluster_id=cluster.cluster_id,
            rule_id=rule_id,
            rule_text=rule_text,
            severity=severity,
            keywords=keywords,
            source_precedent_ids=list(cluster.precedent_ids),
            validator_agreement=cluster.validator_agreement,
            dominant_dimensions=cluster.dominant_dimensions,
            escalation_type=cluster.escalation_type,
            status=RuleCandidateStatus.PENDING,
            proposed_at=time.time(),
            constitutional_hash_before=self._constitutional_hash,
        )

    def _get_candidate(
        self,
        candidate_id: str,
        expected_status: RuleCandidateStatus,
    ) -> RuleCandidate:
        if candidate_id not in self._candidates:
            raise KeyError(f"Candidate {candidate_id!r} not found.")
        c = self._candidates[candidate_id]
        if c.status != expected_status:
            raise ValueError(
                f"Candidate {candidate_id} is {c.status.value}, "
                f"expected {expected_status.value}."
            )
        return c


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a.get(d, 0.0) * b.get(d, 0.0) for d in _DIMENSIONS)
    na = math.sqrt(sum(a.get(d, 0.0) ** 2 for d in _DIMENSIONS))
    nb = math.sqrt(sum(b.get(d, 0.0) ** 2 for d in _DIMENSIONS))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _infer_severity(dominant_dimensions: list[str]) -> str:
    if "safety" in dominant_dimensions or "security" in dominant_dimensions:
        return "high"
    if "privacy" in dominant_dimensions or "fairness" in dominant_dimensions:
        return "high"
    return "medium"


def _generate_rule_text(cluster: PrecedentCluster) -> str:
    """Generate a human-readable rule from cluster metadata."""
    dims = cluster.dominant_dimensions
    if not dims:
        return (
            f"Governance decisions of type '{cluster.escalation_type}' "
            f"with elevated impact scores require additional review."
        )
    dims_str = " and ".join(dims[:2])
    threshold = 0.5
    centroid_vals = [cluster.centroid_vector.get(d, 0.0) for d in dims[:2]]
    if centroid_vals:
        threshold = round(sum(centroid_vals) / len(centroid_vals), 1)

    return (
        f"Decisions with {dims_str} impact scores above {threshold:.1f} "
        f"({cluster.escalation_type.replace('_', ' ')}) "
        f"require explicit justification referencing the affected governance dimensions."
    )


def _extract_keywords(cluster: PrecedentCluster) -> list[str]:
    """Extract keywords from dominant dimensions and escalation type."""
    kw: list[str] = list(cluster.dominant_dimensions)
    etype = cluster.escalation_type.replace("_", " ")
    if etype not in kw:
        kw.append(etype)
    # Add dimension-specific keywords
    kw_map = {
        "safety": ["harm", "danger", "risk"],
        "security": ["access", "breach", "unauthorized"],
        "privacy": ["personal data", "PII", "consent"],
        "fairness": ["discriminat", "bias", "equit"],
        "transparency": ["explainab", "disclose", "audit"],
        "reliability": ["uptime", "integrity", "fault"],
        "efficiency": ["resource", "latency", "cost"],
    }
    for d in cluster.dominant_dimensions[:2]:
        kw.extend(kw_map.get(d, [])[:2])
    return list(dict.fromkeys(kw))  # deduplicate, preserve order


def _append_rule_to_yaml(constitution_yaml: str, rule_yaml_block: str) -> str:
    """Append a rule YAML block to the rules list in a constitution YAML string."""
    if "rules:" in constitution_yaml:
        return constitution_yaml.rstrip() + "\n" + rule_yaml_block
    return constitution_yaml.rstrip() + "\nrules:\n" + rule_yaml_block
