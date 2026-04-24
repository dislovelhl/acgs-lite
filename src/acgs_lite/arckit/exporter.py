"""Export ACGS compliance evidence as an arc-kit Markdown artifact."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

try:
    _VERSION = _pkg_version("acgs-lite")
except PackageNotFoundError:
    _VERSION = "dev"


DEFAULT_FRAMEWORKS = ["eu_ai_act", "nist_ai_rmf", "iso_42001", "gdpr"]

_GAP_FALLBACK = "Independent legal review and residual-risk sign-off are not recorded."


def export_evidence(
    *,
    system_id: str,
    project_id: str,
    assessor: Any | None = None,
    domain: str = "general",
    constitution_path: str | Path | None = None,
    audit_log_path: str | Path | None = None,
    jurisdiction: str = "european_union",
    processes_pii: bool | None = None,
    autonomy_level: str | None = None,
) -> str:
    """Run ACGS compliance assessment and render arc-kit evidence Markdown.

    ``processes_pii`` and ``autonomy_level`` should reflect real system
    characteristics. When omitted they default to ``True`` and
    ``'human_in_the_loop'`` and the output is marked as using unverified
    defaults so reviewers know to supply accurate values.
    """
    _pii = processes_pii if processes_pii is not None else True
    _autonomy = autonomy_level if autonomy_level is not None else "human_in_the_loop"
    _unverified_defaults = processes_pii is None or autonomy_level is None

    if assessor is None:
        from acgs_lite.compliance import MultiFrameworkAssessor

        assessor = MultiFrameworkAssessor(frameworks=DEFAULT_FRAMEWORKS)

    report = assessor.assess(
        {
            "system_id": system_id,
            "jurisdiction": jurisdiction,
            "domain": domain,
            "processes_pii": _pii,
            "autonomy_level": _autonomy,
        }
    )
    rules = _load_rules(constitution_path) if constitution_path else []
    audit_summary = _load_audit_summary(audit_log_path) if audit_log_path else None
    assessed_at = getattr(report, "assessed_at", "") or datetime.now(timezone.utc).isoformat()

    lines = [
        f"> **Template Origin**: ACGS Bridge | **ACGS Version**: {_VERSION} | **Command**: `acgs arckit export`",
        "",
        *_build_document_header(project_id, assessed_at),
    ]
    if _unverified_defaults:
        lines += [
            "> **⚠ UNVERIFIED DEFAULTS**: `processes_pii` and/or `autonomy_level` were not supplied.",
            "> Assessment used placeholder values. Provide accurate system facts before treating",
            "> this document as regulatory evidence.",
            "",
        ]
    lines += [
        "## Executive Summary",
        "",
        f"System `{system_id}` assessed across {len(report.frameworks_assessed)} frameworks.",
        f"Overall compliance score: **{report.overall_score:.0%}**",
        "",
    ]
    lines.extend(_framework_sections(report))
    if rules:
        lines.extend(_rules_inventory(rules))
    if audit_summary is not None:
        lines.extend(_audit_section(audit_summary))
    lines.extend(_gap_analysis(report))
    return "\n".join(lines).rstrip() + "\n"


def _build_document_header(project_id: str, assessed_at: str) -> list[str]:
    return [
        "## Document Control",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Document ID** | ARC-{project_id}-ACGS-v1.0 |",
        "| **Document Type** | ACGS Compliance Evidence |",
        f"| **Project** | Project {project_id} |",
        "| **Classification** | OFFICIAL |",
        "| **Status** | DRAFT |",
        "| **Version** | 1.0 |",
        f"| **Created Date** | {assessed_at[:10]} |",
        f"| **Last Modified** | {assessed_at[:10]} |",
        "| **Owner** | ACGS Bridge |",
        "",
    ]


def _framework_sections(report: Any) -> list[str]:
    titles = {
        "eu_ai_act": "EU AI Act Compliance Score",
        "nist_ai_rmf": "NIST AI RMF Coverage",
        "iso_42001": "ISO 42001 Coverage",
        "gdpr": "GDPR Coverage",
    }
    lines: list[str] = []
    for framework_id in DEFAULT_FRAMEWORKS:
        assessment = report.by_framework.get(framework_id)
        title = titles[framework_id]
        lines.extend([f"## {title}", "", "| Metric | Value |", "|--------|-------|"])
        if assessment is None:
            lines.extend(["| Score | Not assessed |", "| Coverage | Not assessed |", ""])
            continue
        lines.extend(
            [
                f"| Framework | {_escape_table(assessment.framework_name)} |",
                f"| Score | {_bar(assessment.compliance_score)} {assessment.compliance_score:.0%} |",
                f"| ACGS Coverage | {_bar(assessment.acgs_lite_coverage)} {assessment.acgs_lite_coverage:.0%} |",
                f"| Open Gaps | {len(assessment.gaps)} |",
                "",
            ]
        )
    return lines


def _rules_inventory(rules: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Active Rules Inventory",
        "",
        "| Rule ID | Severity | Category | Text |",
        "|---------|----------|----------|------|",
    ]
    for rule in rules:
        lines.append(
            f"| {rule.get('id', '')} | {rule.get('severity', '')} | "
            f"{rule.get('category', '')} | {_escape_table(rule.get('text', ''))} |"
        )
    lines.append("")
    return lines


def _audit_section(summary: dict[str, Any]) -> list[str]:
    return [
        "## Audit Trail Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Entries | {summary['entries']} |",
        f"| Violations | {summary['violations']} |",
        f"| Last Event | {_escape_table(str(summary['last_event']))} |",
        "",
    ]


def _gap_analysis(report: Any) -> list[str]:
    lines = ["## Gap Analysis", ""]
    gaps = list(getattr(report, "cross_framework_gaps", ()) or ())
    if not gaps:
        for assessment in report.by_framework.values():
            gaps.extend(list(getattr(assessment, "gaps", ()) or ()))
    if not gaps:
        gaps = [_GAP_FALLBACK]
    for gap in gaps[:10]:
        lines.append(f"- {gap}")
    lines.append("")
    return lines


def _load_rules(path: str | Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    rules = data.get("rules", [])
    return rules if isinstance(rules, list) else []


def _load_audit_summary(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in raw.splitlines() if line.strip()]
    entries = data if isinstance(data, list) else data.get("entries", [])
    violations = sum(
        1
        for entry in entries
        if isinstance(entry, dict)
        and (entry.get("event") == "violation" or entry.get("type") == "violation")
    )
    return {
        "entries": len(entries),
        "violations": violations,
        "last_event": json.dumps(entries[-1], sort_keys=True)[:80] if entries else "none",
    }


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score * width)))
    return "█" * filled + "░" * (width - filled)


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
