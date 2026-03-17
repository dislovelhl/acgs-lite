"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GovernanceTestCase:
    """exp129: Immutable governance test case."""

    action: str
    expected_decision: str
    context: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TestCaseFailure:
    """exp129: Failure record for a single governance test case."""

    test_case: GovernanceTestCase
    actual_decision: str
    details: str = ""


@dataclass(frozen=True, slots=True)
class TestSuiteResult:
    """exp129: Aggregate result for a governance test suite run."""

    total: int
    passed: int
    failed: int
    failures: tuple[TestCaseFailure, ...]
    pass_rate: float
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize the suite result to a JSON-compatible dict."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "failures": [
                {
                    "test_case": {
                        "action": f.test_case.action,
                        "expected_decision": f.test_case.expected_decision,
                        "context": f.test_case.context,
                        "description": f.test_case.description,
                        "tags": list(f.test_case.tags),
                    },
                    "actual_decision": f.actual_decision,
                    "details": f.details,
                }
                for f in self.failures
            ],
            "pass_rate": self.pass_rate,
            "duration_ms": self.duration_ms,
        }


class GovernanceTestSuite:
    """exp129: Bounded in-memory test suite for constitution validation behavior."""

    __slots__ = ("_cases", "_name")

    _MAX_CASES = 10_000

    def __init__(self, name: str = "default") -> None:
        self._cases: list[GovernanceTestCase] = []
        self._name = name

    def add_case(
        self,
        action: str,
        expected_decision: str,
        context: dict[str, Any] | None = None,
        description: str = "",
        tags: tuple[str, ...] = (),
    ) -> GovernanceTestCase:
        """Add one test case to the suite."""
        if len(self._cases) >= self._MAX_CASES:
            raise ValueError(f"Test suite exceeds max size of {self._MAX_CASES}")

        case = GovernanceTestCase(
            action=action,
            expected_decision=expected_decision,
            context=context or {},
            description=description,
            tags=tags,
        )
        self._cases.append(case)
        return case

    def add_cases(self, cases: Sequence[GovernanceTestCase]) -> None:
        """Add multiple test cases to the suite."""
        incoming = len(cases)
        if len(self._cases) + incoming > self._MAX_CASES:
            raise ValueError(f"Test suite exceeds max size of {self._MAX_CASES}")
        self._cases.extend(cases)

    def run(self, engine: Any) -> TestSuiteResult:
        """Run all test cases against a GovernanceEngine.

        Args:
            engine: A ``GovernanceEngine`` instance (or any
                object with a ``validate(action, context=)``
                method returning an object with a ``valid``
                attribute and ``violations`` list).
        """
        started = time.perf_counter()
        failures: list[TestCaseFailure] = []

        for case in self._cases:
            ctx = case.context or None
            try:
                result = engine.validate(case.action, context=ctx)
            except Exception:
                actual_decision = "deny"
            else:
                if result.valid:
                    actual_decision = "allow"
                elif result.violations:
                    sev = getattr(
                        result.violations[0],
                        "severity",
                        None,
                    )
                    blocks = getattr(sev, "blocks", lambda: True)
                    actual_decision = "deny" if callable(blocks) and blocks() else "escalate"
                else:
                    actual_decision = "allow"
            if actual_decision != case.expected_decision:
                failures.append(
                    TestCaseFailure(
                        test_case=case,
                        actual_decision=actual_decision,
                        details=(
                            f"Expected {case.expected_decision!r} but got {actual_decision!r}"
                        ),
                    )
                )

        duration_ms = (time.perf_counter() - started) * 1000.0
        total = len(self._cases)
        failed = len(failures)
        passed = total - failed
        pass_rate = (passed / total) if total > 0 else 1.0

        return TestSuiteResult(
            total=total,
            passed=passed,
            failed=failed,
            failures=tuple(failures),
            pass_rate=pass_rate,
            duration_ms=duration_ms,
        )

    def export(self) -> list[dict[str, Any]]:
        """Export all test cases as dictionaries."""
        return [
            {
                "action": c.action,
                "expected_decision": c.expected_decision,
                "context": c.context,
                "description": c.description,
                "tags": list(c.tags),
            }
            for c in self._cases
        ]

    def __len__(self) -> int:
        return len(self._cases)
