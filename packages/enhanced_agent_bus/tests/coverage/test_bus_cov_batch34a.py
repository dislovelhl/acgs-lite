"""Coverage tests for the currently active ``src/acgs_lite`` runtime.

This shard used to assert against older ``acgs_lite`` APIs that are no longer
exposed by the root runtime imported by the repository test harness. Keep this
file aligned with the public methods on ``acgs_lite.constitution.Constitution``
that actually execute under ``--import-mode=importlib``.
"""

from __future__ import annotations

import pytest
from acgs_lite.constitution import AcknowledgedTension, Constitution, Rule, Severity
from acgs_lite.errors import ConstitutionalViolationError
from pydantic import ValidationError as PydanticValidationError


def _simple_rule(
    rule_id: str = "R1",
    text: str = "Test rule",
    severity: str = "high",
    keywords: list[str] | None = None,
    **kwargs: object,
) -> dict[str, object]:
    return {
        "id": rule_id,
        "text": text,
        "severity": severity,
        "keywords": keywords or ["testword"],
        **kwargs,
    }


def _make_constitution(rules_data: list[dict[str, object]], **kwargs: object) -> Constitution:
    return Constitution.from_dict({"rules": rules_data, **kwargs})


class TestFromYamlStr:
    def test_non_mapping_yaml_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            Constitution.from_yaml_str("- item1\n- item2\n")

    def test_round_trip_yaml(self) -> None:
        constitution = _make_constitution([_simple_rule()])
        round_tripped = Constitution.from_yaml_str(constitution.to_yaml())
        assert round_tripped.hash == constitution.hash


class TestFromTemplate:
    def test_unknown_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown governance domain"):
            Constitution.from_template("nonexistent_domain")

    def test_all_domains_valid(self) -> None:
        for domain in ("gitlab", "healthcare", "finance", "security", "general"):
            constitution = Constitution.from_template(domain)
            assert constitution.rules

    def test_case_insensitive_with_spaces(self) -> None:
        constitution = Constitution.from_template("  GitLab  ")
        assert constitution.name == "gitlab-governance"


class TestValidateYamlSchema:
    def test_missing_rules_rejected(self) -> None:
        result = Constitution.validate_yaml_schema({})
        assert result["valid"] is False
        assert any("'rules' is required" in error for error in result["errors"])

    def test_duplicate_rule_ids_rejected(self) -> None:
        result = Constitution.validate_yaml_schema(
            {
                "rules": [
                    _simple_rule("DUP"),
                    _simple_rule("DUP", text="duplicate"),
                ]
            }
        )
        assert result["valid"] is False
        assert any("duplicate rule id 'DUP'" in error for error in result["errors"])

    def test_rules_without_matchers_warn(self) -> None:
        result = Constitution.validate_yaml_schema(
            {"rules": [{"id": "R1", "text": "No matchers", "severity": "high"}]}
        )
        assert result["valid"] is True
        assert any("no keywords or patterns" in warning for warning in result["warnings"])


class TestValidateIntegrity:
    def test_duplicate_rule_ids_flagged(self) -> None:
        with pytest.raises(PydanticValidationError, match="Duplicate rule ID: DUP"):
            Constitution(
                rules=[
                    Rule(id="DUP", text="rule a", severity=Severity.HIGH, keywords=["a"]),
                    Rule(id="DUP", text="rule b", severity=Severity.LOW, keywords=["b"]),
                ]
            )

    def test_self_dependency(self) -> None:
        constitution = _make_constitution([_simple_rule("SELF", depends_on=["SELF"])])
        result = constitution.validate_integrity()
        assert any("depends on itself" in error for error in result["errors"])

    def test_unknown_dependency(self) -> None:
        with pytest.raises(
            PydanticValidationError,
            match="depends_on references non-existent rule GHOST",
        ):
            _make_constitution([_simple_rule("A1", depends_on=["GHOST"])])

    def test_circular_dependency(self) -> None:
        constitution = _make_constitution(
            [
                _simple_rule("C1", depends_on=["C2"]),
                _simple_rule("C2", depends_on=["C1"]),
            ]
        )
        result = constitution.validate_integrity()
        assert any("Circular dependency detected" in error for error in result["errors"])

    def test_unknown_workflow_action_warning(self) -> None:
        # ViolationAction is a strict enum: unknown values are rejected at construction
        # time by Pydantic, not deferred to validate_integrity() as warnings.
        with pytest.raises(PydanticValidationError):
            _make_constitution([_simple_rule("W1", workflow_action="exotic_action")])

    def test_no_keywords_warn_via_integrity_validation(self) -> None:
        constitution = Constitution(
            rules=[Rule(id="BARE", text="No signals", severity=Severity.LOW)]
        )
        result = constitution.validate_integrity()
        assert any("no keywords or patterns" in warning for warning in result["warnings"])

    def test_empty_workflow_action_gets_default(self) -> None:
        # Empty string is coerced to the default ViolationAction.BLOCK by Pydantic
        constitution = _make_constitution([_simple_rule("NW1", workflow_action="")])
        assert constitution.rules[0].workflow_action is not None


class TestDependencyGraph:
    def test_dependency_graph_roots_dependents_and_orphans(self) -> None:
        constitution = _make_constitution(
            [
                _simple_rule("ROOT", workflow_action="block"),
                _simple_rule("CHILD", depends_on=["ROOT"], workflow_action="warn"),
                _simple_rule("ORPHAN", workflow_action="warn"),
            ]
        )
        graph = constitution.dependency_graph()
        assert ("CHILD", "ROOT") in graph["edges"]
        assert graph["dependents"]["ROOT"] == ["CHILD"]
        assert "ROOT" in graph["roots"]
        assert "ORPHAN" in graph["orphans"]


class TestGovernanceSummary:
    def test_summary_counts_active_rules_and_coverage(self) -> None:
        constitution = _make_constitution(
            [
                _simple_rule(
                    "S1",
                    severity="critical",
                    category="security",
                    subcategory="sandbox",
                    workflow_action="block",
                    tags=["pci"],
                ),
                _simple_rule(
                    "S2",
                    severity="low",
                    category="audit",
                    workflow_action="warn",
                    enabled=False,
                    tags=["sox"],
                ),
            ]
        )
        summary = constitution.governance_summary()
        assert summary["total_rules"] == 2
        assert summary["active_rules"] == 1
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_category"]["security"] == 1
        assert summary["coverage"]["blocking_rules"] == 1


class TestMerge:
    def _base(self, hardcoded: bool = False) -> Constitution:
        return _make_constitution(
            [
                _simple_rule(
                    "SHARED",
                    "base rule",
                    severity="high",
                    hardcoded=hardcoded,
                    workflow_action="block",
                ),
                _simple_rule("ONLY-A", "a only", workflow_action="warn"),
            ]
        )

    def _overlay(self, severity: str = "critical") -> Constitution:
        return _make_constitution(
            [
                _simple_rule(
                    "SHARED",
                    "overlay rule",
                    severity=severity,
                    workflow_action="block_and_notify",
                ),
                _simple_rule("ONLY-B", "b only", workflow_action="warn"),
            ]
        )

    def test_invalid_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            self._base().merge(self._overlay(), strategy="invalid")

    def test_keep_self_strategy(self) -> None:
        result = self._base().merge(self._overlay(), strategy="keep_self")
        shared = result["constitution"].get_rule("SHARED")
        assert shared is not None
        assert shared.text == "base rule"
        assert result["rules_from_self"] >= 1

    def test_keep_other_strategy(self) -> None:
        result = self._base().merge(self._overlay(), strategy="keep_other")
        shared = result["constitution"].get_rule("SHARED")
        assert shared is not None
        assert shared.text == "overlay rule"

    def test_keep_higher_severity_chooses_critical(self) -> None:
        result = self._base().merge(self._overlay(severity="critical"))
        shared = result["constitution"].get_rule("SHARED")
        assert shared is not None
        assert shared.severity == Severity.CRITICAL

    def test_keep_higher_severity_tie_goes_to_self(self) -> None:
        result = self._base().merge(self._overlay(severity="high"))
        shared = result["constitution"].get_rule("SHARED")
        assert shared is not None
        assert shared.text == "base rule"

    def test_hardcoded_override_blocked_keep_other(self) -> None:
        with pytest.raises(ConstitutionalViolationError, match="hardcoded"):
            self._base(hardcoded=True).merge(self._overlay(), strategy="keep_other")

    def test_hardcoded_override_allowed_with_flag(self) -> None:
        result = self._base(hardcoded=True).merge(
            self._overlay(),
            strategy="keep_other",
            allow_hardcoded_override=True,
        )
        assert result["constitution"] is not None

    def test_acknowledged_tensions(self) -> None:
        tension = AcknowledgedTension(rule_id="SHARED", rationale="Testing acknowledged")
        result = self._base().merge(
            self._overlay(severity="critical"),
            acknowledged_tensions=[tension],
        )
        assert len(result["acknowledged_tensions_applied"]) >= 1
        assert result["unacknowledged_tensions"] == []


class TestConflictDetection:
    def test_conflicting_rules_reported(self) -> None:
        constitution = Constitution(
            rules=[
                Rule(
                    id="A",
                    text="a",
                    severity=Severity.HIGH,
                    keywords=["shared"],
                    workflow_action="block",
                ),
                Rule(
                    id="B",
                    text="b",
                    severity=Severity.LOW,
                    keywords=["shared"],
                    workflow_action="warn",
                ),
            ]
        )
        result = constitution.detect_conflicts()
        assert result["has_conflicts"] is True
        assert result["conflict_count"] == 1
        assert result["conflicts"][0]["shared_keywords"] == ["shared"]


class TestFilter:
    def test_filter_by_min_severity_marks_metadata(self) -> None:
        constitution = Constitution.from_template("general")
        filtered = constitution.filter(min_severity="critical")
        assert filtered.metadata["filtered"] is True
        assert all(rule.severity == Severity.CRITICAL for rule in filtered.rules)

    def test_filter_empty_raises(self) -> None:
        constitution = Constitution.from_template("general")
        with pytest.raises(ValueError, match="empty constitution"):
            constitution.filter(category="not-a-real-category")


class TestSemanticCoverage:
    def test_semantic_rule_clusters_detect_privacy_rule(self) -> None:
        constitution = Constitution.from_template("general")
        clusters = constitution.semantic_rule_clusters()
        assert "GEN-004" in clusters["privacy"]

    def test_analyze_coverage_gaps_reports_missing_domain(self) -> None:
        constitution = Constitution.from_template("general")
        report = constitution.analyze_coverage_gaps()
        assert "transparency" in report["missing_domains"]
        assert any("transparency" in recommendation for recommendation in report["recommendations"])

    def test_analyze_coverage_gaps_rejects_bad_threshold(self) -> None:
        constitution = Constitution.from_template("general")
        with pytest.raises(ValueError, match="weak_threshold must be >= 1"):
            constitution.analyze_coverage_gaps(weak_threshold=0)


class TestExplain:
    def test_allow_no_triggers(self) -> None:
        constitution = _make_constitution([_simple_rule(keywords=["secret_word_xyz"])])
        result = constitution.explain("harmless action text")
        assert result["decision"] == "allow"
        assert "ALLOWED" in result["explanation"]

    def test_deny_with_blocking_rule(self) -> None:
        result = Constitution.from_template("general").explain("invest in crypto buy stocks")
        assert result["decision"] == "deny"
        assert result["blocking_rules"]

    def test_warnings_only(self) -> None:
        constitution = _make_constitution(
            [_simple_rule(severity="low", keywords=["soft_warning_xyz"])]
        )
        result = constitution.explain("action with soft_warning_xyz mention")
        assert result["decision"] == "allow"
        assert result["warning_rules"]
        assert "warning" in result["explanation"].lower()


class TestDiff:
    def test_no_changes(self) -> None:
        constitution = _make_constitution([_simple_rule()])
        result = constitution.diff(constitution)
        assert result["hash_changed"] is False
        assert result["summary"] == "no changes"

    def test_severity_change_tracked(self) -> None:
        original = _make_constitution([_simple_rule("D1", severity="low")])
        updated = _make_constitution([_simple_rule("D1", severity="critical")])
        result = original.diff(updated)
        assert result["hash_changed"] is True
        assert len(result["severity_changes"]) == 1
        assert result["severity_changes"][0]["old"] == "low"


class TestUpdateRule:
    def test_update_nonexistent_raises(self) -> None:
        constitution = _make_constitution([_simple_rule("U1")])
        with pytest.raises(KeyError, match="not found"):
            constitution.update_rule("GHOST", text="new text")

    def test_update_creates_new_constitution(self) -> None:
        constitution = _make_constitution([_simple_rule("U1")])
        updated = constitution.update_rule("U1", text="updated text", change_reason="test")
        rule = updated.get_rule("U1")
        assert updated.hash != constitution.hash
        assert rule is not None
        assert rule.text == "updated text"

    def test_rule_history_recorded(self) -> None:
        constitution = _make_constitution([_simple_rule("U1")])
        updated = constitution.update_rule("U1", text="v2", change_reason="reason1")
        assert updated.rule_version("U1") == 2
        assert len(updated.rule_changelog("U1")) == 1

    def test_severity_string_coerced(self) -> None:
        constitution = _make_constitution([_simple_rule("U1", severity="low")])
        updated = constitution.update_rule("U1", severity="critical")
        rule = updated.get_rule("U1")
        assert rule is not None
        assert rule.severity == Severity.CRITICAL


class TestCascade:
    def test_hardcoded_parent_wins(self) -> None:
        parent = Constitution(
            rules=[
                Rule(
                    id="F1",
                    text="parent hardcoded",
                    severity=Severity.CRITICAL,
                    keywords=["kw"],
                    hardcoded=True,
                )
            ]
        )
        child = Constitution(
            rules=[
                Rule(id="F1", text="child override", severity=Severity.LOW, keywords=["kw"]),
                Rule(id="F2", text="child only", severity=Severity.LOW, keywords=["kw2"]),
            ]
        )
        federated = parent.cascade(child)
        rule = federated.get_rule("F1")
        assert rule is not None
        assert rule.text == "parent hardcoded"
        assert federated.get_rule("F2") is not None

    def test_non_hardcoded_child_wins(self) -> None:
        parent = Constitution(
            rules=[
                Rule(
                    id="F1",
                    text="parent",
                    severity=Severity.HIGH,
                    keywords=["kw"],
                    hardcoded=False,
                )
            ]
        )
        child = Constitution(
            rules=[Rule(id="F1", text="child wins", severity=Severity.LOW, keywords=["kw"])]
        )
        federated = parent.cascade(child)
        rule = federated.get_rule("F1")
        assert rule is not None
        assert rule.text == "child wins"


class TestBuilder:
    def test_builder_extends_and_builds(self) -> None:
        constitution = (
            Constitution.from_template("general")
            .builder()
            .add_rule(
                "CUSTOM-001",
                "No risky export",
                severity="high",
                keywords=["risky export"],
                workflow_action="block",
            )
            .build()
        )
        assert constitution.get_rule("CUSTOM-001") is not None

    def test_builder_rejects_duplicate_rule_id(self) -> None:
        builder = Constitution.from_template("general").builder()
        with pytest.raises(ValueError, match="already exists"):
            builder.add_rule("GEN-001", "duplicate")


class TestMiscConstitution:
    def test_hash_versioned(self) -> None:
        constitution = _make_constitution([_simple_rule()])
        assert constitution.hash_versioned.startswith("sha256:v1:")

    def test_json_schema_structure(self) -> None:
        schema = Constitution.json_schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "rules" in schema["properties"]

    def test_from_rules(self) -> None:
        rule = Rule(id="FR1", text="test", severity=Severity.LOW, keywords=["kw"])
        constitution = Constitution.from_rules([rule], name="custom")
        assert constitution.name == "custom"
        assert len(constitution.rules) == 1


class TestFastAuditLog:
    def test_record_fast_and_entries(self) -> None:
        from acgs_lite.engine.core import _FastAuditLog

        log = _FastAuditLog("testhash")
        log.record_fast("req1", "agent1", "action1", True, [], "testhash", 1.0, "2026-01-01")
        assert len(log) == 1
        assert len(log.entries) == 1
        assert log.entries[0].agent_id == "agent1"

    def test_record_compat_shim(self) -> None:
        from acgs_lite.audit import AuditEntry
        from acgs_lite.engine.core import _FastAuditLog

        log = _FastAuditLog("h")
        entry = AuditEntry(
            id="r1",
            type="validation",
            agent_id="a1",
            action="act",
            valid=True,
            violations=[],
            constitutional_hash="h",
            latency_ms=1.0,
        )
        assert log.record(entry) == ""
        assert len(log) == 1
        assert log.entries[0].agent_id == "a1"


class TestNoopRecorder:
    def test_append_and_len(self) -> None:
        from acgs_lite.engine.core import _NoopRecorder

        recorder = _NoopRecorder()
        assert len(recorder) == 0
        recorder.append("anything")
        recorder.append(None)
        assert len(recorder) == 2


class TestDedupViolations:
    def test_dedup_removes_duplicates(self) -> None:
        from acgs_lite.engine.core import Violation, _dedup_violations

        first = Violation("R1", "text", Severity.HIGH, "content", "cat")
        duplicate = Violation("R1", "text", Severity.HIGH, "content2", "cat")
        second = Violation("R2", "text2", Severity.LOW, "content", "cat2")
        result = _dedup_violations([first, duplicate, second])
        assert len(result) == 2
        assert result[0].rule_id == "R1"
        assert result[1].rule_id == "R2"


class TestValidationResult:
    def test_to_dict(self) -> None:
        from acgs_lite.engine.core import ValidationResult, Violation

        result = ValidationResult(
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
        payload = result.to_dict()
        assert payload["valid"] is False
        assert len(payload["violations"]) == 2
        assert payload["violations"][0]["severity"] == "critical"

    def test_blocking_violations(self) -> None:
        from acgs_lite.engine.core import ValidationResult, Violation

        result = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[
                Violation("R1", "txt", Severity.CRITICAL, "m", "cat"),
                Violation("R2", "txt2", Severity.LOW, "m2", "cat2"),
            ],
        )
        blocking = result.blocking_violations
        assert len(blocking) == 1
        assert blocking[0].rule_id == "R1"

    def test_warnings(self) -> None:
        from acgs_lite.engine.core import ValidationResult, Violation

        # warnings is a separate field from violations; populate it directly.
        result = ValidationResult(
            valid=True,
            constitutional_hash="abc",
            warnings=[
                Violation("R1", "txt", Severity.LOW, "m", "cat"),
                Violation("R2", "txt2", Severity.MEDIUM, "m2", "cat2"),
            ],
        )
        assert len(result.warnings) == 2


class TestGovernanceEngineSlowPath:
    def test_validate_allow_with_real_audit_log(self) -> None:
        from acgs_lite.audit import AuditLog
        from acgs_lite.engine.core import GovernanceEngine

        constitution = _make_constitution([_simple_rule(keywords=["never_match_xyz_abc"])])
        audit_log = AuditLog()
        engine = GovernanceEngine(constitution, audit_log=audit_log)
        result = engine.validate("harmless action")
        assert result.valid is True
        assert len(audit_log.entries) == 1
        assert audit_log.entries[0].valid is True
