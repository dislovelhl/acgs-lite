"""Tests for the opt-in SMT verification gate."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.formal.smt_gate import NullVerificationGate, Z3VerificationGate


def _constitution_with_rules(*rules: Rule) -> Constitution:
    return Constitution.from_rules(list(rules), name="test-constitution")


def test_null_verification_gate_always_allows() -> None:
    rule = Rule(
        id="RULE-001", text="block secrets", severity=Severity.CRITICAL, keywords=["secret"]
    )

    result = NullVerificationGate().check(rule, _constitution_with_rules(rule))

    assert result.satisfiable is True
    assert result.contradiction is False
    assert result.warnings == ()


def test_z3_verification_gate_warns_when_z3_unavailable() -> None:
    rule = Rule(
        id="RULE-001", text="block secrets", severity=Severity.CRITICAL, keywords=["secret"]
    )

    result = Z3VerificationGate(z3_module=None).check(rule, _constitution_with_rules(rule))

    assert result.satisfiable is True
    assert result.contradiction is False
    assert "z3-solver not installed" in result.warnings[0]


def test_z3_verification_gate_detects_same_rule_id_severity_contradiction() -> None:
    original = Rule(
        id="RULE-001",
        text="block secrets",
        severity=Severity.CRITICAL,
        keywords=["secret"],
    )
    conflicting = Rule(
        id="RULE-001",
        text="warn on secrets",
        severity=Severity.HIGH,
        keywords=["secret"],
    )
    constitution = cast(Constitution, SimpleNamespace(rules=[original, conflicting]))

    result = Z3VerificationGate(z3_module=None).check(original, constitution)

    assert result.contradiction is True


def test_z3_verification_gate_warns_when_rule_has_no_keywords() -> None:
    rule = Rule(id="RULE-001", text="block secrets", severity=Severity.CRITICAL, keywords=[])

    result = Z3VerificationGate(z3_module=object()).check(rule, _constitution_with_rules(rule))

    assert result.satisfiable is True
    assert result.contradiction is False
    assert result.warnings == ("rule has no keywords; SMT verification skipped",)
