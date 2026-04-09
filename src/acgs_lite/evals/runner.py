"""Offline constitution evaluation runner."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError

from .report import EvalRunReport, EvalScenarioResult
from .schema import EvalScenario, load_scenarios


def _actual_from_exception(exc: ConstitutionalViolationError) -> dict[str, Any]:
    action_taken = exc.enforcement_action.value if exc.enforcement_action is not None else None
    return {
        "valid": False,
        "action_taken": action_taken,
        "rule_ids": [exc.rule_id],
        "warning_triggered": False,
        "review_requested": action_taken == "require_human_review",
        "escalation_triggered": action_taken == "escalate_to_senior",
        "incident_triggered": action_taken == "halt_and_alert",
    }


def _actual_from_result(result: Any) -> dict[str, Any]:
    action_taken = result.action_taken.value if result.action_taken is not None else None
    rule_ids = [violation.rule_id for violation in result.violations]
    rule_ids.extend(violation.rule_id for violation in result.warnings)
    return {
        "valid": result.valid,
        "action_taken": action_taken,
        "rule_ids": rule_ids,
        "warning_triggered": bool(result.warnings),
        "review_requested": bool(result.review_requests),
        "escalation_triggered": bool(result.escalations),
        "incident_triggered": bool(result.incident_alerts),
    }


def evaluate_scenario(engine: GovernanceEngine, scenario: EvalScenario) -> EvalScenarioResult:
    """Run one scenario and compare the actual outcome to expectations."""
    try:
        result = engine.validate(scenario.input_action, context=scenario.context)
        actual = _actual_from_result(result)
    except ConstitutionalViolationError as exc:
        actual = _actual_from_exception(exc)

    failures: list[str] = []
    actual_rule_ids = tuple(actual["rule_ids"])
    if actual["valid"] != scenario.expected_valid:
        failures.append(
            f"expected_valid={scenario.expected_valid} actual_valid={actual['valid']}"
        )
    if scenario.expected_action_taken is not None and actual["action_taken"] != scenario.expected_action_taken:
        failures.append(
            "expected_action_taken="
            f"{scenario.expected_action_taken} actual_action_taken={actual['action_taken']}"
        )
    if set(actual_rule_ids) != set(scenario.expected_rule_ids):
        failures.append(
            f"expected_rule_ids={sorted(scenario.expected_rule_ids)} actual_rule_ids={sorted(actual_rule_ids)}"
        )
    for field_name, actual_key in (
        ("expected_warning", "warning_triggered"),
        ("expected_review_request", "review_requested"),
        ("expected_escalation", "escalation_triggered"),
        ("expected_incident", "incident_triggered"),
    ):
        expected_value = getattr(scenario, field_name)
        if expected_value is not None and actual[actual_key] != expected_value:
            failures.append(f"{field_name}={expected_value} actual_{actual_key}={actual[actual_key]}")

    return EvalScenarioResult(
        scenario_id=scenario.id,
        passed=len(failures) == 0,
        failures=tuple(failures),
        actual_valid=actual["valid"],
        actual_action_taken=actual["action_taken"],
        actual_rule_ids=actual_rule_ids,
        warning_triggered=actual["warning_triggered"],
        review_requested=actual["review_requested"],
        escalation_triggered=actual["escalation_triggered"],
        incident_triggered=actual["incident_triggered"],
        tags=tuple(scenario.tags),
    )


def run_eval(
    constitution_path: str | Path,
    scenarios_path: str | Path,
) -> EvalRunReport:
    """Run an offline eval suite against a constitution file."""
    constitution = Constitution.from_yaml(constitution_path)
    scenarios = load_scenarios(scenarios_path)
    engine = GovernanceEngine(constitution, strict=False)

    results = tuple(evaluate_scenario(engine, scenario) for scenario in scenarios)
    distribution = Counter(result.actual_action_taken or "allow" for result in results)
    passed = sum(1 for result in results if result.passed)
    return EvalRunReport(
        constitution_path=str(constitution_path),
        constitutional_hash=constitution.hash,
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        action_distribution=dict(sorted(distribution.items())),
        results=results,
    )


__all__ = ["evaluate_scenario", "run_eval"]
