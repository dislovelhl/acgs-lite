"""Regression tests for the split constitution package layout.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from acgs_lite import ConstitutionBuilder
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution import core as core_facade
from acgs_lite.constitution.constitution import Constitution as SplitConstitution
from acgs_lite.constitution.rule import Rule as SplitRule


def test_core_facade_reexports_split_types() -> None:
    assert core_facade.Constitution is SplitConstitution
    assert core_facade.Rule is SplitRule
    assert core_facade.Severity is Severity


def test_root_package_reexports_split_builder_stack() -> None:
    constitution = (
        ConstitutionBuilder("split-check")
        .add_rule("R-001", "No disclosure", severity="critical", keywords=["secret"])
        .build()
    )

    assert isinstance(constitution, SplitConstitution)
    assert constitution.rules[0].severity is Severity.CRITICAL


def test_rule_match_detail_works_via_split_rule_module() -> None:
    rule = Rule(
        id="R-DETAIL",
        text="No secret disclosure",
        severity=Severity.CRITICAL,
        keywords=["secret"],
        category="security",
        workflow_action="block",
    )

    detail = rule.match_detail("bypass secret token")

    assert detail["matched"] is True
    assert detail["rule_id"] == "R-DETAIL"
    assert detail["trigger_type"] == "keyword"
    assert detail["workflow_action"] == "block"


def test_constitution_yaml_roundtrip_preserves_split_exports() -> None:
    original = Constitution.from_rules(
        [
            Rule(
                id="R-YAML",
                text="Keep audit trail",
                severity=Severity.HIGH,
                keywords=["audit"],
            )
        ],
        name="yaml-split",
    )

    reconstructed = Constitution.from_yaml_str(original.to_yaml())

    assert isinstance(reconstructed, SplitConstitution)
    assert reconstructed.hash == original.hash
    assert reconstructed.rules[0].id == "R-YAML"
