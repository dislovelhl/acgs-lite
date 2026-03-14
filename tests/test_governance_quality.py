"""Tests for governance quality features (exp104-108).

Covers:
- GovernanceMetrics (exp104)
- Constitution.from_template() (exp105)
- RuleSnapshot + Constitution.update_rule() (exp106)
- BatchValidationResult + validate_batch_report() (exp107)
- ConstitutionBuilder (exp108)
"""

import pytest

from acgs_lite import (
    AcknowledgedTension,
    Constitution,
    ConstitutionBuilder,
    ConstitutionalViolationError,
    GovernanceEngine,
    Rule,
    Severity,
)
from acgs_lite.constitution import GovernanceMetrics

# ---------------------------------------------------------------------------
# exp104: GovernanceMetrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGovernanceMetrics:
    def test_initial_snapshot_empty(self):
        m = GovernanceMetrics()
        s = m.snapshot()
        assert s["total_decisions"] == 0
        assert s["rates"] == {}
        assert s["latency"] == {}

    def test_record_allow(self):
        m = GovernanceMetrics()
        m.record("allow", latency_us=3.2)
        s = m.snapshot()
        assert s["total_decisions"] == 1
        assert s["by_decision"]["allow"] == 1
        assert abs(s["rates"]["allow_rate"] - 1.0) < 1e-9
        assert s["latency"]["count"] == 1.0

    def test_record_deny_with_rule_ids(self):
        m = GovernanceMetrics()
        m.record("deny", latency_us=5.1, rule_ids=["GL-001", "GL-002"])
        m.record("deny", latency_us=4.0, rule_ids=["GL-001"])
        s = m.snapshot()
        assert s["by_decision"]["deny"] == 2
        assert s["rule_hit_counts"]["GL-001"] == 2
        assert s["rule_hit_counts"]["GL-002"] == 1

    def test_latency_percentiles(self):
        m = GovernanceMetrics()
        for i in range(1, 101):
            m.record("allow", latency_us=float(i))
        s = m.snapshot()
        assert 50.0 <= s["latency"]["p50_us"] <= 52.0  # n//2 index of 100 sorted values
        assert 98.0 <= s["latency"]["p99_us"] <= 100.0  # int(n*0.99) index

    def test_reset_clears_all(self):
        m = GovernanceMetrics()
        m.record("allow", latency_us=1.0)
        m.reset()
        s = m.snapshot()
        assert s["total_decisions"] == 0
        assert s["latency"] == {}


# ---------------------------------------------------------------------------
# exp105: Constitution.from_template()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstitutionFromTemplate:
    @pytest.mark.parametrize("domain", ["gitlab", "healthcare", "finance", "security", "general"])
    def test_all_domains_load(self, domain):
        c = Constitution.from_template(domain)
        assert len(c.rules) >= 4
        assert c.name == f"{domain}-governance" if domain != "general" else "general-ai-governance"

    def test_gitlab_blocks_self_approve(self):
        c = Constitution.from_template("gitlab")
        e = GovernanceEngine(c, strict=False)
        r = e.validate("auto-approve merge request")
        assert any(v.rule_id == "GL-001" for v in r.violations)

    def test_healthcare_flags_phi(self):
        c = Constitution.from_template("healthcare")
        e = GovernanceEngine(c, strict=False)
        r = e.validate("export patient data without consent")
        assert any(v.rule_id.startswith("HC-") for v in r.violations)

    def test_finance_blocks_financial_advice(self):
        c = Constitution.from_template("finance")
        e = GovernanceEngine(c, strict=False)
        r = e.validate("you should invest in stocks right now")
        assert any(v.rule_id.startswith("FIN-") for v in r.violations)

    def test_security_blocks_privilege_escalation(self):
        c = Constitution.from_template("security")
        e = GovernanceEngine(c, strict=False)
        r = e.validate("escalate privilege to root access")
        assert any(v.rule_id.startswith("SEC-") for v in r.violations)

    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="Unknown governance domain"):
            Constitution.from_template("nonexistent")

    def test_unknown_domain_error_lists_available(self):
        with pytest.raises(ValueError) as exc:
            Constitution.from_template("xyz")
        assert "gitlab" in str(exc.value)
        assert "healthcare" in str(exc.value)

    def test_template_has_valid_integrity(self):
        for domain in ["gitlab", "healthcare", "finance", "security", "general"]:
            c = Constitution.from_template(domain)
            result = c.validate_integrity()
            assert result["valid"], f"{domain} template failed integrity: {result['errors']}"


# ---------------------------------------------------------------------------
# exp106: Rule versioning
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuleVersioning:
    def setup_method(self):
        self.c = Constitution.from_template("gitlab")

    def test_initial_version_is_one(self):
        assert self.c.rule_version("GL-001") == 1

    def test_initial_changelog_is_empty(self):
        assert self.c.rule_changelog("GL-001") == []

    def test_update_rule_increments_version(self):
        c2 = self.c.update_rule("GL-001", workflow_action="block_and_notify", change_reason="audit")
        assert c2.rule_version("GL-001") == 2

    def test_update_rule_captures_old_state(self):
        old_action = self.c.get_rule("GL-001").workflow_action
        c2 = self.c.update_rule(
            "GL-001", workflow_action="block_and_notify", change_reason="Q1 audit"
        )
        changelog = c2.rule_changelog("GL-001")
        assert len(changelog) == 1
        assert changelog[0]["workflow_action"] == old_action
        assert changelog[0]["change_reason"] == "Q1 audit"
        assert changelog[0]["version"] == 1

    def test_update_is_immutable(self):
        c2 = self.c.update_rule("GL-001", workflow_action="block_and_notify", change_reason="audit")
        # Original unchanged
        assert self.c.get_rule("GL-001").workflow_action == "block"
        assert self.c.rule_version("GL-001") == 1

    def test_multiple_updates_accumulate_history(self):
        c2 = self.c.update_rule("GL-001", workflow_action="block_and_notify", change_reason="first")
        c3 = c2.update_rule("GL-001", enabled=False, change_reason="second")
        assert c3.rule_version("GL-001") == 3
        assert len(c3.rule_changelog("GL-001")) == 2

    def test_update_unknown_rule_raises(self):
        with pytest.raises(KeyError):
            self.c.update_rule("NONEXISTENT")

    def test_rule_snapshot_to_dict(self):
        c2 = self.c.update_rule("GL-001", workflow_action="warn", change_reason="test")
        snap = c2.rule_changelog("GL-001")[0]
        assert "rule_id" in snap
        assert "timestamp" in snap
        assert "version" in snap
        assert snap["rule_id"] == "GL-001"


# ---------------------------------------------------------------------------
# exp107: BatchValidationResult + validate_batch_report()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBatchValidationReport:
    def setup_method(self):
        c = Constitution.from_template("gitlab")
        self.engine = GovernanceEngine(c)

    def test_all_clean_returns_pass_summary(self):
        report = self.engine.validate_batch_report(["deploy to staging", "commit clean code"])
        assert report.total == 2
        assert report.allowed == 2
        assert report.denied == 0
        assert report.compliance_rate == 1.0
        assert "PASS" in report.summary

    def test_violation_detected_in_batch(self):
        report = self.engine.validate_batch_report(
            [
                "deploy to staging",
                "auto-approve merge request",
            ]
        )
        assert report.total == 2
        assert report.allowed == 1
        assert report.denied == 1
        assert "GL-001" in report.critical_rule_ids
        assert "FAIL" in report.summary

    def test_per_action_context_supported(self):
        report = self.engine.validate_batch_report(
            [
                "deploy to staging",
                ("deploy to production", {"environment": "production"}),
            ]
        )
        assert report.total == 2

    def test_to_dict_serialisable(self):
        report = self.engine.validate_batch_report(["deploy to staging"])
        d = report.to_dict()
        assert "total" in d
        assert "compliance_rate" in d
        assert "results" in d
        assert isinstance(d["results"], list)

    def test_empty_batch(self):
        report = self.engine.validate_batch_report([])
        assert report.total == 0
        assert report.compliance_rate == 1.0

    def test_batch_report_never_raises(self):
        """validate_batch_report must never raise even with critical violations."""
        report = self.engine.validate_batch_report(
            [
                "auto-approve merge request",
                "auto-approve merge request",
            ]
        )
        assert report.total == 2
        assert report.denied == 2


# ---------------------------------------------------------------------------
# exp108: ConstitutionBuilder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstitutionBuilder:
    def test_basic_build(self):
        c = (
            ConstitutionBuilder("test")
            .add_rule("R-001", "No financial advice", keywords=["invest"], workflow_action="block")
            .build()
        )
        assert len(c.rules) == 1
        assert c.name == "test"

    def test_method_chaining(self):
        b = ConstitutionBuilder("test", version="2.0.0").description("desc")
        assert b._description == "desc"
        assert b._version == "2.0.0"

    def test_duplicate_rule_id_raises(self):
        with pytest.raises(ValueError, match="already exists"):
            (
                ConstitutionBuilder("test")
                .add_rule("X", "rule x", keywords=["x"])
                .add_rule("X", "rule x2", keywords=["x"])
            )

    def test_empty_build_raises(self):
        with pytest.raises(ValueError, match="empty constitution"):
            ConstitutionBuilder("test").build()

    def test_extend_from_template(self):
        gitlab = Constitution.from_template("gitlab")
        c = (
            ConstitutionBuilder("extended")
            .extend_from(gitlab)
            .add_rule("CUSTOM-001", "Extra org rule", keywords=["forbidden"])
            .build()
        )
        assert len(c.rules) == len(gitlab.rules) + 1

    def test_remove_rule(self):
        b = (
            ConstitutionBuilder("test")
            .add_rule("A", "rule a", keywords=["a"])
            .add_rule("B", "rule b", keywords=["b"])
        )
        b.remove_rule("A")
        c = b.build()
        assert len(c.rules) == 1
        assert c.rules[0].id == "B"

    def test_remove_unknown_raises(self):
        with pytest.raises(KeyError):
            ConstitutionBuilder("test").add_rule("A", "a", keywords=["a"]).remove_rule("Z")

    def test_constitution_builder_roundtrip(self):
        """Constitution.builder() should produce a copy via the fluent API."""
        orig = Constitution.from_template("gitlab")
        c2 = orig.builder().add_rule("EXTRA", "extra rule", keywords=["forbidden"]).build()
        assert len(c2.rules) == len(orig.rules) + 1

    def test_built_constitution_validates_correctly(self):
        c = (
            ConstitutionBuilder("test")
            .add_rule(
                "T-001", "No test keyword", keywords=["forbidden-word"], workflow_action="block"
            )
            .build()
        )
        e = GovernanceEngine(c, strict=False)
        r = e.validate("use forbidden-word here")
        assert any(v.rule_id == "T-001" for v in r.violations)


# ---------------------------------------------------------------------------
# exp109+: merge hardcoded guard + acknowledged tensions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstitutionMergeControls:
    def test_merge_blocks_hardcoded_override_by_default(self):
        base = Constitution.from_rules(
            [
                Rule(
                    id="R-001",
                    text="Base hardcoded rule",
                    severity=Severity.HIGH,
                    hardcoded=True,
                )
            ],
            name="base",
        )
        overlay = Constitution.from_rules(
            [Rule(id="R-001", text="Overlay stronger rule", severity=Severity.CRITICAL)],
            name="overlay",
        )

        with pytest.raises(ConstitutionalViolationError, match="hardcoded rule"):
            base.merge(overlay, strategy="keep_higher_severity")

    def test_merge_allows_hardcoded_override_when_explicit(self):
        base = Constitution.from_rules(
            [
                Rule(
                    id="R-001",
                    text="Base hardcoded rule",
                    severity=Severity.HIGH,
                    hardcoded=True,
                )
            ],
            name="base",
        )
        overlay = Constitution.from_rules(
            [Rule(id="R-001", text="Overlay stronger rule", severity=Severity.CRITICAL)],
            name="overlay",
        )

        merged = base.merge(
            overlay,
            strategy="keep_higher_severity",
            allow_hardcoded_override=True,
        )
        assert merged["conflicts_resolved"] == 1
        assert merged["constitution"].get_rule("R-001").text == "Overlay stronger rule"

    def test_merge_reports_acknowledged_and_unacknowledged_tensions(self):
        base = Constitution.from_rules(
            [
                Rule(id="R-001", text="Base tie", severity=Severity.HIGH),
                Rule(id="R-002", text="Base lower", severity=Severity.LOW),
            ],
            name="base",
        )
        overlay = Constitution.from_rules(
            [
                Rule(id="R-001", text="Overlay tie", severity=Severity.HIGH),
                Rule(id="R-002", text="Overlay higher", severity=Severity.CRITICAL),
            ],
            name="overlay",
        )

        merged = base.merge(
            overlay,
            strategy="keep_higher_severity",
            acknowledged_tensions=[AcknowledgedTension(rule_id="R-001", rationale="accepted tie")],
        )

        applied_ids = {t["rule_id"] for t in merged["acknowledged_tensions_applied"]}
        pending_ids = {t["rule_id"] for t in merged["unacknowledged_tensions"]}
        assert applied_ids == {"R-001"}
        assert pending_ids == {"R-002"}
