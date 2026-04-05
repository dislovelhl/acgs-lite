"""Precedent Store — constitutional case law with 7-vector retrieval.

Phase 3.1 of the subnet implementation roadmap.

Stores validated miner judgments as constitutional precedent and provides
k-nearest-neighbour retrieval by 7-vector governance score similarity.
When a new ambiguous case arrives, the store retrieves the k most similar
precedents. If the top match exceeds an auto-resolve confidence threshold,
the system returns an auto-resolution — no miner needed.

Zero-retraining architecture (as specified in §5 of the Q&A doc):
  • Embeddings (the 7-vector governance scores) are never retrained
  • Only the precedent index grows as new cases are resolved
  • Every retrieval and auto-resolution is fully traceable to source cases
  • Bayesian weight updates are separate from the retrieval index

Key invariants:
  • PrecedentRecord is only stored after validator acceptance (quorum met)
  • A single miner's judgment never becomes precedent alone
  • Rollback: any precedent can be revoked by marking it inactive

Roadmap reference: 08-subnet-implementation-roadmap.md § Phase 3
Q&A reference:    07-subnet-concept-qa-responses.md § 5
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from typing import Any

from constitutional_swarm.bittensor.protocol import EscalationType

# ---------------------------------------------------------------------------
# Vector utilities
# ---------------------------------------------------------------------------

_GOVERNANCE_DIMENSIONS = (
    "safety",
    "security",
    "privacy",
    "fairness",
    "reliability",
    "transparency",
    "efficiency",
)


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two 7-vector governance score dicts.

    Missing dimensions default to 0.0.
    Returns value in [0.0, 1.0] (inputs are non-negative governance scores).
    """
    dims = _GOVERNANCE_DIMENSIONS
    dot = sum(a.get(d, 0.0) * b.get(d, 0.0) for d in dims)
    norm_a = math.sqrt(sum(a.get(d, 0.0) ** 2 for d in dims))
    norm_b = math.sqrt(sum(b.get(d, 0.0) ** 2 for d in dims))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _euclidean_distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Euclidean distance between two 7-vector dicts."""
    dims = _GOVERNANCE_DIMENSIONS
    return math.sqrt(sum((a.get(d, 0.0) - b.get(d, 0.0)) ** 2 for d in dims))


# ---------------------------------------------------------------------------
# Precedent record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrecedentRecord:
    """A single validated miner judgment recorded as constitutional precedent.

    Immutable. All three party perspectives are stored:
      miner   — judgment + written rationale
      validator — acceptance + votes + proof
      sn_owner  — escalation type + impact vector (scoring weights at time)

    The impact_vector stores the 7 governance dimension scores that caused
    the escalation — this is the "embedding" used for retrieval.
    """

    precedent_id: str
    case_id: str
    task_id: str
    miner_uid: str

    # Miner perspective
    judgment: str
    reasoning: str

    # Validator perspective
    validation_accepted: bool
    votes_for: int
    votes_against: int
    proof_root_hash: str
    validator_grade: float          # 0.0-1.0; votes_for / total_votes

    # SN Owner perspective
    escalation_type: EscalationType
    impact_vector: dict[str, float]  # 7-dim governance scores at escalation time
    ambiguous_dimensions: tuple[str, ...]  # which vectors triggered escalation
    constitutional_hash: str

    # Metadata
    recorded_at: float
    is_active: bool = True          # False = revoked/rolled back

    @classmethod
    def create(
        cls,
        case_id: str,
        task_id: str,
        miner_uid: str,
        judgment: str,
        reasoning: str,
        votes_for: int,
        votes_against: int,
        proof_root_hash: str,
        escalation_type: EscalationType,
        impact_vector: dict[str, float],
        constitutional_hash: str,
        ambiguous_dimensions: tuple[str, ...] = (),
    ) -> PrecedentRecord:
        total_votes = votes_for + votes_against
        grade = votes_for / total_votes if total_votes > 0 else 0.0
        return cls(
            precedent_id=uuid.uuid4().hex[:12],
            case_id=case_id,
            task_id=task_id,
            miner_uid=miner_uid,
            judgment=judgment,
            reasoning=reasoning,
            validation_accepted=True,  # only accepted judgments become precedent
            votes_for=votes_for,
            votes_against=votes_against,
            proof_root_hash=proof_root_hash,
            validator_grade=grade,
            escalation_type=escalation_type,
            impact_vector=impact_vector,
            ambiguous_dimensions=ambiguous_dimensions,
            constitutional_hash=constitutional_hash,
            recorded_at=time.time(),
        )


# ---------------------------------------------------------------------------
# Retrieval result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrecedentMatch:
    """A single precedent retrieved by similarity search."""

    precedent: PrecedentRecord
    similarity: float       # cosine similarity to the query vector
    rank: int               # 1 = best match

    @property
    def is_high_confidence(self) -> bool:
        return self.similarity >= 0.85


@dataclass
class RetrievalResult:
    """Result of a precedent retrieval operation.

    If auto_resolution is set, the store recommends resolving the case
    without human deliberation (similarity exceeded the threshold).
    """

    query_vector: dict[str, float]
    matches: list[PrecedentMatch]
    auto_resolution: str | None = None    # judgment text if auto-resolving
    auto_resolution_confidence: float = 0.0
    auto_resolution_source: str = ""      # precedent_id of the source

    @property
    def can_auto_resolve(self) -> bool:
        return self.auto_resolution is not None

    @property
    def top_match(self) -> PrecedentMatch | None:
        return self.matches[0] if self.matches else None


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


class PrecedentRevokedError(RuntimeError):
    """Raised when trying to use a revoked precedent."""


# ---------------------------------------------------------------------------
# Precedent Store
# ---------------------------------------------------------------------------


class PrecedentStore:
    """Constitutional case law database with 7-vector similarity retrieval.

    Stores validated miner judgments and supports k-NN retrieval by
    7-vector governance score similarity. When a new ambiguous case
    arrives, call retrieve() to find similar past cases and optionally
    get an auto-resolution if confidence is high enough.

    Usage::

        store = PrecedentStore(
            constitutional_hash="608508a9bd224290",
            auto_resolve_threshold=0.85,
        )

        # Record a validated judgment
        record = PrecedentRecord.create(
            case_id="...", task_id="...", miner_uid="miner-01",
            judgment="Privacy takes precedence",
            reasoning="ECHR Article 8 applies",
            votes_for=2, votes_against=0,
            proof_root_hash="abc123",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_vector={"privacy": 0.9, "transparency": 0.6, ...},
            constitutional_hash="608508a9bd224290",
        )
        store.add(record)

        # Retrieve similar precedents for a new case
        result = store.retrieve(
            impact_vector={"privacy": 0.88, "transparency": 0.62, ...},
            k=5,
        )
        if result.can_auto_resolve:
            # No miner needed for this case
            judgment = result.auto_resolution

        # Revoke a bad precedent (Governor action)
        store.revoke("precedent_id_here", reason="Contradicts new rule HEALTH-SEC-047")
    """

    def __init__(
        self,
        constitutional_hash: str,
        auto_resolve_threshold: float = 0.85,
        min_votes_for_precedent: int = 2,
    ) -> None:
        self._constitutional_hash = constitutional_hash
        self._auto_resolve_threshold = auto_resolve_threshold
        self._min_votes = min_votes_for_precedent
        self._records: dict[str, PrecedentRecord] = {}
        self._revocation_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @property
    def constitutional_hash(self) -> str:
        return self._constitutional_hash

    @property
    def size(self) -> int:
        """Number of active precedents."""
        return sum(1 for r in self._records.values() if r.is_active)

    @property
    def total_stored(self) -> int:
        """Total records including revoked."""
        return len(self._records)

    def add(self, record: PrecedentRecord) -> None:
        """Add a validated precedent record.

        Validates:
          • Constitutional hash match
          • Minimum validator votes
          • Not already present (idempotent add raises ValueError)
        """
        if record.constitutional_hash != self._constitutional_hash:
            raise ValueError(
                f"Constitutional hash mismatch: "
                f"expected={self._constitutional_hash} "
                f"got={record.constitutional_hash}"
            )
        if not record.validation_accepted:
            raise ValueError(
                f"Precedent {record.precedent_id} was not accepted by validators. "
                "Only accepted judgments may be stored."
            )
        if record.votes_for < self._min_votes:
            raise ValueError(
                f"Insufficient validator votes: "
                f"got={record.votes_for} required={self._min_votes}"
            )
        if record.precedent_id in self._records:
            raise ValueError(
                f"Precedent {record.precedent_id} already stored."
            )
        self._records[record.precedent_id] = record

    def retrieve(
        self,
        impact_vector: dict[str, float],
        k: int = 5,
        escalation_type: EscalationType | None = None,
        min_similarity: float = 0.0,
    ) -> RetrievalResult:
        """Retrieve k most similar precedents to the query vector.

        Filters:
          • Only active (non-revoked) records
          • Optionally filter by escalation_type
          • Only records with similarity >= min_similarity

        Auto-resolution: if the top match exceeds auto_resolve_threshold,
        the result includes an auto_resolution suggestion.

        Args:
            impact_vector: 7-dimensional governance score dict for the query
            k: maximum number of results to return
            escalation_type: optional filter by escalation category
            min_similarity: minimum cosine similarity to include

        Returns:
            RetrievalResult with ranked matches and optional auto-resolution
        """
        candidates = [
            r for r in self._records.values()
            if r.is_active
            and (escalation_type is None or r.escalation_type == escalation_type)
        ]

        # Score all candidates
        scored = [
            (r, _cosine_similarity(impact_vector, r.impact_vector))
            for r in candidates
        ]

        # Filter and sort
        filtered = [
            (r, sim) for r, sim in scored if sim >= min_similarity
        ]
        filtered.sort(key=lambda x: x[1], reverse=True)

        # Build matches
        matches = [
            PrecedentMatch(precedent=r, similarity=sim, rank=i + 1)
            for i, (r, sim) in enumerate(filtered[:k])
        ]

        # Check for auto-resolution
        auto_resolution = None
        auto_confidence = 0.0
        auto_source = ""
        if matches and matches[0].similarity >= self._auto_resolve_threshold:
            best = matches[0].precedent
            auto_resolution = best.judgment
            auto_confidence = matches[0].similarity
            auto_source = best.precedent_id

        return RetrievalResult(
            query_vector=impact_vector,
            matches=matches,
            auto_resolution=auto_resolution,
            auto_resolution_confidence=auto_confidence,
            auto_resolution_source=auto_source,
        )

    def revoke(self, precedent_id: str, reason: str = "") -> None:
        """Revoke a precedent (Governor action).

        The record is kept in the store (for audit purposes) but
        marked inactive so it will not be returned in future retrievals.
        Revoked precedents are tracked in the revocation log.

        Raises KeyError if the precedent_id is not found.
        """
        if precedent_id not in self._records:
            raise KeyError(f"Precedent {precedent_id!r} not found.")

        record = self._records[precedent_id]
        # Replace with an inactive copy (PrecedentRecord is frozen)
        import dataclasses
        inactive = dataclasses.replace(record, is_active=False)
        self._records[precedent_id] = inactive

        self._revocation_log.append({
            "precedent_id": precedent_id,
            "revoked_at": time.time(),
            "reason": reason,
        })

    # ------------------------------------------------------------------
    # Statistics and reporting
    # ------------------------------------------------------------------

    def escalation_distribution(self) -> dict[str, int]:
        """Count active precedents by escalation type."""
        counts: dict[str, int] = {}
        for r in self._records.values():
            if r.is_active:
                key = r.escalation_type.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def miner_contribution_counts(self) -> dict[str, int]:
        """Count active precedents contributed by each miner."""
        counts: dict[str, int] = {}
        for r in self._records.values():
            if r.is_active:
                counts[r.miner_uid] = counts.get(r.miner_uid, 0) + 1
        return counts

    def escalation_rate_projection(
        self,
        baseline_rate: float = 0.03,
        decay_per_1k: float = 0.005,
    ) -> float:
        """Estimate current escalation rate given precedent accumulation.

        As precedents accumulate, the auto-resolution rate increases
        and effective escalation rate decreases.

        baseline_rate: starting escalation rate (default 3%)
        decay_per_1k:  reduction per 1,000 active precedents (default 0.5%)
        """
        active = self.size
        thousands = active / 1000.0
        projected = baseline_rate - (thousands * decay_per_1k)
        return max(0.005, projected)  # floor at 0.5% — some cases always novel

    def summary(self) -> dict[str, Any]:
        active = self.size
        total = self.total_stored
        return {
            "constitutional_hash": self._constitutional_hash,
            "active_precedents": active,
            "total_stored": total,
            "revoked": total - active,
            "auto_resolve_threshold": self._auto_resolve_threshold,
            "min_votes_required": self._min_votes,
            "escalation_distribution": self.escalation_distribution(),
            "revocation_log_entries": len(self._revocation_log),
            "projected_escalation_rate": self.escalation_rate_projection(),
        }
