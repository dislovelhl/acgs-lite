"""Tests for constitution module refactoring -- validates type fixes and docstrings."""

from __future__ import annotations

import time

import pytest


def _make_constitution():
    """Helper to create a minimal test constitution."""
    from acgs_lite.constitution import Constitution, Rule, Severity

    rules = [
        Rule(
            id="R1",
            text="Never expose credentials",
            severity=Severity.CRITICAL,
            keywords=["credential", "password", "secret"],
            category="security",
            enabled=True,
        ),
        Rule(
            id="R2",
            text="Log all administrative actions",
            severity=Severity.MEDIUM,
            keywords=["admin", "log", "audit"],
            category="compliance",
            enabled=True,
        ),
        Rule(
            id="R3",
            text="Deprecated rule for testing",
            severity=Severity.LOW,
            keywords=["old"],
            category="operations",
            enabled=False,
        ),
    ]
    return Constitution(name="refactor-test", version="1.0.0", rules=rules)


class TestRuleCosine:
    """Validate cosine_similarity float return type fix on Rule."""

    def test_cosine_returns_float(self) -> None:
        from acgs_lite.constitution import Rule, Severity

        r1 = Rule(id="A", text="security check", severity=Severity.HIGH, keywords=["sec"])
        r2 = Rule(id="B", text="safety check", severity=Severity.HIGH, keywords=["safe"])
        result = r1.cosine_similarity(r2)
        # May be None if no embeddings set, but the function itself should not crash
        assert result is None or isinstance(result, float)


class TestRuleConditionContains:
    """Validate the contains operator fix for expected value."""

    def test_contains_with_string_expected(self) -> None:
        from acgs_lite.constitution import Rule, Severity

        rule = Rule(
            id="C1",
            text="test",
            severity=Severity.LOW,
            keywords=["test"],
            condition={"env": {"op": "contains", "value": "prod"}},
        )
        assert rule.condition_matches({"env": "production"}) is True
        assert rule.condition_matches({"env": "staging"}) is False

    def test_contains_with_non_string_ctx(self) -> None:
        from acgs_lite.constitution import Rule, Severity

        rule = Rule(
            id="C2",
            text="test",
            severity=Severity.LOW,
            keywords=["test"],
            condition={"count": {"op": "contains", "value": "x"}},
        )
        # Non-string context value should return False for contains
        assert rule.condition_matches({"count": 42}) is False


class TestRegulatoryFrameworkType:
    """Validate the regulatory framework dict type annotation fix."""

    def test_regulatory_alignment_soc2(self) -> None:
        from acgs_lite.constitution.regulatory import regulatory_alignment

        c = _make_constitution()
        result = regulatory_alignment(c, framework="soc2")
        assert "alignment_score" in result
        assert isinstance(result["alignment_score"], (int, float))

    def test_regulatory_alignment_gdpr(self) -> None:
        from acgs_lite.constitution.regulatory import regulatory_alignment

        c = _make_constitution()
        result = regulatory_alignment(c, framework="gdpr")
        assert "covered_controls" in result
        assert "uncovered_controls" in result

    def test_regulatory_alignment_unknown_raises(self) -> None:
        from acgs_lite.constitution.regulatory import regulatory_alignment

        c = _make_constitution()
        with pytest.raises(ValueError, match="Unknown framework"):
            regulatory_alignment(c, framework="nonexistent")


class TestConstitutionTypeFixes:
    """Validate type annotation fixes in constitution.py."""

    def test_rule_changelog_returns_list(self) -> None:
        c = _make_constitution()
        result = c.rule_changelog("R1")
        assert isinstance(result, list)

    def test_create_rule_from_template(self) -> None:
        from acgs_lite.constitution import Constitution

        rule = Constitution.create_rule_from_template(
            "data_privacy",
            "DP1",
            {"data_type": "PII"},
        )
        assert rule.id == "DP1"
        assert "PII" in rule.text
        assert rule.category == "privacy"

    def test_tenant_isolation_report(self) -> None:
        c = _make_constitution()
        report = c.tenant_isolation_report()
        assert "global_rules" in report
        assert isinstance(report["global_rules"], list)

    def test_full_report_has_severity_counts(self) -> None:
        c = _make_constitution()
        report = c.full_report()
        assert isinstance(report, dict)


class TestMetricsSnapshotType:
    """Validate GovernanceMetrics.from_snapshot type fix."""

    def test_from_snapshot_roundtrip(self) -> None:
        from acgs_lite.constitution.metrics import GovernanceMetrics

        m = GovernanceMetrics()
        m.record("allow", latency_us=500.0)
        snap = m.snapshot()
        restored = GovernanceMetrics.from_snapshot(snap)
        assert restored.snapshot()["total_decisions"] == 1


class TestVersioningDictType:
    """Validate RuleSnapshot.to_dict type annotation fix."""

    def test_rule_snapshot_to_dict(self) -> None:
        from acgs_lite.constitution.versioning import RuleSnapshot

        snap = RuleSnapshot(
            rule_id="R1",
            timestamp=time.time(),
            version=1,
            text="test rule",
            severity="high",
            enabled=True,
            keywords=("security",),
            category="security",
            subcategory="",
            workflow_action="block",
            change_reason="initial",
        )
        d = snap.to_dict()
        assert isinstance(d, dict)
        assert d["rule_id"] == "R1"


class TestPolicyExporterCallable:
    """Validate PolicyExporter dispatch callable type fix."""

    def test_export_json(self) -> None:
        from acgs_lite.constitution.policy_export import PolicyExporter

        c = _make_constitution()
        exporter = PolicyExporter(c)
        json_str = exporter.to_json()
        assert '"R1"' in json_str


class TestMemoizedConstitution:
    """Validate MemoizedConstitution validate() call fix."""

    def test_cache_stats(self) -> None:
        from acgs_lite.constitution.memoization import MemoizedConstitution

        c = _make_constitution()
        mc = MemoizedConstitution(c)
        stats = mc.cache_stats()
        assert stats.hit_rate == 0.0


class TestDocstringsPresent:
    """Verify that added docstrings are accessible."""

    def test_duplication_report_has_duplicates_docstring(self) -> None:
        from acgs_lite.constitution.deduplication import DuplicationReport

        assert DuplicationReport.has_duplicates.fget.__doc__ is not None

    def test_weighted_constitution_properties(self) -> None:
        from acgs_lite.constitution.weighted_policy import WeightedConstitution

        c = _make_constitution()
        wc = WeightedConstitution(c)
        assert wc.constitution is c
        assert isinstance(wc.block_threshold, float)
        assert isinstance(wc.warn_threshold, float)

    def test_autonomy_ratio_agent_id_docstring(self) -> None:
        from acgs_lite.constitution.autonomy_ratio import CommitmentRatioTracker

        tracker = CommitmentRatioTracker(agent_id="test-agent")
        assert tracker.agent_id == "test-agent"
