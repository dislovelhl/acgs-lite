"""Governance test suite — declarative fixture-driven regression testing for governance rules.

Provides a pytest-style test framework for governance rule authoring workflows.
Test cases are plain dicts or dataclasses (compatible with YAML fixture loading),
and the suite runs them against any callable governance engine, producing
CI-ready pass/fail reports with regression detection.

Zero hot-path overhead — all test execution is offline, driven by the test author.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TestOutcome(str, Enum):
    """Result of a single governance test case."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # unexpected exception during evaluation
    SKIP = "skip"  # case marked as skipped


@dataclass
class GovernanceTestCase:
    """A single declarative governance test case.

    Attributes:
        name: Human-readable test name.
        input_text: The text to evaluate against the governance engine.
        context: Optional context dict passed alongside the text.
        expected_decision: Expected top-level outcome (e.g. ``"allow"``, ``"deny"``).
        expected_rules_triggered: Rule IDs expected to fire (subset check).
        expected_rules_not_triggered: Rule IDs that must NOT fire.
        skip: If True, this case is skipped (useful for WIP cases).
        tags: Arbitrary tags for filtering (e.g. ``["pii", "regression"]``).
    """

    name: str
    input_text: str
    expected_decision: str
    context: dict[str, Any] = field(default_factory=dict)
    expected_rules_triggered: list[str] = field(default_factory=list)
    expected_rules_not_triggered: list[str] = field(default_factory=list)
    skip: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceTestCase:
        """Construct from a plain dict (e.g. loaded from YAML/JSON)."""
        return cls(
            name=data["name"],
            input_text=data["input_text"],
            expected_decision=data["expected_decision"],
            context=data.get("context", {}),
            expected_rules_triggered=data.get("expected_rules_triggered", []),
            expected_rules_not_triggered=data.get("expected_rules_not_triggered", []),
            skip=data.get("skip", False),
            tags=data.get("tags", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "input_text": self.input_text,
            "expected_decision": self.expected_decision,
            "context": self.context,
            "expected_rules_triggered": self.expected_rules_triggered,
            "expected_rules_not_triggered": self.expected_rules_not_triggered,
            "skip": self.skip,
            "tags": self.tags,
        }


@dataclass
class AssertionResult:
    """Outcome of asserting one test case against an actual governance result."""

    case_name: str
    outcome: TestOutcome
    actual_decision: str | None = None
    actual_rules_triggered: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)  # human-readable failure reasons
    error_message: str | None = None
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.outcome == TestOutcome.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "outcome": self.outcome.value,
            "actual_decision": self.actual_decision,
            "actual_rules_triggered": self.actual_rules_triggered,
            "failures": self.failures,
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 3),
        }


@dataclass
class TestReport:
    """Aggregated results from running a governance test suite."""

    results: list[AssertionResult] = field(default_factory=list)
    suite_name: str = ""
    run_at: float = field(default_factory=time.monotonic)

    @property
    def passed(self) -> list[AssertionResult]:
        return [r for r in self.results if r.outcome == TestOutcome.PASS]

    @property
    def failed(self) -> list[AssertionResult]:
        return [r for r in self.results if r.outcome == TestOutcome.FAIL]

    @property
    def errors(self) -> list[AssertionResult]:
        return [r for r in self.results if r.outcome == TestOutcome.ERROR]

    @property
    def skipped(self) -> list[AssertionResult]:
        return [r for r in self.results if r.outcome == TestOutcome.SKIP]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def ci_passed(self) -> bool:
        """Return True if the suite passes CI (no failures or errors)."""
        return not self.failed and not self.errors

    def coverage_pct(self) -> float:
        """Fraction of non-skipped cases that passed."""
        runnable = [r for r in self.results if r.outcome != TestOutcome.SKIP]
        if not runnable:
            return 0.0
        return len([r for r in runnable if r.outcome == TestOutcome.PASS]) / len(runnable)

    def regressions(self, baseline: TestReport) -> list[AssertionResult]:
        """Return cases that passed in *baseline* but fail in this report."""
        baseline_passed = {r.case_name for r in baseline.passed}
        return [r for r in self.failed if r.case_name in baseline_passed]

    def summary(self) -> str:
        label = "✅ PASS" if self.ci_passed else "❌ FAIL"
        return (
            f"{label} — {len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.errors)} errors, {len(self.skipped)} skipped "
            f"({self.coverage_pct():.0%} coverage)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "ci_passed": self.ci_passed,
            "summary": self.summary(),
            "total": self.total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "errors": len(self.errors),
            "skipped": len(self.skipped),
            "coverage_pct": round(self.coverage_pct(), 4),
            "results": [r.to_dict() for r in self.results],
        }

    def to_text(self) -> str:
        """Render as human-readable text output (pytest-style)."""
        lines: list[str] = [f"=== Governance Test Suite: {self.suite_name} ===", ""]
        for r in self.results:
            icon = {"pass": "✓", "fail": "✗", "error": "!", "skip": "s"}.get(r.outcome.value, "?")
            lines.append(f"  {icon} {r.case_name} ({r.duration_ms:.1f}ms)")
            for failure in r.failures:
                lines.append(f"      → {failure}")
            if r.error_message:
                lines.append(f"      ! ERROR: {r.error_message}")
        lines += ["", self.summary()]
        return "\n".join(lines)


# Type alias for the governance engine callable.
# It should accept (text: str, context: dict) and return a result with:
#   .decision or ["decision"] → str
#   .triggered_rules or ["triggered_rules"] → list of rule-id-bearing objects
GovernanceEngineFn = Callable[[str, dict[str, Any]], Any]


class GovernanceTestSuite:
    """Declarative fixture-driven test framework for governance rules.

    Runs :class:`GovernanceTestCase` fixtures against any callable governance
    engine and produces a :class:`TestReport` with CI-friendly pass/fail status.

    The engine callable must accept ``(text: str, context: dict)`` and return
    an object (or dict) with:
    - ``.decision`` or ``["decision"]`` → outcome string
    - ``.triggered_rules`` or ``["triggered_rules"]`` → list of rule objects
      (each having ``.id`` or ``["id"]``)

    Example usage::

        suite = GovernanceTestSuite(engine=my_engine.evaluate, name="PII Suite")

        suite.add_case(GovernanceTestCase(
            name="blocks SSN",
            input_text="Here is the SSN: 123-45-6789",
            expected_decision="deny",
            expected_rules_triggered=["pii-block"],
        ))
        suite.add_case(GovernanceTestCase(
            name="allows generic greeting",
            input_text="Hello, how are you?",
            expected_decision="allow",
        ))

        report = suite.run()
        print(report.to_text())
        assert report.ci_passed
    """

    def __init__(
        self,
        engine: GovernanceEngineFn,
        *,
        name: str = "GovernanceTestSuite",
        fail_fast: bool = False,
    ) -> None:
        self._engine = engine
        self._name = name
        self._fail_fast = fail_fast
        self._cases: list[GovernanceTestCase] = []
        self._baseline: TestReport | None = None

    def add_case(self, case: GovernanceTestCase) -> None:
        """Add a single test case to the suite."""
        self._cases.append(case)

    def add_cases(self, cases: list[GovernanceTestCase]) -> None:
        """Add multiple test cases at once."""
        self._cases.extend(cases)

    def load_from_dicts(self, data: list[dict[str, Any]]) -> None:
        """Load test cases from a list of plain dicts (e.g. parsed from YAML)."""
        for item in data:
            self._cases.append(GovernanceTestCase.from_dict(item))

    def generate_from_history(
        self,
        history: list[dict[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[GovernanceTestCase]:
        """Generate test fixtures from recorded decision history.

        Each history entry should have: ``input_text``, ``decision``,
        and optionally ``triggered_rule_ids`` and ``context``.

        Returns the generated cases (also adds them to the suite).
        """
        cases: list[GovernanceTestCase] = []
        entries = history[:limit] if limit else history
        for i, entry in enumerate(entries):
            case = GovernanceTestCase(
                name=f"history-{i:04d}: {entry.get('input_text', '')[:40]}",
                input_text=entry.get("input_text", ""),
                expected_decision=entry.get("decision", "allow"),
                context=entry.get("context", {}),
                expected_rules_triggered=entry.get("triggered_rule_ids", []),
                tags=["generated-from-history"],
            )
            cases.append(case)
        self._cases.extend(cases)
        return cases

    def run(
        self,
        *,
        tags: list[str] | None = None,
        case_names: list[str] | None = None,
    ) -> TestReport:
        """Execute all (or filtered) test cases and return a :class:`TestReport`.

        Args:
            tags: If given, only run cases that have at least one matching tag.
            case_names: If given, only run cases with these exact names.

        Returns:
            :class:`TestReport` with per-case results and aggregate stats.
        """
        cases_to_run = self._cases
        if tags is not None:
            tag_set = set(tags)
            cases_to_run = [c for c in cases_to_run if tag_set.intersection(c.tags)]
        if case_names is not None:
            name_set = set(case_names)
            cases_to_run = [c for c in cases_to_run if c.name in name_set]

        report = TestReport(suite_name=self._name)

        for case in cases_to_run:
            result = self._run_case(case)
            report.results.append(result)
            if self._fail_fast and result.outcome in (TestOutcome.FAIL, TestOutcome.ERROR):
                break

        self._baseline = report
        return report

    def assert_no_regressions(
        self, baseline: TestReport, current: TestReport
    ) -> list[AssertionResult]:
        """Return cases that regressed from baseline to current.

        Raises nothing — caller decides how to handle regressions.
        """
        return current.regressions(baseline)

    def case_count(self) -> int:
        """Return the number of registered test cases."""
        return len(self._cases)

    def filter_cases(self, *, tags: list[str] | None = None) -> list[GovernanceTestCase]:
        """Return cases matching the given tag filter."""
        if tags is None:
            return list(self._cases)
        tag_set = set(tags)
        return [c for c in self._cases if tag_set.intersection(c.tags)]

    def export_fixtures(self) -> list[dict[str, Any]]:
        """Export all test cases as a list of dicts (suitable for YAML/JSON serialisation)."""
        return [c.to_dict() for c in self._cases]

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _run_case(self, case: GovernanceTestCase) -> AssertionResult:
        if case.skip:
            return AssertionResult(case_name=case.name, outcome=TestOutcome.SKIP)

        start = time.monotonic()
        try:
            raw_result = self._engine(case.input_text, case.context)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.monotonic() - start) * 1000
            return AssertionResult(
                case_name=case.name,
                outcome=TestOutcome.ERROR,
                error_message=f"{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - start) * 1000
        actual_decision = self._extract_decision(raw_result)
        actual_rule_ids = self._extract_rule_ids(raw_result)

        failures: list[str] = []

        if actual_decision != case.expected_decision:
            failures.append(
                f"decision mismatch: expected '{case.expected_decision}', got '{actual_decision}'"
            )

        for expected_id in case.expected_rules_triggered:
            if expected_id not in actual_rule_ids:
                failures.append(f"expected rule '{expected_id}' to trigger, but it did not")

        for forbidden_id in case.expected_rules_not_triggered:
            if forbidden_id in actual_rule_ids:
                failures.append(f"rule '{forbidden_id}' triggered but was expected NOT to fire")

        outcome = TestOutcome.PASS if not failures else TestOutcome.FAIL
        return AssertionResult(
            case_name=case.name,
            outcome=outcome,
            actual_decision=actual_decision,
            actual_rules_triggered=actual_rule_ids,
            failures=failures,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _extract_decision(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("decision", ""))
        return str(getattr(result, "decision", ""))

    @staticmethod
    def _extract_rule_ids(result: Any) -> list[str]:
        if isinstance(result, dict):
            rules = result.get("triggered_rules", [])
        else:
            rules = getattr(result, "triggered_rules", [])
        ids: list[str] = []
        for rule in rules:
            if isinstance(rule, dict):
                rid = rule.get("id") or rule.get("rule_id", "")
            else:
                rid = getattr(rule, "id", getattr(rule, "rule_id", ""))
            if rid:
                ids.append(str(rid))
        return ids
