from __future__ import annotations

from dataclasses import dataclass

import pytest

from acgs_lite.arckit.command_emitter import emit_command, write_command
from acgs_lite.arckit.exporter import (
    _framework_sections,
    _gap_analysis,
    _load_audit_summary,
    _load_rules,
)
from acgs_lite.arckit.generator import (
    build_constitution,
    manifest_from_yaml,
    rules_from_dpia,
    rules_from_principles,
    rules_from_requirements,
    rules_from_risks,
    source_as_dict,
)
from acgs_lite.arckit.models import ArcKitSource, ExtractedRule
from acgs_lite.arckit.parser import (
    parse_principles,
    parse_project,
    parse_requirements,
    parse_risk_register,
)


def test_generator_filter_helpers_and_source_dict() -> None:
    rules = [
        ExtractedRule("PRIN-001", "principle", "medium", "principles", source_type="PRIN"),
        ExtractedRule("RISK-001", "risk", "critical", "risk", source_type="RISK"),
        ExtractedRule("DATA-001", "data", "critical", "data-protection", source_type="DPIA"),
        ExtractedRule("COMP-001", "comp", "high", "compliance", source_type="REQ"),
    ]
    assert rules_from_principles(rules) == [rules[0]]
    assert rules_from_risks(rules) == [rules[1]]
    assert rules_from_dpia(rules) == [rules[2]]
    assert rules_from_requirements(rules) == [rules[3]]
    assert source_as_dict(ArcKitSource(project_id="001"))["project_id"] == "001"


def test_build_constitution_from_rule_list_dedupes_ids_and_round_trips(tmp_path) -> None:
    rules = [
        ExtractedRule("COMP-001", "Rule one", "high", "compliance"),
        ExtractedRule("COMP-001", "Rule two", "high", "compliance"),
    ]
    manifest = build_constitution(rules, source=ArcKitSource(project_id="222"), name="custom")
    assert [rule["id"] for rule in manifest.rules] == ["COMP-001", "COMP-002"]
    target = tmp_path / "constitution.yaml"
    manifest.write_yaml(target)
    loaded = manifest_from_yaml(target)
    assert loaded.name == "custom"


def test_command_emitter_claude_and_invalid_format(tmp_path) -> None:
    assert "/arckit:acgs" in emit_command("claude")
    target = tmp_path / "claude.md"
    write_command("claude", target)
    assert target.exists()
    with pytest.raises(ValueError):
        emit_command("unknown")


@dataclass(frozen=True)
class EmptyReport:
    by_framework: dict
    cross_framework_gaps: tuple = ()


def test_exporter_missing_framework_and_fallback_gap_paths(tmp_path) -> None:
    sections = _framework_sections(EmptyReport(by_framework={}))
    assert "Not assessed" in "\n".join(sections)
    gaps = _gap_analysis(EmptyReport(by_framework={}))
    assert "Independent legal review" in "\n".join(gaps)
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    assert _load_rules(bad_yaml) == []


def test_exporter_reads_jsonl_audit_summary(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text('{"event": "allow"}\n{"event": "violation", "rule": "R1"}\n', encoding="utf-8")
    summary = _load_audit_summary(audit)
    assert summary["entries"] == 2
    assert summary["violations"] == 1


def test_parser_warning_paths_and_heading_requirements(tmp_path) -> None:
    principles = tmp_path / "ARC-001-PRIN-v1.0.md"
    principles.write_text(
        "| Field | Value |\n|---|---|\n| Document ID | ARC-001-PRIN-v1.0 |\n", encoding="utf-8"
    )
    with pytest.warns(RuntimeWarning):
        assert parse_principles(principles) == []

    risks = tmp_path / "ARC-001-RISK-v1.0.md"
    risks.write_text(
        "| Field | Value |\n|---|---|\n| Document ID | ARC-001-RISK-v1.0 |\n", encoding="utf-8"
    )
    with pytest.warns(RuntimeWarning):
        assert parse_risk_register(risks) == []

    requirements = tmp_path / "ARC-001-REQ-v1.0.md"
    requirements.write_text(
        "# Requirements\n\n"
        "#### SEC-9: Secret handling\n\n"
        "**Requirement**: The system must not expose API keys.\n",
        encoding="utf-8",
    )
    parsed = parse_requirements(requirements)
    assert parsed[0].severity == "critical"


@pytest.mark.parametrize(
    "phrase",
    [
        "must not expose API keys",
        "shall not expose API keys",
        "must never expose API keys",
        "is prohibited from exposing API keys",
        "is forbidden from exposing API keys",
    ],
)
def test_requirement_critical_verbs_map_to_critical(tmp_path, phrase: str) -> None:
    requirements = tmp_path / "ARC-001-REQ-v1.0.md"
    requirements.write_text(
        f"# Requirements\n\n#### SEC-9: Secret handling\n\n**Requirement**: The system {phrase}.\n",
        encoding="utf-8",
    )

    parsed = parse_requirements(requirements)

    assert parsed[0].severity == "critical"


def test_parser_project_not_found_and_empty_project(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_project(tmp_path / "missing")
    project = parse_project(tmp_path)
    assert project.project_id == "unknown"
    assert project.rules == []
