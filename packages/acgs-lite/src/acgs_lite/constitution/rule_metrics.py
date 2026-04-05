"""Per-rule precision/recall/F1 metrics for governance test suites.

Extends GovernanceTestSuite reports with standard ML classification metrics
per rule and scenario-level outcome metrics.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .test_suite import TestOutcome, TestReport


@dataclass(slots=True)
class RuleMetrics:
    """Precision/recall/F1 for a single governance rule."""

    rule_id: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def support(self) -> int:
        """Number of scenarios where this rule was expected to fire."""
        return self.true_positives + self.false_negatives

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "support": self.support,
        }


@dataclass(slots=True)
class ScenarioOutcomeMetrics:
    """Scenario-level decision accuracy metrics."""

    total: int = 0
    correct: int = 0
    incorrect: int = 0
    errors: int = 0
    skipped: int = 0

    @property
    def accuracy(self) -> float:
        runnable = self.total - self.skipped
        return self.correct / runnable if runnable > 0 else 0.0

    @property
    def error_rate(self) -> float:
        runnable = self.total - self.skipped
        return self.errors / runnable if runnable > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "errors": self.errors,
            "skipped": self.skipped,
            "accuracy": round(self.accuracy, 4),
            "error_rate": round(self.error_rate, 4),
        }


@dataclass
class EvalReport:
    """Combined eval report: per-rule metrics + scenario-level outcomes."""

    rule_metrics: dict[str, RuleMetrics] = field(default_factory=dict)
    scenario_metrics: ScenarioOutcomeMetrics = field(default_factory=ScenarioOutcomeMetrics)
    suite_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        sorted_rules = sorted(self.rule_metrics.values(), key=lambda r: r.rule_id)
        return {
            "suite_name": self.suite_name,
            "scenario_metrics": self.scenario_metrics.to_dict(),
            "rule_metrics": {rm.rule_id: rm.to_dict() for rm in sorted_rules},
            "summary": self.summary(),
        }

    def summary(self) -> str:
        sm = self.scenario_metrics
        rules_with_support = [rm for rm in self.rule_metrics.values() if rm.support > 0]
        if rules_with_support:
            avg_f1 = sum(rm.f1_score for rm in rules_with_support) / len(rules_with_support)
        else:
            avg_f1 = 0.0
        return (
            f"Scenarios: {sm.accuracy:.1%} accuracy ({sm.correct}/{sm.total - sm.skipped}). "
            f"Rules: avg F1={avg_f1:.3f} across {len(rules_with_support)} rules with support."
        )

    def to_markdown(self) -> str:
        """Render as markdown summary table."""
        lines: list[str] = [
            f"# Eval Report: {self.suite_name}",
            "",
            "## Scenario-Level Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total | {self.scenario_metrics.total} |",
            f"| Correct | {self.scenario_metrics.correct} |",
            f"| Incorrect | {self.scenario_metrics.incorrect} |",
            f"| Errors | {self.scenario_metrics.errors} |",
            f"| Skipped | {self.scenario_metrics.skipped} |",
            f"| **Accuracy** | **{self.scenario_metrics.accuracy:.1%}** |",
            "",
            "## Per-Rule Metrics",
            "",
            "| Rule ID | Precision | Recall | F1 | TP | FP | FN | TN | Support |",
            "|---------|-----------|--------|----|----|----|----|----|---------|",
        ]
        for rm in sorted(self.rule_metrics.values(), key=lambda r: r.rule_id):
            lines.append(
                f"| {rm.rule_id} | {rm.precision:.3f} | {rm.recall:.3f} | "
                f"{rm.f1_score:.3f} | {rm.true_positives} | {rm.false_positives} | "
                f"{rm.false_negatives} | {rm.true_negatives} | {rm.support} |"
            )
        lines += ["", f"**Summary:** {self.summary()}"]
        return "\n".join(lines)


def compute_eval_report(
    report: TestReport,
    *,
    all_rule_ids: list[str],
    expected_rules_map: dict[str, list[str]],
    not_expected_rules_map: dict[str, list[str]] | None = None,
) -> EvalReport:
    """Compute per-rule and scenario-level metrics from a TestReport.

    Args:
        report: The TestReport from GovernanceTestSuite.run().
        all_rule_ids: All active rule IDs in the constitution.
        expected_rules_map: case_name → list of rule IDs expected to fire.
        not_expected_rules_map: case_name → list of rule IDs expected NOT to fire.

    Returns:
        EvalReport with per-rule P/R/F1 and scenario-level accuracy.
    """
    if not_expected_rules_map is None:
        not_expected_rules_map = {}

    # Canonicalize rule IDs to uppercase
    all_rule_ids_upper = [rid.upper() for rid in all_rule_ids]

    # Initialize per-rule metrics
    rule_metrics: dict[str, RuleMetrics] = {
        rid: RuleMetrics(rule_id=rid) for rid in all_rule_ids_upper
    }

    scenario = ScenarioOutcomeMetrics()

    for result in report.results:
        scenario.total += 1

        if result.outcome == TestOutcome.SKIP:
            scenario.skipped += 1
            continue
        if result.outcome == TestOutcome.ERROR:
            scenario.errors += 1
            continue

        # Scenario-level: decision correct?
        if result.outcome == TestOutcome.PASS:
            scenario.correct += 1
        else:
            scenario.incorrect += 1

        # Per-rule metrics
        actual_fired = {rid.upper() for rid in result.actual_rules_triggered}
        expected_fired = {rid.upper() for rid in expected_rules_map.get(result.case_name, [])}
        expected_not_fired = {
            rid.upper() for rid in not_expected_rules_map.get(result.case_name, [])
        }

        for rid in all_rule_ids_upper:
            rm = rule_metrics[rid]
            fired = rid in actual_fired
            should_fire = rid in expected_fired
            should_not_fire = rid in expected_not_fired

            if should_fire and fired:
                rm.true_positives += 1
            elif should_fire and not fired:
                rm.false_negatives += 1
            elif should_not_fire and fired:
                rm.false_positives += 1
            elif should_not_fire and not fired:
                rm.true_negatives += 1
            elif not should_fire and not should_not_fire:
                # No assertion for this rule on this scenario — skip
                # (don't pollute metrics with unlabeled data)
                pass
            else:
                # fired but no positive assertion and no negative assertion
                pass

    return EvalReport(
        rule_metrics=rule_metrics,
        scenario_metrics=scenario,
        suite_name=report.suite_name,
    )
