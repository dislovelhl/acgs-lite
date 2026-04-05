"""Runtime rule activation regressions for GovernanceEngine."""

from __future__ import annotations

import pytest

from acgs_lite import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError


def test_condition_gated_rule_only_applies_in_matching_context() -> None:
    constitution = Constitution.from_rules(
        [
            Rule(
                id="PROD-ONLY",
                text="Do not deploy directly to production",
                severity=Severity.CRITICAL,
                keywords=["deploy"],
                condition={"env": "production"},
            )
        ]
    )
    engine = GovernanceEngine(constitution, audit_mode="fast")

    dev_result = engine.validate("deploy new model", context={"env": "dev"})
    assert dev_result.valid is True
    assert dev_result.violations == []

    with pytest.raises(ConstitutionalViolationError):
        engine.validate("deploy new model", context={"env": "production"})


def test_deprecated_rules_are_not_enforced() -> None:
    constitution = Constitution.from_rules(
        [
            Rule(
                id="OLD-RULE",
                text="Legacy rule kept for audit history",
                severity=Severity.CRITICAL,
                keywords=["legacy forbidden action"],
                deprecated=True,
            )
        ]
    )
    engine = GovernanceEngine(constitution, audit_mode="fast")

    result = engine.validate("legacy forbidden action")
    assert result.valid is True
    assert result.violations == []
    assert result.rules_checked == 0


def test_future_dated_rules_are_not_enforced_before_activation() -> None:
    constitution = Constitution.from_rules(
        [
            Rule(
                id="FUTURE-RULE",
                text="Future activation rule",
                severity=Severity.CRITICAL,
                keywords=["future-only action"],
                valid_from="2099-01-01",
            )
        ]
    )
    engine = GovernanceEngine(constitution, audit_mode="fast")

    result = engine.validate("future-only action")
    assert result.valid is True
    assert result.violations == []
    assert result.rules_checked == 0
