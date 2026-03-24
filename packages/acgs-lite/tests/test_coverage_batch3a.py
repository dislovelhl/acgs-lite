"""Batch 3a coverage tests for under-covered constitution modules.

Targets:
  - merging.py
  - conflict_resolution.py
  - permission_ceiling.py
  - analytics.py
  - filtering.py
  - interpolation.py
  - policy_export.py
  - feature_flag.py
  - graduated_enforcement.py
  - memoization.py
  - deduplication.py
  - quorum.py
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.core import Constitution, Rule, Severity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rule(
    rid: str,
    text: str = "test rule",
    severity: Severity = Severity.HIGH,
    keywords: list[str] | None = None,
    **kwargs,
) -> Rule:
    return Rule(
        id=rid,
        text=text,
        severity=severity,
        keywords=keywords or ["test"],
        **kwargs,
    )


def _const(rules: list[Rule], name: str = "test") -> Constitution:
    return Constitution.from_rules(rules, name=name)


# ===========================================================================
# merging.py
# ===========================================================================


class TestInherit:
    def test_child_wins_override(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1", text="parent", severity=Severity.LOW)])
        child = _const([_rule("R1", text="child", severity=Severity.HIGH)])

        result = inherit(parent, child)
        assert len(result.rules) == 1
        assert result.rules[0].text == "child"

    def test_parent_wins_override(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1", text="parent", severity=Severity.CRITICAL)])
        child = _const([_rule("R1", text="child", severity=Severity.LOW)])

        result = inherit(parent, child, override_strategy="parent_wins")
        assert result.rules[0].text == "parent"

    def test_higher_severity_override_picks_child(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1", severity=Severity.LOW)])
        child = _const([_rule("R1", severity=Severity.CRITICAL)])

        result = inherit(parent, child, override_strategy="higher_severity")
        assert result.rules[0].severity == Severity.CRITICAL

    def test_higher_severity_override_picks_parent(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1", severity=Severity.CRITICAL)])
        child = _const([_rule("R1", severity=Severity.LOW)])

        result = inherit(parent, child, override_strategy="higher_severity")
        assert result.rules[0].severity == Severity.CRITICAL

    def test_unknown_strategy_defaults_to_child(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1", text="parent")])
        child = _const([_rule("R1", text="child")])

        result = inherit(parent, child, override_strategy="unknown")
        assert result.rules[0].text == "child"

    def test_child_only_rules_appended(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1")])
        child = _const([_rule("R2")])

        result = inherit(parent, child)
        ids = [r.id for r in result.rules]
        assert "R1" in ids
        assert "R2" in ids

    def test_metadata_inherited(self):
        from acgs_lite.constitution.merging import inherit

        parent = _const([_rule("R1")])
        child = _const([_rule("R2")])

        result = inherit(parent, child)
        assert result.metadata["_inherited_from"] == parent.name
        assert result.metadata["_override_strategy"] == "child_wins"


class TestMergeConstitutions:
    def test_union_strategy_keeps_higher_severity(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1", severity=Severity.LOW)])
        c2 = _const([_rule("R1", severity=Severity.HIGH)])

        result = merge_constitutions(c1, c2, strategy="union")
        assert result.rules[0].severity == Severity.HIGH

    def test_replace_strategy(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1", text="old")])
        c2 = _const([_rule("R1", text="new")])

        result = merge_constitutions(c1, c2, strategy="replace")
        assert result.rules[0].text == "new"

    def test_strict_strategy_raises_on_conflict(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1", text="a")])
        c2 = _const([_rule("R1", text="b")])

        with pytest.raises(ValueError, match="Conflicting rule"):
            merge_constitutions(c1, c2, strategy="strict")

    def test_strict_strategy_allows_identical(self):
        from acgs_lite.constitution.merging import merge_constitutions

        r = _rule("R1", text="same", severity=Severity.HIGH, keywords=["test"])
        c1 = _const([r])
        c2 = _const([r])

        result = merge_constitutions(c1, c2, strategy="strict")
        assert len(result.rules) == 1

    def test_conservative_strategy_excludes_other_only_rules(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1")])
        c2 = _const([_rule("R2")])

        result = merge_constitutions(c1, c2, strategy="conservative")
        ids = [r.id for r in result.rules]
        assert "R1" in ids
        assert "R2" not in ids

    def test_union_includes_other_only_rules(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1")])
        c2 = _const([_rule("R2")])

        result = merge_constitutions(c1, c2, strategy="union")
        ids = [r.id for r in result.rules]
        assert "R1" in ids
        assert "R2" in ids

    def test_merged_name_and_version(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = Constitution(name="alpha", version="1.0.0", rules=[_rule("R1")])
        c2 = Constitution(name="beta", version="2.0.0", rules=[_rule("R2")])

        result = merge_constitutions(c1, c2)
        assert "alpha" in result.name
        assert "beta" in result.name
        assert result.version == "2.0.0"

    def test_unknown_strategy_keeps_self(self):
        from acgs_lite.constitution.merging import merge_constitutions

        c1 = _const([_rule("R1", text="self")])
        c2 = _const([_rule("R1", text="other")])

        result = merge_constitutions(c1, c2, strategy="whatever")
        assert result.rules[0].text == "self"


class TestApplyAmendments:
    def test_empty_amendments(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1")])
        result = apply_amendments(c, [])
        assert len(result.rules) == 1

    def test_add_rule_dict(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1")])
        amendment = {
            "amendment_type": "add_rule",
            "changes": {
                "rule": {"id": "R2", "text": "new rule", "keywords": ["new"]},
            },
            "title": "Add R2",
        }
        result = apply_amendments(c, [amendment])
        ids = [r.id for r in result.rules]
        assert "R2" in ids

    def test_add_rule_object(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1")])
        new_rule = _rule("R3", text="object rule")
        amendment = {
            "amendment_type": "add_rule",
            "changes": {"rule": new_rule},
            "title": "Add R3",
        }
        result = apply_amendments(c, [amendment])
        assert any(r.id == "R3" for r in result.rules)

    def test_add_rule_invalid_type(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1")])
        amendment = {
            "amendment_type": "add_rule",
            "changes": {"rule": "invalid"},
            "title": "Bad",
        }
        with pytest.raises(TypeError):
            apply_amendments(c, [amendment])

    def test_remove_rule(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1"), _rule("R2")])
        amendment = {
            "amendment_type": "remove_rule",
            "changes": {"rule_id": "R1"},
            "title": "Remove R1",
        }
        result = apply_amendments(c, [amendment])
        ids = [r.id for r in result.rules]
        assert "R1" not in ids
        assert "R2" in ids

    def test_modify_rule(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1", severity=Severity.LOW)])
        amendment = {
            "amendment_type": "modify_rule",
            "changes": {"rule_id": "R1", "severity": "critical"},
            "title": "Escalate R1",
        }
        result = apply_amendments(c, [amendment])
        r1 = next(r for r in result.rules if r.id == "R1")
        assert r1.severity == Severity.CRITICAL

    def test_modify_severity(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1", severity=Severity.LOW)])
        amendment = {
            "amendment_type": "modify_severity",
            "changes": {"rule_id": "R1", "severity": "high"},
            "title": "bump",
        }
        result = apply_amendments(c, [amendment])
        r1 = next(r for r in result.rules if r.id == "R1")
        assert r1.severity == Severity.HIGH

    def test_modify_workflow(self):
        from acgs_lite.constitution.merging import apply_amendments

        c = _const([_rule("R1", workflow_action="warn")])
        amendment = {
            "amendment_type": "modify_workflow",
            "changes": {"rule_id": "R1", "workflow_action": "block"},
            "title": "Upgrade",
        }
        result = apply_amendments(c, [amendment])
        r1 = next(r for r in result.rules if r.id == "R1")
        assert r1.workflow_action == "block"

    def test_object_amendment(self):
        """Amendment passed as an object with attributes instead of dict."""
        from acgs_lite.constitution.merging import apply_amendments

        class FakeAmendment:
            amendment_type = "remove_rule"
            changes = {"rule_id": "R1"}
            title = "Remove R1"
            description = ""

        c = _const([_rule("R1"), _rule("R2")])
        result = apply_amendments(c, [FakeAmendment()])
        assert not any(r.id == "R1" for r in result.rules)


# ===========================================================================
# conflict_resolution.py
# ===========================================================================


class TestResolveConflicts:
    def test_severity_precedence(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([
            _rule("R1", severity=Severity.CRITICAL),
            _rule("R2", severity=Severity.LOW),
        ])
        conflicts = [{"rule_a": "R1", "rule_b": "R2"}]
        result = resolve_conflicts(c, conflicts)
        assert len(result["resolutions"]) == 1
        assert result["resolutions"][0]["winner"] == "R1"
        assert result["resolutions"][0]["reason"] == "severity_precedence"

    def test_specificity_precedence(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([
            _rule("R1", keywords=["a", "b", "c"]),
            _rule("R2", keywords=["a"]),
        ])
        conflicts = [{"rule_a": "R1", "rule_b": "R2"}]
        result = resolve_conflicts(c, conflicts)
        assert result["resolutions"][0]["winner"] == "R1"
        assert result["resolutions"][0]["reason"] == "specificity"

    def test_hardcoded_precedence(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([
            _rule("R1", keywords=["a"], hardcoded=True),
            _rule("R2", keywords=["a"], hardcoded=False),
        ])
        conflicts = [{"rule_a": "R1", "rule_b": "R2"}]
        result = resolve_conflicts(c, conflicts)
        assert result["resolutions"][0]["winner"] == "R1"
        assert result["resolutions"][0]["reason"] == "hardcoded_precedence"

    def test_unresolved_when_equal(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([
            _rule("R1", keywords=["a"]),
            _rule("R2", keywords=["b"]),
        ])
        conflicts = [{"rule_a": "R1", "rule_b": "R2"}]
        result = resolve_conflicts(c, conflicts)
        assert len(result["unresolved"]) == 1

    def test_missing_rule_goes_to_unresolved(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([_rule("R1")])
        conflicts = [{"rule_a": "R1", "rule_b": "MISSING"}]
        result = resolve_conflicts(c, conflicts)
        assert len(result["unresolved"]) == 1

    def test_empty_conflicts_list(self):
        from acgs_lite.constitution.conflict_resolution import resolve_conflicts

        c = _const([_rule("R1")])
        result = resolve_conflicts(c, [])
        assert result["resolutions"] == []
        assert result["unresolved"] == []


class TestDetectSemanticConflicts:
    def test_fewer_than_two_embedded_rules(self):
        from acgs_lite.constitution.conflict_resolution import detect_semantic_conflicts

        c = _const([_rule("R1")])
        result = detect_semantic_conflicts(c)
        assert result["has_conflicts"] is False
        assert result["rules_with_embeddings"] == 0

    def test_no_conflicts_same_severity(self):
        from acgs_lite.constitution.conflict_resolution import detect_semantic_conflicts

        emb = [1.0, 0.0, 0.0]
        c = _const([
            _rule("R1", embedding=emb, severity=Severity.HIGH),
            _rule("R2", embedding=emb, severity=Severity.HIGH),
        ])
        result = detect_semantic_conflicts(c)
        assert result["has_conflicts"] is False

    def test_detects_severity_conflict(self):
        from acgs_lite.constitution.conflict_resolution import detect_semantic_conflicts

        emb = [1.0, 0.0, 0.0]
        c = _const([
            _rule("R1", embedding=emb, severity=Severity.HIGH),
            _rule("R2", embedding=emb, severity=Severity.LOW),
        ])
        result = detect_semantic_conflicts(c)
        assert result["has_conflicts"] is True
        assert result["conflict_count"] == 1

    def test_detects_workflow_conflict(self):
        from acgs_lite.constitution.conflict_resolution import detect_semantic_conflicts

        emb = [1.0, 0.0, 0.0]
        c = _const([
            _rule("R1", embedding=emb, workflow_action="block"),
            _rule("R2", embedding=emb, workflow_action="warn"),
        ])
        result = detect_semantic_conflicts(c)
        assert result["has_conflicts"] is True


# ===========================================================================
# permission_ceiling.py
# ===========================================================================


class TestGetPermissionCeiling:
    def test_strict_ceiling(self):
        from acgs_lite.constitution.permission_ceiling import get_permission_ceiling

        c = Constitution(name="t", rules=[_rule("R1")], permission_ceiling="strict")
        result = get_permission_ceiling(c)
        assert result["ceiling"] == "strict"
        assert result["allow_override_critical"] is False

    def test_permissive_ceiling(self):
        from acgs_lite.constitution.permission_ceiling import get_permission_ceiling

        c = Constitution(name="t", rules=[_rule("R1")], permission_ceiling="permissive")
        result = get_permission_ceiling(c)
        assert result["ceiling"] == "permissive"
        assert result["allow_override_critical"] is True
        assert result["require_human_above_severity"] == "low"

    def test_standard_ceiling_default(self):
        from acgs_lite.constitution.permission_ceiling import get_permission_ceiling

        c = Constitution(name="t", rules=[_rule("R1")], permission_ceiling="standard")
        result = get_permission_ceiling(c)
        assert result["ceiling"] == "standard"

    def test_unknown_ceiling_defaults_to_standard(self):
        from acgs_lite.constitution.permission_ceiling import get_permission_ceiling

        c = Constitution(name="t", rules=[_rule("R1")], permission_ceiling="foobar")
        result = get_permission_ceiling(c)
        assert result["ceiling"] == "standard"

    def test_none_ceiling_defaults_to_standard(self):
        from acgs_lite.constitution.permission_ceiling import get_permission_ceiling

        c = Constitution(name="t", rules=[_rule("R1")])
        result = get_permission_ceiling(c)
        assert result["ceiling"] == "standard"


class TestRuleRegulatoryClauseMap:
    def test_tag_based_mapping(self):
        from acgs_lite.constitution.permission_ceiling import rule_regulatory_clause_map

        c = _const([_rule("R1", tags=["gdpr"])])
        result = rule_regulatory_clause_map(c)
        assert "R1" in result["by_rule"]
        assert any("GDPR" in clause for clause in result["by_rule"]["R1"])

    def test_metadata_based_clauses(self):
        from acgs_lite.constitution.permission_ceiling import rule_regulatory_clause_map

        c = _const([_rule("R1", metadata={"regulatory_clauses": ["Custom Clause 1"]})])
        result = rule_regulatory_clause_map(c)
        assert "Custom Clause 1" in result["by_rule"]["R1"]

    def test_no_clauses(self):
        from acgs_lite.constitution.permission_ceiling import rule_regulatory_clause_map

        c = _const([_rule("R1")])
        result = rule_regulatory_clause_map(c)
        assert "R1" not in result["by_rule"]

    def test_by_tag_always_populated(self):
        from acgs_lite.constitution.permission_ceiling import rule_regulatory_clause_map

        c = _const([_rule("R1")])
        result = rule_regulatory_clause_map(c)
        assert "gdpr" in result["by_tag"]
        assert "sox" in result["by_tag"]


# ===========================================================================
# analytics.py
# ===========================================================================


class TestClassifyActionIntent:
    def test_negative_verb_detected(self):
        from acgs_lite.constitution.analytics import classify_action_intent

        result = classify_action_intent("bypass all security checks")
        assert result["intent"] == "potentially_harmful"
        assert result["has_negative_verb"] is True
        assert result["confidence"] == 0.85

    def test_positive_verb_detected(self):
        from acgs_lite.constitution.analytics import classify_action_intent

        result = classify_action_intent("run security audit")
        assert result["intent"] == "constructive"
        assert result["has_positive_verb"] is True
        assert result["confidence"] == 0.8

    def test_neutral_action(self):
        from acgs_lite.constitution.analytics import classify_action_intent

        result = classify_action_intent("something neutral")
        assert result["intent"] == "neutral"
        assert result["confidence"] == 0.5

    def test_negative_overrides_positive(self):
        from acgs_lite.constitution.analytics import classify_action_intent

        result = classify_action_intent("run bypass of validation")
        assert result["intent"] == "potentially_harmful"


class TestScoreContextRisk:
    def test_empty_context(self):
        from acgs_lite.constitution.analytics import score_context_risk

        result = score_context_risk({})
        assert result["risk_score"] == 0.0
        assert result["handling_tier"] == "standard"

    def test_production_context(self):
        from acgs_lite.constitution.analytics import score_context_risk

        result = score_context_risk({"env": "production"})
        assert result["risk_score"] >= 0.7
        assert result["handling_tier"] == "maximum"
        assert "production_environment" in result["signals"]

    def test_test_context(self):
        from acgs_lite.constitution.analytics import score_context_risk

        result = score_context_risk({"env": "test"})
        assert result["risk_score"] <= 0.4
        assert result["handling_tier"] == "relaxed"

    def test_staging_context(self):
        from acgs_lite.constitution.analytics import score_context_risk

        result = score_context_risk({"env": "staging"})
        assert result["handling_tier"] == "elevated"

    def test_financial_data(self):
        from acgs_lite.constitution.analytics import score_context_risk

        result = score_context_risk({"data_type": "payment"})
        assert "financial_data" in result["signals"]


class TestGovernanceDecisionReport:
    def test_no_rules_allows(self):
        from acgs_lite.constitution.analytics import governance_decision_report

        result = governance_decision_report("do something")
        assert result["decision_hint"] == "allow"
        assert result["triggered_rules"] == []
        assert result["max_severity"] is None

    def test_with_matching_rule_deny(self):
        from acgs_lite.constitution.analytics import governance_decision_report

        r = _rule("R1", keywords=["bypass"], severity=Severity.CRITICAL)
        result = governance_decision_report("bypass security", rules=[r])
        assert result["decision_hint"] == "deny"
        assert result["max_severity"] == "critical"

    def test_escalate_on_medium(self):
        from acgs_lite.constitution.analytics import governance_decision_report

        r = _rule("R1", keywords=["data"], severity=Severity.MEDIUM)
        result = governance_decision_report("access data", rules=[r])
        assert result["decision_hint"] == "escalate"

    def test_context_risk_included(self):
        from acgs_lite.constitution.analytics import governance_decision_report

        result = governance_decision_report("x", context={"env": "production"})
        assert result["context_risk"]["risk_score"] > 0


# ===========================================================================
# filtering.py
# ===========================================================================


class TestFilter:
    def test_filter_by_severity(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", severity=Severity.HIGH),
            _rule("R2", severity=Severity.LOW),
        ])
        result = filter(c, severity="high")
        assert len(result.rules) == 1
        assert result.rules[0].id == "R1"

    def test_filter_by_min_severity(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", severity=Severity.CRITICAL),
            _rule("R2", severity=Severity.LOW),
            _rule("R3", severity=Severity.HIGH),
        ])
        result = filter(c, min_severity="high")
        ids = [r.id for r in result.rules]
        assert "R1" in ids
        assert "R3" in ids
        assert "R2" not in ids

    def test_filter_by_category(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", category="safety"),
            _rule("R2", category="privacy"),
        ])
        result = filter(c, category="safety")
        assert len(result.rules) == 1

    def test_filter_by_tag(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", tags=["gdpr"]),
            _rule("R2", tags=["sox"]),
        ])
        result = filter(c, tag="gdpr")
        assert len(result.rules) == 1
        assert result.rules[0].id == "R1"

    def test_filter_by_workflow_action(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", workflow_action="block"),
            _rule("R2", workflow_action="warn"),
        ])
        result = filter(c, workflow_action="block")
        assert len(result.rules) == 1

    def test_filter_enabled_only(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([
            _rule("R1", enabled=True),
            _rule("R2", enabled=False),
        ])
        result = filter(c, enabled_only=True)
        assert len(result.rules) == 1

    def test_filter_empty_raises(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([_rule("R1", severity=Severity.LOW)])
        with pytest.raises(ValueError, match="empty constitution"):
            filter(c, severity="critical")

    def test_filter_metadata_marked(self):
        from acgs_lite.constitution.filtering import filter

        c = _const([_rule("R1")])
        result = filter(c)
        assert result.metadata.get("filtered") is True


# ===========================================================================
# interpolation.py
# ===========================================================================


class TestInterpolation:
    def test_render_text_basic(self):
        from acgs_lite.constitution.interpolation import render_text

        result = render_text("Agent ${agent.id} denied", {"agent": {"id": "alpha"}})
        assert result == "Agent alpha denied"

    def test_render_text_unresolved_preserved(self):
        from acgs_lite.constitution.interpolation import render_text

        result = render_text("Agent ${agent.id} denied", {})
        assert result == "Agent ${agent.id} denied"

    def test_render_text_no_placeholders(self):
        from acgs_lite.constitution.interpolation import render_text

        result = render_text("plain text", {"agent": {"id": "x"}})
        assert result == "plain text"

    def test_render_text_empty_context(self):
        from acgs_lite.constitution.interpolation import render_text

        result = render_text("${foo}", {})
        assert result == "${foo}"

    def test_extract_placeholders(self):
        from acgs_lite.constitution.interpolation import extract_placeholders

        paths = extract_placeholders("${agent.id} and ${resource.type}")
        assert paths == ["agent.id", "resource.type"]

    def test_extract_no_placeholders(self):
        from acgs_lite.constitution.interpolation import extract_placeholders

        assert extract_placeholders("no placeholders") == []

    def test_render_rule_with_placeholder(self):
        from acgs_lite.constitution.interpolation import render_rule

        r = _rule("R1", text="Agent ${agent.id} restricted")
        rendered = render_rule(r, {"agent": {"id": "bot-1"}})
        assert rendered.text == "Agent bot-1 restricted"
        assert rendered.id == "R1"

    def test_render_rule_no_change_returns_same(self):
        from acgs_lite.constitution.interpolation import render_rule

        r = _rule("R1", text="plain rule")
        rendered = render_rule(r, {"agent": {"id": "x"}})
        assert rendered is r

    def test_render_rule_empty_context_returns_same(self):
        from acgs_lite.constitution.interpolation import render_rule

        r = _rule("R1", text="Agent ${x}")
        rendered = render_rule(r, {})
        assert rendered is r

    def test_render_constitution(self):
        from acgs_lite.constitution.interpolation import render_constitution

        c = _const([_rule("R1", text="Hello ${name}")])
        rendered = render_constitution(c, {"name": "world"})
        assert rendered.rules[0].text == "Hello world"

    def test_render_constitution_no_change(self):
        from acgs_lite.constitution.interpolation import render_constitution

        c = _const([_rule("R1", text="plain")])
        rendered = render_constitution(c, {"name": "world"})
        assert rendered is c

    def test_render_constitution_empty_context(self):
        from acgs_lite.constitution.interpolation import render_constitution

        c = _const([_rule("R1", text="${x}")])
        rendered = render_constitution(c, {})
        assert rendered is c

    def test_context_coverage(self):
        from acgs_lite.constitution.interpolation import context_coverage

        rules = [
            _rule("R1", text="Agent ${agent.id}"),
            _rule("R2", text="plain rule"),
        ]
        result = context_coverage(rules)
        assert "R1" in result
        assert result["R1"] == ["agent.id"]
        assert "R2" not in result

    def test_validate_context_schema_complete(self):
        from acgs_lite.constitution.interpolation import validate_context_schema

        rules = [_rule("R1", text="Agent ${agent.id}")]
        result = validate_context_schema(rules, {"agent": {"id": "x"}})
        assert result["complete"] is True
        assert result["coverage_pct"] == 100.0

    def test_validate_context_schema_incomplete(self):
        from acgs_lite.constitution.interpolation import validate_context_schema

        rules = [_rule("R1", text="Agent ${agent.id}")]
        result = validate_context_schema(rules, {})
        assert result["complete"] is False
        assert len(result["unresolved"]) == 1

    def test_validate_context_schema_no_placeholders(self):
        from acgs_lite.constitution.interpolation import validate_context_schema

        rules = [_rule("R1", text="plain")]
        result = validate_context_schema(rules, {})
        assert result["complete"] is True
        assert result["coverage_pct"] == 100.0

    def test_nested_path_resolution(self):
        from acgs_lite.constitution.interpolation import render_text

        result = render_text(
            "${a.b.c}",
            {"a": {"b": {"c": "deep"}}},
        )
        assert result == "deep"


# ===========================================================================
# policy_export.py
# ===========================================================================


class TestPolicyExporter:
    def test_to_json(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1", text="test rule")])
        exporter = PolicyExporter(c)
        data = json.loads(exporter.to_json())
        assert data["rule_count"] == 1
        assert data["rules"][0]["id"] == "R1"

    def test_to_csv(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1", keywords=["a", "b"])])
        exporter = PolicyExporter(c)
        csv_str = exporter.to_csv()
        assert "id" in csv_str
        assert "R1" in csv_str
        assert "a|b" in csv_str

    def test_to_markdown(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1", text="md rule")])
        exporter = PolicyExporter(c)
        md = exporter.to_markdown()
        assert "| R1 |" in md
        assert "md rule" in md

    def test_to_text_summary(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        txt = exporter.to_text_summary()
        assert "Constitution:" in txt
        assert "R1" in txt

    def test_to_yaml(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        yaml_str = exporter.to_yaml()
        assert "R1" in yaml_str

    def test_export_file(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            exporter.export_file(path, fmt="json")
            with open(path) as fh:
                data = json.load(fh)
            assert data["rule_count"] == 1
        finally:
            os.unlink(path)

    def test_export_file_unsupported_format(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        with pytest.raises(ValueError, match="Unsupported format"):
            exporter.export_file("/tmp/x", fmt="pdf")

    def test_export_all(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        with tempfile.TemporaryDirectory() as tmpdir:
            written = exporter.export_all(tmpdir)
            assert len(written) == 5
            for _fmt, path in written.items():
                assert os.path.isfile(path)

    def test_csv_custom_delimiter(self):
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _const([_rule("R1")])
        exporter = PolicyExporter(c)
        csv_str = exporter.to_csv(delimiter="\t")
        assert "\t" in csv_str


# ===========================================================================
# feature_flag.py
# ===========================================================================


class TestFlagManager:
    def test_create_and_get_flag(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        flag = mgr.create_flag("F1", description="test", rollout_pct=50)
        assert flag.flag_id == "F1"
        assert mgr.get_flag("F1") is not None

    def test_is_enabled_100pct(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=100)
        assert mgr.is_enabled("F1", actor="anyone") is True

    def test_is_enabled_0pct(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=0)
        assert mgr.is_enabled("F1", actor="anyone") is False

    def test_nonexistent_flag_disabled(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.is_enabled("nope") is False

    def test_deny_actor(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=100, deny_actors=["blocked"])
        assert mgr.is_enabled("F1", actor="blocked") is False
        assert mgr.is_enabled("F1", actor="allowed") is True

    def test_allow_actor_only(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=100, allow_actors=["vip"])
        assert mgr.is_enabled("F1", actor="vip") is True
        assert mgr.is_enabled("F1", actor="other") is False

    def test_kill_switch(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.is_enabled("F1") is True
        mgr.kill("F1", reason="regression")
        assert mgr.is_enabled("F1") is False

    def test_kill_already_killed(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.kill("F1")
        assert mgr.kill("F1") is False

    def test_kill_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.kill("nope") is False

    def test_revive(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.kill("F1")
        assert mgr.revive("F1") is True
        assert mgr.is_enabled("F1") is True

    def test_revive_not_killed(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.revive("F1") is False

    def test_revive_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.revive("nope") is False

    def test_archive(self):
        from acgs_lite.constitution.feature_flag import FlagManager, FlagStatus

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.archive("F1") is True
        assert mgr.is_enabled("F1") is False
        flags = mgr.list_flags(status=FlagStatus.ARCHIVED)
        assert len(flags) == 1

    def test_archive_already_archived(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.archive("F1")
        assert mgr.archive("F1") is False

    def test_archive_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.archive("nope") is False

    def test_set_rollout(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=0)
        assert mgr.set_rollout("F1", 100) is True
        assert mgr.is_enabled("F1") is True

    def test_set_rollout_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.set_rollout("nope", 50) is False

    def test_set_rollout_clamps(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.set_rollout("F1", 200)
        flag = mgr.get_flag("F1")
        assert flag.rollout_pct == 100

    def test_add_allow_actor(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", allow_actors=["a"])
        assert mgr.add_allow_actor("F1", "b") is True
        assert mgr.is_enabled("F1", actor="b") is True

    def test_add_allow_actor_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.add_allow_actor("nope", "a") is False

    def test_add_deny_actor(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.add_deny_actor("F1", "bad") is True
        assert mgr.is_enabled("F1", actor="bad") is False

    def test_add_deny_actor_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.add_deny_actor("nope", "a") is False

    def test_remove_allow_actor(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", allow_actors=["a", "b"])
        assert mgr.remove_allow_actor("F1", "a") is True

    def test_remove_allow_actor_not_present(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.remove_allow_actor("F1", "x") is False

    def test_remove_allow_actor_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.remove_allow_actor("nope", "a") is False

    def test_remove_deny_actor(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", deny_actors=["bad"])
        assert mgr.remove_deny_actor("F1", "bad") is True

    def test_remove_deny_actor_not_present(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        assert mgr.remove_deny_actor("F1", "x") is False

    def test_remove_deny_actor_nonexistent(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        assert mgr.remove_deny_actor("nope", "a") is False

    def test_changelog(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.kill("F1")
        log = mgr.changelog(flag_id="F1")
        assert len(log) == 2
        assert log[0].change_type == "created"
        assert log[1].change_type == "killed"

    def test_changelog_all(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.create_flag("F2")
        assert len(mgr.changelog()) == 2

    def test_list_flags_all(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.create_flag("F2")
        assert len(mgr.list_flags()) == 2

    def test_list_flags_by_status(self):
        from acgs_lite.constitution.feature_flag import FlagManager, FlagStatus

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.create_flag("F2")
        mgr.kill("F2")
        active = mgr.list_flags(status=FlagStatus.ACTIVE)
        assert len(active) == 1

    def test_summary(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1")
        mgr.create_flag("F2")
        mgr.kill("F2")
        s = mgr.summary()
        assert s["total_flags"] == 2
        assert s["by_status"]["active"] == 1
        assert s["by_status"]["killed"] == 1

    def test_rollout_deterministic(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        mgr.create_flag("F1", rollout_pct=50)
        result1 = mgr.is_enabled("F1", actor="test-actor")
        result2 = mgr.is_enabled("F1", actor="test-actor")
        assert result1 == result2  # deterministic

    def test_create_flag_clamps_rollout(self):
        from acgs_lite.constitution.feature_flag import FlagManager

        mgr = FlagManager()
        flag = mgr.create_flag("F1", rollout_pct=-10)
        assert flag.rollout_pct == 0
        flag2 = mgr.create_flag("F2", rollout_pct=200)
        assert flag2.rollout_pct == 100


# ===========================================================================
# graduated_enforcement.py
# ===========================================================================


class TestGraduatedEnforcer:
    def test_evaluate_no_policy_allows(self):
        from acgs_lite.constitution.graduated_enforcement import EnforcementLevel, GraduatedEnforcer

        ge = GraduatedEnforcer()
        assert ge.evaluate("R1") == EnforcementLevel.ALLOW

    def test_evaluate_warn_threshold_zero(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=0, block_threshold=5))
        assert ge.evaluate("R1") == EnforcementLevel.WARN

    def test_escalation_to_block(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=0, block_threshold=3))
        for _ in range(3):
            ge.record_violation("R1", actor="bot")
        assert ge.evaluate("R1", actor="bot") == EnforcementLevel.BLOCK

    def test_throttle_level(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(
            warn_threshold=1,
            throttle_threshold=3,
            block_threshold=5,
        ))
        for _ in range(3):
            ge.record_violation("R1", actor="bot")
        assert ge.evaluate("R1", actor="bot") == EnforcementLevel.THROTTLE

    def test_cooldown_resets(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(
            warn_threshold=0, block_threshold=3, cooldown_seconds=10, auto_reset=True,
        ))
        base = 1000.0
        for i in range(2):
            ge.record_violation("R1", actor="bot", now=base + i)
        assert ge.evaluate("R1", actor="bot", now=base + 2) == EnforcementLevel.WARN

        # After cooldown, should reset
        assert ge.evaluate("R1", actor="bot", now=base + 100) == EnforcementLevel.WARN

    def test_manual_override(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy())
        ge.override_level("R1", "bot", EnforcementLevel.BLOCK, reason="admin decision")
        assert ge.evaluate("R1", actor="bot") == EnforcementLevel.BLOCK

    def test_clear_override(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=0, block_threshold=5))
        ge.override_level("R1", "bot", EnforcementLevel.BLOCK)
        assert ge.clear_override("R1", "bot") is True
        level = ge.evaluate("R1", actor="bot")
        assert level != EnforcementLevel.BLOCK

    def test_clear_override_no_record(self):
        from acgs_lite.constitution.graduated_enforcement import GraduatedEnforcer

        ge = GraduatedEnforcer()
        assert ge.clear_override("R1", "bot") is False

    def test_clear_override_not_overridden(self):
        from acgs_lite.constitution.graduated_enforcement import GraduatedEnforcer

        ge = GraduatedEnforcer()
        ge.record_violation("R1", actor="bot")
        assert ge.clear_override("R1", "bot") is False

    def test_reset_violations(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EnforcementLevel,
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=0, block_threshold=2))
        ge.record_violation("R1", actor="bot")
        ge.record_violation("R1", actor="bot")
        assert ge.reset_violations("R1", "bot") is True
        # After reset, current_level is ALLOW (count=0, record exists but reset)
        assert ge.evaluate("R1", actor="bot") == EnforcementLevel.ALLOW

    def test_reset_violations_no_record(self):
        from acgs_lite.constitution.graduated_enforcement import GraduatedEnforcer

        ge = GraduatedEnforcer()
        assert ge.reset_violations("R1", "bot") is False

    def test_get_record(self):
        from acgs_lite.constitution.graduated_enforcement import GraduatedEnforcer

        ge = GraduatedEnforcer()
        ge.record_violation("R1", actor="bot")
        rec = ge.get_record("R1", "bot")
        assert rec is not None
        assert rec.count == 1

    def test_get_record_none(self):
        from acgs_lite.constitution.graduated_enforcement import GraduatedEnforcer

        ge = GraduatedEnforcer()
        assert ge.get_record("R1", "bot") is None

    def test_escalation_log(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=1, block_threshold=3))
        ge.record_violation("R1", actor="bot")
        log = ge.escalation_log(rule_id="R1")
        assert len(log) >= 1

    def test_escalation_log_all(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=1, block_threshold=3))
        ge.record_violation("R1", actor="bot")
        assert len(ge.escalation_log()) >= 1

    def test_remove_policy(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy())
        assert ge.remove_policy("R1") is True
        assert ge.remove_policy("R1") is False
        assert ge.get_policy("R1") is None

    def test_summary(self):
        from acgs_lite.constitution.graduated_enforcement import (
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy())
        ge.record_violation("R1", actor="bot")
        s = ge.summary()
        assert s["total_tracked_pairs"] >= 1
        assert s["policies_configured"] == 1

    def test_cooldown_on_record_violation(self):
        """Cooldown resets count inside record_violation too."""
        from acgs_lite.constitution.graduated_enforcement import (
            EscalationPolicy,
            GraduatedEnforcer,
        )

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(
            warn_threshold=0, block_threshold=3, cooldown_seconds=10, auto_reset=True,
        ))
        base = 1000.0
        ge.record_violation("R1", actor="bot", now=base)
        ge.record_violation("R1", actor="bot", now=base + 1)
        # After cooldown, recording a new violation should reset count
        rec = ge.record_violation("R1", actor="bot", now=base + 100)
        assert rec.count == 1  # reset to 0, then +1


# ===========================================================================
# memoization.py
# ===========================================================================


class TestLRUCache:
    def test_basic_get_put(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=2)
        cache.put("a", 1)
        found, val = cache.get("a")
        assert found is True
        assert val == 1

    def test_cache_miss(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=2)
        found, val = cache.get("missing")
        assert found is False

    def test_eviction(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # evicts "a"
        found, _ = cache.get("a")
        assert found is False

    def test_lru_promotion(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # promote "a"
        cache.put("c", 3)  # evicts "b" (not "a")
        found_a, _ = cache.get("a")
        found_b, _ = cache.get("b")
        assert found_a is True
        assert found_b is False

    def test_maxsize_validation(self):
        from acgs_lite.constitution.memoization import _LRUCache

        with pytest.raises(ValueError):
            _LRUCache(maxsize=0)

    def test_clear(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=5)
        cache.put("a", 1)
        cache.clear()
        assert cache.currsize == 0

    def test_stats(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=5)
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        assert cache.hits == 1
        assert cache.misses == 1

    def test_update_existing_key(self):
        from acgs_lite.constitution.memoization import _LRUCache

        cache = _LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("a", 2)
        found, val = cache.get("a")
        assert val == 2
        assert cache.currsize == 1


class TestCacheStats:
    def test_hit_rate(self):
        from acgs_lite.constitution.memoization import CacheStats

        stats = CacheStats(hits=3, misses=1, maxsize=10, currsize=1)
        assert stats.hit_rate == 0.75
        assert stats.total == 4

    def test_hit_rate_zero_total(self):
        from acgs_lite.constitution.memoization import CacheStats

        stats = CacheStats(hits=0, misses=0, maxsize=10, currsize=0)
        assert stats.hit_rate == 0.0

    def test_to_dict(self):
        from acgs_lite.constitution.memoization import CacheStats

        stats = CacheStats(hits=1, misses=1, maxsize=10, currsize=1)
        d = stats.to_dict()
        assert d["hits"] == 1
        assert "hit_rate" in d

    def test_repr(self):
        from acgs_lite.constitution.memoization import CacheStats

        stats = CacheStats(hits=1, misses=1, maxsize=10, currsize=1)
        assert "CacheStats" in repr(stats)


class TestCacheKey:
    def test_deterministic(self):
        from acgs_lite.constitution.memoization import _cache_key

        k1 = _cache_key("action", {"env": "prod"})
        k2 = _cache_key("action", {"env": "prod"})
        assert k1 == k2

    def test_case_insensitive(self):
        from acgs_lite.constitution.memoization import _cache_key

        k1 = _cache_key("Action", {})
        k2 = _cache_key("action", {})
        assert k1 == k2

    def test_different_context_different_key(self):
        from acgs_lite.constitution.memoization import _cache_key

        k1 = _cache_key("action", {"env": "prod"})
        k2 = _cache_key("action", {"env": "test"})
        assert k1 != k2


class TestMemoizedConstitution:
    def test_validate_caches(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1", keywords=["test"])])
        mc = MemoizedConstitution(c, maxsize=10)
        mc.validate("test action")
        mc.validate("test action")
        stats = mc.cache_stats()
        assert stats.hits >= 1

    def test_explain_caches(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1", keywords=["test"])])
        mc = MemoizedConstitution(c, maxsize=10)
        mc.explain("test action")
        mc.explain("test action")
        stats = mc.cache_stats()
        assert stats.hits >= 1

    def test_clear_cache(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1", keywords=["test"])])
        mc = MemoizedConstitution(c, maxsize=10)
        mc.validate("test action")
        mc.clear_cache()
        assert mc.cache_stats().currsize == 0

    def test_update_constitution(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c1 = _const([_rule("R1", keywords=["test"])])
        c2 = _const([_rule("R2", keywords=["other"])])
        mc = MemoizedConstitution(c1, maxsize=10)
        mc.validate("test action")
        mc.update_constitution(c2)
        assert mc.cache_stats().currsize == 0
        assert mc.constitution is c2

    def test_delegation(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1")])
        mc = MemoizedConstitution(c)
        assert mc.name == c.name
        assert len(mc.rules) == len(c.rules)

    def test_repr(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1")])
        mc = MemoizedConstitution(c)
        assert "MemoizedConstitution" in repr(mc)

    def test_warm(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1", keywords=["test"])])
        mc = MemoizedConstitution(c, maxsize=10)
        result = mc.warm(["test action", "other action"])
        assert result["warmed"] == 2
        assert result["already_cached"] == 0

        # Warm again
        result2 = mc.warm(["test action"])
        assert result2["already_cached"] == 1

    def test_explain_with_context(self):
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _const([_rule("R1", text="Agent ${agent.id}", keywords=["agent"])])
        mc = MemoizedConstitution(c, maxsize=10)
        result = mc.explain("agent action", context={"agent": {"id": "bot"}})
        assert isinstance(result, dict)


# ===========================================================================
# deduplication.py
# ===========================================================================


class TestJaccard:
    def test_identical_sets(self):
        from acgs_lite.constitution.deduplication import _jaccard

        assert _jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0

    def test_disjoint_sets(self):
        from acgs_lite.constitution.deduplication import _jaccard

        assert _jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_both_empty(self):
        from acgs_lite.constitution.deduplication import _jaccard

        assert _jaccard(frozenset(), frozenset()) == 1.0

    def test_partial_overlap(self):
        from acgs_lite.constitution.deduplication import _jaccard

        result = _jaccard(frozenset({"a", "b"}), frozenset({"b", "c"}))
        assert abs(result - 1 / 3) < 0.01


class TestFindDuplicates:
    def test_no_duplicates(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["alpha"]),
            _rule("R2", keywords=["beta"]),
        ])
        report = find_duplicates(c)
        assert not report.has_duplicates

    def test_exact_duplicates(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        report = find_duplicates(c)
        assert len(report.exact_groups) == 1
        assert len(report.strictly_redundant_ids) == 1

    def test_subset_redundancy(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        report = find_duplicates(c)
        assert len(report.subset_pairs) == 1
        assert report.subset_pairs[0].subset_id == "R1"
        assert report.subset_pairs[0].is_strictly_redundant is True

    def test_subset_different_severity_not_strict(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data"], severity=Severity.LOW, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        report = find_duplicates(c)
        if report.subset_pairs:
            assert report.subset_pairs[0].is_strictly_redundant is False

    def test_near_duplicates(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data", "access", "privacy", "pii", "security", "audit"]),
            _rule("R2", keywords=["data", "access", "privacy", "pii", "security", "review"]),
        ])
        report = find_duplicates(c, near_threshold=0.7)
        assert len(report.near_duplicate_pairs) >= 1

    def test_disabled_rules_excluded(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data"], enabled=False),
            _rule("R2", keywords=["data"]),
        ])
        report = find_duplicates(c)
        assert not report.has_duplicates

    def test_deprecated_rules_excluded(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data"], deprecated=True),
            _rule("R2", keywords=["data"]),
        ])
        report = find_duplicates(c)
        assert not report.has_duplicates

    def test_report_summary(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([_rule("R1", keywords=["x"])])
        report = find_duplicates(c)
        s = report.summary()
        assert "rule_count" in s
        assert "has_duplicates" in s

    def test_report_to_dict(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([_rule("R1", keywords=["x"])])
        report = find_duplicates(c)
        d = report.to_dict()
        assert "exact_groups" in d

    def test_report_render_text(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([
            _rule("R1", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        report = find_duplicates(c)
        text = report.render_text()
        assert "Duplication Report" in text

    def test_report_render_text_no_duplicates(self):
        from acgs_lite.constitution.deduplication import find_duplicates

        c = _const([_rule("R1", keywords=["x"])])
        report = find_duplicates(c)
        text = report.render_text()
        assert "No duplicates found" in text


class TestDeduplicate:
    def test_no_duplicates_returns_same(self):
        from acgs_lite.constitution.deduplication import deduplicate

        c = _const([_rule("R1", keywords=["alpha"]), _rule("R2", keywords=["beta"])])
        result, report = deduplicate(c)
        assert len(result.rules) == 2

    def test_removes_exact_duplicates(self):
        from acgs_lite.constitution.deduplication import deduplicate

        c = _const([
            _rule("R1", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        result, report = deduplicate(c)
        assert len(result.rules) == 1

    def test_keep_most_keywords_strategy(self):
        from acgs_lite.constitution.deduplication import deduplicate

        c = _const([
            _rule("R1", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        result, _ = deduplicate(c, strategy="keep_most_keywords")
        assert len(result.rules) == 1

    def test_keep_oldest_strategy(self):
        from acgs_lite.constitution.deduplication import deduplicate

        c = _const([
            _rule("R1", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
            _rule("R2", keywords=["data", "access"], severity=Severity.HIGH, category="safety"),
        ])
        result, _ = deduplicate(c, strategy="keep_oldest")
        assert len(result.rules) == 1


# ===========================================================================
# quorum.py
# ===========================================================================


class TestQuorumManager:
    def test_open_and_status(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=2)
        status = mgr.status(gid)
        assert status.state == "open"
        assert status.remaining == 2

    def test_approval_flow(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=2)
        mgr.vote(gid, voter_id="alice", approve=True)
        mgr.vote(gid, voter_id="bob", approve=True)
        status = mgr.status(gid)
        assert status.state == "approved"
        assert status.remaining == 0

    def test_veto_rejects_immediately(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=3)
        mgr.vote(gid, voter_id="alice", approve=True)
        mgr.vote(gid, voter_id="bob", approve=False)
        status = mgr.status(gid)
        assert status.state == "rejected"
        assert status.vetoes == 1

    def test_cannot_vote_on_closed_gate(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=1)
        mgr.vote(gid, voter_id="alice", approve=True)
        with pytest.raises(ValueError, match="already"):
            mgr.vote(gid, voter_id="bob", approve=True)

    def test_duplicate_vote_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=3)
        mgr.vote(gid, voter_id="alice", approve=True)
        with pytest.raises(ValueError, match="already voted"):
            mgr.vote(gid, voter_id="alice", approve=True)

    def test_ineligible_voter_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=1, eligible_voters={"alice"})
        with pytest.raises(ValueError, match="not in the eligible"):
            mgr.vote(gid, voter_id="bob", approve=True)

    def test_timeout(self):
        from acgs_lite.constitution.quorum import QuorumManager

        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=2, timeout_minutes=5, _now=now)
        expired = now + timedelta(minutes=10)
        status = mgr.status(gid, _now=expired)
        assert status.state == "timed_out"

    def test_vote_after_timeout_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=2, timeout_minutes=1, _now=now)
        expired = now + timedelta(minutes=5)
        with pytest.raises(ValueError):
            mgr.vote(gid, voter_id="alice", approve=True, _now=expired)

    def test_required_approvals_less_than_1_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        with pytest.raises(ValueError, match="1"):
            mgr.open("deploy", required_approvals=0)

    def test_duplicate_gate_id_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        mgr.open("deploy", gate_id="G1")
        with pytest.raises(ValueError, match="already exists"):
            mgr.open("deploy2", gate_id="G1")

    def test_vote_unknown_gate_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        with pytest.raises(KeyError):
            mgr.vote("unknown", voter_id="alice", approve=True)

    def test_status_unknown_gate_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        with pytest.raises(KeyError):
            mgr.status("unknown")

    def test_votes_list(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=2)
        mgr.vote(gid, voter_id="alice", approve=True, note="lgtm")
        votes = mgr.votes(gid)
        assert len(votes) == 1
        assert votes[0].voter_id == "alice"
        assert votes[0].note == "lgtm"

    def test_votes_unknown_gate_raises(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        with pytest.raises(KeyError):
            mgr.votes("unknown")

    def test_open_gates(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid1 = mgr.open("a", required_approvals=1)
        gid2 = mgr.open("b", required_approvals=1)
        mgr.vote(gid1, voter_id="alice", approve=True)
        open_gates = mgr.open_gates()
        assert gid2 in open_gates
        assert gid1 not in open_gates

    def test_list_gates(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        mgr.open("a", gate_id="G2")
        mgr.open("b", gate_id="G1")
        gates = mgr.list_gates()
        assert gates == ["G1", "G2"]

    def test_summary(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        mgr.open("a", required_approvals=1)
        mgr.open("b", required_approvals=1)
        s = mgr.summary()
        assert s["gate_count"] == 2
        assert s["open_count"] == 2

    def test_custom_gate_id(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", gate_id="custom-1")
        assert gid == "custom-1"

    def test_no_eligible_voters_anyone_can_vote(self):
        from acgs_lite.constitution.quorum import QuorumManager

        mgr = QuorumManager()
        gid = mgr.open("deploy", required_approvals=1)
        mgr.vote(gid, voter_id="random-agent", approve=True)
        assert mgr.status(gid).state == "approved"
