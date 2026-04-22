from __future__ import annotations

import json
import re
from typing import ClassVar

from acgs_lite.arckit.exporter import export_evidence
from acgs_lite.arckit.generator import build_constitution
from acgs_lite.arckit.parser import parse_project
from acgs_lite.compliance import MultiFrameworkAssessor

from .helpers import fixtures_dir


def test_exp_001_export_returns_non_empty_string() -> None:
    assert export_evidence(project_id="001", system_id="test-agent").strip()


def test_exp_002_output_contains_header_table() -> None:
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert "| Field | Value |" in markdown


def test_exp_003_document_id_matches_pattern() -> None:
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert "ARC-001-ACGS-v1.0" in markdown


def test_exp_004_contains_eu_ai_act_section() -> None:
    assert "EU AI Act Compliance Score" in export_evidence(project_id="001", system_id="test-agent")


def test_exp_005_contains_nist_section() -> None:
    assert "NIST AI RMF Coverage" in export_evidence(project_id="001", system_id="test-agent")


def test_exp_006_contains_iso_section() -> None:
    assert "ISO 42001 Coverage" in export_evidence(project_id="001", system_id="test-agent")


def test_exp_007_contains_gdpr_section() -> None:
    assert "GDPR Coverage" in export_evidence(project_id="001", system_id="test-agent")


def test_exp_008_constitution_adds_active_rules_inventory(tmp_path) -> None:
    manifest = build_constitution(parse_project(fixtures_dir()))
    target = tmp_path / "constitution.yaml"
    manifest.write_yaml(target)
    markdown = export_evidence(project_id="001", system_id="test-agent", constitution_path=target)
    assert "Active Rules Inventory" in markdown


def test_exp_009_rules_inventory_shows_rule_ids_severity_categories(tmp_path) -> None:
    manifest = build_constitution(parse_project(fixtures_dir()))
    target = tmp_path / "constitution.yaml"
    manifest.write_yaml(target)
    markdown = export_evidence(project_id="001", system_id="test-agent", constitution_path=target)
    assert "| DATA-001 | critical | data-protection |" in markdown


def test_exp_010_audit_log_adds_audit_summary(tmp_path) -> None:
    audit_log = tmp_path / "audit.json"
    audit_log.write_text(json.dumps([{"event": "violation", "rule_id": "DATA-001"}]), encoding="utf-8")
    markdown = export_evidence(project_id="001", system_id="test-agent", audit_log_path=audit_log)
    assert "Audit Trail Summary" in markdown


def test_exp_010b_audit_summary_ignores_violation_substrings_in_notes(tmp_path) -> None:
    audit_log = tmp_path / "audit.json"
    audit_log.write_text(json.dumps([{"event": "allow", "note": "no violation detected"}]), encoding="utf-8")
    markdown = export_evidence(project_id="001", system_id="test-agent", audit_log_path=audit_log)
    assert "| Violations | 0 |" in markdown


def test_exp_011_markdown_has_balanced_fences_and_tables() -> None:
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert markdown.count("```") % 2 == 0
    assert re.search(r"\| Field \| Value \|\n\|-+\|-+\|", markdown)


def test_exp_012_no_optional_flags_still_valid() -> None:
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert "Gap Analysis" in markdown


def test_exp_013_scores_render_text_bars() -> None:
    assert "█" in export_evidence(project_id="001", system_id="test-agent")


def test_exp_014_gap_analysis_lists_uncovered_control_with_real_assessor() -> None:
    markdown = export_evidence(
        project_id="001",
        system_id="test-agent",
        assessor=MultiFrameworkAssessor(frameworks=["eu_ai_act", "nist_ai_rmf", "iso_42001", "gdpr"]),
    )
    assert re.search(r"## Gap Analysis\n\n- .+", markdown)


def test_int_003_multi_framework_assessor_runs_minimal_descriptor() -> None:
    report = MultiFrameworkAssessor(frameworks=["eu_ai_act"]).assess({"system_id": "test-agent"})
    assert report.overall_score >= 0


def test_int_004_export_contains_positive_eu_ai_act_score() -> None:
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert re.search(r"EU AI Act Compliance Score[\s\S]*Score \| █", markdown)


def test_exp_015_framework_name_with_pipe_does_not_corrupt_table() -> None:
    """ADV-2: assessor-derived framework_name containing '|' must be escaped."""
    class _FakeAssessment:
        framework_name = "EU | AI Act"
        compliance_score = 0.75
        acgs_lite_coverage = 0.80
        gaps: ClassVar[list] = []

    class _FakeReport:
        frameworks_assessed: ClassVar[list[str]] = ["eu_ai_act"]
        overall_score = 0.75
        assessed_at = ""
        by_framework: ClassVar[dict[str, _FakeAssessment]] = {"eu_ai_act": _FakeAssessment()}
        cross_framework_gaps: ClassVar[list] = []

    class _FakeAssessor:
        def assess(self, _descriptor):
            return _FakeReport()

    markdown = export_evidence(project_id="001", system_id="test-agent", assessor=_FakeAssessor())
    # No stray table-cell break: every table row must have balanced pipes
    for line in markdown.splitlines():
        if line.startswith("|") and "EU" in line:
            cells = [c.strip() for c in line.split("|")]
            assert len(cells) >= 3, f"Table row corrupted: {line!r}"


def test_exp_016_default_call_warns_about_unverified_system_facts() -> None:
    """Regression: hardcoded processes_pii/autonomy_level produces authoritative-looking output."""
    markdown = export_evidence(project_id="001", system_id="test-agent")
    assert "UNVERIFIED DEFAULTS" in markdown


def test_exp_017_explicit_system_facts_suppress_warning() -> None:
    """When caller supplies real system facts, no unverified-defaults warning appears."""
    markdown = export_evidence(
        project_id="001",
        system_id="test-agent",
        processes_pii=False,
        autonomy_level="fully_autonomous",
    )
    assert "UNVERIFIED DEFAULTS" not in markdown


def test_exp_018_explicit_processes_pii_appears_in_assessor_descriptor() -> None:
    """Caller-supplied processes_pii is passed through to the assessor descriptor."""
    captured: list[dict] = []

    class _CapturingAssessor:
        def assess(self, descriptor):
            captured.append(dict(descriptor))
            from acgs_lite.compliance import MultiFrameworkAssessor

            return MultiFrameworkAssessor().assess(descriptor)

    export_evidence(
        project_id="001",
        system_id="test-agent",
        assessor=_CapturingAssessor(),
        processes_pii=False,
        autonomy_level="batch_automated",
    )
    assert captured[0]["processes_pii"] is False
    assert captured[0]["autonomy_level"] == "batch_automated"

