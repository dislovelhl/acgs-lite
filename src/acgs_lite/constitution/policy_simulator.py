"""exp220: GovernancePolicySimulator — advanced what-if analysis for policy changes.

Extends the basic simulation (exp130) with multi-scenario comparison, impact risk
scoring, recommendation generation, and differential analysis across multiple
proposed constitutions simultaneously.

Where exp130 answers "what changes?", this answers "should we ship it?" by
quantifying the blast radius, regression risk, and governance posture delta of a
proposed rule change before it reaches production.

Key capabilities:
- Multi-constitution comparison: test N candidate constitutions against the same
  action corpus in a single run.
- Impact risk scoring: classify each action delta as safe/low/medium/high/critical
  based on transition type (allow→deny is high; deny→allow is critical).
- Blast radius estimation: percentage of actions affected, weighted by risk.
- Regression detection: any deny→allow transition is flagged as a potential regression.
- Recommendation engine: go/no-go/review verdict with confidence score.
- Diff matrix: side-by-side comparison table across all candidates.
- Historical corpus support: feed recorded decision logs as the action corpus for
  realistic simulation.

Usage::

    from acgs_lite.constitution.policy_simulator import GovernancePolicySimulator

    sim = GovernancePolicySimulator()
    report = sim.compare(
        baseline=current_constitution,
        candidates={"v2": proposed_v2, "v3": proposed_v3},
        actions=["deploy to prod", "read user data", "delete backups"],
    )
    print(report.recommendation)
    print(report.summary())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_RISK_MATRIX: dict[tuple[str, str], str] = {
    ("allow", "allow"): "none",
    ("deny", "deny"): "none",
    ("allow", "deny"): "medium",
    ("deny", "allow"): "critical",
    ("allow", "escalate"): "low",
    ("escalate", "allow"): "low",
    ("deny", "escalate"): "high",
    ("escalate", "deny"): "medium",
    ("escalate", "escalate"): "none",
}

_RISK_WEIGHTS: dict[str, float] = {
    "none": 0.0,
    "low": 0.2,
    "medium": 0.5,
    "high": 0.8,
    "critical": 1.0,
}


def _safe_validate(constitution: Any, action: str, context: dict[str, Any] | None = None) -> str:
    try:
        result = constitution.validate(action, context=context or {})
        return str(getattr(result, "outcome", "allow")).lower()
    except Exception as exc:
        logger.debug(
            "policy simulator validation failed for action %r; returning error outcome: %s",
            action,
            exc,
            exc_info=True,
        )
        return "error"


@dataclass(frozen=True)
class ActionDelta:
    """Outcome change for a single action between baseline and candidate."""

    action: str
    baseline_outcome: str
    candidate_outcome: str
    changed: bool
    risk_level: str
    risk_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "baseline": self.baseline_outcome,
            "candidate": self.candidate_outcome,
            "changed": self.changed,
            "risk_level": self.risk_level,
        }


@dataclass(frozen=True)
class CandidateReport:
    """Simulation results for one candidate constitution."""

    candidate_id: str
    deltas: tuple[ActionDelta, ...]
    total_actions: int
    changed_count: int
    regressions: int
    blast_radius: float
    weighted_risk: float
    recommendation: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "total_actions": self.total_actions,
            "changed_count": self.changed_count,
            "regressions": self.regressions,
            "blast_radius_pct": round(self.blast_radius * 100, 2),
            "weighted_risk": round(self.weighted_risk, 4),
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 3),
            "deltas": [d.to_dict() for d in self.deltas if d.changed],
        }


@dataclass
class SimulationComparisonReport:
    """Full comparison report across baseline and N candidates."""

    baseline_id: str
    candidates: dict[str, CandidateReport] = field(default_factory=dict)
    actions_evaluated: int = 0
    generated_at: str = ""

    @property
    def best_candidate(self) -> str | None:
        go = {cid: cr for cid, cr in self.candidates.items() if cr.recommendation == "go"}
        if not go:
            return None
        return min(go, key=lambda cid: go[cid].weighted_risk)

    @property
    def recommendation(self) -> str:
        best = self.best_candidate
        if best:
            return f"go: {best}"
        review = [cid for cid, cr in self.candidates.items() if cr.recommendation == "review"]
        if review:
            return f"review: {', '.join(review)}"
        return "no-go: all candidates flagged"

    def summary(self) -> str:
        lines = [
            "=== GovernancePolicySimulator Report ===",
            f"Baseline       : {self.baseline_id}",
            f"Candidates     : {len(self.candidates)}",
            f"Actions tested : {self.actions_evaluated}",
            f"Recommendation : {self.recommendation}",
            "",
        ]
        for cid, cr in self.candidates.items():
            lines.append(
                f"  {cid:<20}  changed={cr.changed_count}/{cr.total_actions}  "
                f"regressions={cr.regressions}  blast={cr.blast_radius:.1%}  "
                f"risk={cr.weighted_risk:.4f}  → {cr.recommendation} ({cr.confidence:.0%})"
            )
        return "\n".join(lines)

    def diff_matrix(self) -> list[dict[str, Any]]:
        """Side-by-side comparison: one row per action, one column per candidate."""
        all_actions: list[str] = []
        deltas_by_cid: dict[str, dict[str, ActionDelta]] = {}
        for cid, cr in self.candidates.items():
            deltas_by_cid[cid] = {d.action: d for d in cr.deltas}
            for d in cr.deltas:
                if d.action not in all_actions:
                    all_actions.append(d.action)

        rows: list[dict[str, Any]] = []
        for action in all_actions:
            row: dict[str, Any] = {"action": action}
            for cid in self.candidates:
                delta = deltas_by_cid.get(cid, {}).get(action)
                if delta:
                    row[cid] = {
                        "outcome": delta.candidate_outcome,
                        "changed": delta.changed,
                        "risk": delta.risk_level,
                    }
                else:
                    row[cid] = {"outcome": "N/A", "changed": False, "risk": "none"}
            rows.append(row)
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "actions_evaluated": self.actions_evaluated,
            "recommendation": self.recommendation,
            "best_candidate": self.best_candidate,
            "generated_at": self.generated_at,
            "candidates": {cid: cr.to_dict() for cid, cr in self.candidates.items()},
        }


class GovernancePolicySimulator:
    """Advanced what-if analyser for proposed governance policy changes.

    Compares one or more candidate constitutions against a baseline using a
    corpus of test actions, quantifying blast radius, risk, and regressions.

    Args:
        regression_threshold: Max acceptable regression fraction before no-go (default: 0).
        risk_threshold: Max weighted risk before downgrading to review (default: 0.3).
    """

    def __init__(
        self,
        regression_threshold: float = 0.0,
        risk_threshold: float = 0.3,
    ) -> None:
        self._regression_threshold = regression_threshold
        self._risk_threshold = risk_threshold

    def compare(
        self,
        baseline: Any,
        candidates: dict[str, Any],
        actions: list[str],
        context: dict[str, Any] | None = None,
        baseline_id: str = "baseline",
    ) -> SimulationComparisonReport:
        """Run a multi-candidate simulation.

        Args:
            baseline: The current production constitution.
            candidates: Mapping of candidate_id → candidate constitution.
            actions: List of action strings to evaluate.
            context: Optional context dict forwarded to validate().
            baseline_id: Label for the baseline in the report.

        Returns:
            :class:`SimulationComparisonReport`.
        """
        ctx = context or {}

        baseline_outcomes: dict[str, str] = {}
        for action in actions:
            baseline_outcomes[action] = _safe_validate(baseline, action, ctx)

        report = SimulationComparisonReport(
            baseline_id=baseline_id,
            actions_evaluated=len(actions),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
        )

        for cid, candidate in candidates.items():
            report.candidates[cid] = self._evaluate_candidate(
                cid, candidate, actions, baseline_outcomes, ctx
            )

        return report

    def evaluate_single(
        self,
        baseline: Any,
        candidate: Any,
        actions: list[str],
        context: dict[str, Any] | None = None,
        candidate_id: str = "candidate",
    ) -> CandidateReport:
        """Convenience method for comparing one candidate against baseline."""
        ctx = context or {}
        baseline_outcomes = {a: _safe_validate(baseline, a, ctx) for a in actions}
        return self._evaluate_candidate(candidate_id, candidate, actions, baseline_outcomes, ctx)

    def _evaluate_candidate(
        self,
        cid: str,
        candidate: Any,
        actions: list[str],
        baseline_outcomes: dict[str, str],
        ctx: dict[str, Any],
    ) -> CandidateReport:
        deltas: list[ActionDelta] = []

        for action in actions:
            baseline_out = baseline_outcomes.get(action, "allow")
            candidate_out = _safe_validate(candidate, action, ctx)
            changed = baseline_out != candidate_out

            key = (baseline_out, candidate_out)
            risk_level = _RISK_MATRIX.get(key, "medium" if changed else "none")
            risk_weight = _RISK_WEIGHTS.get(risk_level, 0.5)

            deltas.append(
                ActionDelta(
                    action=action,
                    baseline_outcome=baseline_out,
                    candidate_outcome=candidate_out,
                    changed=changed,
                    risk_level=risk_level,
                    risk_weight=risk_weight,
                )
            )

        total = len(deltas)
        changed_count = sum(1 for d in deltas if d.changed)
        regressions = sum(
            1 for d in deltas if d.baseline_outcome == "deny" and d.candidate_outcome == "allow"
        )
        blast_radius = changed_count / total if total > 0 else 0.0
        weighted_risk = (
            sum(d.risk_weight for d in deltas if d.changed) / total if total > 0 else 0.0
        )

        regression_rate = regressions / total if total > 0 else 0.0
        if regression_rate > self._regression_threshold:
            recommendation = "no-go"
            confidence = min(1.0, 0.6 + regression_rate)
        elif weighted_risk > self._risk_threshold:
            recommendation = "review"
            confidence = 0.5 + weighted_risk * 0.3
        else:
            recommendation = "go"
            confidence = max(0.5, 1.0 - weighted_risk - blast_radius * 0.2)

        return CandidateReport(
            candidate_id=cid,
            deltas=tuple(deltas),
            total_actions=total,
            changed_count=changed_count,
            regressions=regressions,
            blast_radius=blast_radius,
            weighted_risk=weighted_risk,
            recommendation=recommendation,
            confidence=round(min(1.0, confidence), 3),
        )
