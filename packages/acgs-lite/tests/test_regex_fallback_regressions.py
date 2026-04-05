"""Regression tests for regex-only fallback behavior in the governance engine."""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine.core import GovernanceEngine


def _disable_rust_and_ac(engine: GovernanceEngine) -> None:
    """Force the engine onto the pure-Python regex fallback path."""
    _h = engine._hot
    engine._hot = (
        None,
        _h[1],
        _h[2],
        _h[3],
        _h[4],
        _h[5],
        _h[6],
        _h[7],
        False,
        _h[9],
        None,
        _h[11],
    )
    engine._ac_iter = None
    engine._rust_validator = None


def _make_mixed_anchor_constitution() -> Constitution:
    return Constitution.from_rules(
        [
            Rule(
                id="ANCHOR-GITHUB",
                text="No GitHub personal access tokens",
                severity=Severity.HIGH,
                keywords=["token"],
                patterns=[r"(?i)(ghp_[a-zA-Z0-9]{36})"],
                category="security",
            ),
            Rule(
                id="NO-ANCHOR-SSN",
                text="No social security numbers in content",
                severity=Severity.CRITICAL,
                keywords=["ssn"],
                patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
                category="pii",
            ),
        ],
        name="mixed-anchor-regression",
    )


@pytest.mark.unit
def test_regex_fallback_scans_no_anchor_patterns_when_anchor_gate_misses() -> None:
    engine = GovernanceEngine(_make_mixed_anchor_constitution(), strict=False)
    _disable_rust_and_ac(engine)

    result = engine.validate("User SSN is 123-45-6789")

    assert result.valid is False
    assert {violation.rule_id for violation in result.violations} == {"NO-ANCHOR-SSN"}


@pytest.mark.unit
def test_regex_fallback_positive_verb_still_scans_no_anchor_patterns() -> None:
    engine = GovernanceEngine(_make_mixed_anchor_constitution(), strict=False)
    _disable_rust_and_ac(engine)

    result = engine.validate("check ssn 123-45-6789 handling")

    assert result.valid is False
    assert {violation.rule_id for violation in result.violations} == {"NO-ANCHOR-SSN"}


@pytest.mark.unit
def test_invalid_regex_pattern_skipped_without_crash() -> None:
    """GovernanceEngine skips rules whose patterns contain invalid regex."""
    good_rule = Rule(
        id="GOOD-001",
        text="No secrets",
        severity=Severity.HIGH,
        keywords=["secret"],
        patterns=[r"\bsecret\b"],
        category="security",
    )
    bad_rule = Rule(
        id="BAD-001",
        text="Bad pattern rule",
        severity=Severity.HIGH,
        keywords=["test"],
        patterns=["valid_placeholder"],
        category="test",
    )
    object.__setattr__(bad_rule, "patterns", ["[invalid"])
    object.__setattr__(bad_rule, "_compiled_pats", [])

    constitution = Constitution.from_rules([good_rule, bad_rule])
    engine = GovernanceEngine(constitution, strict=False)

    assert len(engine._active_rules) == 1
    assert engine._active_rules[0].id == "GOOD-001"

    result = engine.validate("this contains a secret")
    assert result.valid is False
    assert any(v.rule_id == "GOOD-001" for v in result.violations)
