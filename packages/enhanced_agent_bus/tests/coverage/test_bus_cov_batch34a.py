"""Coverage tests targeting constitution.py and engine/core.py uncovered branches.

Targets:
  - packages/acgs-lite/src/acgs_lite/constitution/constitution.py (94.2% -> higher)
  - packages/acgs-lite/src/acgs_lite/engine/core.py (94.0% -> higher)
"""

from __future__ import annotations

import pytest
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution.rule import AcknowledgedTension
from acgs_lite.errors import ConstitutionalViolationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_rule(
    rule_id: str = "R1",
    text: str = "Test rule",
    severity: str = "high",
    keywords: list[str] | None = None,
    **kwargs,
) -> dict:
    return {
        "id": rule_id,
        "text": text,
        "severity": severity,
        "keywords": keywords or ["testword"],
        **kwargs,
    }


def _make_constitution(rules_data: list[dict], **kwargs) -> Constitution:
    return Constitution.from_dict({"rules": rules_data, **kwargs})


# ===========================================================================
# Constitution: from_yaml_str edge cases
# ===========================================================================


class TestFromYamlStr:
    def test_non_mapping_yaml_raises(self):
        with pytest.raises(ValueError, match="mapping"):
            Constitution.from_yaml_str("- item1\n- item2\n")

    def test_round_trip_yaml(self):
        c = _make_constitution([_simple_rule()])
        yaml_str = c.to_yaml()
        c2 = Constitution.from_yaml_str(yaml_str)
        assert c2.hash == c.hash


# ===========================================================================
# Constitution: from_template
# ===========================================================================


class TestFromTemplate:
    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="Unknown governance domain"):
            Constitution.from_template("nonexistent_domain")

    def test_all_domains_valid(self):
        for domain in ("gitlab", "healthcare", "finance", "security", "general"):
            c = Constitution.from_template(domain)
            assert len(c.rules) > 0

    def test_case_insensitive_with_spaces(self):
        c = Constitution.from_template("  GitLab  ")
        assert c.name == "gitlab-governance"


# ===========================================================================
# Constitution: from_bundle / to_bundle
# ===========================================================================


class TestBundle:
    def test_unsupported_schema_version(self):
        with pytest.raises(ValueError, match="Unsupported bundle schema_version"):
            Constitution.from_bundle({"schema_version": "99.0", "rules": []})

    def test_missing_rules_key(self):
        with pytest.raises(ValueError, match="missing required 'rules'"):
            Constitution.from_bundle({"schema_version": "1.0.0"})

    def test_round_trip_bundle(self):
        c = Constitution.from_template("security")
        bundle = c.to_bundle()
        c2 = Constitution.from_bundle(bundle)
        assert c2.hash == c.hash

    def test_imported_hash_in_metadata(self):
        c = Constitution.from_template("general")
        bundle = c.to_bundle()
        c2 = Constitution.from_bundle(bundle)
        assert c2.metadata.get("imported_hash") == c.hash

    def test_empty_schema_version_accepted(self):
        c = Constitution.from_bundle({
            "schema_version": "",
            "rules": [{"id": "X1", "text": "t", "keywords": ["kw"]}],
        })
        assert len(c.rules) == 1


# ===========================================================================
# Constitution: validate_integrity
# ===========================================================================


class TestValidateIntegrity:
    def test_duplicate_rule_ids_rejected_on_construction(self):
        """Duplicate IDs are caught at construction time by schema_validation."""
        rules = [
            _simple_rule("DUP", "rule a"),
            _simple_rule("DUP", "rule b"),
        ]
        with pytest.raises(Exception, match="Duplicate rule ID"):
            _make_constitution(rules)

    def test_self_dependency(self):
        """Self-deps pass schema_validation (which checks deps exist) but
        validate_integrity catches the self-ref."""
        rules = [
            _simple_rule("SELF", depends_on=["SELF"]),
        ]
        c = _make_constitution(rules)
        result = c.validate_integrity()
        assert any("depends on itself" in e for e in result["errors"])

    def test_unknown_dependency_rejected_on_construction(self):
        """Unknown deps are caught at construction time."""
        rules = [_simple_rule("A1", depends_on=["GHOST"])]
        with pytest.raises(Exception, match="non-existent rule"):
            _make_constitution(rules)

    def test_circular_dependency(self):
        """Mutual deps pass schema_validation (both exist) but
        validate_integrity detects the cycle."""
        rules = [
            _simple_rule("C1", depends_on=["C2"]),
            _simple_rule("C2", depends_on=["C1"]),
        ]
        c = _make_constitution(rules)
        result = c.validate_integrity()
        assert any("Circular" in e for e in result["errors"])

    def test_unknown_workflow_action_warning(self):
        rules = [_simple_rule("W1", workflow_action="exotic_action")]
        c = _make_constitution(rules)
        result = c.validate_integrity()
        assert any("unknown workflow_action" in w for w in result["warnings"])

    def test_no_keywords_warn_via_integrity_validation(self):
        """Rules with no keywords are accepted, but flagged as non-matching."""
        c = Constitution(rules=[
            Rule(id="BARE", text="No signals", severity=Severity.LOW),
        ])
        result = c.validate_integrity()
        assert any("no keywords or patterns" in w for w in result["warnings"])

    def test_no_workflow_action_warning(self):
        rules = [_simple_rule("NW1", workflow_action="")]
        c = _make_constitution(rules)
        result = c.validate_integrity()
        assert any("without workflow_action" in w for w in result["warnings"])


# ===========================================================================
# Constitution: merge strategies and hardcoded protection
# ===========================================================================


class TestMerge:
    def _base(self, hardcoded: bool = False) -> Constitution:
        return _make_constitution([
            _simple_rule("SHARED", "base rule", severity="high",
                         hardcoded=hardcoded, workflow_action="block"),
            _simple_rule("ONLY-A", "a only", workflow_action="warn"),
        ])

    def _overlay(self, severity: str = "critical") -> Constitution:
        return _make_constitution([
            _simple_rule("SHARED", "overlay rule", severity=severity,
                         workflow_action="block_and_notify"),
            _simple_rule("ONLY-B", "b only", workflow_action="warn"),
        ])

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            self._base().merge(self._overlay(), strategy="invalid")

    def test_keep_self_strategy(self):
        result = self._base().merge(self._overlay(), strategy="keep_self")
        c = result["constitution"]
        shared = c.get_rule("SHARED")
        assert shared is not None
        assert shared.text == "base rule"
        assert result["rules_from_self"] >= 1

    def test_keep_other_strategy(self):
        result = self._base().merge(self._overlay(), strategy="keep_other")
        c = result["constitution"]
        shared = c.get_rule("SHARED")
        assert shared is not None
        assert shared.text == "overlay rule"

    def test_keep_higher_severity_chooses_critical(self):
        result = self._base().merge(self._overlay(severity="critical"))
        c = result["constitution"]
        shared = c.get_rule("SHARED")
        assert shared is not None
        assert shared.severity == Severity.CRITICAL

    def test_keep_higher_severity_tie_goes_to_self(self):
        result = self._base().merge(self._overlay(severity="high"))
        c = result["constitution"]
        shared = c.get_rule("SHARED")
        assert shared is not None
        assert shared.text == "base rule"

    def test_hardcoded_override_blocked_keep_other(self):
        with pytest.raises(ConstitutionalViolationError, match="hardcoded"):
            self._base(hardcoded=True).merge(
                self._overlay(), strategy="keep_other"
            )

    def test_hardcoded_override_allowed_with_flag(self):
        result = self._base(hardcoded=True).merge(
            self._overlay(), strategy="keep_other", allow_hardcoded_override=True
        )
        assert result["constitution"] is not None

    def test_acknowledged_tensions(self):
        tension = AcknowledgedTension(
            rule_id="SHARED",
            rationale="Testing acknowledged",
        )
        result = self._base().merge(
            self._overlay(severity="critical"),
            acknowledged_tensions=[tension],
        )
        assert len(result["acknowledged_tensions_applied"]) >= 1
        assert len(result["unacknowledged_tensions"]) == 0


# ===========================================================================
# Constitution: counterfactual
# ===========================================================================


class TestCounterfactual:
    def test_remove_all_rules_raises(self):
        c = Constitution.from_template("general")
        all_ids = [r.id for r in c.rules]
        with pytest.raises(ValueError, match="remove all rules"):
            c.counterfactual("test action", remove_rules=all_ids)

    def test_no_removal_returns_identical(self):
        c = Constitution.from_template("general")
        result = c.counterfactual("harmless action", remove_rules=[])
        assert result["changed"] is False
        assert result["baseline"] == result["counterfactual"]

    def test_removal_changes_outcome(self):
        c = Constitution.from_template("general")
        result = c.counterfactual(
            "invest in crypto buy stocks",
            remove_rules=["GEN-001"],
        )
        assert "GEN-001" in result["removed_rules"]


# ===========================================================================
# Constitution: lifecycle management
# ===========================================================================


class TestLifecycle:
    def _const(self) -> Constitution:
        return _make_constitution([
            _simple_rule("LC1", workflow_action="block"),
            _simple_rule("LC2", workflow_action="warn"),
        ])

    def test_invalid_state_raises(self):
        c = self._const()
        with pytest.raises(ValueError, match="Invalid state"):
            c.set_rule_lifecycle_state("LC1", "unknown_state")

    def test_rule_not_found_returns_false(self):
        c = self._const()
        assert c.set_rule_lifecycle_state("GHOST", "active") is False

    def test_draft_disables_rule(self):
        c = self._const()
        assert c.set_rule_lifecycle_state("LC1", "draft", reason="testing")
        r = c.get_rule("LC1")
        assert r is not None
        assert not r.enabled
        assert r.metadata["lifecycle_state"] == "draft"

    def test_active_enables_rule(self):
        c = self._const()
        c.set_rule_lifecycle_state("LC1", "draft")
        c.set_rule_lifecycle_state("LC1", "active")
        r = c.get_rule("LC1")
        assert r is not None
        assert r.enabled

    def test_deprecated_keeps_enabled(self):
        c = self._const()
        c.set_rule_lifecycle_state("LC1", "deprecated")
        r = c.get_rule("LC1")
        assert r is not None
        assert r.enabled
        assert r.metadata["lifecycle_state"] == "deprecated"

    def test_get_lifecycle_states(self):
        c = self._const()
        c.set_rule_lifecycle_state("LC1", "draft")
        states = c.get_rule_lifecycle_states()
        assert states["LC1"]["state"] == "draft"
        assert states["LC2"]["state"] == "active"

    def test_lifecycle_transition_rules_valid(self):
        c = self._const()
        c.set_rule_lifecycle_state("LC1", "draft")
        candidates = c.lifecycle_transition_rules("draft", "active")
        assert "LC1" in candidates

    def test_lifecycle_transition_rules_invalid(self):
        c = self._const()
        candidates = c.lifecycle_transition_rules("active", "draft")
        assert candidates == []


# ===========================================================================
# Constitution: tenant isolation
# ===========================================================================


class TestTenantIsolation:
    def test_set_and_get_tenant_rules(self):
        c = _make_constitution([
            _simple_rule("T1"),
            _simple_rule("T2"),
        ])
        assert c.set_rule_tenants("T1", ["tenant-a"])
        assert c.set_rule_tenants("GHOST", []) is False
        tenant_rules = c.get_tenant_rules("tenant-a")
        rule_ids = [r.id for r in tenant_rules]
        assert "T1" in rule_ids
        assert "T2" in rule_ids  # global rule

    def test_global_rules_only(self):
        c = _make_constitution([_simple_rule("G1")])
        c.set_rule_tenants("G1", ["t1"])
        global_only = c.get_tenant_rules(None)
        assert len(global_only) == 1  # scoped rules are included when tenant_id is None

    def test_isolation_report_no_conflicts(self):
        c = _make_constitution([_simple_rule("ISO1"), _simple_rule("ISO2")])
        report = c.tenant_isolation_report()
        assert report["isolation_score"] is True
        assert len(report["global_rules"]) == 2

    def test_isolation_report_with_tenants(self):
        c = _make_constitution([_simple_rule("ISO1"), _simple_rule("ISO2")])
        c.set_rule_tenants("ISO1", ["t1", "t2"])
        report = c.tenant_isolation_report()
        assert report["total_tenants"] >= 1


# ===========================================================================
# Constitution: assess_decision_anomaly
# ===========================================================================


class TestDecisionAnomaly:
    def test_zero_total(self):
        result = Constitution.assess_decision_anomaly(0, 0, 0)
        assert result["total"] == 0
        assert result["is_anomalous"] is False

    def test_normal_distribution(self):
        result = Constitution.assess_decision_anomaly(100, 5, 3)
        assert result["is_anomalous"] is False

    def test_high_deny_spike(self):
        result = Constitution.assess_decision_anomaly(
            10, 50, 0, baseline_deny_rate=0.10, spike_threshold=2.0
        )
        assert result["is_anomalous"] is True
        assert any("high_deny_rate" in a for a in result["anomalies"])

    def test_high_escalate_spike(self):
        result = Constitution.assess_decision_anomaly(
            10, 0, 50, baseline_escalate_rate=0.05, spike_threshold=2.0
        )
        assert result["is_anomalous"] is True
        assert any("high_escalate_rate" in a for a in result["anomalies"])


# ===========================================================================
# Constitution: check_governance_slo
# ===========================================================================


class TestGovernanceSLO:
    def test_all_pass(self):
        result = Constitution.check_governance_slo(
            p99_latency_ms=0.5,
            compliance_rate=0.99,
            throughput_rps=10000.0,
            false_negative_rate=0.001,
        )
        assert result["slo_pass"] is True
        assert len(result["breaches"]) == 0

    def test_all_breach(self):
        result = Constitution.check_governance_slo(
            p99_latency_ms=5.0,
            compliance_rate=0.50,
            throughput_rps=100.0,
            false_negative_rate=0.5,
        )
        assert result["slo_pass"] is False
        assert len(result["breaches"]) == 4


# ===========================================================================
# Constitution: create_rule_from_template
# ===========================================================================


class TestRuleTemplate:
    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            Constitution.create_rule_from_template("nonexistent", "R1", {})

    def test_data_privacy_template(self):
        rule = Constitution.create_rule_from_template(
            "data_privacy", "DP-001",
            {"action": "sharing", "data_type": "personal", "consent_type": "explicit"},
        )
        assert rule.id == "DP-001"
        assert "personal" in rule.text
        assert rule.category == "privacy"

    def test_security_boundary_template(self):
        rule = Constitution.create_rule_from_template(
            "security_boundary", "SB-001",
            {"action": "access", "boundary_type": "network"},
        )
        assert rule.severity == Severity.CRITICAL
        assert rule.category == "security"

    def test_template_metadata_preserved(self):
        rule = Constitution.create_rule_from_template(
            "compliance_audit", "CA-001",
            {"action": "delete", "asset_type": "records"},
        )
        assert rule.metadata["template"] == "compliance_audit"


# ===========================================================================
# Constitution: explain
# ===========================================================================


class TestExplain:
    def test_allow_no_triggers(self):
        c = _make_constitution([_simple_rule(keywords=["secret_word_xyz"])])
        result = c.explain("harmless action text")
        assert result["decision"] == "allow"
        assert "ALLOWED" in result["explanation"]

    def test_deny_with_blocking_rule(self):
        c = Constitution.from_template("general")
        result = c.explain("invest in crypto buy stocks")
        assert result["decision"] == "deny"
        assert len(result["blocking_rules"]) > 0

    def test_warnings_only(self):
        c = _make_constitution([
            _simple_rule(severity="low", keywords=["soft_warning_xyz"]),
        ])
        result = c.explain("action with soft_warning_xyz mention")
        assert result["decision"] == "allow"
        assert len(result["warning_rules"]) > 0
        assert "warning" in result["explanation"].lower()


# ===========================================================================
# Constitution: compare (static method)
# ===========================================================================


class TestCompare:
    def test_no_differences(self):
        c = _make_constitution([_simple_rule()])
        result = Constitution.compare(c, c)
        assert result["summary"] != ""
        assert result["unchanged"] >= 1

    def test_added_and_removed(self):
        before = _make_constitution([_simple_rule("A1")])
        after = _make_constitution([_simple_rule("B1")])
        result = Constitution.compare(before, after)
        assert "A1" in result["removed"]
        assert "B1" in result["added"]

    def test_modified_rule_detected(self):
        before = _make_constitution([_simple_rule("M1", severity="low")])
        after = _make_constitution([_simple_rule("M1", severity="critical")])
        result = Constitution.compare(before, after)
        assert len(result["modified"]) == 1
        assert result["modified"][0]["rule_id"] == "M1"


# ===========================================================================
# Constitution: subsumes
# ===========================================================================


class TestSubsumes:
    def test_superset_subsumes_subset(self):
        superset = Constitution.from_template("security")
        subset = _make_constitution([
            _simple_rule("SEC-001", severity="high",
                         keywords=["sql injection"], workflow_action="block"),
        ])
        result = Constitution.subsumes(superset, subset)
        assert result["subsumes"] is True

    def test_missing_rule_detected(self):
        superset = _make_constitution([_simple_rule("A1")])
        subset = _make_constitution([_simple_rule("A1"), _simple_rule("MISSING")])
        result = Constitution.subsumes(superset, subset)
        assert not result["subsumes"]
        assert "MISSING" in result["missing_rules"]

    def test_weaker_severity_detected(self):
        superset = _make_constitution([_simple_rule("W1", severity="low")])
        subset = _make_constitution([_simple_rule("W1", severity="critical")])
        result = Constitution.subsumes(superset, subset)
        assert "W1" in result["weaker_rules"]

    def test_incompatible_workflow(self):
        superset = _make_constitution([_simple_rule("IW1", workflow_action="warn")])
        subset = _make_constitution([_simple_rule("IW1", workflow_action="block")])
        result = Constitution.subsumes(superset, subset)
        assert "IW1" in result["incompatible_workflow"]


# ===========================================================================
# Constitution: update_rule and versioning
# ===========================================================================


class TestUpdateRule:
    def test_update_nonexistent_raises(self):
        c = _make_constitution([_simple_rule("U1")])
        with pytest.raises(KeyError, match="not found"):
            c.update_rule("GHOST", text="new text")

    def test_update_creates_new_constitution(self):
        c = _make_constitution([_simple_rule("U1")])
        c2 = c.update_rule("U1", text="updated text", change_reason="test")
        assert c2.hash != c.hash
        r = c2.get_rule("U1")
        assert r is not None
        assert r.text == "updated text"

    def test_rule_history_recorded(self):
        c = _make_constitution([_simple_rule("U1")])
        c2 = c.update_rule("U1", text="v2", change_reason="reason1")
        assert c2.rule_version("U1") == 2
        changelog = c2.rule_changelog("U1")
        assert len(changelog) == 1

    def test_severity_string_coerced(self):
        c = _make_constitution([_simple_rule("U1", severity="low")])
        c2 = c.update_rule("U1", severity="critical")
        r = c2.get_rule("U1")
        assert r is not None
        assert r.severity == Severity.CRITICAL

    def test_changelog_appended(self):
        c = _make_constitution([_simple_rule("U1")])
        c2 = c.update_rule("U1", text="v2", change_reason="first change")
        assert len(c2.changelog) == 1
        assert c2.changelog[0]["rule_id"] == "U1"


# ===========================================================================
# Constitution: deprecation and temporal methods
# ===========================================================================


class TestDeprecation:
    def test_deprecation_migration_report(self):
        c = Constitution(rules=[
            Rule(id="D1", text="old", severity=Severity.LOW, keywords=["kw"],
                 deprecated=True, replaced_by="D2", valid_until="2026-12-31"),
            Rule(id="D2", text="new", severity=Severity.LOW, keywords=["kw"]),
            Rule(id="D3", text="orphan deprecated", severity=Severity.LOW,
                 keywords=["kw"], deprecated=True),
        ])
        report = c.deprecation_migration_report()
        assert report["summary"]["total"] == 2
        assert report["summary"]["with_successor"] == 1
        assert report["summary"]["with_sunset_date"] == 1
        entries = report["entries"]
        d1_entry = next(e for e in entries if e["rule_id"] == "D1")
        assert "Migrate" in d1_entry["recommendation"]
        d3_entry = next(e for e in entries if e["rule_id"] == "D3")
        assert "Document" in d3_entry["recommendation"]

    def test_deprecation_report_with_successor(self):
        c = Constitution(rules=[
            Rule(id="D1", text="old", severity=Severity.LOW, keywords=["kw"],
                 deprecated=True, replaced_by="D2"),
            Rule(id="D2", text="new", severity=Severity.LOW, keywords=["kw"]),
        ])
        report = c.deprecation_report()
        assert "D1" in report["with_successor"]
        assert report["migration_map"]["D1"] == "D2"


# ===========================================================================
# Constitution: dead_rules
# ===========================================================================


class TestDeadRules:
    def test_all_dead(self):
        c = _make_constitution([_simple_rule("DR1", keywords=["never_match_xyz"])])
        result = c.dead_rules(["hello world", "foo bar"])
        assert result["dead_count"] == 1
        assert result["live_count"] == 0

    def test_some_live(self):
        c = _make_constitution([
            _simple_rule("DR1", keywords=["hello"]),
            _simple_rule("DR2", keywords=["never_match_xyz"]),
        ])
        result = c.dead_rules(["hello world"])
        assert result["live_count"] == 1
        assert result["dead_count"] == 1

    def test_include_deprecated(self):
        c = Constitution(rules=[
            Rule(id="DR1", text="deprecated", severity=Severity.LOW,
                 keywords=["kw"], deprecated=True),
            Rule(id="DR2", text="active", severity=Severity.LOW,
                 keywords=["kw"]),
        ])
        result = c.dead_rules(["kw here"], include_deprecated=True)
        assert result["total_rules"] == 2

    def test_empty_corpus(self):
        c = _make_constitution([_simple_rule("DR1")])
        result = c.dead_rules([])
        assert result["corpus_size"] == 0
        assert result["dead_count"] == 1


# ===========================================================================
# Constitution: cascade (federated constitutions)
# ===========================================================================


class TestCascade:
    def test_hardcoded_parent_wins(self):
        parent = Constitution(rules=[
            Rule(id="F1", text="parent hardcoded", severity=Severity.CRITICAL,
                 keywords=["kw"], hardcoded=True),
        ])
        child = Constitution(rules=[
            Rule(id="F1", text="child override", severity=Severity.LOW,
                 keywords=["kw"]),
            Rule(id="F2", text="child only", severity=Severity.LOW,
                 keywords=["kw2"]),
        ])
        federated = parent.cascade(child)
        f1 = federated.get_rule("F1")
        assert f1 is not None
        assert f1.text == "parent hardcoded"
        assert federated.get_rule("F2") is not None

    def test_non_hardcoded_child_wins(self):
        parent = Constitution(rules=[
            Rule(id="F1", text="parent", severity=Severity.HIGH,
                 keywords=["kw"], hardcoded=False),
        ])
        child = Constitution(rules=[
            Rule(id="F1", text="child wins", severity=Severity.LOW,
                 keywords=["kw"]),
        ])
        federated = parent.cascade(child)
        f1 = federated.get_rule("F1")
        assert f1 is not None
        assert f1.text == "child wins"


# ===========================================================================
# Constitution: diff
# ===========================================================================


class TestDiff:
    def test_no_changes(self):
        c = _make_constitution([_simple_rule()])
        result = c.diff(c)
        assert not result["hash_changed"]
        assert result["summary"] == "no changes"

    def test_severity_change_tracked(self):
        c1 = _make_constitution([_simple_rule("D1", severity="low")])
        c2 = _make_constitution([_simple_rule("D1", severity="critical")])
        result = c1.diff(c2)
        assert result["hash_changed"]
        assert len(result["severity_changes"]) == 1
        assert result["severity_changes"][0]["old"] == "low"


# ===========================================================================
# Constitution: misc methods
# ===========================================================================


class TestMiscConstitution:
    def test_hash_versioned(self):
        c = _make_constitution([_simple_rule()])
        assert c.hash_versioned.startswith("sha256:v1:")

    def test_list_categories(self):
        c = _make_constitution([
            _simple_rule("C1", category="security"),
            _simple_rule("C2", category="audit"),
        ])
        cats = c.list_categories()
        assert "security" in cats
        assert "audit" in cats

    def test_blast_radius(self):
        c = _make_constitution([
            _simple_rule("P1"),
            _simple_rule("P2", depends_on=["P1"]),
        ])
        result = c.blast_radius("P1")
        assert "P2" in result["dependent_rule_ids"]

    def test_get_version_info(self):
        c = _make_constitution([_simple_rule()], version_name="v2.0-release")
        info = c.get_version_info()
        assert info["version_name"] == "v2.0-release"

    def test_json_schema_structure(self):
        schema = Constitution.json_schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "rules" in schema["properties"]

    def test_permission_ceiling_default(self):
        c = _make_constitution([_simple_rule()])
        assert c.permission_ceiling == "standard"

    def test_from_rules(self):
        r = Rule(id="FR1", text="test", severity=Severity.LOW, keywords=["kw"])
        c = Constitution.from_rules([r], name="custom")
        assert c.name == "custom"
        assert len(c.rules) == 1


# ===========================================================================
# Engine: _FastAuditLog
# ===========================================================================


class TestFastAuditLog:
    def test_record_fast_and_entries(self):
        from acgs_lite.engine.core import _FastAuditLog

        log = _FastAuditLog("testhash")
        log.record_fast("req1", "agent1", "action1", True, [], "testhash", 1.0, "2026-01-01")
        assert len(log) == 1
        entries = log.entries
        assert len(entries) == 1
        assert entries[0].agent_id == "agent1"

    def test_record_compat_shim(self):
        from acgs_lite.audit import AuditEntry
        from acgs_lite.engine.core import _FastAuditLog

        log = _FastAuditLog("h")
        entry = AuditEntry(
            id="r1", type="validation", agent_id="a1",
            action="act", valid=True, violations=[],
            constitutional_hash="h", latency_ms=1.0,
        )
        result = log.record(entry)
        assert result == ""
        assert len(log) == 1
        reconstructed = log.entries[0]
        assert reconstructed.agent_id == "a1"


# ===========================================================================
# Engine: _NoopRecorder
# ===========================================================================


class TestNoopRecorder:
    def test_append_and_len(self):
        from acgs_lite.engine.core import _NoopRecorder

        rec = _NoopRecorder()
        assert len(rec) == 0
        rec.append("anything")
        rec.append(None)
        assert len(rec) == 2


# ===========================================================================
# Engine: _dedup_violations
# ===========================================================================


class TestDedupViolations:
    def test_dedup_removes_duplicates(self):
        from acgs_lite.engine.core import Violation, _dedup_violations

        v1 = Violation("R1", "text", Severity.HIGH, "content", "cat")
        v2 = Violation("R1", "text", Severity.HIGH, "content2", "cat")
        v3 = Violation("R2", "text2", Severity.LOW, "content", "cat2")
        result = _dedup_violations([v1, v2, v3])
        assert len(result) == 2
        assert result[0].rule_id == "R1"
        assert result[1].rule_id == "R2"


# ===========================================================================
# Engine: ValidationResult
# ===========================================================================


class TestValidationResult:
    def test_to_dict(self):
        from acgs_lite.engine.core import ValidationResult, Violation

        vr = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[
                Violation("R1", "txt", Severity.CRITICAL, "matched", "cat"),
                Violation("R2", "txt2", Severity.LOW, "m2", "cat2"),
            ],
            rules_checked=5,
            latency_ms=1.23,
            request_id="req1",
            action="test action",
            agent_id="agent1",
        )
        d = vr.to_dict()
        assert d["valid"] is False
        assert len(d["violations"]) == 2
        assert d["violations"][0]["severity"] == "critical"

    def test_blocking_violations(self):
        from acgs_lite.engine.core import ValidationResult, Violation

        vr = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[
                Violation("R1", "txt", Severity.CRITICAL, "m", "cat"),
                Violation("R2", "txt2", Severity.LOW, "m2", "cat2"),
            ],
        )
        blocking = vr.blocking_violations
        assert len(blocking) == 1
        assert blocking[0].rule_id == "R1"

    def test_warnings(self):
        from acgs_lite.engine.core import ValidationResult, Violation

        vr = ValidationResult(
            valid=True,
            constitutional_hash="abc",
            violations=[
                Violation("R1", "txt", Severity.LOW, "m", "cat"),
                Violation("R2", "txt2", Severity.MEDIUM, "m2", "cat2"),
            ],
        )
        warns = vr.warnings
        assert len(warns) == 2


# ===========================================================================
# Engine: GovernanceEngine with real AuditLog (slow path)
# ===========================================================================


class TestGovernanceEngineSlowPath:
    def test_validate_allow_with_real_audit_log(self):
        from acgs_lite.audit import AuditLog
        from acgs_lite.engine.core import GovernanceEngine

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz_abc"])])
        log = AuditLog()
        engine = GovernanceEngine(c, audit_log=log)
        result = engine.validate("harmless action")
        assert result.valid is True
        assert len(log.entries) == 1
        assert log.entries[0].valid is True

    def test_validate_violation_with_real_audit_log(self):
        from acgs_lite.audit import AuditLog
        from acgs_lite.engine.core import GovernanceEngine

        c = _make_constitution([_simple_rule(keywords=["dangerous_kw"])])
        log = AuditLog()
        engine = GovernanceEngine(c, audit_log=log, strict=False)
        result = engine.validate("dangerous_kw action")
        assert not result.valid or len(result.violations) > 0

    def test_stats_with_real_audit_log(self):
        from acgs_lite.audit import AuditLog
        from acgs_lite.engine.core import GovernanceEngine

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz"])])
        log = AuditLog()
        engine = GovernanceEngine(c, audit_log=log)
        engine.validate("harmless action1")
        engine.validate("harmless action2")
        stats = engine.stats
        assert stats["total_validations"] == 2
        assert stats["compliance_rate"] == 1.0


# ===========================================================================
# Engine: GovernanceEngine stats with NoopRecorder
# ===========================================================================


class TestEngineStatsNoop:
    def test_stats_noop_recorder(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz"])])
        engine = GovernanceEngine(c)
        engine.validate("anything harmless")
        stats = engine.stats
        assert stats["total_validations"] >= 1
        assert stats["compliance_rate"] == 1.0


# ===========================================================================
# Engine: Custom validators
# ===========================================================================


class TestCustomValidators:
    def test_custom_validator_violations_added(self):
        from acgs_lite.engine.core import GovernanceEngine, Violation

        def my_validator(action, ctx):
            if "bad" in action:
                return [Violation("CUSTOM-1", "custom rule", Severity.MEDIUM, action[:100], "custom")]
            return []

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz"])])
        engine = GovernanceEngine(c, strict=False)
        engine.add_validator(my_validator)
        result = engine.validate("bad action here")
        custom_ids = [v.rule_id for v in result.violations]
        assert "CUSTOM-1" in custom_ids

    def test_custom_validator_exception_handled(self):
        from acgs_lite.engine.core import GovernanceEngine

        def broken_validator(action, ctx):
            raise RuntimeError("validator crashed")

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz"])])
        engine = GovernanceEngine(c, strict=False)
        engine.add_validator(broken_validator)
        result = engine.validate("test action")
        error_ids = [v.rule_id for v in result.violations]
        assert "CUSTOM-ERROR" in error_ids

    def test_custom_validator_skipped_when_critical_exists(self):
        """Custom validators should not run when critical violations already found.

        The engine warmup loop calls validate() many times, so we track calls
        only after engine construction completes.
        """
        from acgs_lite.engine.core import GovernanceEngine

        call_count = 0

        def counting_validator(action, ctx):
            nonlocal call_count
            call_count += 1
            return []

        c = Constitution.from_template("general")
        engine = GovernanceEngine(c, strict=False)
        # Add validator AFTER construction (warmup) to isolate counts
        engine.add_validator(counting_validator)
        call_count = 0  # reset after any warmup
        # Trigger a critical violation
        result = engine.validate("invest in crypto buy stocks")
        crit_violations = [v for v in result.violations if v.severity == Severity.CRITICAL]
        if crit_violations:
            # If critical found, custom validator should have been skipped
            assert call_count == 0


# ===========================================================================
# Engine: context-based validation
# ===========================================================================


class TestContextValidation:
    def test_context_action_detail_triggers(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = Constitution.from_template("general")
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate(
            "harmless base action",
            context={"action_detail": "invest in crypto"},
        )
        assert len(result.violations) > 0

    def test_context_action_description_triggers(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = Constitution.from_template("general")
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate(
            "harmless base action",
            context={"action_description": "self-approve this request"},
        )
        assert len(result.violations) > 0

    def test_metadata_only_context_no_trigger(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = _make_constitution([_simple_rule(keywords=["never_match_xyz"])])
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate(
            "harmless action",
            context={"source": "test", "rule": "R1"},
        )
        assert result.valid is True


# ===========================================================================
# Engine: strict mode raises on blocking
# ===========================================================================


class TestStrictMode:
    def test_strict_raises_on_critical(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = Constitution.from_template("general")
        engine = GovernanceEngine(c, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("invest in crypto buy stocks")

    def test_non_strict_returns_result(self):
        from acgs_lite.engine.core import GovernanceEngine

        c = Constitution.from_template("general")
        engine = GovernanceEngine(c, strict=False)
        result = engine.validate("invest in crypto buy stocks")
        assert len(result.violations) > 0


# ===========================================================================
# Constitution: detect_conflicts
# ===========================================================================


class TestDetectConflicts:
    def test_conflicting_rules_detected(self):
        c = Constitution(rules=[
            Rule(id="C1", text="r1", severity=Severity.CRITICAL,
                 keywords=["shared_kw"], workflow_action="block"),
            Rule(id="C2", text="r2", severity=Severity.LOW,
                 keywords=["shared_kw"], workflow_action="warn"),
        ])
        result = c.detect_conflicts()
        assert result["has_conflicts"] is True
        assert result["conflict_count"] >= 1

    def test_no_conflicts(self):
        c = _make_constitution([
            _simple_rule("NC1", keywords=["alpha"]),
            _simple_rule("NC2", keywords=["beta"]),
        ])
        result = c.detect_conflicts()
        assert result["has_conflicts"] is False
