from __future__ import annotations

import warnings

from acgs_lite.arckit.parser import (
    FILENAME_RE,
    MAX_ARTIFACT_BYTES,
    parse_dpia,
    parse_principles,
    parse_project,
    parse_requirements,
    parse_risk_register,
)

from .helpers import fixture_path, fixtures_dir


def test_parse_001_principles_return_extracted_rules() -> None:
    rules = parse_principles(fixture_path("ARC-001-PRIN-v1.0.md"))
    assert rules
    assert all(rule.category == "principles" for rule in rules)


def test_parse_002_security_principle_has_high_severity() -> None:
    rules = parse_principles(fixture_path("ARC-001-PRIN-v1.0.md"))
    security_rule = next(rule for rule in rules if "Security by Design" in rule.text)
    assert security_rule.severity == "high"


def test_parse_003_high_risk_maps_to_critical() -> None:
    rules = parse_risk_register(fixture_path("ARC-001-RISK-v1.0.md"))
    assert rules[0].severity == "critical"


def test_parse_004_medium_risk_maps_to_high() -> None:
    rules = parse_risk_register(fixture_path("ARC-001-RISK-v1.0.md"))
    assert rules[1].severity == "high"


def test_parse_005_low_risk_maps_to_medium() -> None:
    rules = parse_risk_register(fixture_path("ARC-001-RISK-v1.0.md"))
    assert rules[2].severity == "medium"


def test_parse_006_dpia_extracts_personal_data_keywords() -> None:
    rules = parse_dpia(fixture_path("ARC-001-DPIA-v1.0.md"))
    assert any("email address" in rule.keywords for rule in rules)


def test_parse_007_dpia_generates_data_rule_ids() -> None:
    rules = parse_dpia(fixture_path("ARC-001-DPIA-v1.0.md"))
    assert all(rule.id.startswith("DATA-") for rule in rules)


def test_parse_008_requirements_extracts_security_rules() -> None:
    rules = parse_requirements(fixture_path("ARC-001-REQ-v1.0.md"))
    assert len(rules) == 3
    assert all(rule.id.startswith("COMP-") for rule in rules)


def test_parse_009_requirements_ignore_functional_requirements() -> None:
    rules = parse_requirements(fixture_path("ARC-001-REQ-v1.0.md"))
    assert not any("search for case records" in rule.text for rule in rules)


def test_parse_010_missing_optional_sections_warn_not_error(tmp_path) -> None:
    path = tmp_path / "ARC-001-DPIA-v1.0.md"
    path.write_text("# DPIA\n\n| Field | Value |\n|---|---|\n| Document ID | ARC-001-DPIA-v1.0 |\n")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        rules = parse_dpia(path)
    assert rules == []
    assert captured


def test_parse_011_empty_files_return_empty_list(tmp_path) -> None:
    path = tmp_path / "ARC-001-RISK-v1.0.md"
    path.write_text("")
    assert parse_risk_register(path) == []


def test_parse_012_extracts_document_id_from_header() -> None:
    rules = parse_principles(fixture_path("ARC-001-PRIN-v1.0.md"))
    assert {rule.source_document_id for rule in rules} == {"ARC-001-PRIN-v1.0"}


def test_parse_013_project_discovers_all_recognized_artifacts() -> None:
    project = parse_project(fixtures_dir())
    assert len(project.rules) >= 13
    assert project.project_id == "001"


def test_parse_014_project_returns_artifact_hashes() -> None:
    project = parse_project(fixtures_dir())
    assert len(project.source.artifact_hashes) == 4
    assert all(len(value) == 64 for value in project.source.artifact_hashes.values())


def test_parse_016_cross_project_artifacts_skipped_with_warning(tmp_path) -> None:
    """ADV-1: artifacts from a different project_id must be skipped, not merged."""
    for source in fixtures_dir().glob("ARC-001-*.md"):
        (tmp_path / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    # Plant a rogue file from project ARC-002
    (tmp_path / "ARC-002-PRIN-v1.0.md").write_text(
        "# Principles\n\n### P-001: Rogue\n**Principle Statement**: This must not leak.\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    assert project.project_id == "001"
    assert not any("rogue" in rule.text.lower() for rule in project.rules)
    assert any("002" in w and "skipping" in w.lower() for w in project.source.warnings)


def test_filename_regex_rejects_path_traversal_names() -> None:
    unsafe_names = [
        "ARC-../etc-RISK-v1.0.md",
        "ARC-..\\etc-RISK-v1.0.md",
        "ARC-001/../../etc-RISK-v1.0.md",
        "ARC-001-RISK-v../1.md",
        "ARC-001-RISK-v1.0/evil.md",
    ]
    assert all(FILENAME_RE.fullmatch(name) is None for name in unsafe_names)


def test_project_skips_filesystem_safe_malformed_arc_names(tmp_path) -> None:
    malformed_names = [
        "ARC-001-RISK-v1.0-extra.md",
        "ARC-001--RISK-v1.0.md",
        "ARC-001-RISK-v1.0.md.bak",
    ]
    for name in malformed_names:
        (tmp_path / name).write_text(
            "# Risks\n\n| Risk ID | Description | Level |\n|---|---|---|\n| R-1 | Rogue risk | High |\n",
            encoding="utf-8",
        )

    project = parse_project(tmp_path)

    assert project.rules == []
    assert project.source.artifact_ids == []
    assert project.source.artifact_hashes == {}


def test_project_skips_oversized_artifact_metadata(tmp_path) -> None:
    path = tmp_path / "ARC-001-REQ-v1.0.md"
    path.write_text("x" * (MAX_ARTIFACT_BYTES + 1), encoding="utf-8")

    project = parse_project(tmp_path)

    assert project.rules == []
    assert project.source.artifact_ids == []
    assert project.source.artifact_hashes == {}
    assert any("exceeds limit" in warning for warning in project.source.warnings)


def test_parse_015_project_skips_unrecognized_markdown(tmp_path) -> None:
    for source in fixtures_dir().glob("*.md"):
        (tmp_path / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Ignore me\n", encoding="utf-8")
    project = parse_project(tmp_path)
    assert "notes" not in project.source.artifact_ids


def test_parse_017_requirements_mixed_table_and_heading_extracts_both(tmp_path) -> None:
    """Regression: 'or' logic silently dropped heading requirements when a table was present."""
    path = tmp_path / "ARC-001-REQ-v1.0.md"
    path.write_text(
        "# Requirements\n\n"
        "| Field | Value |\n|---|---|\n| Document ID | ARC-001-REQ-v1.0 |\n\n"
        "## Requirements\n\n"
        "| Requirement ID | Type | Requirement | Priority |\n"
        "|---|---|---|---|\n"
        "| COMP-TBL-001 | Compliance | The system must encrypt personal data at rest | MUST_HAVE |\n\n"
        "#### SEC-HDG-001: Audit Logging\n\n"
        "**Requirement**: All administrative actions must be logged for GDPR review.\n",
        encoding="utf-8",
    )
    rules = parse_requirements(path)
    ids = [r.source_rule_id for r in rules]
    assert "COMP-TBL-001" in ids, "table requirement must be extracted"
    assert "SEC-HDG-001" in ids, "heading requirement silently dropped (regression)"
    assert len(rules) == 2
