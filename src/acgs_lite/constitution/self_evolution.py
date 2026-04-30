"""Self-evolution system for safe, governed policy improvement.

The engine in this module does **not** mutate a constitution directly. It turns
runtime decision feedback into scored evolution candidates, then optionally
submits those candidates to :class:`AmendmentProtocol` so MACI separation,
quorum, voting, ratification, and audit trails still control every change.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .amendments import Amendment, AmendmentProtocol, AmendmentType
from .rule import Severity, ViolationAction

if TYPE_CHECKING:
    from acgs_lite.engine.decision_record import GovernanceDecisionRecord

    from .constitution import Constitution


_RE_WORD = re.compile(r"[a-z0-9][a-z0-9_\-]{2,}")
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "must",
    "should",
    "would",
    "could",
    "into",
    "action",
    "agent",
    "request",
    "user",
}


@dataclass(frozen=True, slots=True)
class SelfEvolutionConfig:
    """Tunable controls for governance self-evolution.

    Args:
        min_support: Minimum repeated evidence count before a candidate is emitted.
        min_fitness: Minimum fitness score for amendment drafting.
        low_confidence_threshold: Allowed decisions below this confidence become
            review candidates.
        max_candidates: Maximum candidates returned per evaluation pass.
        proposer_id: Identity used when drafting amendments. Validators/executors
            must be separate actors in the amendment protocol.
    """

    min_support: int = 2
    min_fitness: float = 0.55
    low_confidence_threshold: float = 0.6
    max_candidates: int = 10
    proposer_id: str = "self-evolution-agent"

    def __post_init__(self) -> None:
        if self.min_support < 1:
            raise ValueError("min_support must be >= 1")
        if not 0.0 <= self.min_fitness <= 1.0:
            raise ValueError("min_fitness must be between 0 and 1")
        if not 0.0 <= self.low_confidence_threshold <= 1.0:
            raise ValueError("low_confidence_threshold must be between 0 and 1")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")


@dataclass(frozen=True, slots=True)
class EvolutionEvidence:
    """A compact evidence item supporting an evolution candidate."""

    audit_entry_id: str = ""
    decision: str = ""
    action: str = ""
    rule_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_entry_id": self.audit_entry_id,
            "decision": self.decision,
            "action": self.action,
            "rule_ids": list(self.rule_ids),
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    """A scored constitutional change candidate."""

    candidate_id: str
    amendment_type: AmendmentType
    title: str
    description: str
    changes: dict[str, Any]
    fitness: float
    risk: str
    support: int
    evidence: tuple[EvolutionEvidence, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "amendment_type": self.amendment_type.value,
            "title": self.title,
            "description": self.description,
            "changes": self.changes,
            "fitness": round(self.fitness, 4),
            "risk": self.risk,
            "support": self.support,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class SelfEvolutionReport:
    """Result of one self-evolution evaluation pass."""

    input_records: int
    candidates: tuple[EvolutionCandidate, ...]
    skipped: dict[str, int] = field(default_factory=dict)

    @property
    def actionable_candidates(self) -> tuple[EvolutionCandidate, ...]:
        return self.candidates

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_records": self.input_records,
            "candidate_count": len(self.candidates),
            "skipped": dict(self.skipped),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class SelfEvolutionEngine:
    """Generate safe constitutional evolution proposals from runtime feedback.

    The engine currently detects three practical improvement classes:

    * uncovered denials: denied actions with violations but no active rule hit,
      producing an ``add_rule`` proposal;
    * repeated hot rules: frequently triggered rules, producing a bounded
      priority/severity tuning proposal;
    * low-confidence allows: allowed actions under the confidence threshold,
      producing a human-review rule proposal.
    """

    def __init__(self, config: SelfEvolutionConfig | None = None) -> None:
        self.config = config or SelfEvolutionConfig()

    def evaluate(
        self,
        records: Iterable[GovernanceDecisionRecord | Mapping[str, Any]],
        constitution: Constitution,
    ) -> SelfEvolutionReport:
        normalized = [_record_to_mapping(record) for record in records]
        existing_rule_ids = {rule.id for rule in constitution.rules}
        skipped: Counter[str] = Counter()
        candidates: list[EvolutionCandidate] = []

        candidates.extend(self._uncovered_denial_candidates(normalized, existing_rule_ids, skipped))
        candidates.extend(self._hot_rule_candidates(normalized, constitution, skipped))
        candidates.extend(self._low_confidence_allow_candidates(normalized, skipped))

        filtered = [candidate for candidate in candidates if candidate.fitness >= self.config.min_fitness]
        filtered.sort(key=lambda c: (c.fitness, c.support, c.candidate_id), reverse=True)
        return SelfEvolutionReport(
            input_records=len(normalized),
            candidates=tuple(filtered[: self.config.max_candidates]),
            skipped=dict(skipped),
        )

    def draft_amendments(
        self,
        report: SelfEvolutionReport,
        protocol: AmendmentProtocol,
        *,
        proposer_id: str | None = None,
        open_voting: bool = False,
    ) -> list[Amendment]:
        """Draft candidates as formal amendments.

        If ``open_voting`` is true, each draft is also moved through
        ``proposed`` to ``voting``. Ratification/enforcement are intentionally
        left to distinct executor actors.
        """

        actor = proposer_id or self.config.proposer_id
        amendments: list[Amendment] = []
        for candidate in report.actionable_candidates:
            amd = protocol.draft(
                proposer_id=actor,
                amendment_type=candidate.amendment_type.value,
                title=candidate.title,
                description=candidate.description,
                changes=candidate.changes,
                metadata={
                    "source": "self_evolution",
                    "candidate_id": candidate.candidate_id,
                    "fitness": candidate.fitness,
                    "risk": candidate.risk,
                    "support": candidate.support,
                    "evidence": [item.to_dict() for item in candidate.evidence],
                },
            )
            if open_voting:
                protocol.propose(amd.amendment_id, proposer_id=actor)
                protocol.open_voting(amd.amendment_id, proposer_id=actor)
            amendments.append(amd)
        return amendments

    def _uncovered_denial_candidates(
        self,
        records: list[Mapping[str, Any]],
        existing_rule_ids: set[str],
        skipped: Counter[str],
    ) -> list[EvolutionCandidate]:
        buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for record in records:
            decision = str(record.get("decision", "")).lower()
            if decision != "deny":
                continue
            rule_ids = _record_rule_ids(record)
            known_hits = [rid for rid in rule_ids if rid in existing_rule_ids]
            violations = record.get("violations") or []
            if known_hits or not violations:
                skipped["covered_or_without_violation_denials"] += 1
                continue
            key = _topic_key(str(record.get("action", "")), violations)
            buckets[key].append(record)

        candidates: list[EvolutionCandidate] = []
        for key, items in buckets.items():
            if len(items) < self.config.min_support:
                skipped["uncovered_denial_below_support"] += len(items)
                continue
            keywords = _keywords(key)
            rule_id = _stable_rule_id("EVO", key)
            support = len(items)
            fitness = _bounded(0.45 + min(0.4, support / 10) + 0.1 * bool(keywords))
            evidence = tuple(_evidence(item, "denied with no active rule coverage") for item in items[:5])
            candidates.append(
                EvolutionCandidate(
                    candidate_id=_stable_rule_id("CAND", f"uncovered:{key}"),
                    amendment_type=AmendmentType.add_rule,
                    title=f"Add coverage for repeated uncovered denial: {key[:60]}",
                    description=(
                        "Runtime feedback repeatedly denied actions with violation evidence, "
                        "but no active constitutional rule was triggered. Add explicit coverage "
                        "so future enforcement is deterministic and auditable."
                    ),
                    changes={
                        "rule": {
                            "id": rule_id,
                            "text": f"Agents must not perform actions matching repeated risk pattern: {key}",
                            "severity": Severity.HIGH.value,
                            "keywords": keywords,
                            "category": "self-evolution",
                            "workflow_action": ViolationAction.BLOCK.value,
                            "tags": ["self-evolution", "runtime-feedback"],
                            "metadata": {"generated_by": "SelfEvolutionEngine", "support": support},
                        }
                    },
                    fitness=fitness,
                    risk="medium",
                    support=support,
                    evidence=evidence,
                )
            )
        return candidates

    def _hot_rule_candidates(
        self,
        records: list[Mapping[str, Any]],
        constitution: Constitution,
        skipped: Counter[str],
    ) -> list[EvolutionCandidate]:
        rule_counts: Counter[str] = Counter()
        for record in records:
            if str(record.get("decision", "")).lower() == "deny":
                rule_counts.update(_record_rule_ids(record))

        by_id = {rule.id: rule for rule in constitution.rules}
        candidates: list[EvolutionCandidate] = []
        for rule_id, support in rule_counts.items():
            rule = by_id.get(rule_id)
            if rule is None or support < self.config.min_support:
                skipped["hot_rule_unknown_or_below_support"] += 1
                continue
            changes: dict[str, Any] = {"rule_id": rule_id, "priority": min(rule.priority + support, 100)}
            amendment_type = AmendmentType.modify_rule
            risk = "low"
            if rule.severity in {Severity.LOW, Severity.MEDIUM}:
                changes["severity"] = Severity.HIGH.value
                changes["workflow_action"] = ViolationAction.BLOCK.value
                risk = "medium"
            candidates.append(
                EvolutionCandidate(
                    candidate_id=_stable_rule_id("CAND", f"hot:{rule_id}:{support}"),
                    amendment_type=amendment_type,
                    title=f"Tune frequently triggered rule {rule_id}",
                    description=(
                        f"Rule {rule_id} triggered {support} denied decisions. Increase priority"
                        " and, for non-blocking severities, escalate to high so repeated risk is handled earlier."
                    ),
                    changes=changes,
                    fitness=_bounded(0.4 + min(0.5, support / 12)),
                    risk=risk,
                    support=support,
                    evidence=tuple(
                        _evidence(item, f"triggered hot rule {rule_id}")
                        for item in records
                        if rule_id in _record_rule_ids(item)
                    )[:5],
                )
            )
        return candidates

    def _low_confidence_allow_candidates(
        self, records: list[Mapping[str, Any]], skipped: Counter[str]
    ) -> list[EvolutionCandidate]:
        items = [
            record
            for record in records
            if str(record.get("decision", "")).lower() == "allow"
            and float(record.get("confidence", 1.0) or 0.0) < self.config.low_confidence_threshold
        ]
        if len(items) < self.config.min_support:
            skipped["low_confidence_allow_below_support"] += len(items)
            return []
        topic = _topic_key(" ".join(str(item.get("action", "")) for item in items), [])
        rule_id = _stable_rule_id("EVO-REVIEW", topic)
        return [
            EvolutionCandidate(
                candidate_id=_stable_rule_id("CAND", f"low-confidence:{topic}"),
                amendment_type=AmendmentType.add_rule,
                title="Require review for repeated low-confidence allow decisions",
                description=(
                    "Multiple actions were allowed with confidence below the configured threshold. "
                    "Route matching future actions to human review instead of silent allow."
                ),
                changes={
                    "rule": {
                        "id": rule_id,
                        "text": f"Actions matching low-confidence allow pattern require human review: {topic}",
                        "severity": Severity.HIGH.value,
                        "keywords": _keywords(topic),
                        "category": "self-evolution",
                        "workflow_action": ViolationAction.REQUIRE_HUMAN_REVIEW.value,
                        "tags": ["self-evolution", "low-confidence", "human-review"],
                        "metadata": {"generated_by": "SelfEvolutionEngine", "support": len(items)},
                    }
                },
                fitness=_bounded(0.5 + min(0.35, len(items) / 12)),
                risk="medium",
                support=len(items),
                evidence=tuple(_evidence(item, "allowed below confidence threshold") for item in items[:5]),
            )
        ]


def _record_to_mapping(record: GovernanceDecisionRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    to_dict = getattr(record, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    msg = f"Unsupported decision record type: {type(record)!r}"
    raise TypeError(msg)


def _record_rule_ids(record: Mapping[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for rule in record.get("triggered_rules") or []:
        if isinstance(rule, Mapping) and rule.get("id"):
            ids.append(str(rule["id"]))
        elif hasattr(rule, "id"):
            ids.append(str(rule.id))
    for violation in record.get("violations") or []:
        if isinstance(violation, Mapping):
            rid = violation.get("rule_id") or violation.get("rule") or violation.get("id")
            if rid:
                ids.append(str(rid))
    return tuple(dict.fromkeys(ids))


def _topic_key(action: str, violations: Any) -> str:
    parts = [action]
    if isinstance(violations, list):
        for violation in violations[:3]:
            if isinstance(violation, Mapping):
                parts.append(str(violation.get("message") or violation.get("reason") or ""))
            else:
                parts.append(str(violation))
    text = " ".join(parts).strip().lower()
    words = _keywords(text, max_keywords=8)
    return " ".join(words) if words else "general runtime risk"


def _keywords(text: str, *, max_keywords: int = 6) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in _RE_WORD.findall(text.lower()):
        if token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        result.append(token)
        if len(result) >= max_keywords:
            break
    return result


def _stable_rule_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _evidence(record: Mapping[str, Any], reason: str) -> EvolutionEvidence:
    return EvolutionEvidence(
        audit_entry_id=str(record.get("audit_entry_id", "")),
        decision=str(record.get("decision", "")),
        action=str(record.get("action", "")),
        rule_ids=_record_rule_ids(record),
        confidence=float(record.get("confidence", 1.0) or 0.0),
        reason=reason,
    )


__all__ = [
    "EvolutionCandidate",
    "EvolutionEvidence",
    "SelfEvolutionConfig",
    "SelfEvolutionEngine",
    "SelfEvolutionReport",
]
