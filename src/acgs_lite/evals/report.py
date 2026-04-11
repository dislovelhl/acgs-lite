"""Structured reports for offline constitution evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EvalScenarioResult:
    """Actual outcome for one evaluation scenario."""

    scenario_id: str
    passed: bool
    failures: tuple[str, ...]
    actual_valid: bool
    actual_action_taken: str | None
    actual_rule_ids: tuple[str, ...]
    warning_triggered: bool
    review_requested: bool
    escalation_triggered: bool
    incident_triggered: bool
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "failures": list(self.failures),
            "actual_valid": self.actual_valid,
            "actual_action_taken": self.actual_action_taken,
            "actual_rule_ids": list(self.actual_rule_ids),
            "warning_triggered": self.warning_triggered,
            "review_requested": self.review_requested,
            "escalation_triggered": self.escalation_triggered,
            "incident_triggered": self.incident_triggered,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class EvalRunReport:
    """Result of running a scenario suite against one constitution."""

    constitution_path: str
    constitutional_hash: str
    total: int
    passed: int
    failed: int
    action_distribution: dict[str, int]
    results: tuple[EvalScenarioResult, ...]

    @property
    def success(self) -> bool:
        return self.failed == 0

    def summary(self) -> str:
        label = "PASS" if self.success else "FAIL"
        return f"{label} — {self.passed}/{self.total} scenarios matched expectations"

    def to_dict(self) -> dict[str, Any]:
        return {
            "constitution_path": self.constitution_path,
            "constitutional_hash": self.constitutional_hash,
            "success": self.success,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "action_distribution": dict(self.action_distribution),
            "summary": self.summary(),
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class ScenarioRegression:
    """Behavioral delta between baseline and candidate for one scenario."""

    scenario_id: str
    regression_type: str
    baseline_action_taken: str | None
    candidate_action_taken: str | None
    baseline_rule_ids: tuple[str, ...]
    candidate_rule_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "regression_type": self.regression_type,
            "baseline_action_taken": self.baseline_action_taken,
            "candidate_action_taken": self.candidate_action_taken,
            "baseline_rule_ids": list(self.baseline_rule_ids),
            "candidate_rule_ids": list(self.candidate_rule_ids),
        }


@dataclass(frozen=True, slots=True)
class EvalComparisonReport:
    """Comparison between baseline and candidate eval runs."""

    baseline: EvalRunReport
    candidate: EvalRunReport
    regressions: tuple[ScenarioRegression, ...] = ()
    changed_rule_sets: tuple[ScenarioRegression, ...] = ()
    changed_actions: tuple[ScenarioRegression, ...] = ()
    action_distribution_delta: dict[str, int] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.regressions) == 0

    def summary(self) -> str:
        label = "PASS" if self.success else "FAIL"
        return (
            f"{label} — regressions={len(self.regressions)}, "
            f"changed_actions={len(self.changed_actions)}, "
            f"changed_rule_sets={len(self.changed_rule_sets)}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary(),
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "regressions": [item.to_dict() for item in self.regressions],
            "changed_rule_sets": [item.to_dict() for item in self.changed_rule_sets],
            "changed_actions": [item.to_dict() for item in self.changed_actions],
            "action_distribution_delta": dict(self.action_distribution_delta),
        }


def compare_eval_reports(baseline: EvalRunReport, candidate: EvalRunReport) -> EvalComparisonReport:
    """Compare two eval runs and flag regressions and behavior deltas."""
    baseline_results = {result.scenario_id: result for result in baseline.results}
    candidate_results = {result.scenario_id: result for result in candidate.results}

    regressions: list[ScenarioRegression] = []
    changed_rule_sets: list[ScenarioRegression] = []
    changed_actions: list[ScenarioRegression] = []

    for scenario_id in sorted(set(baseline_results) & set(candidate_results)):
        before = baseline_results[scenario_id]
        after = candidate_results[scenario_id]
        if before.passed and not after.passed:
            regressions.append(
                ScenarioRegression(
                    scenario_id=scenario_id,
                    regression_type="baseline_pass_candidate_fail",
                    baseline_action_taken=before.actual_action_taken,
                    candidate_action_taken=after.actual_action_taken,
                    baseline_rule_ids=before.actual_rule_ids,
                    candidate_rule_ids=after.actual_rule_ids,
                )
            )
        if before.actual_action_taken != after.actual_action_taken:
            changed_actions.append(
                ScenarioRegression(
                    scenario_id=scenario_id,
                    regression_type="action_changed",
                    baseline_action_taken=before.actual_action_taken,
                    candidate_action_taken=after.actual_action_taken,
                    baseline_rule_ids=before.actual_rule_ids,
                    candidate_rule_ids=after.actual_rule_ids,
                )
            )
        if before.actual_rule_ids != after.actual_rule_ids:
            changed_rule_sets.append(
                ScenarioRegression(
                    scenario_id=scenario_id,
                    regression_type="rule_set_changed",
                    baseline_action_taken=before.actual_action_taken,
                    candidate_action_taken=after.actual_action_taken,
                    baseline_rule_ids=before.actual_rule_ids,
                    candidate_rule_ids=after.actual_rule_ids,
                )
            )

    all_actions = set(baseline.action_distribution) | set(candidate.action_distribution)
    distribution_delta = {
        action: candidate.action_distribution.get(action, 0)
        - baseline.action_distribution.get(action, 0)
        for action in sorted(all_actions)
    }

    return EvalComparisonReport(
        baseline=baseline,
        candidate=candidate,
        regressions=tuple(regressions),
        changed_rule_sets=tuple(changed_rule_sets),
        changed_actions=tuple(changed_actions),
        action_distribution_delta=distribution_delta,
    )


__all__ = [
    "EvalComparisonReport",
    "EvalRunReport",
    "EvalScenarioResult",
    "ScenarioRegression",
    "compare_eval_reports",
]
