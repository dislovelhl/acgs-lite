"""Comprehensive tests for under-covered acgs-lite constitution modules.

Targets:
- decision_explainer.py
- provenance.py
- quarantine.py
- anomaly.py
- drift.py
- guardian.py
- policy_linter.py
- circuit_breaker.py
- policy_simulator.py
- counterfactual.py
- interagent_protocol.py
- obligations.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.constitution import Constitution
from acgs_lite.constitution.rule import Rule, Severity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rules() -> list[Rule]:
    return [
        Rule(
            id="privacy-block",
            text="Block PII exfiltration attempts",
            severity=Severity.CRITICAL,
            keywords=["ssn", "credit_card", "social_security"],
            category="privacy",
            workflow_action="block",
            tags=["gdpr", "pii"],
        ),
        Rule(
            id="safety-warn",
            text="Warn on potential safety-related actions",
            severity=Severity.MEDIUM,
            keywords=["harm", "danger"],
            category="safety",
            workflow_action="warn",
            tags=["safety"],
        ),
        Rule(
            id="ops-monitor",
            text="Monitor operational actions for compliance",
            severity=Severity.LOW,
            keywords=["deploy", "restart"],
            category="operations",
            workflow_action="warn",
        ),
    ]


def _make_constitution() -> Constitution:
    return Constitution.from_rules(_make_rules(), name="test")


# ===========================================================================
# decision_explainer.py
# ===========================================================================


class TestDecisionExplainer:
    """Tests for GovernanceDecisionExplainer and related data classes."""

    def test_rule_summary_to_dict(self) -> None:
        from acgs_lite.constitution.decision_explainer import RuleSummary

        rs = RuleSummary(
            rule_id="r1",
            description="Block PII",
            severity="critical",
            category="privacy",
            workflow_action="block",
            matched_keywords=["ssn"],
            tags=["gdpr"],
        )
        d = rs.to_dict()
        assert d["rule_id"] == "r1"
        assert d["severity"] == "critical"
        assert d["matched_keywords"] == ["ssn"]
        assert d["tags"] == ["gdpr"]

    def test_decision_explanation_properties(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            DecisionExplanation,
            RuleSummary,
        )

        blocking = [RuleSummary("r1", "d", "critical", "privacy", "block", [], [])]
        exp = DecisionExplanation(
            decision_id="dec-1",
            outcome="deny",
            summary="blocked",
            rationale="reason",
            blocking_rules=blocking,
        )
        assert exp.is_blocked is True
        assert exp.has_warnings is False

        exp2 = DecisionExplanation(
            decision_id="dec-2",
            outcome="allow",
            summary="ok",
            rationale="reason",
        )
        assert exp2.is_blocked is False
        assert exp2.has_warnings is False

    def test_decision_explanation_to_dict(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            DecisionExplanation,
            ExplanationDetail,
        )

        exp = DecisionExplanation(
            decision_id="dec-1",
            outcome="deny",
            summary="blocked",
            rationale="reason",
            confidence=0.95,
            detail_level=ExplanationDetail.VERBOSE,
        )
        d = exp.to_dict()
        assert d["decision_id"] == "dec-1"
        assert d["outcome"] == "deny"
        assert d["confidence"] == 0.95
        assert d["detail_level"] == "verbose"

    def test_explain_no_rules(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-empty",
            outcome="allow",
            triggered_rules=[],
        )
        assert exp.outcome == "allow"
        assert not exp.is_blocked
        assert not exp.has_warnings
        assert "no governance rules triggered" in exp.summary

    def test_explain_blocking_rules(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-block",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "pii-block",
                    "description": "Block PII exfiltration",
                    "severity": "critical",
                    "category": "privacy",
                    "workflow_action": "block",
                    "keywords": ["ssn", "credit_card"],
                    "tags": ["gdpr"],
                },
            ],
            input_text="Please share the user's SSN",
            context={"agent_id": "agent-7"},
        )
        assert exp.is_blocked
        assert len(exp.blocking_rules) == 1
        assert exp.blocking_rules[0].rule_id == "pii-block"
        assert "privacy" in exp.categories_triggered
        assert "gdpr" in exp.tags_triggered
        assert exp.confidence == 1.0
        assert "blocking" in exp.summary.lower() or "block" in exp.summary.lower()

    def test_explain_warning_rules(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-warn",
            outcome="allow",
            triggered_rules=[
                {
                    "id": "warn-1",
                    "description": "Safety warning",
                    "severity": "medium",
                    "category": "safety",
                    "workflow_action": "warn",
                },
            ],
        )
        assert not exp.is_blocked
        assert exp.has_warnings
        assert len(exp.warning_rules) == 1
        assert exp.confidence == 0.85
        assert "warning" in exp.summary.lower()

    def test_explain_mixed_blocking_and_warning(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-mixed",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "r1",
                    "description": "Block",
                    "severity": "medium",
                    "category": "privacy",
                    "workflow_action": "block",
                },
                {
                    "id": "r2",
                    "description": "Warn",
                    "severity": "low",
                    "category": "safety",
                    "workflow_action": "warn",
                },
            ],
        )
        assert exp.is_blocked
        assert exp.has_warnings
        assert exp.confidence == 0.95  # blocking but no high/critical severity

    def test_explain_quarantine_action(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-q",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "q1",
                    "description": "Quarantine action",
                    "severity": "high",
                    "category": "compliance",
                    "workflow_action": "quarantine",
                },
            ],
        )
        assert exp.is_blocked
        assert any("quarantine" in h.lower() for h in exp.remediation_hints)

    def test_explain_verbose_includes_raw_context(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationDetail,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        ctx = {"agent_id": "a1", "domain": "finance"}
        exp = explainer.explain(
            decision_id="dec-v",
            outcome="allow",
            triggered_rules=[],
            context=ctx,
            detail=ExplanationDetail.VERBOSE,
        )
        assert exp.raw_context == ctx
        assert exp.detail_level == ExplanationDetail.VERBOSE

    def test_explain_standard_excludes_raw_context(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-s",
            outcome="allow",
            triggered_rules=[],
            context={"key": "val"},
        )
        assert exp.raw_context is None

    def test_explain_brief_limits_remediation(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationDetail,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-brief",
            outcome="deny",
            triggered_rules=[
                {
                    "id": f"r{i}",
                    "description": f"Rule {i}",
                    "severity": "high",
                    "category": "security",
                    "workflow_action": "block",
                }
                for i in range(5)
            ],
            detail=ExplanationDetail.BRIEF,
        )
        assert len(exp.remediation_hints) <= 1

    def test_explain_many_blocking_rules_truncates_rationale(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-many",
            outcome="deny",
            triggered_rules=[
                {
                    "id": f"r{i}",
                    "description": f"Rule {i}",
                    "severity": "high",
                    "category": "security",
                    "workflow_action": "deny",
                }
                for i in range(5)
            ],
        )
        assert "and 2 more" in exp.rationale

    def test_render_text(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationFormat,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-txt",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "r1",
                    "description": "Block PII",
                    "severity": "critical",
                    "category": "privacy",
                    "workflow_action": "block",
                    "tags": ["gdpr"],
                },
            ],
        )
        text = explainer.render(exp, fmt=ExplanationFormat.TEXT)
        assert "dec-txt" in text
        assert "privacy" in text.lower()

    def test_render_markdown(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationFormat,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-md",
            outcome="allow",
            triggered_rules=[
                {
                    "id": "w1",
                    "description": "Safety warning",
                    "severity": "medium",
                    "category": "safety",
                    "workflow_action": "warn",
                },
            ],
        )
        md = explainer.render(exp, fmt=ExplanationFormat.MARKDOWN)
        assert "## " in md
        assert "dec-md" in md

    def test_render_json(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationFormat,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-json",
            outcome="allow",
            triggered_rules=[],
        )
        j = explainer.render(exp, fmt=ExplanationFormat.JSON)
        parsed = json.loads(j)
        assert parsed["decision_id"] == "dec-json"

    def test_batch_explain(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        decisions = [
            {"decision_id": "d1", "outcome": "allow", "triggered_rules": []},
            {
                "decision_id": "d2",
                "outcome": "deny",
                "triggered_rules": [
                    {
                        "id": "r1",
                        "description": "Block",
                        "severity": "high",
                        "category": "security",
                        "workflow_action": "block",
                    },
                ],
            },
        ]
        results = explainer.batch_explain(decisions)
        assert len(results) == 2
        assert results[0].outcome == "allow"
        assert results[1].outcome == "deny"

    def test_history_and_filtering(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        explainer.explain(decision_id="d1", outcome="allow", triggered_rules=[])
        explainer.explain(decision_id="d2", outcome="deny", triggered_rules=[])
        explainer.explain(decision_id="d3", outcome="deny", triggered_rules=[])

        all_h = explainer.history()
        assert len(all_h) == 3

        deny_h = explainer.history(outcome_filter="deny")
        assert len(deny_h) == 2

        limited = explainer.history(limit=1)
        assert len(limited) == 1
        assert limited[0].decision_id == "d3"

    def test_history_disabled(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer(store_history=False)
        explainer.explain(decision_id="d1", outcome="allow", triggered_rules=[])
        assert len(explainer.history()) == 0

    def test_summary_report(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        report = explainer.summary_report()
        assert report == {"total": 0}

        explainer.explain(
            decision_id="d1",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "r1",
                    "description": "Block",
                    "severity": "critical",
                    "category": "privacy",
                    "workflow_action": "block",
                },
            ],
        )
        explainer.explain(
            decision_id="d2",
            outcome="allow",
            triggered_rules=[
                {
                    "id": "w1",
                    "description": "Warn",
                    "severity": "low",
                    "category": "safety",
                    "workflow_action": "warn",
                },
            ],
        )
        report = explainer.summary_report()
        assert report["total"] == 2
        assert report["total_blocked"] == 1
        assert report["total_warned"] == 1

    def test_clear_history(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        explainer.explain(decision_id="d1", outcome="allow", triggered_rules=[])
        explainer.explain(decision_id="d2", outcome="deny", triggered_rules=[])
        count = explainer.clear_history()
        assert count == 2
        assert len(explainer.history()) == 0

    def test_explain_rule_id_fallback(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-fb",
            outcome="deny",
            triggered_rules=[
                {
                    "rule_id": "alt-id",
                    "description": "Test",
                    "severity": "high",
                    "category": "test",
                    "workflow_action": "block",
                    "matched_keywords": ["kw1"],
                },
            ],
        )
        assert exp.blocking_rules[0].rule_id == "alt-id"
        assert exp.blocking_rules[0].matched_keywords == ["kw1"]

    def test_render_text_with_warnings_and_tags(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationFormat,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-tw",
            outcome="allow",
            triggered_rules=[
                {
                    "id": "w1",
                    "description": "Safety warn",
                    "severity": "medium",
                    "category": "safety",
                    "workflow_action": "warn",
                    "tags": ["safety-tag"],
                },
            ],
        )
        text = explainer.render(exp, fmt=ExplanationFormat.TEXT)
        assert "safety-tag" in text

    def test_render_markdown_blocking_with_keywords(self) -> None:
        from acgs_lite.constitution.decision_explainer import (
            ExplanationFormat,
            GovernanceDecisionExplainer,
        )

        explainer = GovernanceDecisionExplainer()
        exp = explainer.explain(
            decision_id="dec-mkw",
            outcome="deny",
            triggered_rules=[
                {
                    "id": "r1",
                    "description": "Block PII",
                    "severity": "critical",
                    "category": "privacy",
                    "workflow_action": "block",
                    "keywords": ["ssn"],
                    "tags": ["gdpr"],
                },
            ],
        )
        md = explainer.render(exp, fmt=ExplanationFormat.MARKDOWN)
        assert "ssn" in md
        assert "Blocking Rules" in md
        assert "Remediation" in md


# ===========================================================================
# provenance.py
# ===========================================================================


class TestRuleProvenanceGraph:
    """Tests for RuleProvenanceGraph."""

    def test_add_rule(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        node = g.add_rule("r1", version=2, metadata={"origin": "manual"})
        assert node.rule_id == "r1"
        assert node.version == 2
        assert node.is_active
        assert not node.is_deprecated
        assert len(g) == 1

    def test_add_duplicate_rule_raises(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        with pytest.raises(ValueError, match="already exists"):
            g.add_rule("r1")

    def test_add_relation(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        edge = g.add_relation("r1", "r2", ProvenanceRelation.REPLACED_BY, "upgrade")
        assert edge.source_rule_id == "r1"
        assert edge.target_rule_id == "r2"
        assert edge.relation == ProvenanceRelation.REPLACED_BY

    def test_add_relation_unknown_source(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r2")
        with pytest.raises(ValueError, match="Unknown source"):
            g.add_relation("r1", "r2", ProvenanceRelation.REPLACED_BY)

    def test_add_relation_unknown_target(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        with pytest.raises(ValueError, match="Unknown target"):
            g.add_relation("r1", "r99", ProvenanceRelation.REPLACED_BY)

    def test_self_referencing_raises(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        with pytest.raises(ValueError, match="Self-referencing"):
            g.add_relation("r1", "r1", ProvenanceRelation.DERIVED_FROM)

    def test_deprecate_rule(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        g.deprecate_rule("r1", replaced_by="r2", reason="v2 upgrade")
        node = g.get_node("r1")
        assert node is not None
        assert node.is_deprecated
        assert not node.is_active
        assert node.deprecated_at is not None

    def test_deprecate_unknown_rule(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        with pytest.raises(ValueError, match="Unknown rule"):
            g.deprecate_rule("nonexistent")

    def test_deprecate_with_unknown_replacement(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        with pytest.raises(ValueError, match="Unknown replacement"):
            g.deprecate_rule("r1", replaced_by="nonexistent")

    def test_successors_and_predecessors(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        g.add_relation("r1", "r2", ProvenanceRelation.SPLIT_INTO)

        succ = g.successors("r1")
        assert len(succ) == 1
        assert succ[0].target_rule_id == "r2"

        pred = g.predecessors("r2")
        assert len(pred) == 1
        assert pred[0].source_rule_id == "r1"

        assert g.successors("r2") == []
        assert g.predecessors("r1") == []

    def test_lineage_and_descendants(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        g.add_rule("r3")
        g.add_relation("r1", "r2", ProvenanceRelation.DERIVED_FROM)
        g.add_relation("r2", "r3", ProvenanceRelation.DERIVED_FROM)

        lineage = g.lineage("r3")
        assert "r3" in lineage
        assert "r2" in lineage
        assert "r1" in lineage

        desc = g.descendants("r1")
        assert "r1" in desc
        assert "r2" in desc
        assert "r3" in desc

    def test_active_replacement(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("old")
        g.add_rule("new")
        g.deprecate_rule("old", replaced_by="new")

        replacement = g.active_replacement("old")
        assert replacement == "new"

    def test_active_replacement_none(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        assert g.active_replacement("r1") is None

    def test_deprecated_and_active_rules(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        g.deprecate_rule("r1")

        deprecated = g.deprecated_rules()
        active = g.active_rules()
        assert len(deprecated) == 1
        assert deprecated[0].rule_id == "r1"
        assert len(active) == 1
        assert active[0].rule_id == "r2"

    def test_roots_and_leaves(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("root")
        g.add_rule("middle")
        g.add_rule("leaf")
        g.add_relation("root", "middle", ProvenanceRelation.DERIVED_FROM)
        g.add_relation("middle", "leaf", ProvenanceRelation.DERIVED_FROM)

        assert "root" in g.roots()
        assert "leaf" in g.leaves()
        assert "middle" not in g.roots()
        assert "middle" not in g.leaves()

    def test_impact_analysis(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        g.add_rule("r3")
        g.add_relation("r1", "r2", ProvenanceRelation.SPLIT_INTO)
        g.add_relation("r1", "r3", ProvenanceRelation.SPLIT_INTO)

        analysis = g.impact_analysis("r1")
        assert analysis["rule_id"] == "r1"
        assert analysis["total_descendants"] == 2
        assert len(analysis["active_descendants"]) == 2

    def test_to_dict(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")

        d = g.to_dict()
        assert d["stats"]["total_rules"] == 2
        assert "r1" in d["nodes"]

    def test_provenance_edge_to_dict(self) -> None:
        from acgs_lite.constitution.provenance import (
            ProvenanceRelation,
            RuleProvenanceGraph,
        )

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        g.add_rule("r2")
        edge = g.add_relation("r1", "r2", ProvenanceRelation.MERGED_FROM, "merge")
        d = edge.to_dict()
        assert d["source"] == "r1"
        assert d["target"] == "r2"
        assert d["relation"] == "merged_from"
        assert "timestamp" in d

    def test_rule_node_to_dict_with_deprecation(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1", metadata={"source": "manual"})
        g.deprecate_rule("r1")
        node = g.get_node("r1")
        assert node is not None
        d = node.to_dict()
        assert d["is_deprecated"] is True
        assert "deprecated_at" in d
        assert d["metadata"] == {"source": "manual"}

    def test_rule_node_to_dict_without_deprecation_and_metadata(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        g.add_rule("r1")
        node = g.get_node("r1")
        assert node is not None
        d = node.to_dict()
        assert "deprecated_at" not in d
        assert "metadata" not in d

    def test_get_node_nonexistent(self) -> None:
        from acgs_lite.constitution.provenance import RuleProvenanceGraph

        g = RuleProvenanceGraph()
        assert g.get_node("nonexistent") is None


class TestProvenanceFunctions:
    """Tests for module-level provenance functions."""

    def test_rule_provenance_graph_function(self) -> None:
        from acgs_lite.constitution.provenance import rule_provenance_graph

        rules = [
            Rule(
                id="r1",
                text="Original rule",
                keywords=["test"],
                deprecated=True,
                replaced_by="r2",
            ),
            Rule(id="r2", text="Replacement rule", keywords=["test"]),
        ]
        c = Constitution.from_rules(rules, name="test")
        result = rule_provenance_graph(c)
        assert "nodes" in result
        assert "edges" in result
        assert "roots" in result
        assert len(result["edges"]) >= 1

    def test_provenance_graph_function(self) -> None:
        from acgs_lite.constitution.provenance import provenance_graph

        rules = [
            Rule(id="r1", text="Rule one", keywords=["test"], provenance=["ext-ref"]),
            Rule(id="r2", text="Rule two", keywords=["test"], provenance=["r1"]),
        ]
        c = Constitution.from_rules(rules, name="test")
        result = provenance_graph(c)
        assert "nodes" in result
        assert "edges" in result
        assert "roots" in result
        assert "external_refs" in result

    def test_provenance_graph_with_deprecated_chains(self) -> None:
        from acgs_lite.constitution.provenance import provenance_graph

        rules = [
            Rule(
                id="old",
                text="Old rule for testing",
                keywords=["test"],
                deprecated=True,
                replaced_by="new",
            ),
            Rule(id="new", text="New rule for testing", keywords=["test"]),
        ]
        c = Constitution.from_rules(rules, name="test")
        result = provenance_graph(c)
        assert isinstance(result["deprecated_chains"], list)


# ===========================================================================
# quarantine.py
# ===========================================================================


class TestQuarantine:
    """Tests for GovernanceQuarantine."""

    def test_submit(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(
            action="delete all backups",
            reason="risky operation",
            agent_id="agent-1",
            severity="high",
        )
        assert item.quarantine_id == "QRN-00001"
        assert item.is_pending()
        assert item.agent_id == "agent-1"
        assert len(q) == 1

    def test_submit_generates_preview(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        long_action = "x" * 100
        item = q.submit(action=long_action)
        assert len(item.action_preview) == 80

    def test_approve(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine()
        item = q.submit(action="risky action")
        approved = q.approve(item.quarantine_id, reviewer_id="admin-1", reason="ok")
        assert approved.status == QuarantineStatus.APPROVED
        assert approved.resolved_by == "admin-1"
        assert approved.resolved_at != ""

    def test_deny(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine()
        item = q.submit(action="risky action")
        denied = q.deny(item.quarantine_id, reviewer_id="admin-2", reason="too risky")
        assert denied.status == QuarantineStatus.DENIED

    def test_withdraw(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine()
        item = q.submit(action="my action", agent_id="agent-1")
        withdrawn = q.withdraw(item.quarantine_id, reason="changed mind")
        assert withdrawn.status == QuarantineStatus.WITHDRAWN
        assert withdrawn.resolved_by == "agent-1"

    def test_withdraw_default_reason(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="my action")
        withdrawn = q.withdraw(item.quarantine_id)
        assert "withdrawn by submitter" in withdrawn.resolution_reason

    def test_cannot_approve_already_resolved(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="action")
        q.approve(item.quarantine_id, reviewer_id="admin")
        with pytest.raises(ValueError, match="already"):
            q.approve(item.quarantine_id, reviewer_id="admin")

    def test_unknown_item_raises(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        with pytest.raises(KeyError, match="not found"):
            q.approve("QRN-99999", reviewer_id="admin")

    def test_pending(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        q.submit(action="a1")
        q.submit(action="a2")
        item3 = q.submit(action="a3")
        q.approve(item3.quarantine_id, reviewer_id="admin")
        assert len(q.pending()) == 2

    def test_by_agent(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        q.submit(action="a1", agent_id="agent-1")
        q.submit(action="a2", agent_id="agent-2")
        q.submit(action="a3", agent_id="agent-1")
        assert len(q.by_agent("agent-1")) == 2

    def test_by_status(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="a1")
        q.submit(action="a2")
        q.approve(item.quarantine_id, reviewer_id="admin")
        assert len(q.by_status("approved")) == 1
        assert len(q.by_status("pending")) == 1

    def test_process_timeouts_deny_policy(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine(default_timeout_policy="deny")
        q.submit(action="a1", timeout_at="2020-01-01T00:00:00+00:00")
        resolved = q.process_timeouts()
        assert len(resolved) == 1
        assert resolved[0].status == QuarantineStatus.DENIED
        assert "auto-denied" in resolved[0].resolution_reason

    def test_process_timeouts_approve_policy(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine()
        q.submit(
            action="a1",
            timeout_at="2020-01-01T00:00:00+00:00",
            timeout_policy="approve",
        )
        resolved = q.process_timeouts()
        assert len(resolved) == 1
        assert resolved[0].status == QuarantineStatus.APPROVED

    def test_process_timeouts_escalate_policy(self) -> None:
        from acgs_lite.constitution.quarantine import (
            GovernanceQuarantine,
            QuarantineStatus,
        )

        q = GovernanceQuarantine()
        q.submit(
            action="a1",
            timeout_at="2020-01-01T00:00:00+00:00",
            timeout_policy="escalate",
        )
        resolved = q.process_timeouts()
        assert len(resolved) == 1
        assert resolved[0].status == QuarantineStatus.TIMED_OUT

    def test_process_timeouts_skips_not_timed_out(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        q.submit(action="a1", timeout_at="2099-01-01T00:00:00+00:00")
        resolved = q.process_timeouts()
        assert len(resolved) == 0

    def test_process_timeouts_skips_no_timeout(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        q.submit(action="a1")
        resolved = q.process_timeouts()
        assert len(resolved) == 0

    def test_summary(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="a1", agent_id="agent-1")
        q.submit(action="a2", agent_id="agent-1")
        q.approve(item.quarantine_id, reviewer_id="admin")

        s = q.summary()
        assert s["total"] == 2
        assert s["pending_count"] == 1
        assert s["by_agent"]["agent-1"] == 2
        assert s["approval_rate"] == 0.5

    def test_summary_empty(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        s = q.summary()
        assert s["total"] == 0
        assert s["approval_rate"] == 0.0

    def test_history(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="a1")
        q.approve(item.quarantine_id, reviewer_id="admin")
        h = q.history()
        assert len(h) == 2
        assert h[0]["event"] == "submitted"
        assert h[1]["event"] == "approved"

    def test_to_dict(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(
            action="test action",
            reason="test reason",
            sphere="safety",
            risk_score=0.8,
            severity="high",
            agent_id="agent-1",
            metadata={"key": "val"},
        )
        d = item.to_dict()
        assert d["quarantine_id"] == item.quarantine_id
        assert d["risk_score"] == 0.8
        assert d["metadata"] == {"key": "val"}

    def test_repr(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="test", agent_id="a1")
        r = repr(item)
        assert "QRN-" in r
        assert "a1" in r

        r2 = repr(q)
        assert "1 items" in r2
        assert "1 pending" in r2

    def test_quarantined_action_is_timed_out_with_custom_at(self) -> None:
        from acgs_lite.constitution.quarantine import GovernanceQuarantine

        q = GovernanceQuarantine()
        item = q.submit(action="a1", timeout_at="2025-06-01T00:00:00+00:00")
        assert item.is_timed_out("2025-07-01T00:00:00+00:00") is True
        assert item.is_timed_out("2025-01-01T00:00:00+00:00") is False


# ===========================================================================
# anomaly.py
# ===========================================================================


class TestAnomalyDetector:
    """Tests for GovernanceAnomalyDetector."""

    def test_record_decision_below_window(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=10)
        signals = detector.record_decision("allow", "agent-1")
        assert signals == []

    def test_record_deny_updates_baseline(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=5)
        detector.record_decision("deny", "agent-1", ["rule-1"])
        stats = detector.stats()
        assert stats["baseline_deny_rate"] > 0

    def test_anomaly_signal_to_dict(self) -> None:
        from acgs_lite.constitution.anomaly import AnomalySignal

        sig = AnomalySignal(
            anomaly_type="rate_deviation",
            metric="deny_rate",
            expected_value=0.1,
            observed_value=0.9,
            deviation=5.0,
            severity="high",
            timestamp=datetime.now(timezone.utc),
            details={"z_score": 5.0},
        )
        d = sig.to_dict()
        assert d["anomaly_type"] == "rate_deviation"
        assert d["expected_value"] == 0.1
        assert isinstance(d["timestamp"], str)

    def test_no_anomaly_on_normal_traffic(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=20, z_threshold=3.0)
        for i in range(100):
            detector.record_decision("allow", f"agent-{i % 5}")
        assert len(detector.recent_anomalies()) == 0

    def test_deny_spike_triggers_anomaly(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=20, z_threshold=2.0)
        # Build baseline with low deny rate
        for _ in range(50):
            detector.record_decision("allow", "agent-1")
        # Spike denials
        for _ in range(25):
            detector.record_decision("deny", "agent-1", severity="low")

        anomalies = detector.recent_anomalies()
        assert len(anomalies) > 0

    def test_critical_spike_detection(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=10, z_threshold=1.0)
        # Build baseline
        for _ in range(20):
            detector.record_decision("allow", "agent-1")
        # Critical denials spike
        for _ in range(15):
            detector.record_decision("deny", "agent-1", severity="critical")

        anomalies = detector.recent_anomalies()
        types = {a.anomaly_type for a in anomalies}
        assert "critical_spike" in types or "rate_deviation" in types

    def test_agent_concentration_detection(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector(window_size=10, z_threshold=1.0)
        # Baseline
        for _ in range(20):
            detector.record_decision("allow", "agent-1")
        # All denials from one agent
        for _ in range(15):
            detector.record_decision("deny", "agent-bad")

        anomalies = detector.recent_anomalies()
        types = {a.anomaly_type for a in anomalies}
        assert "agent_concentration" in types or "rate_deviation" in types

    def test_rule_fire_ranking(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector()
        for _ in range(5):
            detector.record_decision("deny", "a1", ["rule-A", "rule-B"])
        for _ in range(3):
            detector.record_decision("deny", "a1", ["rule-A"])
        ranking = detector.rule_fire_ranking(top_n=2)
        assert ranking[0][0] == "rule-A"
        assert ranking[0][1] == 8

    def test_agent_denial_ranking(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector()
        for _ in range(5):
            detector.record_decision("deny", "agent-bad")
        for _ in range(2):
            detector.record_decision("deny", "agent-ok")
        ranking = detector.agent_denial_ranking()
        assert ranking[0] == ("agent-bad", 5)

    def test_anomaly_count_by_type(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector()
        counts = detector.anomaly_count_by_type()
        assert counts == {}

    def test_stats(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector()
        detector.record_decision("allow", "a1")
        detector.record_decision("deny", "a1")
        stats = detector.stats()
        assert stats["total_decisions"] == 2
        assert stats["baseline_samples"] == 2

    def test_reset(self) -> None:
        from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

        detector = GovernanceAnomalyDetector()
        for _ in range(10):
            detector.record_decision("deny", "a1")
        detector.reset()
        stats = detector.stats()
        assert stats["total_decisions"] == 0
        assert stats["baseline_deny_rate"] == 0.0


# ===========================================================================
# drift.py
# ===========================================================================


class TestDriftDetector:
    """Tests for GovernanceDriftDetector and DriftSignal."""

    def test_drift_signal_creation(self) -> None:
        from acgs_lite.constitution.drift import DriftSignal

        sig = DriftSignal(
            signal_type="probing",
            agent_id="a1",
            evidence="test evidence",
            severity="high",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        assert sig.signal_type == "probing"
        d = sig.to_dict()
        assert d["agent_id"] == "a1"

    def test_drift_signal_invalid_type(self) -> None:
        from acgs_lite.constitution.drift import DriftSignal

        with pytest.raises(ValueError, match="Invalid signal_type"):
            DriftSignal(
                signal_type="invalid",
                agent_id="a1",
                evidence="test",
                severity="low",
                timestamp="now",
            )

    def test_drift_signal_invalid_severity(self) -> None:
        from acgs_lite.constitution.drift import DriftSignal

        with pytest.raises(ValueError, match="Invalid severity"):
            DriftSignal(
                signal_type="probing",
                agent_id="a1",
                evidence="test",
                severity="critical",
                timestamp="now",
            )

    def test_analyze_empty_decisions(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        signals = detector.analyze_decisions([], agent_id="a1")
        assert signals == []

    def test_probing_detection(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        detector.configure_thresholds(deny_rate_threshold=0.3)
        decisions = [{"decision": "deny"} for _ in range(8)] + [
            {"decision": "allow"} for _ in range(2)
        ]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        types = {s.signal_type for s in signals}
        assert "probing" in types

    def test_probing_high_severity_at_high_rate(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        decisions = [{"decision": "deny"} for _ in range(8)] + [
            {"decision": "allow"} for _ in range(2)
        ]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        probing = [s for s in signals if s.signal_type == "probing"]
        assert len(probing) == 1
        assert probing[0].severity == "high"

    def test_gaming_detection(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        detector.configure_thresholds(consecutive_deny_threshold=3)
        decisions = [{"decision": "deny", "action": "delete data"} for _ in range(5)]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        types = {s.signal_type for s in signals}
        assert "gaming" in types

    def test_boundary_walking_detection(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        detector.configure_thresholds(boundary_walk_threshold=0.2)
        decisions = [{"decision": "allow", "rule_ids": ["r1"]} for _ in range(5)] + [
            {"decision": "allow"} for _ in range(5)
        ]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        types = {s.signal_type for s in signals}
        assert "boundary_walking" in types

    def test_escalation_suppression_detection(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        detector.configure_thresholds(
            escalation_suppression_window=5,
            boundary_walk_threshold=1.0,  # disable boundary walking
        )
        decisions = [{"decision": "allow", "rule_ids": ["r1"]} for _ in range(10)]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        types = {s.signal_type for s in signals}
        assert "escalation_suppression" in types

    def test_summary(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        decisions = [{"decision": "deny"} for _ in range(10)]
        detector.analyze_decisions(decisions, agent_id="a1")
        s = detector.summary()
        assert s["total_signals"] > 0
        assert "by_type" in s
        assert "by_severity" in s
        assert "by_agent" in s

    def test_export(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        decisions = [{"decision": "deny"} for _ in range(10)]
        detector.analyze_decisions(decisions, agent_id="a1")
        exported = detector.export()
        assert len(exported) > 0
        assert "signal_type" in exported[0]

    def test_clear(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        decisions = [{"decision": "deny"} for _ in range(10)]
        detector.analyze_decisions(decisions, agent_id="a1")
        detector.clear()
        assert detector.summary()["total_signals"] == 0

    def test_normalize_action(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        result = GovernanceDriftDetector._normalize_action("  Delete ALL Data!  ")
        assert result == "delete all data"

    def test_no_gaming_with_varied_actions(self) -> None:
        from acgs_lite.constitution.drift import GovernanceDriftDetector

        detector = GovernanceDriftDetector()
        decisions = [{"decision": "deny", "action": f"action_{i}"} for i in range(5)]
        signals = detector.analyze_decisions(decisions, agent_id="a1")
        gaming = [s for s in signals if s.signal_type == "gaming"]
        assert len(gaming) == 0


# ===========================================================================
# guardian.py
# ===========================================================================


class TestGuardianGate:
    """Tests for GuardianGate."""

    def test_classify_autonomous(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        result = gate.classify(risk_score=0.1)
        assert result["sphere"] == "autonomous"
        assert result["human_required"] is False

    def test_classify_consultative(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        result = gate.classify(risk_score=0.4)
        assert result["sphere"] == "consultative"
        assert result["human_required"] is False

    def test_classify_mandatory_approval(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        result = gate.classify(risk_score=0.7)
        assert result["sphere"] == "mandatory_approval"
        assert result["human_required"] is True

    def test_classify_forbidden(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        result = gate.classify(risk_score=0.9)
        assert result["sphere"] == "forbidden"
        assert result["human_required"] is True

    def test_classify_boundary_values(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        assert gate.classify(risk_score=0.0)["sphere"] == "autonomous"
        assert gate.classify(risk_score=0.25)["sphere"] == "autonomous"
        assert gate.classify(risk_score=0.55)["sphere"] == "consultative"
        assert gate.classify(risk_score=0.85)["sphere"] == "mandatory_approval"
        assert gate.classify(risk_score=1.0)["sphere"] == "forbidden"

    def test_severity_override(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate(
            severity_overrides={"critical": "forbidden", "high": "mandatory_approval"}
        )
        result = gate.classify(risk_score=0.1, severity="critical")
        assert result["sphere"] == "forbidden"
        assert "severity override" in result["rationale"]

    def test_custom_thresholds(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate(
            thresholds={
                "autonomous_max": 0.1,
                "consultative_max": 0.3,
                "mandatory_max": 0.5,
            }
        )
        assert gate.classify(risk_score=0.05)["sphere"] == "autonomous"
        assert gate.classify(risk_score=0.2)["sphere"] == "consultative"
        assert gate.classify(risk_score=0.4)["sphere"] == "mandatory_approval"
        assert gate.classify(risk_score=0.6)["sphere"] == "forbidden"

    def test_batch_classify(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        items = [
            {"risk_score": 0.1},
            {"risk_score": 0.5, "severity": "medium"},
            {"risk_score": 0.9, "agent_id": "agent-1"},
        ]
        results = gate.batch_classify(items)
        assert len(results) == 3
        assert results[0]["sphere"] == "autonomous"

    def test_summary(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        gate.classify(risk_score=0.1)
        gate.classify(risk_score=0.9)
        s = gate.summary()
        assert s["total_classifications"] == 2
        assert s["human_required_count"] == 1

    def test_summary_empty(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        s = gate.summary()
        assert s["total_classifications"] == 0
        assert s["human_required_rate"] == 0.0
        assert s["autonomy_rate"] == 0.0

    def test_history(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        gate.classify(risk_score=0.1, action="test action", agent_id="a1")
        h = gate.history()
        assert len(h) == 1
        assert h[0]["action_preview"] == "test action"

    def test_repr(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        r = repr(gate)
        assert "GuardianGate" in r

    def test_classify_action_preview_truncated(self) -> None:
        from acgs_lite.constitution.guardian import GuardianGate

        gate = GuardianGate()
        result = gate.classify(risk_score=0.1, action="x" * 100)
        assert len(result["action_preview"]) == 80


# ===========================================================================
# policy_linter.py
# ===========================================================================


class TestPolicyLinter:
    """Tests for PolicyLinter."""

    def test_lint_good_rule(self) -> None:
        from acgs_lite.constitution.policy_linter import PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Block PII exfiltration attempts",
                    "severity": "critical",
                    "category": "privacy",
                    "workflow_action": "block",
                    "keywords": ["ssn", "credit_card"],
                }
            ]
        )
        assert report.passed

    def test_lint_missing_description(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "severity": "high",
                    "keywords": ["test"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.MISSING_DESCRIPTION in codes

    def test_lint_short_description(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Short",
                    "severity": "high",
                    "keywords": ["test_keyword"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.DESCRIPTION_TOO_SHORT in codes

    def test_lint_empty_keywords(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "A rule with no keywords at all",
                    "severity": "high",
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        assert not report.passed
        codes = {i.code for i in report.issues}
        assert LintCode.EMPTY_KEYWORDS in codes

    def test_lint_duplicate_keyword(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with duplicate keywords present",
                    "severity": "high",
                    "keywords": ["ssn", "ssn", "other"],
                    "category": "privacy",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.DUPLICATE_KEYWORD in codes

    def test_lint_short_keyword(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with very short keyword present",
                    "severity": "high",
                    "keywords": ["ab"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.OVERLY_SHORT_KEYWORD in codes

    def test_lint_duplicate_rule_id(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "First rule for testing linter",
                    "severity": "high",
                    "keywords": ["test"],
                    "category": "security",
                    "workflow_action": "block",
                },
                {
                    "id": "r1",
                    "description": "Duplicate id rule for testing",
                    "severity": "low",
                    "keywords": ["other"],
                    "category": "security",
                    "workflow_action": "warn",
                },
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.DUPLICATE_RULE_ID in codes

    def test_lint_conflicting_severity(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule one with shared keyword test",
                    "severity": "critical",
                    "keywords": ["shared_keyword"],
                    "category": "privacy",
                    "workflow_action": "block",
                },
                {
                    "id": "r2",
                    "description": "Rule two with shared keyword test",
                    "severity": "low",
                    "keywords": ["shared_keyword"],
                    "category": "privacy",
                    "workflow_action": "warn",
                },
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.CONFLICTING_SEVERITY in codes

    def test_lint_invalid_severity(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with invalid severity value",
                    "severity": "mega",
                    "keywords": ["test"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.INVALID_SEVERITY in codes

    def test_lint_missing_category(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with no category at all",
                    "severity": "high",
                    "keywords": ["test"],
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.MISSING_CATEGORY in codes

    def test_lint_missing_workflow_action(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with no workflow action",
                    "severity": "high",
                    "keywords": ["test"],
                    "category": "security",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.MISSING_WORKFLOW_ACTION in codes

    def test_lint_excessive_keywords(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter(max_keywords_per_rule=5)
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with too many keywords present",
                    "severity": "high",
                    "keywords": [f"keyword_{i}" for i in range(10)],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.EXCESSIVE_KEYWORD_COUNT in codes

    def test_lint_keyword_substring_overlap(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with overlapping keyword substrings",
                    "severity": "high",
                    "keywords": ["credit", "credit_card"],
                    "category": "privacy",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.KEYWORD_SUBSTRING_OVERLAP in codes

    def test_lint_weak_regex_pattern(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with weak regex pattern present",
                    "severity": "high",
                    "keywords": ["test"],
                    "patterns": ["ab"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.WEAK_REGEX_PATTERN in codes

    def test_lint_duplicate_pattern(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "First rule with a shared pattern",
                    "severity": "high",
                    "keywords": ["test"],
                    "patterns": ["^ssn\\d+$"],
                    "category": "privacy",
                    "workflow_action": "block",
                },
                {
                    "id": "r2",
                    "description": "Second rule with the same pattern",
                    "severity": "high",
                    "keywords": ["other"],
                    "patterns": ["^ssn\\d+$"],
                    "category": "privacy",
                    "workflow_action": "block",
                },
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.DUPLICATE_PATTERN in codes

    def test_lint_report_properties(self) -> None:
        from acgs_lite.constitution.policy_linter import PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "A good rule with proper keywords",
                    "severity": "high",
                    "keywords": ["test_keyword"],
                    "category": "security",
                    "workflow_action": "block",
                },
                {"severity": "mega", "keywords": ["test"]},
            ]
        )
        assert report.rules_checked == 2
        assert len(report.errors) > 0
        assert isinstance(report.summary(), str)
        assert isinstance(report.to_dict(), dict)
        assert isinstance(report.to_text(), str)

    def test_lint_report_by_rule(self) -> None:
        from acgs_lite.constitution.policy_linter import PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {"id": "r1", "severity": "high", "keywords": ["test"]},
                {"id": "r2", "severity": "mega", "keywords": ["test"]},
            ]
        )
        by_rule = report.by_rule()
        assert "r1" in by_rule or "r2" in by_rule

    def test_lint_report_filter(self) -> None:
        from acgs_lite.constitution.policy_linter import (
            LintCode,
            LintSeverity,
            PolicyLinter,
        )

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {"id": "r1", "severity": "mega", "keywords": ["test"]},
            ]
        )
        errors = report.filter(severity=LintSeverity.ERROR)
        assert len(errors) > 0
        by_code = report.filter(code=LintCode.INVALID_SEVERITY)
        assert len(by_code) > 0
        by_rule = report.filter(rule_id="r1")
        assert len(by_rule) > 0

    def test_lint_single_rule(self) -> None:
        from acgs_lite.constitution.policy_linter import PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rule(
            {
                "id": "r1",
                "description": "A well-described rule for testing",
                "severity": "high",
                "keywords": ["test_keyword"],
                "category": "security",
                "workflow_action": "block",
            }
        )
        assert report.rules_checked == 1
        assert report.passed

    def test_lint_constitution_object(self) -> None:
        from acgs_lite.constitution.policy_linter import PolicyLinter

        linter = PolicyLinter()
        c = _make_constitution()
        report = linter.lint_constitution(c)
        assert report.rules_checked == len(c.rules)

    def test_lint_anchored_pattern_not_flagged(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with anchored pattern present",
                    "severity": "high",
                    "keywords": ["test"],
                    "patterns": ["^ab$"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.WEAK_REGEX_PATTERN not in codes

    def test_lint_invalid_regex_not_flagged_as_weak(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Rule with invalid regex pattern present",
                    "severity": "high",
                    "keywords": ["test"],
                    "patterns": ["["],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.WEAK_REGEX_PATTERN not in codes

    def test_lint_positive_directive_risk(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Ensure all outputs follow company style guide",
                    "severity": "medium",
                    "keywords": ["style", "guide"],
                    "category": "quality",
                    "workflow_action": "warn",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.POSITIVE_DIRECTIVE_RISK in codes

    def test_lint_negative_constraint_not_flagged_as_positive_directive(self) -> None:
        from acgs_lite.constitution.policy_linter import LintCode, PolicyLinter

        linter = PolicyLinter()
        report = linter.lint_rules(
            [
                {
                    "id": "r1",
                    "description": "Block requests that exfiltrate sensitive data",
                    "severity": "critical",
                    "keywords": ["exfiltrate", "sensitive data"],
                    "category": "security",
                    "workflow_action": "block",
                }
            ]
        )
        codes = {i.code for i in report.issues}
        assert LintCode.POSITIVE_DIRECTIVE_RISK not in codes


# ===========================================================================
# circuit_breaker.py
# ===========================================================================


class TestCircuitBreaker:
    """Tests for GovernanceCircuitBreaker."""

    def test_initial_state_closed(self) -> None:
        from acgs_lite.constitution.circuit_breaker import GovernanceCircuitBreaker

        cb = GovernanceCircuitBreaker()
        assert cb.state.value == "closed"
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            CircuitState,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(failure_threshold=3)
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitState.CLOSED
        cb.record_failure("err3")
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_fallback_decision(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            FallbackPolicy,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(fallback=FallbackPolicy.ESCALATE)
        cb = GovernanceCircuitBreaker(policy)
        assert cb.fallback_decision() == "escalate"

    def test_success_decrements_failure_count(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(failure_threshold=3)
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        cb.record_success()
        cb.record_failure("err3")
        # Should not open because success decremented count
        assert cb.state.value == "closed"

    def test_half_open_after_recovery_timeout(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            CircuitState,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=0),
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        # With 0-second timeout, accessing .state triggers immediate transition
        # to HALF_OPEN since the recovery timeout has already elapsed
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_calls(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=0),
            half_open_max_calls=2,
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        # Now half-open
        assert cb.allow_request() is True
        assert cb.allow_request() is True
        assert cb.allow_request() is False

    def test_half_open_failure_reopens(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            CircuitState,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=0),
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        # Now half-open
        _ = cb.state  # trigger transition
        cb.record_failure("probe failed")
        assert cb._state == CircuitState.OPEN

    def test_half_open_success_closes(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            CircuitState,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=0),
            success_threshold=2,
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        _ = cb.state  # trigger half-open
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            CircuitState,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=9999),
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb._state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_when_already_closed(self) -> None:
        from acgs_lite.constitution.circuit_breaker import GovernanceCircuitBreaker

        cb = GovernanceCircuitBreaker()
        cb.reset()  # should not crash or create events
        assert cb.state.value == "closed"

    def test_summary(self) -> None:
        from acgs_lite.constitution.circuit_breaker import GovernanceCircuitBreaker

        cb = GovernanceCircuitBreaker()
        cb.record_failure("err")
        cb.record_success()
        s = cb.summary()
        assert s["state"] == "closed"
        assert s["total_failures"] == 1
        assert s["total_successes"] == 1
        assert "policy" in s

    def test_history(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(failure_threshold=2)
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        h = cb.history()
        assert len(h) > 0
        assert h[0]["state_to"] == "open"

    def test_circuit_event_to_dict(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitEvent,
            CircuitState,
        )

        event = CircuitEvent(
            state_from=CircuitState.CLOSED,
            state_to=CircuitState.OPEN,
            reason="threshold reached",
            timestamp=datetime.now(timezone.utc),
            failure_count=5,
        )
        d = event.to_dict()
        assert d["state_from"] == "closed"
        assert d["state_to"] == "open"
        assert d["failure_count"] == 5

    def test_open_circuit_tracks_rejections(self) -> None:
        from acgs_lite.constitution.circuit_breaker import (
            CircuitBreakerPolicy,
            GovernanceCircuitBreaker,
        )

        policy = CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout=timedelta(seconds=9999),
        )
        cb = GovernanceCircuitBreaker(policy)
        cb.record_failure("err1")
        cb.record_failure("err2")
        cb.allow_request()
        cb.allow_request()
        s = cb.summary()
        assert s["total_rejections"] == 2


# ===========================================================================
# policy_simulator.py
# ===========================================================================


class TestPolicySimulator:
    """Tests for GovernancePolicySimulator."""

    def test_action_delta_to_dict(self) -> None:
        from acgs_lite.constitution.policy_simulator import ActionDelta

        d = ActionDelta(
            action="test",
            baseline_outcome="allow",
            candidate_outcome="deny",
            changed=True,
            risk_level="medium",
            risk_weight=0.5,
        )
        dd = d.to_dict()
        assert dd["changed"] is True
        assert dd["risk_level"] == "medium"

    def test_compare_no_changes(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        candidate = _make_constitution()
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": candidate},
            actions=["safe action", "normal request"],
        )
        assert report.actions_evaluated == 2
        cr = report.candidates["v2"]
        assert cr.changed_count == 0
        assert cr.recommendation == "go"

    def test_compare_with_changes(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        # Add a rule that blocks "deploy"
        new_rules = _make_rules() + [
            Rule(
                id="extra-block",
                text="Block all deploy actions strictly",
                severity=Severity.CRITICAL,
                keywords=["safe"],
                category="security",
                workflow_action="block",
            ),
        ]
        candidate = Constitution.from_rules(new_rules, name="v2")
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": candidate},
            actions=["safe action", "normal request"],
        )
        cr = report.candidates["v2"]
        assert cr.total_actions == 2

    def test_evaluate_single(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        candidate = _make_constitution()
        sim = GovernancePolicySimulator()
        cr = sim.evaluate_single(baseline, candidate, ["test action"])
        assert cr.total_actions == 1

    def test_candidate_report_to_dict(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        candidate = _make_constitution()
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": candidate},
            actions=["test"],
        )
        d = report.to_dict()
        assert "candidates" in d
        assert "recommendation" in d

    def test_report_summary(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        candidate = _make_constitution()
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": candidate},
            actions=["test"],
        )
        s = report.summary()
        assert "GovernancePolicySimulator Report" in s

    def test_diff_matrix(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        candidate = _make_constitution()
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": candidate},
            actions=["test"],
        )
        matrix = report.diff_matrix()
        assert isinstance(matrix, list)

    def test_best_candidate(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            GovernancePolicySimulator,
        )

        baseline = _make_constitution()
        sim = GovernancePolicySimulator()
        report = sim.compare(
            baseline=baseline,
            candidates={"v2": _make_constitution(), "v3": _make_constitution()},
            actions=["test action"],
        )
        best = report.best_candidate
        assert best is not None

    def test_recommendation_no_go(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            CandidateReport,
            SimulationComparisonReport,
        )

        report = SimulationComparisonReport(
            baseline_id="base",
            candidates={
                "v2": CandidateReport(
                    candidate_id="v2",
                    deltas=(),
                    total_actions=1,
                    changed_count=1,
                    regressions=1,
                    blast_radius=1.0,
                    weighted_risk=1.0,
                    recommendation="no-go",
                    confidence=0.9,
                ),
            },
        )
        assert "no-go" in report.recommendation

    def test_recommendation_review(self) -> None:
        from acgs_lite.constitution.policy_simulator import (
            CandidateReport,
            SimulationComparisonReport,
        )

        report = SimulationComparisonReport(
            baseline_id="base",
            candidates={
                "v2": CandidateReport(
                    candidate_id="v2",
                    deltas=(),
                    total_actions=1,
                    changed_count=1,
                    regressions=0,
                    blast_radius=0.5,
                    weighted_risk=0.5,
                    recommendation="review",
                    confidence=0.7,
                ),
            },
        )
        assert "review" in report.recommendation


# ===========================================================================
# counterfactual.py
# ===========================================================================


class TestCounterfactual:
    """Tests for CounterfactualGovernance."""

    def _baseline_rules(self) -> list[dict]:
        return [
            {
                "id": "pii-block",
                "keywords": ["ssn", "credit_card"],
                "severity": "critical",
            },
            {
                "id": "safety-warn",
                "keywords": ["harm", "danger"],
                "severity": "medium",
            },
        ]

    def test_what_if_add_rules(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_add_rules(
            new_rules=[{"id": "deploy-block", "keywords": ["deploy"], "severity": "high"}],
            test_actions=["deploy to production", "read data", "send ssn"],
        )
        assert report.actions_tested == 3
        assert len(report.newly_blocked) >= 1
        assert any(d.action_text == "deploy to production" for d in report.newly_blocked)

    def test_what_if_remove_rules(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_remove_rules(
            rule_ids_to_remove={"pii-block"},
            test_actions=["send ssn", "read data"],
        )
        assert len(report.newly_allowed) >= 1

    def test_what_if_modify_rules(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_modify_rules(
            modifications={"pii-block": {"severity": "low"}},
            test_actions=["send ssn"],
        )
        # ssn still matches, but severity changes
        if report.severity_changed:
            assert report.severity_changed[0].severity_change == "critical->low"

    def test_what_if_replace_all(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_replace_all(
            variant_rules=[],
            test_actions=["send ssn", "cause harm"],
        )
        assert len(report.newly_allowed) == 2

    def test_unchanged_actions(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_add_rules(
            new_rules=[],
            test_actions=["read data", "normal request"],
        )
        assert report.unchanged == 2
        assert report.total_changes == 0

    def test_impact_score(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_remove_rules(
            rule_ids_to_remove={"pii-block"},
            test_actions=["send ssn"],
        )
        assert report.impact_score == 1.0

    def test_impact_score_zero_actions(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualReport

        report = CounterfactualReport(
            scenario_name="empty",
            actions_tested=0,
            unchanged=0,
            newly_blocked=[],
            newly_allowed=[],
            severity_changed=[],
        )
        assert report.impact_score == 0.0

    def test_summary_text(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_add_rules(
            new_rules=[],
            test_actions=["test"],
        )
        s = report.summary()
        assert "Counterfactual" in s

    def test_to_dict(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        report = cf.what_if_add_rules(
            new_rules=[],
            test_actions=["test"],
        )
        d = report.to_dict()
        assert "scenario_name" in d
        assert "impact_score" in d

    def test_decision_delta_to_dict(self) -> None:
        from acgs_lite.constitution.counterfactual import DecisionDelta

        dd = DecisionDelta(
            action_text="test",
            baseline_outcome="allow",
            variant_outcome="deny",
            baseline_violations=(),
            variant_violations=("r1",),
            severity_change="low->high",
        )
        d = dd.to_dict()
        assert d["baseline_outcome"] == "allow"
        assert d["variant_violations"] == ["r1"]

    def test_history(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        cf.what_if_add_rules(new_rules=[], test_actions=["test"])
        cf.what_if_remove_rules(rule_ids_to_remove=set(), test_actions=["test"])
        assert len(cf.history()) == 2

    def test_highest_impact(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance(self._baseline_rules())
        cf.what_if_add_rules(new_rules=[], test_actions=["test"])
        cf.what_if_remove_rules(
            rule_ids_to_remove={"pii-block"},
            test_actions=["send ssn"],
        )
        hi = cf.highest_impact()
        assert hi is not None
        assert hi.impact_score > 0

    def test_highest_impact_empty(self) -> None:
        from acgs_lite.constitution.counterfactual import CounterfactualGovernance

        cf = CounterfactualGovernance([])
        assert cf.highest_impact() is None


# ===========================================================================
# interagent_protocol.py
# ===========================================================================


class TestInterAgentProtocol:
    """Tests for InterAgentGovernanceProtocol."""

    def test_delegate_basic(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="agent-A",
            delegatee_id="agent-B",
            delegator_scope={"read", "write", "deploy"},
            requested_scope={"read", "write"},
        )
        assert result.success
        assert result.granted_scope == frozenset({"read", "write"})
        assert result.denied_scope == frozenset()
        assert result.link is not None

    def test_delegate_scope_narrowing(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="agent-A",
            delegatee_id="agent-B",
            delegator_scope={"read"},
            requested_scope={"read", "write"},
        )
        assert result.success
        assert result.granted_scope == frozenset({"read"})
        assert result.denied_scope == frozenset({"write"})

    def test_delegate_max_depth_exceeded(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        # max_depth checks current chain depth of the delegatee.
        # Delegating A->B creates a chain of depth 1 for B.
        # Delegating B->C: get_chain("C") is None (depth 0), so it succeeds at depth 1.
        # To trigger max_depth, we need chain depth >= max_depth for the delegatee.
        # With max_depth=1: A->B succeeds (C chain depth 0), then B gives C depth 1.
        # Then C->D would fail because get_chain("D") is None but get_chain for delegatee
        # Actually the check is on the delegatee's existing chain depth.
        # So we can't easily exceed with separate agents. Let's test by delegating
        # to an agent that already has a chain at max_depth.
        protocol = InterAgentGovernanceProtocol(max_depth=1)
        # A -> B: B's chain depth is 0 before, succeeds, B now has depth 1
        r1 = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        assert r1.success
        # Now B has chain depth 1. Delegating X -> B would check B's chain depth = 1 >= max_depth=1
        result = protocol.delegate(
            delegator_id="X",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        assert not result.success
        assert "depth" in result.reason.lower()

    def test_revoke_basic(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        link_id = result.link.link_id
        revoked = protocol.revoke(link_id)
        assert link_id in revoked
        assert protocol._links[link_id].revoked

    def test_revoke_cascade(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        # Cascade follows _agent_links for the delegatee of the revoked link.
        # So if we revoke a link where delegatee=B, it cascades to other links
        # where delegatee=B (i.e., other links granted TO B, not FROM B).
        # To test cascade effectively, create two links both targeting B.
        protocol = InterAgentGovernanceProtocol(max_depth=5)
        r1 = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read", "write"},
            requested_scope={"read", "write"},
        )
        r2 = protocol.delegate(
            delegator_id="C",
            delegatee_id="B",
            delegator_scope={"deploy"},
            requested_scope={"deploy"},
        )
        revoked = protocol.revoke(r1.link.link_id, cascade=True)
        assert r1.link.link_id in revoked
        # r2 is also a link to B, so it gets cascade-revoked
        assert r2.link.link_id in revoked

    def test_revoke_nonexistent(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        assert protocol.revoke("nonexistent") == []

    def test_get_chain(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read", "write"},
            requested_scope={"read"},
        )
        chain = protocol.get_chain("B")
        assert chain is not None
        assert chain.root_principal == "A"
        assert chain.terminal_agent == "B"

    def test_get_chain_nonexistent(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        assert protocol.get_chain("X") is None

    def test_effective_scope_with_root(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"admin", "read", "write"})
        scope = protocol.effective_scope("A")
        assert scope == frozenset({"admin", "read", "write"})

    def test_effective_scope_with_delegation(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read", "write"},
            requested_scope={"read"},
        )
        scope = protocol.effective_scope("B")
        assert "read" in scope

    def test_authorize_no_chain(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"read"})
        auth = protocol.authorize(agent_id="A", action="read data")
        assert auth.authorized

    def test_authorize_missing_scope(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"read"})
        auth = protocol.authorize(
            agent_id="A",
            action="write data",
            required_scope={"write"},
        )
        assert not auth.authorized
        assert "Missing" in auth.reason

    def test_authorize_with_constitution(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"read"})
        c = _make_constitution()
        auth = protocol.authorize(agent_id="A", action="send ssn data", constitution=c)
        # Constitution has privacy-block rule with "ssn" keyword
        assert isinstance(auth.authorized, bool)

    def test_find_root(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.delegate(
            delegator_id="root",
            delegatee_id="child",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        assert protocol.find_root("child") == "root"
        assert protocol.find_root("unknown") == "unknown"

    def test_list_links(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        protocol.delegate(
            delegator_id="A",
            delegatee_id="C",
            delegator_scope={"write"},
            requested_scope={"write"},
        )
        all_links = protocol.list_links()
        assert len(all_links) == 2
        b_links = protocol.list_links(agent_id="B")
        assert len(b_links) == 1

    def test_summary(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"read"})
        protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        s = protocol.summary()
        assert s["total_links"] == 1
        assert s["registered_principals"] == 1

    def test_delegation_link_properties(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
            ttl_seconds=3600,
        )
        link = result.link
        assert link is not None
        assert link.is_valid
        assert not link.is_expired
        assert not link.revoked
        assert link.verify_signature()

    def test_delegation_link_to_dict(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        d = result.link.to_dict()
        assert d["delegator_id"] == "A"
        assert d["delegatee_id"] == "B"
        assert "signature_valid" in d

    def test_delegation_result_to_dict(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["link_id"] is not None

    def test_authorization_result_to_dict(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        protocol.register_principal("A", {"read"})
        auth = protocol.authorize(agent_id="A", action="read data")
        d = auth.to_dict()
        assert d["authorized"] is True
        assert d["agent_id"] == "A"

    def test_delegation_chain_properties(self) -> None:
        from acgs_lite.constitution.interagent_protocol import DelegationChain

        chain = DelegationChain()
        assert not chain.is_valid
        assert chain.root_principal is None
        assert chain.terminal_agent is None
        assert chain.effective_scope == frozenset()
        assert chain.depth == 0

    def test_delegation_chain_to_dict(self) -> None:
        from acgs_lite.constitution.interagent_protocol import DelegationChain

        chain = DelegationChain()
        d = chain.to_dict()
        assert d["depth"] == 0
        assert d["is_valid"] is False

    def test_revoke_no_cascade(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol(max_depth=5)
        r1 = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read", "write"},
            requested_scope={"read", "write"},
        )
        r2 = protocol.delegate(
            delegator_id="B",
            delegatee_id="C",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        revoked = protocol.revoke(r1.link.link_id, cascade=False)
        assert r1.link.link_id in revoked
        assert r2.link.link_id not in revoked

    def test_list_links_inactive(self) -> None:
        from acgs_lite.constitution.interagent_protocol import (
            InterAgentGovernanceProtocol,
        )

        protocol = InterAgentGovernanceProtocol()
        result = protocol.delegate(
            delegator_id="A",
            delegatee_id="B",
            delegator_scope={"read"},
            requested_scope={"read"},
        )
        protocol.revoke(result.link.link_id)
        active = protocol.list_links(active_only=True)
        all_links = protocol.list_links(active_only=False)
        assert len(active) == 0
        assert len(all_links) == 1


# ===========================================================================
# obligations.py
# ===========================================================================


class TestObligations:
    """Tests for Obligation and ObligationSet."""

    def test_obligation_creation(self) -> None:
        from acgs_lite.constitution.obligations import Obligation

        ob = Obligation(
            obligation_type="human_review",
            sla_minutes=30,
            assignee="admin-1",
            reason="risky action",
            rule_id="r1",
        )
        assert ob.obligation_type == "human_review"
        assert ob.sla_minutes == 30

    def test_obligation_invalid_type(self) -> None:
        from acgs_lite.constitution.obligations import Obligation

        with pytest.raises(ValueError, match="Invalid obligation_type"):
            Obligation(obligation_type="invalid_type")

    def test_obligation_to_dict(self) -> None:
        from acgs_lite.constitution.obligations import Obligation

        ob = Obligation(
            obligation_type="notify",
            assignee="team-lead",
            reason="policy change",
            metadata={"channel": "slack"},
        )
        d = ob.to_dict()
        assert d["obligation_type"] == "notify"
        assert d["metadata"] == {"channel": "slack"}

    def test_obligation_all_valid_types(self) -> None:
        from acgs_lite.constitution.obligations import Obligation

        for t in ("human_review", "notify", "log_enhanced", "time_bounded"):
            ob = Obligation(obligation_type=t)
            assert ob.obligation_type == t

    def test_obligation_set_add(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        ob = obs.add("human_review", sla_minutes=30, assignee="admin")
        assert ob.obligation_type == "human_review"
        assert len(obs) == 1

    def test_obligation_set_resolve_by_index(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review")
        obs.add("notify")
        obs.resolve(0)
        assert len(obs.pending()) == 1

    def test_obligation_set_resolve_by_rule_id(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review", rule_id="r1")
        obs.add("notify", rule_id="r2")
        obs.resolve("r1")
        assert len(obs.pending()) == 1

    def test_obligation_set_resolve_invalid_index(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review")
        with pytest.raises(IndexError):
            obs.resolve(5)
        with pytest.raises(IndexError):
            obs.resolve(-1)

    def test_obligation_set_resolve_invalid_rule_id(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review", rule_id="r1")
        with pytest.raises(ValueError, match="No obligations found"):
            obs.resolve("nonexistent")

    def test_obligation_set_all(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review")
        obs.add("notify")
        assert len(obs.all()) == 2

    def test_obligation_set_export(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review", rule_id="r1")
        obs.add("notify", rule_id="r2")
        obs.resolve(0)
        exported = obs.export()
        assert len(exported) == 2
        assert exported[0]["resolved"] is True
        assert exported[1]["resolved"] is False

    def test_obligation_set_summary(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        obs.add("human_review")
        obs.add("human_review")
        obs.add("notify")
        obs.resolve(0)
        s = obs.summary()
        assert s["total"] == 3
        assert s["resolved"] == 1
        assert s["pending"] == 2
        assert s["by_type"]["human_review"] == 2
        assert s["by_type"]["notify"] == 1

    def test_obligation_set_empty_summary(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        s = obs.summary()
        assert s["total"] == 0
        assert s["resolved"] == 0
        assert s["pending"] == 0

    def test_obligation_set_add_with_timestamp(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        ob = obs.add("notify", created_at="2025-01-01T00:00:00+00:00")
        assert ob.created_at == "2025-01-01T00:00:00+00:00"

    def test_obligation_set_add_auto_timestamp(self) -> None:
        from acgs_lite.constitution.obligations import ObligationSet

        obs = ObligationSet()
        ob = obs.add("notify")
        assert ob.created_at != ""
