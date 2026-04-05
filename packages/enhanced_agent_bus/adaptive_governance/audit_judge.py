"""LLM-as-Judge audit pipeline for governance decision quality assessment.

Samples production decisions from the audit log, sends them to an LLM judge
with constitutional rubrics, and converts disagreements into regression test
candidates for the eval harness.

MACI role: OBSERVER — read-only audit access, cannot modify rules or execute.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any

from .llm_judge import JudgmentScore, LLMGovernanceJudge, LLMJudgment
from .rubrics import build_audit_rubric


@dataclass(slots=True)
class JudgmentResult:
    """Result of judging a single governance decision."""

    entry_id: str
    action: str
    engine_decision: str
    judge_decision: str
    scores: JudgmentScore
    reasoning: str
    model_id: str
    agrees_with_engine: bool = True


@dataclass
class AuditReport:
    """Aggregated report from an audit judge session."""

    total_sampled: int
    judgments: list[JudgmentResult] = field(default_factory=list)

    @property
    def avg_accuracy(self) -> float:
        if not self.judgments:
            return 0.0
        return sum(j.scores.accuracy for j in self.judgments) / len(self.judgments)

    @property
    def avg_proportionality(self) -> float:
        if not self.judgments:
            return 0.0
        return sum(j.scores.proportionality for j in self.judgments) / len(self.judgments)

    @property
    def agreement_rate(self) -> float:
        if not self.judgments:
            return 0.0
        agreed = sum(1 for j in self.judgments if j.agrees_with_engine)
        return agreed / len(self.judgments)

    @property
    def disagreements(self) -> list[JudgmentResult]:
        return [j for j in self.judgments if not j.agrees_with_engine]

    @property
    def regression_candidates(self) -> list[dict[str, Any]]:
        """Convert disagreements into GovernanceTestCase-compatible dicts.

        Each dict can be loaded by ``GovernanceTestSuite.load_from_dicts()``.
        The judge's decision becomes the expected decision (it disagreed with
        the engine, so the judge's view is the "correct" answer for regression).
        """
        candidates = []
        for j in self.disagreements:
            case_name = f"audit-regression-{j.entry_id[:8]}"
            candidates.append(
                {
                    "name": case_name,
                    "input_text": j.action,
                    "expected_decision": j.judge_decision,
                    "expected_rules_triggered": j.scores.missed_violations,
                    "tags": ["audit-regression", "auto-generated"],
                }
            )
        return candidates

    def summary(self) -> str:
        return (
            f"Audit: {self.total_sampled} sampled, "
            f"{len(self.judgments)} judged, "
            f"accuracy={self.avg_accuracy:.2f}, "
            f"agreement={self.agreement_rate:.0%}, "
            f"{len(self.disagreements)} disagreements"
        )


class GovernanceAuditJudge:
    """Samples audit entries and evaluates them with an LLM judge.

    Parameters
    ----------
    constitution:
        The ``Constitution`` object (from ``acgs_lite``).
    llm_judge:
        An ``LLMGovernanceJudge`` implementation.
    sample_size:
        Number of entries to sample per audit run.
    seed:
        Random seed for reproducible sampling.
    """

    def __init__(
        self,
        constitution: Any,
        llm_judge: LLMGovernanceJudge,
        *,
        sample_size: int = 100,
        seed: int = 42,
    ) -> None:
        self.constitution = constitution
        self.llm_judge = llm_judge
        self.sample_size = sample_size
        self._rng = random.Random(seed)

    def sample_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        strategy: str = "stratified",
    ) -> list[dict[str, Any]]:
        """Sample audit entries for judging.

        Parameters
        ----------
        entries:
            List of audit entry dicts (must have ``valid``, ``action``, ``id``).
        strategy:
            ``"stratified"`` (proportional allow/deny) or ``"random"``.
        """
        if len(entries) <= self.sample_size:
            return list(entries)

        if strategy == "stratified":
            allows = [e for e in entries if _resolve_engine_decision(e) == "allow"]
            denies = [e for e in entries if _resolve_engine_decision(e) == "deny"]
            total = len(allows) + len(denies)
            if total == 0:
                return []
            n_allow = max(1, round(self.sample_size * len(allows) / total))
            n_deny = self.sample_size - n_allow
            if n_deny < 1 and denies:
                n_deny = 1
                n_allow = self.sample_size - 1
            sampled_allows = self._rng.sample(allows, min(n_allow, len(allows)))
            sampled_denies = self._rng.sample(denies, min(n_deny, len(denies)))
            sampled = (sampled_allows + sampled_denies)[: self.sample_size]
            self._rng.shuffle(sampled)
            return sampled

        return self._rng.sample(entries, self.sample_size)

    async def judge_entry(self, entry: dict[str, Any]) -> JudgmentResult:
        """Judge a single audit entry against the constitution."""
        action = entry.get("action", "")
        # Support both canonical "decision" field and legacy "valid" boolean
        engine_decision = _resolve_engine_decision(entry)
        engine_violations = entry.get("violations", [])
        # Normalize violations: may be rule IDs or full dicts
        violation_dicts = []
        for v in engine_violations:
            if isinstance(v, str):
                violation_dicts.append({"rule_id": v})
            elif isinstance(v, dict):
                violation_dicts.append(v)

        rules = _extract_rules(self.constitution)
        context = entry.get("context", entry.get("metadata", {}))

        # MACI: pass extracted rules (read-only data), not the live constitution object
        judgment: LLMJudgment = await self.llm_judge.evaluate(
            action=action,
            context={
                "rubric": build_audit_rubric(
                    action=action,
                    engine_decision=engine_decision,
                    engine_violations=violation_dicts,
                    constitution_rules=rules,
                    context=context,
                )
            },
            constitution=self.constitution,
        )

        # Validate judge decision is allow/deny, default to deny (fail-closed)
        judge_decision = judgment.decision if judgment.decision in ("allow", "deny") else "deny"
        agrees = judge_decision == engine_decision

        return JudgmentResult(
            entry_id=entry.get("id", _hash_action(action)),
            action=action,
            engine_decision=engine_decision,
            judge_decision=judge_decision,
            scores=judgment.scores,
            reasoning=judgment.reasoning,
            model_id=judgment.model_id,
            agrees_with_engine=agrees,
        )

    async def run_audit(self, entries: list[dict[str, Any]]) -> AuditReport:
        """Run a full audit cycle: sample, judge, aggregate."""
        sampled = self.sample_entries(entries)
        report = AuditReport(total_sampled=len(sampled))

        for entry in sampled:
            result = await self.judge_entry(entry)
            report.judgments.append(result)

        return report


def _resolve_engine_decision(entry: dict[str, Any]) -> str:
    """Resolve engine decision from canonical or legacy entry format.

    Supports both the canonical ``decision`` field (from ``GovernanceDecisionRecord``)
    and the legacy ``valid`` boolean (from ``AuditEntry``).  Falls back to ``"deny"``
    (fail-closed) if neither is present.
    """
    if "decision" in entry:
        d = entry["decision"]
        return d if d in ("allow", "deny") else "deny"
    valid = entry.get("valid")
    if valid is None:
        return "deny"  # fail-closed
    return "allow" if valid else "deny"


def _extract_rules(constitution: Any) -> list[dict[str, Any]]:
    """Extract rule dicts from a Constitution object."""
    rules = []
    rule_list = getattr(constitution, "rules", [])
    for r in rule_list:
        if hasattr(r, "id"):
            rules.append(
                {
                    "id": r.id,
                    "text": getattr(r, "text", ""),
                    "severity": getattr(r, "severity", "").value
                    if hasattr(getattr(r, "severity", ""), "value")
                    else str(getattr(r, "severity", "")),
                    "keywords": list(getattr(r, "keywords", [])),
                }
            )
        elif isinstance(r, dict):
            rules.append(r)
    return rules


def _hash_action(action: str) -> str:
    """Generate a short hash for an action string."""
    return hashlib.sha256(action.encode()).hexdigest()[:12]


__all__ = ["AuditReport", "GovernanceAuditJudge", "JudgmentResult"]
