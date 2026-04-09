"""Comprehensive coverage tests for acgs_lite.constitution.constitution.Constitution.

Targets the ~773 uncovered lines identified by coverage analysis.
Focuses on methods not exercised by existing test files.
"""

from __future__ import annotations

import pytest

from acgs_lite.constitution.constitution import Constitution
from acgs_lite.constitution.rule import AcknowledgedTension, Rule, Severity
from acgs_lite.errors import ConstitutionalViolationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "R-001",
    text: str = "Test rule",
    severity: Severity = Severity.HIGH,
    keywords: list[str] | None = None,
    patterns: list[str] | None = None,
    category: str = "general",
    subcategory: str = "",
    workflow_action: str = "block",
    tags: list[str] | None = None,
    depends_on: list[str] | None = None,
    enabled: bool = True,
    hardcoded: bool = False,
    priority: int = 0,
    condition: dict | None = None,
    deprecated: bool = False,
    replaced_by: str = "",
    valid_from: str = "",
    valid_until: str = "",
    embedding: list[float] | None = None,
    metadata: dict | None = None,
) -> Rule:
    return Rule(
        id=rule_id,
        text=text,
        severity=severity,
        keywords=keywords or ["test"],
        patterns=patterns or [],
        category=category,
        subcategory=subcategory,
        workflow_action=workflow_action,
        tags=tags or [],
        depends_on=depends_on or [],
        enabled=enabled,
        hardcoded=hardcoded,
        priority=priority,
        condition=condition or {},
        deprecated=deprecated,
        replaced_by=replaced_by,
        valid_from=valid_from,
        valid_until=valid_until,
        embedding=embedding or [],
        metadata=metadata or {},
    )


def _simple_constitution(name: str = "test", rules: list[Rule] | None = None) -> Constitution:
    if rules is None:
        rules = [
            _make_rule("R-001", "No secrets", keywords=["secret", "password"], category="security"),
            _make_rule(
                "R-002",
                "Audit trail",
                keywords=["audit", "log"],
                category="audit",
                severity=Severity.MEDIUM,
                workflow_action="warn",
            ),
        ]
    return Constitution(name=name, rules=rules)


# ===========================================================================
# from_yaml_str
# ===========================================================================


class TestFromYamlStr:
    def test_round_trip(self) -> None:
        c = _simple_constitution()
        yaml_str = c.to_yaml()
        c2 = Constitution.from_yaml_str(yaml_str)
        assert c2.hash == c.hash
        assert len(c2.rules) == len(c.rules)

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            Constitution.from_yaml_str("- item1\n- item2\n")


# ===========================================================================
# from_dict
# ===========================================================================


class TestFromDict:
    def test_minimal(self) -> None:
        c = Constitution.from_dict(
            {"rules": [{"id": "X-1", "text": "Do stuff", "severity": "low", "keywords": ["stuff"]}]}
        )
        assert c.name == "default"
        assert c.rules[0].id == "X-1"
        assert c.rules[0].severity == Severity.LOW

    def test_with_all_fields(self) -> None:
        c = Constitution.from_dict(
            {
                "name": "full",
                "version": "2.0.0",
                "description": "Full test",
                "permission_ceiling": "STRICT",
                "version_name": "v2-rc1",
                "metadata": {"env": "test"},
                "rules": [
                    {
                        "id": "F-1",
                        "text": "Full rule",
                        "severity": "critical",
                        "keywords": ["kw"],
                        "patterns": [r"\d+"],
                        "category": "security",
                        "subcategory": "test-sub",
                        "depends_on": [],
                        "enabled": True,
                        "workflow_action": "block",
                        "hardcoded": True,
                        "tags": ["compliance"],
                        "priority": 5,
                        "condition": {"env": "prod"},
                        "deprecated": False,
                        "replaced_by": "",
                        "valid_from": "2025-01-01",
                        "valid_until": "2027-12-31",
                        "embedding": [0.1, 0.2],
                        "metadata": {"source": "test"},
                    }
                ],
            }
        )
        assert c.permission_ceiling == "strict"
        assert c.version_name == "v2-rc1"
        assert c.rules[0].hardcoded is True
        assert c.rules[0].priority == 5
        assert c.rules[0].condition == {"env": "prod"}

    def test_from_rules_classmethod(self) -> None:
        rules = [_make_rule("R-1"), _make_rule(rule_id="R-2")]
        c = Constitution.from_rules(rules, name="custom-name")
        assert c.name == "custom-name"
        assert len(c.rules) == 2


# ===========================================================================
# from_template — all domains
# ===========================================================================


class TestFromTemplate:
    @pytest.mark.parametrize("domain", ["gitlab", "healthcare", "finance", "security", "general"])
    def test_valid_domains(self, domain: str) -> None:
        c = Constitution.from_template(domain)
        assert len(c.rules) >= 1
        assert c.name != "default"

    def test_unknown_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown governance domain"):
            Constitution.from_template("aerospace")

    def test_case_insensitive(self) -> None:
        c = Constitution.from_template("  GitLab  ")
        assert c.name == "gitlab-governance"


# ===========================================================================
# default()
# ===========================================================================


class TestDefault:
    def test_default_has_core_rules(self) -> None:
        c = Constitution.default()
        assert c.name == "acgs-default"
        assert len(c.rules) == 6
        ids = {r.id for r in c.rules}
        assert "ACGS-001" in ids
        assert "ACGS-006" in ids

    def test_default_integrity(self) -> None:
        c = Constitution.default()
        result = c.validate_integrity()
        assert result["valid"] is True


# ===========================================================================
# Properties and basic accessors
# ===========================================================================


class TestProperties:
    def test_hash_is_deterministic(self) -> None:
        c1 = _simple_constitution()
        c2 = _simple_constitution()
        assert c1.hash == c2.hash
        assert len(c1.hash) == 16

    def test_hash_versioned(self) -> None:
        c = _simple_constitution()
        assert c.hash_versioned.startswith("sha256:v1:")
        assert c.hash in c.hash_versioned

    def test_active_rules(self) -> None:
        rules = [
            _make_rule("R-1", enabled=True),
            _make_rule(rule_id="R-2", enabled=False),
        ]
        c = Constitution(name="t", rules=rules)
        assert len(c.active_rules()) == 1
        assert c.active_rules()[0].id == "R-1"

    def test_get_rule_found(self) -> None:
        c = _simple_constitution()
        assert c.get_rule("R-001") is not None
        assert c.get_rule("R-001").text == "No secrets"

    def test_get_rule_not_found(self) -> None:
        c = _simple_constitution()
        assert c.get_rule("NONEXISTENT") is None

    def test_len(self) -> None:
        c = _simple_constitution()
        assert len(c) == 2

    def test_repr(self) -> None:
        c = _simple_constitution()
        r = repr(c)
        assert "test" in r
        assert "rules=2" in r


# ===========================================================================
# update_rule + rule_changelog + rule_version
# ===========================================================================


class TestUpdateRule:
    def test_basic_update(self) -> None:
        c = _simple_constitution()
        c2 = c.update_rule("R-001", severity="critical", change_reason="escalated")
        assert c2.get_rule("R-001").severity == Severity.CRITICAL
        assert c2.hash != c.hash

    def test_changelog_recorded(self) -> None:
        c = _simple_constitution()
        c2 = c.update_rule("R-001", change_reason="test change")
        assert len(c2.changelog) == 1
        assert c2.changelog[0]["operation"] == "update_rule"
        assert c2.changelog[0]["rule_id"] == "R-001"

    def test_rule_version_increments(self) -> None:
        c = _simple_constitution()
        assert c.rule_version("R-001") == 1
        c2 = c.update_rule("R-001", change_reason="first")
        assert c2.rule_version("R-001") == 2
        c3 = c2.update_rule("R-001", change_reason="second")
        assert c3.rule_version("R-001") == 3

    def test_rule_changelog_returns_snapshots(self) -> None:
        c = _simple_constitution()
        c2 = c.update_rule("R-001", severity="critical", change_reason="bump")
        log = c2.rule_changelog("R-001")
        assert len(log) == 1
        assert log[0]["change_reason"] == "bump"

    def test_rule_changelog_empty_for_untouched(self) -> None:
        c = _simple_constitution()
        assert c.rule_changelog("R-001") == []

    def test_update_nonexistent_raises(self) -> None:
        c = _simple_constitution()
        with pytest.raises(KeyError, match="NONEXISTENT"):
            c.update_rule("NONEXISTENT", severity="low")

    def test_immutability(self) -> None:
        c = _simple_constitution()
        original_hash = c.hash
        _ = c.update_rule("R-001", severity="critical", change_reason="test")
        assert c.hash == original_hash


# ===========================================================================
# deprecated_rules / active_non_deprecated / active_rules_at
# ===========================================================================


class TestDeprecation:
    def test_deprecated_rules(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True, replaced_by="R-2"),
            _make_rule(rule_id="R-2"),
        ]
        c = Constitution(name="d", rules=rules)
        dep = c.deprecated_rules()
        assert len(dep) == 1
        assert dep[0].id == "R-1"

    def test_active_non_deprecated(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True),
            _make_rule(rule_id="R-2"),
        ]
        c = Constitution(name="d", rules=rules)
        active = c.active_non_deprecated()
        assert len(active) == 1
        assert active[0].id == "R-2"

    def test_active_rules_at(self) -> None:
        rules = [
            _make_rule("R-1", valid_from="2025-01-01", valid_until="2025-12-31"),
            _make_rule(rule_id="R-2"),  # no temporal bounds
        ]
        c = Constitution(name="t", rules=rules)
        at_mid = c.active_rules_at("2025-06-15")
        assert len(at_mid) == 2
        at_after = c.active_rules_at("2026-06-15")
        assert len(at_after) == 1
        assert at_after[0].id == "R-2"


# ===========================================================================
# deprecation_report / deprecation_migration_report
# ===========================================================================


class TestDeprecationReports:
    def test_deprecation_report(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True, replaced_by="R-2"),
            _make_rule(rule_id="R-2"),
            _make_rule(rule_id="R-3", deprecated=True),
        ]
        c = Constitution(name="d", rules=rules)
        report = c.deprecation_report()
        assert report["deprecated_count"] == 2
        assert "R-1" in report["with_successor"]
        assert "R-3" in report["without_successor"]
        assert report["migration_map"]["R-1"] == "R-2"

    def test_deprecation_migration_report_with_successor(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True, replaced_by="R-2", valid_until="2026-06-01"),
            _make_rule(rule_id="R-2"),
        ]
        c = Constitution(name="d", rules=rules)
        report = c.deprecation_migration_report()
        assert report["summary"]["total"] == 1
        assert report["summary"]["with_successor"] == 1
        assert report["summary"]["with_sunset_date"] == 1
        entry = report["entries"][0]
        assert entry["replaced_by"] == "R-2"
        assert "Migrate to rule R-2" in entry["recommendation"]

    def test_deprecation_migration_report_no_successor(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True),
        ]
        c = Constitution(name="d", rules=rules)
        report = c.deprecation_migration_report()
        entry = report["entries"][0]
        assert entry["replaced_by"] is None
        assert "Document successor" in entry["recommendation"]

    def test_deprecation_migration_report_sunset_only(self) -> None:
        rules = [
            _make_rule("R-1", deprecated=True, valid_until="2026-12-31"),
        ]
        c = Constitution(name="d", rules=rules)
        report = c.deprecation_migration_report()
        entry = report["entries"][0]
        assert "Sunset by 2026-12-31" in entry["recommendation"]


# ===========================================================================
# explain
# ===========================================================================


class TestExplain:
    def test_no_trigger(self) -> None:
        c = _simple_constitution()
        result = c.explain("hello world")
        assert result["decision"] == "allow"
        assert "ALLOWED" in result["explanation"]
        assert result["recommendation"] == "No action required."

    def test_blocking_trigger(self) -> None:
        c = _simple_constitution()
        result = c.explain("reveal the secret password")
        assert result["decision"] == "deny"
        assert len(result["blocking_rules"]) >= 1
        assert "DENIED" in result["explanation"]

    def test_warning_only(self) -> None:
        rules = [
            _make_rule("R-1", severity=Severity.LOW, keywords=["caution"], workflow_action="warn"),
        ]
        c = Constitution(name="w", rules=rules)
        result = c.explain("proceed with caution")
        assert result["decision"] == "allow"
        assert len(result["warning_rules"]) >= 1
        assert "warning" in result["explanation"].lower()

    def test_tags_collected(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret"], tags=["gdpr", "pci"]),
        ]
        c = Constitution(name="t", rules=rules)
        result = c.explain("secret value")
        assert "gdpr" in result["tags_involved"]

    def test_blocking_with_warnings(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["danger"], severity=Severity.CRITICAL),
            _make_rule(
                rule_id="R-2", keywords=["danger"], severity=Severity.LOW, workflow_action="warn"
            ),
        ]
        c = Constitution(name="bw", rules=rules)
        result = c.explain("danger zone")
        assert result["decision"] == "deny"
        assert "Additionally" in result["explanation"]


# ===========================================================================
# compare (static)
# ===========================================================================


class TestCompare:
    def test_identical(self) -> None:
        c = _simple_constitution()
        result = Constitution.compare(c, c)
        assert result["added"] == []
        assert result["removed"] == []
        assert result["modified"] == []
        assert result["unchanged"] == 2
        assert result["summary"] == "2 unchanged"

    def test_added_and_removed(self) -> None:
        before = Constitution(name="b", rules=[_make_rule("R-1")])
        after = Constitution(name="a", rules=[_make_rule(rule_id="R-2")])
        result = Constitution.compare(before, after)
        assert "R-2" in result["added"]
        assert "R-1" in result["removed"]

    def test_modified_severity(self) -> None:
        r1 = _make_rule("R-1", severity=Severity.LOW)
        r2 = _make_rule("R-1", severity=Severity.CRITICAL)
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert len(result["modified"]) == 1
        assert "severity" in result["modified"][0]["changes"][0]

    def test_modified_text(self) -> None:
        r1 = _make_rule("R-1", text="old text")
        r2 = _make_rule("R-1", text="new text")
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("text" in c for c in result["modified"][0]["changes"])

    def test_modified_keywords(self) -> None:
        r1 = _make_rule("R-1", keywords=["a", "b"])
        r2 = _make_rule("R-1", keywords=["a", "c"])
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("keywords" in c for c in result["modified"][0]["changes"])

    def test_modified_enabled(self) -> None:
        r1 = _make_rule("R-1", enabled=True)
        r2 = _make_rule("R-1", enabled=False)
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("enabled" in c for c in result["modified"][0]["changes"])

    def test_modified_tags(self) -> None:
        r1 = _make_rule("R-1", tags=["gdpr"])
        r2 = _make_rule("R-1", tags=["sox"])
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("tags" in c for c in result["modified"][0]["changes"])

    def test_modified_category(self) -> None:
        r1 = _make_rule("R-1", category="security")
        r2 = _make_rule("R-1", category="audit")
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("category" in c for c in result["modified"][0]["changes"])

    def test_modified_priority(self) -> None:
        r1 = _make_rule("R-1", priority=1)
        r2 = _make_rule("R-1", priority=5)
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("priority" in c for c in result["modified"][0]["changes"])

    def test_modified_workflow_action(self) -> None:
        r1 = _make_rule("R-1", workflow_action="block")
        r2 = _make_rule("R-1", workflow_action="warn")
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("workflow_action" in c for c in result["modified"][0]["changes"])

    def test_modified_patterns(self) -> None:
        r1 = _make_rule("R-1", patterns=[r"\d+"])
        r2 = _make_rule("R-1", patterns=[r"\w+"])
        before = Constitution(name="b", rules=[r1])
        after = Constitution(name="a", rules=[r2])
        result = Constitution.compare(before, after)
        assert any("patterns" in c for c in result["modified"][0]["changes"])

    def test_no_differences(self) -> None:
        c = Constitution(name="x", rules=[])
        result = Constitution.compare(c, c)
        assert result["summary"] == "No differences"


# ===========================================================================
# diff (instance)
# ===========================================================================


class TestDiff:
    def test_same_constitution(self) -> None:
        c = _simple_constitution()
        result = c.diff(c)
        assert result["hash_changed"] is False
        assert result["added"] == []
        assert result["removed"] == []
        assert result["summary"] == "no changes"

    def test_added_rule(self) -> None:
        c1 = Constitution(name="a", rules=[_make_rule("R-1")])
        c2 = Constitution(name="b", rules=[_make_rule("R-1"), _make_rule(rule_id="R-2")])
        result = c1.diff(c2)
        assert "R-2" in result["added"]

    def test_severity_change(self) -> None:
        r1 = _make_rule("R-1", severity=Severity.LOW)
        r2 = _make_rule("R-1", severity=Severity.CRITICAL)
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.diff(c2)
        assert len(result["severity_changes"]) == 1
        assert result["severity_changes"][0]["old"] == "low"
        assert result["severity_changes"][0]["new"] == "critical"

    def test_multiple_field_changes(self) -> None:
        r1 = _make_rule(
            "R-1",
            text="old",
            category="a",
            subcategory="s1",
            workflow_action="block",
            hardcoded=False,
            priority=0,
        )
        r2 = _make_rule(
            "R-1",
            text="new",
            category="b",
            subcategory="s2",
            workflow_action="warn",
            hardcoded=True,
            priority=5,
        )
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.diff(c2)
        assert len(result["modified"]) == 1
        changes = result["modified"][0]["changes"]
        assert "text" in changes
        assert "category" in changes
        assert "subcategory" in changes
        assert "workflow_action" in changes
        assert "hardcoded" in changes
        assert "priority" in changes


# ===========================================================================
# validate_integrity
# ===========================================================================


class TestValidateIntegrity:
    def test_valid_constitution(self) -> None:
        c = _simple_constitution()
        result = c.validate_integrity()
        assert result["valid"] is True

    def test_duplicate_ids(self) -> None:
        # Duplicate IDs are caught at construction time by _validate_rules
        with pytest.raises(ValueError, match="Duplicate rule ID"):
            Constitution(name="d", rules=[_make_rule("R-1"), _make_rule("R-1")])

    def test_unknown_dependency(self) -> None:
        # Unknown deps are caught at construction time by validate_rules
        with pytest.raises((ValueError,), match="non-existent rule"):
            Constitution(name="d", rules=[_make_rule("R-1", depends_on=["NONEXISTENT"])])

    def test_self_dependency(self) -> None:
        rules = [_make_rule("R-1", depends_on=["R-1"])]
        c = Constitution(name="d", rules=rules)
        result = c.validate_integrity()
        assert any("depends on itself" in e for e in result["errors"])

    def test_unknown_workflow_action_raises(self) -> None:
        """Unknown workflow_action values are rejected by Pydantic at Rule construction."""
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises(ValidationError):
            _make_rule("R-1", workflow_action="custom_action")

    def test_no_workflow_warning_empty_coerced_to_block(self) -> None:
        """Empty string workflow_action is coerced to BLOCK (no 'no workflow' warning)."""
        rules = [_make_rule("R-1", workflow_action="")]
        c = Constitution(name="d", rules=rules)
        result = c.validate_integrity()
        # Empty string is coerced to BLOCK; all rules now have workflow_action set
        assert all("without workflow_action" not in w for w in result.get("warnings", []))


# ===========================================================================
# subsumes (static)
# ===========================================================================


class TestSubsumes:
    def test_identical_subsumes(self) -> None:
        c = _simple_constitution()
        result = Constitution.subsumes(c, c)
        assert result["subsumes"] is True

    def test_missing_rule(self) -> None:
        superset = Constitution(name="s", rules=[_make_rule("R-1")])
        subset = Constitution(name="sub", rules=[_make_rule(rule_id="R-2")])
        result = Constitution.subsumes(superset, subset)
        assert result["subsumes"] is False
        assert "R-2" in result["missing_rules"]

    def test_weaker_severity(self) -> None:
        superset_rule = _make_rule("R-1", severity=Severity.LOW)
        subset_rule = _make_rule("R-1", severity=Severity.CRITICAL)
        superset = Constitution(name="s", rules=[superset_rule])
        subset = Constitution(name="sub", rules=[subset_rule])
        result = Constitution.subsumes(superset, subset)
        assert result["subsumes"] is False
        assert "R-1" in result["weaker_rules"]

    def test_weaker_workflow(self) -> None:
        superset_rule = _make_rule("R-1", workflow_action="warn")
        subset_rule = _make_rule("R-1", workflow_action="block")
        superset = Constitution(name="s", rules=[superset_rule])
        subset = Constitution(name="sub", rules=[subset_rule])
        result = Constitution.subsumes(superset, subset)
        assert result["subsumes"] is False
        assert "R-1" in result["incompatible_workflow"]

    def test_stronger_subsumes(self) -> None:
        superset_rule = _make_rule("R-1", severity=Severity.CRITICAL, workflow_action="block")
        subset_rule = _make_rule("R-1", severity=Severity.LOW, workflow_action="warn")
        superset = Constitution(name="s", rules=[superset_rule])
        subset = Constitution(name="sub", rules=[subset_rule])
        result = Constitution.subsumes(superset, subset)
        assert result["subsumes"] is True


# ===========================================================================
# counterfactual
# ===========================================================================


class TestCounterfactual:
    def test_no_rules_removed(self) -> None:
        c = Constitution.default()
        result = c.counterfactual("bypass validation")
        assert result["changed"] is False
        assert result["removed_rules"] == []

    def test_removing_rule_changes_result(self) -> None:
        # Use ACGS-006 which has no dependents
        c = Constitution.default()
        result = c.counterfactual(
            "here is my password secret key",
            remove_rules=["ACGS-006"],
        )
        assert isinstance(result["baseline"], dict)
        assert isinstance(result["counterfactual"], dict)
        assert len(result["removed_rules"]) == 1

    def test_remove_all_raises(self) -> None:
        rules = [_make_rule("R-1")]
        c = Constitution(name="x", rules=rules)
        with pytest.raises(ValueError, match="remove all rules"):
            c.counterfactual("test", remove_rules=["R-1"])

    def test_empty_remove_set(self) -> None:
        c = _simple_constitution()
        result = c.counterfactual("test action", remove_rules=["", ""])
        assert result["removed_rules"] == []


# ===========================================================================
# dependency_graph
# ===========================================================================


class TestDependencyGraph:
    def test_no_deps(self) -> None:
        c = _simple_constitution()
        graph = c.dependency_graph()
        assert graph["edges"] == []
        assert len(graph["roots"]) == 2
        assert len(graph["orphans"]) == 2

    def test_with_deps(self) -> None:
        rules = [
            _make_rule("R-1"),
            _make_rule(rule_id="R-2", depends_on=["R-1"]),
        ]
        c = Constitution(name="d", rules=rules)
        graph = c.dependency_graph()
        assert len(graph["edges"]) == 1
        assert ("R-2", "R-1") in graph["edges"]
        assert "R-1" in graph["dependents"]
        assert "R-2" in graph["dependents"]["R-1"]


# ===========================================================================
# rule_dependencies (semantic)
# ===========================================================================


class TestRuleDependencies:
    def test_keyword_clusters(self) -> None:
        # Need >50% keyword overlap for semantic_edges
        rules = [
            _make_rule("R-1", keywords=["secret", "password", "credential"]),
            _make_rule(rule_id="R-2", keywords=["secret", "password", "credential"]),
            _make_rule(rule_id="R-3", keywords=["audit", "log"]),
        ]
        c = Constitution(name="d", rules=rules)
        result = c.rule_dependencies()
        assert len(result["semantic_edges"]) >= 1

    def test_severity_chains(self) -> None:
        rules = [
            _make_rule("R-1", severity=Severity.CRITICAL, keywords=["secret"]),
            _make_rule(rule_id="R-2", severity=Severity.LOW, keywords=["secret"]),
        ]
        c = Constitution(name="d", rules=rules)
        result = c.rule_dependencies()
        assert len(result["severity_chains"]) >= 1

    def test_workflow_groups(self) -> None:
        c = _simple_constitution()
        result = c.rule_dependencies()
        assert "general" in result["workflow_groups"]


# ===========================================================================
# detect_conflicts
# ===========================================================================


class TestDetectConflicts:
    def test_no_conflicts(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret"]),
            _make_rule(rule_id="R-2", keywords=["audit"]),
        ]
        c = Constitution(name="c", rules=rules)
        result = c.detect_conflicts()
        assert result["has_conflicts"] is False

    def test_severity_conflict(self) -> None:
        rules = [
            _make_rule(
                "R-1", keywords=["danger"], severity=Severity.CRITICAL, workflow_action="block"
            ),
            _make_rule(
                rule_id="R-2", keywords=["danger"], severity=Severity.LOW, workflow_action="block"
            ),
        ]
        c = Constitution(name="c", rules=rules)
        result = c.detect_conflicts()
        assert result["has_conflicts"] is True
        assert result["conflict_count"] >= 1

    def test_workflow_conflict(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["danger"], severity=Severity.HIGH, workflow_action="block"),
            _make_rule(
                rule_id="R-2", keywords=["danger"], severity=Severity.HIGH, workflow_action="warn"
            ),
        ]
        c = Constitution(name="c", rules=rules)
        result = c.detect_conflicts()
        assert result["has_conflicts"] is True
        conflict = result["conflicts"][0]
        assert conflict["workflow_conflict"] is True


# ===========================================================================
# to_yaml / to_bundle / from_bundle
# ===========================================================================


class TestSerialization:
    def test_to_yaml_includes_all_fields(self) -> None:
        rules = [
            _make_rule(
                "R-1",
                patterns=[r"\d+"],
                subcategory="sub1",
                tags=["gdpr"],
                hardcoded=True,
                priority=5,
                enabled=False,
            ),
        ]
        c = Constitution(name="t", rules=rules, metadata={"env": "test"})
        yaml_str = c.to_yaml()
        assert "R-1" in yaml_str
        assert "gdpr" in yaml_str
        assert "hardcoded" in yaml_str
        assert "priority" in yaml_str
        assert "env" in yaml_str

    def test_to_bundle_round_trip(self) -> None:
        c = Constitution.from_template("security")
        bundle = c.to_bundle()
        assert bundle["schema_version"] == "1.0.0"
        assert bundle["rule_count"] == len(c.rules)
        c2 = Constitution.from_bundle(bundle)
        assert c2.hash == c.hash

    def test_to_bundle_includes_condition_and_deprecated(self) -> None:
        rules = [
            _make_rule(
                "R-1",
                condition={"env": "prod"},
                deprecated=True,
                replaced_by="R-2",
                valid_from="2025-01-01",
                valid_until="2026-01-01",
                metadata={"source": "test"},
            ),
        ]
        c = Constitution(name="t", rules=rules)
        bundle = c.to_bundle()
        rule_data = bundle["rules"][0]
        assert rule_data["condition"] == {"env": "prod"}
        assert rule_data["deprecated"] is True
        assert rule_data["replaced_by"] == "R-2"
        assert rule_data["valid_from"] == "2025-01-01"
        assert rule_data["valid_until"] == "2026-01-01"
        assert rule_data["metadata"]["source"] == "test"

    def test_from_bundle_bad_schema(self) -> None:
        with pytest.raises(ValueError, match="Unsupported bundle"):
            Constitution.from_bundle({"schema_version": "99.0.0", "rules": []})

    def test_from_bundle_missing_rules(self) -> None:
        with pytest.raises(ValueError, match="missing required"):
            Constitution.from_bundle({"schema_version": "1.0.0"})

    def test_from_bundle_preserves_imported_hash(self) -> None:
        c = _simple_constitution()
        bundle = c.to_bundle()
        c2 = Constitution.from_bundle(bundle)
        assert c2.metadata.get("imported_hash") == c.hash


# ===========================================================================
# json_schema / validate_yaml_schema
# ===========================================================================


class TestJsonSchema:
    def test_json_schema_structure(self) -> None:
        schema = Constitution.json_schema()
        assert schema["type"] == "object"
        assert "rules" in schema["required"]
        assert "properties" in schema

    def test_validate_yaml_schema_valid(self) -> None:
        data = {
            "name": "test",
            "rules": [{"id": "R-1", "text": "Test rule"}],
        }
        result = Constitution.validate_yaml_schema(data)
        assert result["valid"] is True

    def test_validate_yaml_schema_missing_rules(self) -> None:
        result = Constitution.validate_yaml_schema({})
        assert result["valid"] is False


# ===========================================================================
# merge (instance)
# ===========================================================================


class TestMerge:
    def test_no_conflicts(self) -> None:
        c1 = Constitution(name="a", rules=[_make_rule("R-1")])
        c2 = Constitution(name="b", rules=[_make_rule(rule_id="R-2")])
        result = c1.merge(c2)
        merged = result["constitution"]
        assert len(merged.rules) == 2
        assert result["conflicts_resolved"] == 0

    def test_keep_self_strategy(self) -> None:
        r1 = _make_rule("R-1", text="version A")
        r2 = _make_rule("R-1", text="version B")
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.merge(c2, strategy="keep_self")
        merged = result["constitution"]
        assert merged.get_rule("R-1").text == "version A"

    def test_keep_other_strategy(self) -> None:
        r1 = _make_rule("R-1", text="version A")
        r2 = _make_rule("R-1", text="version B")
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.merge(c2, strategy="keep_other")
        merged = result["constitution"]
        assert merged.get_rule("R-1").text == "version B"

    def test_keep_higher_severity(self) -> None:
        r1 = _make_rule("R-1", severity=Severity.LOW)
        r2 = _make_rule("R-1", severity=Severity.CRITICAL)
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.merge(c2, strategy="keep_higher_severity")
        merged = result["constitution"]
        assert merged.get_rule("R-1").severity == Severity.CRITICAL

    def test_keep_higher_severity_tie_keeps_self(self) -> None:
        r1 = _make_rule("R-1", text="self version", severity=Severity.HIGH)
        r2 = _make_rule("R-1", text="other version", severity=Severity.HIGH)
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.merge(c2, strategy="keep_higher_severity")
        merged = result["constitution"]
        assert merged.get_rule("R-1").text == "self version"

    def test_invalid_strategy_raises(self) -> None:
        c1 = _simple_constitution()
        c2 = _simple_constitution()
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            c1.merge(c2, strategy="invalid")

    def test_hardcoded_override_blocked(self) -> None:
        r1 = _make_rule("R-1", text="hardcoded rule", hardcoded=True)
        r2 = _make_rule("R-1", text="override attempt")
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        with pytest.raises(ConstitutionalViolationError):
            c1.merge(c2, strategy="keep_other")

    def test_hardcoded_override_allowed_with_flag(self) -> None:
        r1 = _make_rule("R-1", text="hardcoded rule", hardcoded=True)
        r2 = _make_rule("R-1", text="override attempt")
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        result = c1.merge(c2, strategy="keep_other", allow_hardcoded_override=True)
        assert result["constitution"].get_rule("R-1").text == "override attempt"

    def test_acknowledged_tensions(self) -> None:
        r1 = _make_rule("R-1", text="version A")
        r2 = _make_rule("R-1", text="version B")
        c1 = Constitution(name="a", rules=[r1])
        c2 = Constitution(name="b", rules=[r2])
        tensions = [AcknowledgedTension(rule_id="R-1", rationale="known")]
        result = c1.merge(c2, strategy="keep_self", acknowledged_tensions=tensions)
        assert len(result["acknowledged_tensions_applied"]) == 1
        assert len(result["unacknowledged_tensions"]) == 0


# ===========================================================================
# cascade
# ===========================================================================


class TestCascade:
    def test_parent_hardcoded_wins(self) -> None:
        parent_rule = _make_rule("R-1", text="parent", hardcoded=True)
        child_rule = _make_rule("R-1", text="child")
        parent = Constitution(name="p", rules=[parent_rule])
        child = Constitution(name="c", rules=[child_rule])
        federated = parent.cascade(child)
        assert federated.get_rule("R-1").text == "parent"

    def test_child_overrides_non_hardcoded(self) -> None:
        parent_rule = _make_rule("R-1", text="parent", hardcoded=False)
        child_rule = _make_rule("R-1", text="child")
        parent = Constitution(name="p", rules=[parent_rule])
        child = Constitution(name="c", rules=[child_rule])
        federated = parent.cascade(child)
        assert federated.get_rule("R-1").text == "child"

    def test_child_only_rules_included(self) -> None:
        parent = Constitution(name="p", rules=[_make_rule("R-1")])
        child = Constitution(name="c", rules=[_make_rule(rule_id="R-2")])
        federated = parent.cascade(child)
        assert federated.get_rule("R-2") is not None

    def test_custom_name(self) -> None:
        parent = Constitution(name="p", rules=[_make_rule("R-1")])
        child = Constitution(name="c", rules=[])
        federated = parent.cascade(child, name="custom-fed")
        assert federated.name == "custom-fed"


# ===========================================================================
# create_rule_from_template (static)
# ===========================================================================


class TestCreateRuleFromTemplate:
    def test_data_privacy_template(self) -> None:
        rule = Constitution.create_rule_from_template(
            "data_privacy",
            "DP-001",
            {"action": "collection", "data_type": "personal", "consent_type": "explicit"},
        )
        assert rule.id == "DP-001"
        assert "collection" in rule.text
        assert "personal" in rule.text
        assert rule.category == "privacy"
        assert rule.severity == Severity.HIGH

    def test_security_boundary_template(self) -> None:
        rule = Constitution.create_rule_from_template(
            "security_boundary",
            "SB-001",
            {"action": "transfer", "boundary_type": "network"},
        )
        assert rule.severity == Severity.CRITICAL
        assert rule.category == "security"

    def test_compliance_audit_template(self) -> None:
        rule = Constitution.create_rule_from_template(
            "compliance_audit",
            "CA-001",
            {"action": "delete", "asset_type": "records"},
        )
        assert rule.severity == Severity.MEDIUM

    def test_resource_limit_template(self) -> None:
        rule = Constitution.create_rule_from_template(
            "resource_limit",
            "RL-001",
            {"resource_type": "API", "limit": "100", "time_period": "hour", "user_type": "free"},
        )
        assert rule.severity == Severity.LOW

    def test_access_control_template(self) -> None:
        rule = Constitution.create_rule_from_template(
            "access_control",
            "AC-001",
            {"auth_method": "MFA", "action": "write", "resource_type": "database"},
        )
        assert rule.category == "security"

    def test_unknown_template_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown template"):
            Constitution.create_rule_from_template("nonexistent", "X-1", {})

    def test_template_metadata_recorded(self) -> None:
        rule = Constitution.create_rule_from_template(
            "data_privacy",
            "DP-002",
            {"action": "sharing", "data_type": "health", "consent_type": "informed"},
        )
        assert rule.metadata["template"] == "data_privacy"
        assert rule.metadata["template_params"]["action"] == "sharing"


# ===========================================================================
# lifecycle management
# ===========================================================================


class TestLifecycle:
    def test_set_lifecycle_to_draft(self) -> None:
        c = _simple_constitution()
        result = c.set_rule_lifecycle_state("R-001", "draft", reason="not ready")
        assert result is True
        rule = c.get_rule("R-001")
        assert rule.enabled is False
        assert rule.metadata["lifecycle_state"] == "draft"

    def test_set_lifecycle_to_active(self) -> None:
        c = _simple_constitution()
        c.set_rule_lifecycle_state("R-001", "draft")
        c.set_rule_lifecycle_state("R-001", "active", reason="ready")
        rule = c.get_rule("R-001")
        assert rule.enabled is True
        assert rule.metadata["lifecycle_state"] == "active"

    def test_set_lifecycle_to_deprecated(self) -> None:
        c = _simple_constitution()
        c.set_rule_lifecycle_state("R-001", "deprecated", reason="replaced")
        rule = c.get_rule("R-001")
        assert rule.enabled is True
        assert rule.metadata["lifecycle_state"] == "deprecated"

    def test_set_lifecycle_invalid_state(self) -> None:
        c = _simple_constitution()
        with pytest.raises(ValueError, match="Invalid state"):
            c.set_rule_lifecycle_state("R-001", "unknown")

    def test_set_lifecycle_nonexistent_rule(self) -> None:
        c = _simple_constitution()
        assert c.set_rule_lifecycle_state("NOPE", "active") is False

    def test_get_rule_lifecycle_states(self) -> None:
        c = _simple_constitution()
        c.set_rule_lifecycle_state("R-001", "draft", reason="wip")
        states = c.get_rule_lifecycle_states()
        assert states["R-001"]["state"] == "draft"
        assert states["R-001"]["enabled"] is False
        assert states["R-001"]["transition"] is not None
        assert states["R-002"]["state"] == "active"  # default

    def test_lifecycle_transition_rules(self) -> None:
        c = _simple_constitution()
        c.set_rule_lifecycle_state("R-001", "draft")
        candidates = c.lifecycle_transition_rules("draft", "active")
        assert "R-001" in candidates

    def test_lifecycle_invalid_transition(self) -> None:
        c = _simple_constitution()
        candidates = c.lifecycle_transition_rules("active", "draft")
        assert candidates == []


# ===========================================================================
# tenant management
# ===========================================================================


class TestTenantManagement:
    def test_set_rule_tenants(self) -> None:
        c = _simple_constitution()
        assert c.set_rule_tenants("R-001", ["tenant-a", "tenant-b"]) is True
        assert c.get_rule("R-001").metadata["tenants"] == ["tenant-a", "tenant-b"]

    def test_set_rule_tenants_nonexistent(self) -> None:
        c = _simple_constitution()
        assert c.set_rule_tenants("NOPE", ["t"]) is False

    def test_get_tenant_rules_global(self) -> None:
        c = _simple_constitution()
        rules = c.get_tenant_rules(tenant_id=None)
        assert len(rules) == 2  # all global

    def test_get_tenant_rules_scoped(self) -> None:
        c = _simple_constitution()
        c.set_rule_tenants("R-001", ["tenant-a"])
        rules = c.get_tenant_rules("tenant-a")
        assert len(rules) == 2  # R-001 scoped to tenant-a + R-002 global
        rules_b = c.get_tenant_rules("tenant-b")
        assert len(rules_b) == 1  # only R-002 global

    def test_tenant_isolation_report(self) -> None:
        c = _simple_constitution()
        c.set_rule_tenants("R-001", ["tenant-a"])
        report = c.tenant_isolation_report()
        assert "R-002" in report["global_rules"]
        assert "tenant-a" in report["tenant_rules"]
        assert report["total_tenants"] == 1
        assert report["isolation_score"] is True


# ===========================================================================
# assess_decision_anomaly (static)
# ===========================================================================


class TestDecisionAnomaly:
    def test_zero_total(self) -> None:
        result = Constitution.assess_decision_anomaly()
        assert result["total"] == 0
        assert result["is_anomalous"] is False

    def test_normal_distribution(self) -> None:
        result = Constitution.assess_decision_anomaly(
            allow_count=85, deny_count=10, escalate_count=5
        )
        assert result["total"] == 100
        assert result["is_anomalous"] is False

    def test_high_deny_spike(self) -> None:
        result = Constitution.assess_decision_anomaly(
            allow_count=10,
            deny_count=80,
            escalate_count=10,
            baseline_deny_rate=0.15,
            spike_threshold=2.0,
        )
        assert result["is_anomalous"] is True
        assert any("high_deny_rate" in a for a in result["anomalies"])

    def test_high_escalate_spike(self) -> None:
        result = Constitution.assess_decision_anomaly(
            allow_count=10,
            deny_count=10,
            escalate_count=80,
            baseline_escalate_rate=0.10,
            spike_threshold=2.0,
        )
        assert result["is_anomalous"] is True
        assert any("high_escalate_rate" in a for a in result["anomalies"])


# ===========================================================================
# check_governance_slo (static)
# ===========================================================================


class TestGovernanceSlo:
    def test_all_pass(self) -> None:
        result = Constitution.check_governance_slo(
            p99_latency_ms=0.5,
            compliance_rate=0.99,
            throughput_rps=10000,
            false_negative_rate=0.001,
        )
        assert result["slo_pass"] is True
        assert len(result["breaches"]) == 0

    def test_all_fail(self) -> None:
        result = Constitution.check_governance_slo(
            p99_latency_ms=10.0,
            compliance_rate=0.5,
            throughput_rps=100,
            false_negative_rate=0.5,
        )
        assert result["slo_pass"] is False
        assert len(result["breaches"]) == 4

    def test_partial_breach(self) -> None:
        result = Constitution.check_governance_slo(
            p99_latency_ms=5.0,  # breaches
            compliance_rate=0.99,  # ok
            throughput_rps=10000,  # ok
            false_negative_rate=0.001,  # ok
        )
        assert result["slo_pass"] is False
        assert result["pass"]["p99"] is False
        assert result["pass"]["compliance"] is True


# ===========================================================================
# list_categories / blast_radius / get_version_info
# ===========================================================================


class TestMiscAccessors:
    def test_list_categories(self) -> None:
        c = _simple_constitution()
        cats = c.list_categories()
        assert "security" in cats
        assert "audit" in cats
        assert cats == sorted(cats)

    def test_blast_radius_with_dependents(self) -> None:
        rules = [
            _make_rule("R-1"),
            _make_rule(rule_id="R-2", depends_on=["R-1"]),
        ]
        c = Constitution(name="d", rules=rules)
        result = c.blast_radius("R-1")
        assert "R-2" in result["dependent_rule_ids"]

    def test_blast_radius_no_dependents(self) -> None:
        c = _simple_constitution()
        result = c.blast_radius("R-001")
        assert result["dependent_rule_ids"] == []

    def test_blast_radius_with_successor(self) -> None:
        rules = [_make_rule("R-1", deprecated=True, replaced_by="R-2")]
        c = Constitution(name="d", rules=rules)
        result = c.blast_radius("R-1")
        assert result["successor_rule_id"] == "R-2"

    def test_blast_radius_nonexistent(self) -> None:
        c = _simple_constitution()
        result = c.blast_radius("NOPE")
        assert result["successor_rule_id"] is None

    def test_get_version_info(self) -> None:
        c = Constitution(
            name="t",
            version="2.0.0",
            version_name="v2-release",
            rules=[_make_rule("R-1")],
        )
        info = c.get_version_info()
        assert info["version"] == "2.0.0"
        assert info["version_name"] == "v2-release"
        assert info["hash"] == c.hash
        assert info["rule_count"] == 1

    def test_get_version_info_no_name(self) -> None:
        c = _simple_constitution()
        info = c.get_version_info()
        assert info["version_name"] is None


# ===========================================================================
# find_similar_rules
# ===========================================================================


class TestFindSimilarRules:
    def test_high_overlap(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret", "password", "key"]),
            _make_rule(rule_id="R-2", keywords=["secret", "password", "token"]),
        ]
        c = Constitution(name="s", rules=rules)
        results = c.find_similar_rules(threshold=0.3)
        assert len(results) >= 1
        assert results[0]["rule_a"] in {"R-1", "R-2"}

    def test_no_overlap(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret"]),
            _make_rule(rule_id="R-2", keywords=["audit"]),
        ]
        c = Constitution(name="s", rules=rules)
        results = c.find_similar_rules(threshold=0.5)
        assert len(results) == 0

    def test_include_disabled(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret", "password"], enabled=True),
            _make_rule(rule_id="R-2", keywords=["secret", "password"], enabled=False),
        ]
        c = Constitution(name="s", rules=rules)
        without = c.find_similar_rules(threshold=0.5, include_disabled=False)
        with_disabled = c.find_similar_rules(threshold=0.5, include_disabled=True)
        assert len(with_disabled) >= len(without)

    def test_recommendation_consolidate(self) -> None:
        rules = [
            _make_rule(
                "R-1", keywords=["secret", "password"], category="security", severity=Severity.HIGH
            ),
            _make_rule(
                rule_id="R-2",
                keywords=["secret", "password"],
                category="security",
                severity=Severity.HIGH,
            ),
        ]
        c = Constitution(name="s", rules=rules)
        results = c.find_similar_rules(threshold=0.5)
        assert results[0]["recommendation"] == "consolidate"

    def test_recommendation_review(self) -> None:
        rules = [
            _make_rule(
                "R-1", keywords=["secret", "password"], category="security", severity=Severity.HIGH
            ),
            _make_rule(
                rule_id="R-2",
                keywords=["secret", "password"],
                category="audit",
                severity=Severity.LOW,
            ),
        ]
        c = Constitution(name="s", rules=rules)
        results = c.find_similar_rules(threshold=0.5)
        assert results[0]["recommendation"] == "review"


# ===========================================================================
# cosine_similar_rules
# ===========================================================================


class TestCosineSimilarRules:
    def test_with_embeddings(self) -> None:
        rules = [
            _make_rule("R-1", embedding=[1.0, 0.0, 0.0, 0.0]),
            _make_rule(rule_id="R-2", embedding=[0.9, 0.1, 0.0, 0.0]),
        ]
        c = Constitution(name="e", rules=rules)
        results = c.cosine_similar_rules(threshold=0.5)
        assert len(results) >= 1
        assert results[0]["method"] == "cosine"

    def test_fallback_to_jaccard(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["secret", "password"]),
            _make_rule(rule_id="R-2", keywords=["secret", "password"]),
        ]
        c = Constitution(name="e", rules=rules)
        results = c.cosine_similar_rules(threshold=0.5)
        assert all(r["method"] == "jaccard" for r in results)

    def test_short_embeddings_fallback(self) -> None:
        rules = [
            _make_rule("R-1", embedding=[1.0, 0.0], keywords=["secret", "password"]),
            _make_rule(rule_id="R-2", embedding=[0.9, 0.1], keywords=["secret", "password"]),
        ]
        c = Constitution(name="e", rules=rules)
        results = c.cosine_similar_rules(threshold=0.5, min_dim=4)
        assert all(r["method"] == "jaccard" for r in results)


# ===========================================================================
# semantic_search
# ===========================================================================


class TestSemanticSearch:
    def test_with_matching_embeddings(self) -> None:
        rules = [
            _make_rule("R-1", embedding=[1.0, 0.0, 0.0]),
            _make_rule(rule_id="R-2", embedding=[0.0, 1.0, 0.0]),
        ]
        c = Constitution(name="s", rules=rules)
        results = c.semantic_search([0.9, 0.1, 0.0], top_k=5, threshold=0.5)
        assert len(results) >= 1
        assert results[0]["rule_id"] == "R-1"

    def test_empty_query(self) -> None:
        c = _simple_constitution()
        assert c.semantic_search([], top_k=5) == []

    def test_no_matching_rules(self) -> None:
        rules = [_make_rule("R-1")]  # no embedding
        c = Constitution(name="s", rules=rules)
        results = c.semantic_search([1.0, 0.0], top_k=5, threshold=0.5)
        assert results == []

    def test_top_k_limits(self) -> None:
        rules = [
            _make_rule(rule_id=f"R-{i}", embedding=[float(i) / 10, 1.0 - float(i) / 10])
            for i in range(1, 6)
        ]
        c = Constitution(name="s", rules=rules)
        results = c.semantic_search([0.5, 0.5], top_k=2, threshold=0.0)
        assert len(results) <= 2


# ===========================================================================
# health_score
# ===========================================================================


class TestHealthScore:
    def test_empty_constitution(self) -> None:
        c = Constitution(name="e", rules=[])
        score = c.health_score()
        assert score["composite"] == 0.0
        assert score["grade"] == "F"
        assert score["rule_count"] == 0

    def test_well_documented(self) -> None:
        c = Constitution.default()
        score = c.health_score()
        assert score["composite"] > 0
        assert score["rule_count"] >= 1
        assert score["grade"] in {"A", "B", "C", "D", "F"}

    def test_grade_boundaries(self) -> None:
        # Just verify the method runs on a template
        c = Constitution.from_template("security")
        score = c.health_score()
        assert 0.0 <= score["composite"] <= 1.0


# ===========================================================================
# maturity_level
# ===========================================================================


class TestMaturityLevel:
    def test_basic_constitution(self) -> None:
        c = _simple_constitution()
        m = c.maturity_level()
        assert m["level"] >= 0
        assert m["label"] != ""
        assert isinstance(m["score"], float)

    def test_high_maturity_constitution(self) -> None:
        rules = [
            _make_rule(
                "R-1",
                tags=["compliance"],
                priority=1,
                workflow_action="block",
                condition={"env": "prod"},
                valid_from="2025-01-01",
                embedding=[0.1, 0.2],
                deprecated=False,
                category="security",
            ),
            _make_rule(
                rule_id="R-2",
                tags=["audit"],
                severity=Severity.LOW,
                priority=2,
                workflow_action="warn",
                category="audit",
                depends_on=["R-1"],
            ),
        ]
        c = Constitution(
            name="mature",
            rules=rules,
            rule_history={"R-1": ["snap"]},
            changelog=[
                {
                    "operation": "create",
                    "rule_id": "R-1",
                    "timestamp": "t",
                    "reason": "init",
                    "actor": "",
                }
            ],
        )
        m = c.maturity_level()
        # Level 3 requires: dependencies, priorities, workflow_actions, conditions
        # Level 4 requires: versioning, changelog, conflict_detection, health_tooling
        assert m["level"] >= 4


# ===========================================================================
# coverage_gaps
# ===========================================================================


class TestCoverageGaps:
    def test_default_constitution(self) -> None:
        c = Constitution.default()
        gaps = c.coverage_gaps()
        assert 0.0 <= gaps["coverage_score"] <= 1.0
        assert isinstance(gaps["uncovered_domains"], list)

    def test_fully_disabled_category(self) -> None:
        rules = [
            _make_rule("R-1", category="custom-cat", enabled=False),
        ]
        c = Constitution(name="d", rules=rules)
        gaps = c.coverage_gaps()
        assert "custom-cat" in gaps["disabled_only_categories"]


# ===========================================================================
# dead_rules
# ===========================================================================


class TestDeadRules:
    def test_all_dead(self) -> None:
        rules = [_make_rule("R-1", keywords=["xyzzy"])]
        c = Constitution(name="d", rules=rules)
        result = c.dead_rules(["hello world", "nothing here"])
        assert result["dead_count"] == 1
        assert result["live_count"] == 0

    def test_all_live(self) -> None:
        rules = [_make_rule("R-1", keywords=["hello"])]
        c = Constitution(name="d", rules=rules)
        result = c.dead_rules(["say hello to everyone"])
        assert result["live_count"] == 1
        assert result["dead_count"] == 0

    def test_empty_corpus(self) -> None:
        c = _simple_constitution()
        result = c.dead_rules([])
        assert result["corpus_size"] == 0
        assert result["dead_count"] == 2

    def test_include_deprecated(self) -> None:
        rules = [
            _make_rule("R-1", keywords=["hello"], deprecated=True),
            _make_rule(rule_id="R-2", keywords=["world"]),
        ]
        c = Constitution(name="d", rules=rules)
        with_dep = c.dead_rules(["hello world"], include_deprecated=True)
        without_dep = c.dead_rules(["hello world"], include_deprecated=False)
        assert with_dep["total_rules"] == 2
        assert without_dep["total_rules"] == 1

    def test_rule_never_fires_recommendation(self) -> None:
        rules = [_make_rule("R-1", keywords=["xyzzy-never-match"])]
        c = Constitution(name="d", rules=rules)
        result = c.dead_rules(["test action"])
        assert "Remove or broaden" in result["dead_rules"][0]["recommendation"]


# ===========================================================================
# posture_score
# ===========================================================================


class TestPostureScore:
    def test_basic(self) -> None:
        c = Constitution.default()
        result = c.posture_score()
        assert 0.0 <= result["posture"] <= 1.0
        assert result["grade"] in {"A+", "A", "B", "C", "D", "F"}
        assert isinstance(result["ci_pass"], bool)

    def test_custom_threshold(self) -> None:
        c = _simple_constitution()
        low = c.posture_score(ci_threshold=0.01)
        high = c.posture_score(ci_threshold=0.99)
        assert low["ci_pass"] is True or low["posture"] < 0.01
        assert high["ci_pass"] is False or high["posture"] >= 0.99


# ===========================================================================
# get_governance_metrics
# ===========================================================================


class TestGovernanceMetrics:
    def test_metrics_structure(self) -> None:
        c = Constitution.default()
        metrics = c.get_governance_metrics()
        assert "rule_counts" in metrics
        assert "complexity_metrics" in metrics
        assert "health_indicators" in metrics
        assert "usage_patterns" in metrics
        assert metrics["rule_counts"]["total"] == 6

    def test_empty_constitution(self) -> None:
        c = Constitution(name="e", rules=[])
        metrics = c.get_governance_metrics()
        assert metrics["rule_counts"]["total"] == 0
        assert metrics["complexity_metrics"]["avg_keywords_per_rule"] == 0


# ===========================================================================
# active_rules_for_context
# ===========================================================================


class TestActiveRulesForContext:
    def test_no_conditions(self) -> None:
        c = _simple_constitution()
        rules = c.active_rules_for_context({"env": "prod"})
        assert len(rules) == 2  # all rules match (no condition = always)

    def test_matching_condition(self) -> None:
        rules = [
            _make_rule("R-1", condition={"env": "prod"}),
            _make_rule(rule_id="R-2"),  # no condition
        ]
        c = Constitution(name="ctx", rules=rules)
        prod_rules = c.active_rules_for_context({"env": "prod"})
        dev_rules = c.active_rules_for_context({"env": "dev"})
        assert len(prod_rules) == 2
        assert len(dev_rules) == 1


# ===========================================================================
# compliance_report
# ===========================================================================


class TestComplianceReport:
    def test_valid_framework(self) -> None:
        c = Constitution.default()
        report = c.compliance_report(framework="soc2")
        assert "summary" in report
        assert "regulatory_alignment" in report
        assert report["summary"]["framework"] in {"soc2", "SOC2"}

    def test_unknown_framework(self) -> None:
        c = _simple_constitution()
        report = c.compliance_report(framework="nonexistent")
        assert "error" in report["summary"]
        assert len(report["recommended_actions"]) >= 1


# ===========================================================================
# full_report
# ===========================================================================


class TestFullReport:
    def test_structure(self) -> None:
        c = Constitution.default()
        report = c.full_report()
        assert "identity" in report
        assert "health" in report
        assert "maturity" in report
        assert "coverage" in report
        assert "regulatory" in report
        assert "deprecation" in report

    def test_unknown_framework_handled(self) -> None:
        c = _simple_constitution()
        report = c.full_report(regulatory_framework="nonexistent")
        assert "error" in report["regulatory"]

    def test_without_similar_rules(self) -> None:
        c = _simple_constitution()
        report = c.full_report(include_similar_rules=False)
        assert report["similar_rules"] == []


# ===========================================================================
# builder
# ===========================================================================


class TestBuilder:
    def test_builder_returns_builder(self) -> None:
        c = _simple_constitution()
        b = c.builder()
        assert b is not None
        c2 = b.add_rule("R-3", "New rule", severity="low", keywords=["new"]).build()
        assert len(c2.rules) == 3
        assert len(c.rules) == 2  # original unchanged
