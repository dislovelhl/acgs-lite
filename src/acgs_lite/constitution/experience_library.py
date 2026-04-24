"""exp231: Governance experience library — learn from past constitutional decisions.

Inspired by XSkill's ExperienceManager pattern, this module accumulates
governance *precedents* from validation outcomes.  Each precedent captures
what action was evaluated, which rules fired, and the resulting decision —
building institutional memory that can inform future governance analysis.

Unlike the hot-path engine (which matches rules in <1µs), this is an
off-path learning system designed for:

- **Precedent retrieval**: "How did we handle similar actions before?"
- **Consistency analysis**: "Are we deciding differently on similar cases?"
- **Audit enrichment**: "What historical context supports this decision?"
- **Rule gap detection**: "Which actions consistently trigger no rules?"

Design (adapted from XSkill's experience accumulation):

- Append-only log of governance decisions (JSON)
- Hash-based deduplication of near-identical precedents
- Embedding-based similarity search for precedent retrieval
- Periodic consolidation to merge redundant entries
- Thread-safe via immutable dataclasses + lock on mutation

Usage::

    from acgs_lite.constitution.experience_library import (
        GovernanceExperienceLibrary,
        GovernancePrecedent,
    )

    lib = GovernanceExperienceLibrary()

    # Record a governance decision
    lib.record(
        action="access patient medical records",
        decision="deny",
        triggered_rules=["PRIV-001", "PRIV-003"],
        context={"env": "production", "role": "intern"},
        rationale="PII access restricted to authorized medical staff",
    )

    # Find similar precedents
    similar = lib.find_similar("view patient lab results", top_k=3)
    for p in similar:
        print(f"  {p.action} → {p.decision} (rules: {p.triggered_rules})")

    # Persistence
    lib.save("governance_precedents.json")
    lib2 = GovernanceExperienceLibrary.load("governance_precedents.json")
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

# ── Data structures ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GovernancePrecedent:
    """A single recorded governance decision outcome.

    Immutable after creation — precedents form an append-only audit trail.

    Attributes:
        id: Unique precedent identifier (P0, P1, ...).
        action: The action text that was evaluated.
        decision: Outcome — "allow", "deny", "warn", or "escalate".
        triggered_rules: list of rule IDs that fired.
        context: Runtime context at decision time.
        rationale: Human-readable explanation of the decision.
        timestamp: When the decision was recorded (ISO-8601).
        category: Primary governance category of the action.
        severity: Highest severity of triggered rules (or "none").
        embedding: Optional embedding vector for semantic search.
    """

    id: str
    action: str
    decision: str
    triggered_rules: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    timestamp: str = ""
    category: str = "general"
    severity: str = "none"
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "action": self.action,
            "decision": self.decision,
            "triggered_rules": list(self.triggered_rules),
            "context": dict(self.context),
            "rationale": self.rationale,
            "timestamp": self.timestamp,
            "category": self.category,
            "severity": self.severity,
            # Embeddings excluded from serialization (regenerated on load)
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernancePrecedent:
        """Deserialize from dict."""
        return cls(
            id=data.get("id", "P0"),
            action=data.get("action", ""),
            decision=data.get("decision", "unknown"),
            triggered_rules=list(data.get("triggered_rules", [])),
            context=dict(data.get("context", {})),
            rationale=data.get("rationale", ""),
            timestamp=data.get("timestamp", ""),
            category=data.get("category", "general"),
            severity=data.get("severity", "none"),
        )


def _action_fingerprint(action: str, context: dict[str, Any]) -> str:
    """Stable fingerprint for deduplication of near-identical evaluations."""
    payload = json.dumps(
        {"a": action.lower().strip(), "c": context},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Core library ────────────────────────────────────────────────────────────


class GovernanceExperienceLibrary:
    """Thread-safe governance precedent library with similarity search.

    Accumulates governance decisions as immutable precedents.  Supports
    deduplication, keyword-based search, and embedding-based similarity
    (when embeddings are provided).

    Args:
        maxsize: Maximum number of precedents to retain (oldest evicted on overflow).
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        self._maxsize = maxsize
        self._precedents: OrderedDict[str, GovernancePrecedent] = OrderedDict()
        self._fingerprints: dict[str, str] = {}  # fingerprint → precedent_id
        self._next_id = 0
        self._lock = Lock()

    def __len__(self) -> int:
        return len(self._precedents)

    @property
    def precedents(self) -> list[GovernancePrecedent]:
        """Snapshot of all precedents (newest first)."""
        with self._lock:
            return list(reversed(self._precedents.values()))

    def record(
        self,
        action: str,
        decision: str,
        *,
        triggered_rules: list[str] | None = None,
        context: dict[str, Any] | None = None,
        rationale: str = "",
        category: str = "general",
        severity: str = "none",
        embedding: list[float] | None = None,
    ) -> GovernancePrecedent | None:
        """Record a governance decision as a precedent.

        Deduplicates based on (action, context) fingerprint — identical
        evaluations are not recorded twice.

        Args:
            action: The action text that was evaluated.
            decision: Outcome — "allow", "deny", "warn", or "escalate".
            triggered_rules: Rule IDs that fired.
            context: Runtime context dict.
            rationale: Explanation of the decision.
            category: Governance category.
            severity: Highest triggered rule severity.
            embedding: Optional pre-computed embedding vector.

        Returns:
            The new GovernancePrecedent, or None if deduplicated away.
        """
        ctx = context or {}
        fp = _action_fingerprint(action, ctx)

        with self._lock:
            # Deduplicate
            if fp in self._fingerprints:
                return None

            # Assign ID and create precedent
            pid = f"P{self._next_id}"
            self._next_id += 1

            precedent = GovernancePrecedent(
                id=pid,
                action=action,
                decision=decision,
                triggered_rules=list(triggered_rules or []),
                context=ctx,
                rationale=rationale,
                timestamp=datetime.now(timezone.utc).isoformat(),
                category=category,
                severity=severity,
                embedding=list(embedding or []),
            )

            self._precedents[pid] = precedent
            self._fingerprints[fp] = pid

            # Evict oldest if over capacity
            while len(self._precedents) > self._maxsize:
                evicted_id, _evicted = self._precedents.popitem(last=False)
                # Remove fingerprint for evicted entry
                self._fingerprints = {
                    k: v for k, v in self._fingerprints.items() if v != evicted_id
                }

            return precedent

    def find_by_keyword(
        self,
        query: str,
        *,
        top_k: int = 10,
        decision_filter: str = "",
    ) -> list[GovernancePrecedent]:
        """Find precedents matching a keyword query.

        Simple keyword search — for semantic search, use ``find_similar()``.

        Args:
            query: Search terms (space-separated, case-insensitive).
            top_k: Maximum results.
            decision_filter: If set, only return precedents with this decision.

        Returns:
            list of matching precedents, most recent first.
        """
        terms = query.lower().split()
        if not terms:
            return []

        results: list[GovernancePrecedent] = []
        with self._lock:
            for p in reversed(self._precedents.values()):
                if decision_filter and p.decision != decision_filter:
                    continue
                action_lower = p.action.lower()
                if all(t in action_lower for t in terms):
                    results.append(p)
                    if len(results) >= top_k:
                        break

        return results

    def find_similar(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_similarity: float = 0.3,
        decision_filter: str = "",
    ) -> list[tuple[GovernancePrecedent, float]]:
        """Find precedents semantically similar to a query embedding.

        Requires precedents to have embeddings (set via ``record(embedding=...)``).

        Args:
            query_embedding: Embedding vector of the query.
            top_k: Maximum results.
            min_similarity: Minimum cosine similarity threshold.
            decision_filter: If set, only return precedents with this decision.

        Returns:
            list of (precedent, similarity_score) tuples, highest first.
        """
        if not query_embedding:
            return []

        scored: list[tuple[GovernancePrecedent, float]] = []

        with self._lock:
            for p in self._precedents.values():
                if not p.embedding:
                    continue
                if decision_filter and p.decision != decision_filter:
                    continue
                sim = _cosine_sim(query_embedding, p.embedding)
                if sim >= min_similarity:
                    scored.append((p, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def consistency_check(
        self,
        *,
        similarity_threshold: float = 0.85,
    ) -> list[dict[str, Any]]:
        """Detect inconsistent decisions on semantically similar actions.

        Finds pairs of precedents where the actions are highly similar
        (by embedding) but the decisions differ — potential governance
        inconsistencies.

        Args:
            similarity_threshold: Cosine similarity above which actions
                are considered "similar enough" to expect consistent decisions.

        Returns:
            list of inconsistency reports, each containing the two
            precedent IDs, their actions, decisions, and similarity score.
        """
        embedded = [(p, p.embedding) for p in self._precedents.values() if p.embedding]
        inconsistencies: list[dict[str, Any]] = []

        for i, (p1, e1) in enumerate(embedded):
            for p2, e2 in embedded[i + 1 :]:
                if p1.decision == p2.decision:
                    continue
                sim = _cosine_sim(e1, e2)
                if sim >= similarity_threshold:
                    inconsistencies.append(
                        {
                            "precedent_a": p1.id,
                            "action_a": p1.action,
                            "decision_a": p1.decision,
                            "precedent_b": p2.id,
                            "action_b": p2.action,
                            "decision_b": p2.decision,
                            "similarity": round(sim, 4),
                        }
                    )

        return inconsistencies

    def stats(self) -> dict[str, Any]:
        """Library statistics for governance dashboards."""
        with self._lock:
            total = len(self._precedents)
            by_decision: dict[str, int] = {}
            by_category: dict[str, int] = {}
            embedded_count = 0

            for p in self._precedents.values():
                by_decision[p.decision] = by_decision.get(p.decision, 0) + 1
                by_category[p.category] = by_category.get(p.category, 0) + 1
                if p.embedding:
                    embedded_count += 1

            return {
                "total_precedents": total,
                "maxsize": self._maxsize,
                "by_decision": by_decision,
                "by_category": by_category,
                "embedded_count": embedded_count,
                "embedding_coverage": embedded_count / total if total else 0.0,
            }

    # ── Persistence ─────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save library to JSON file.

        Args:
            path: File path for output.
        """
        with self._lock:
            data = {
                "version": 1,
                "next_id": self._next_id,
                "precedents": [p.to_dict() for p in self._precedents.values()],
            }
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path, *, maxsize: int = 10_000) -> GovernanceExperienceLibrary:
        """Load library from JSON file.

        Args:
            path: File path to load from.
            maxsize: Maximum library size.

        Returns:
            Populated GovernanceExperienceLibrary.
        """
        content = Path(path).read_text(encoding="utf-8")
        data = json.loads(content)

        lib = cls(maxsize=maxsize)
        lib._next_id = data.get("next_id", 0)

        for pdata in data.get("precedents", []):
            p = GovernancePrecedent.from_dict(pdata)
            lib._precedents[p.id] = p
            fp = _action_fingerprint(p.action, p.context)
            lib._fingerprints[fp] = p.id

        return lib


# ── Helpers ─────────────────────────────────────────────────────────────────


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return float(dot / (mag_a * mag_b))
