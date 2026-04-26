"""S_test_fixture — rule precision/recall/F1 against the governance test suite.

The grounded fact (per QEC-vs-ACGS research stage 5 / addendum) is rule-test-
fixture coherence: ``RuleMetrics.f1_score`` and ``EvalReport`` already compute
per-rule TP/FP/FN/TN against ``GovernanceTestSuite``. This stabilizer lifts
those numerics to a binary {pass, fail} bit by thresholding F1.

The "Rego policy ↔" framing from the research is *deferred* — only landing as
a stabilizer once ``rego_export.py`` outputs are wired into the same fixture
loop. v0 stays at the rule/test layer.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import ClassVar

from ..failure_modes import StabilizerOutcome, StabilizerResult
from ..rule_metrics import EvalReport


class RuleFixtureStabilizer:
    """``S_test_fixture`` — emit PASS if rule F1 >= threshold, FAIL otherwise."""

    id: ClassVar[str] = "S_test_fixture"

    __slots__ = ("_f1_threshold",)

    def __init__(self, f1_threshold: float = 0.7) -> None:
        if not 0.0 <= f1_threshold <= 1.0:
            msg = f"f1_threshold must be in [0, 1], got {f1_threshold}"
            raise ValueError(msg)
        self._f1_threshold = f1_threshold

    @property
    def f1_threshold(self) -> float:
        """The F1 threshold below which the stabilizer fails."""
        return self._f1_threshold

    def evaluate(self, *, rule_id: str, eval_report: EvalReport) -> StabilizerResult:
        """Emit PASS if the rule's F1 meets threshold, FAIL otherwise.

        Raises ``KeyError`` if ``rule_id`` is not present in
        ``eval_report.rule_metrics``. Caller should canonicalise to upper-case
        (the eval-report builder upper-cases internally).
        """
        metrics = eval_report.rule_metrics[rule_id]
        passed = metrics.f1_score >= self._f1_threshold
        return StabilizerResult(
            stabilizer_id=self.id,
            outcome=StabilizerOutcome.PASS if passed else StabilizerOutcome.FAIL,
            rule_id=rule_id,
            evidence={
                "f1_score": round(metrics.f1_score, 4),
                "precision": round(metrics.precision, 4),
                "recall": round(metrics.recall, 4),
                "true_positives": metrics.true_positives,
                "false_positives": metrics.false_positives,
                "false_negatives": metrics.false_negatives,
                "support": metrics.support,
                "threshold": self._f1_threshold,
            },
        )
