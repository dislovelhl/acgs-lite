"""Compliance report exporter — text, Markdown, and JSON output.

Converts a MultiFrameworkReport or FrameworkAssessment into
human-readable output suitable for auditors, executives, and developers.

Three output formats:
- **text**:     Plain-text executive summary + per-framework detail
- **markdown**: GitHub-flavoured Markdown with tables and status badges
- **json**:     Full machine-readable report (delegates to report.to_dict())

Usage::

    from acgs_lite.compliance import MultiFrameworkAssessor
    from acgs_lite.compliance.report_exporter import ComplianceReportExporter

    report = MultiFrameworkAssessor().assess({"system_id": "my-ai"})
    exporter = ComplianceReportExporter(report)

    print(exporter.to_text())
    exporter.to_markdown_file("compliance_report.md")
    exporter.to_json_file("compliance_report.json")

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from acgs_lite.compliance.base import (
    ChecklistStatus,
    FrameworkAssessment,
    MultiFrameworkReport,
)

# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

_STATUS_EMOJI: dict[str, str] = {
    ChecklistStatus.COMPLIANT: "✅",
    ChecklistStatus.PARTIAL: "🔶",
    ChecklistStatus.NON_COMPLIANT: "❌",
    ChecklistStatus.PENDING: "⏳",
    ChecklistStatus.NOT_APPLICABLE: "➖",
}

_SCORE_LABEL = {
    (0.9, 1.01): "Excellent",
    (0.75, 0.9): "Good",
    (0.5, 0.75): "Fair",
    (0.25, 0.5): "Needs Improvement",
    (0.0, 0.25): "Critical Gaps",
}


def _score_label(score: float) -> str:
    for (lo, hi), label in _SCORE_LABEL.items():
        if lo <= score < hi:
            return label
    return "Unknown"


def _score_bar(score: float, width: int = 20) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _pct(score: float) -> str:
    return f"{score:.1%}"


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


class ComplianceReportExporter:
    """Export a MultiFrameworkReport in text, Markdown, or JSON format.

    Args:
        report: The MultiFrameworkReport produced by MultiFrameworkAssessor.
        title: Optional report title.

    """

    def __init__(
        self,
        report: MultiFrameworkReport,
        title: str = "ACGS AI Governance — Compliance Report",
    ) -> None:
        self._report = report
        self._title = title
        self._generated_at = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    # Plain text
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        """Return a full plain-text compliance report."""
        r = self._report
        lines: list[str] = []

        # Header
        lines += [
            "=" * 72,
            self._title.center(72),
            "=" * 72,
            f"  System:       {r.system_id}",
            f"  Generated:    {self._generated_at}",
            f"  Frameworks:   {len(r.frameworks_assessed)}",
            f"  Overall:      {_pct(r.overall_score)}  "
            f"{_score_bar(r.overall_score)}  {_score_label(r.overall_score)}",
            f"  ACGS coverage:{_pct(r.acgs_lite_total_coverage)} "
            f"(requirements auto-satisfied by acgs-lite)",
            "=" * 72,
            "",
        ]

        # Framework summary table
        lines += [
            "FRAMEWORK SUMMARY",
            "-" * 72,
            f"  {'Framework':<42} {'Score':>6}  {'Coverage':>8}  {'Gaps':>4}",
            "  " + "-" * 66,
        ]
        for fid in sorted(r.frameworks_assessed):
            fa = r.by_framework.get(fid)
            if fa is None:
                continue
            lines.append(
                f"  {fa.framework_name[:42]:<42} "
                f"{_pct(fa.compliance_score):>6}  "
                f"{_pct(fa.acgs_lite_coverage):>8}  "
                f"{len(fa.gaps):>4}"
            )
        lines += ["", ""]

        # Cross-framework gaps
        if r.cross_framework_gaps:
            lines += ["CROSS-FRAMEWORK GAPS", "-" * 72]
            for i, gap in enumerate(r.cross_framework_gaps, 1):
                lines.append(f"  {i}. {gap}")
            lines += ["", ""]

        # Per-framework detail
        lines += ["FRAMEWORK DETAIL", "-" * 72, ""]
        for fid in sorted(r.frameworks_assessed):
            fa = r.by_framework.get(fid)
            if fa is None:
                continue
            lines += _text_framework_section(fa)

        # Prioritised recommendations
        if r.recommendations:
            lines += ["PRIORITISED RECOMMENDATIONS", "-" * 72]
            for i, rec in enumerate(r.recommendations, 1):
                lines.append(f"  {i}. {rec}")
            lines += ["", ""]

        # Footer
        lines += [
            "=" * 72,
            "DISCLAIMER".center(72),
            "This is an indicative self-assessment only. It is not legal advice.",
            "Consult qualified legal counsel for binding compliance opinions.",
            "=" * 72,
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Return a GitHub-flavoured Markdown compliance report."""
        r = self._report
        lines: list[str] = []

        # Title
        lines += [
            f"# {self._title}",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **System** | `{r.system_id}` |",
            f"| **Generated** | {self._generated_at} |",
            f"| **Frameworks assessed** | {len(r.frameworks_assessed)} |",
            f"| **Overall score** | {_pct(r.overall_score)} — {_score_label(r.overall_score)} |",
            f"| **ACGS-lite auto-coverage** | {_pct(r.acgs_lite_total_coverage)} |",
            "",
        ]

        # Summary table
        lines += [
            "## Framework Summary",
            "",
            "| Framework | Score | ACGS Coverage | Gaps | Status |",
            "|-----------|------:|-------------:|-----:|--------|",
        ]
        for fid in sorted(r.frameworks_assessed):
            fa = r.by_framework.get(fid)
            if fa is None:
                continue
            badge = _md_score_badge(fa.compliance_score)
            lines.append(
                f"| {fa.framework_name} "
                f"| {_pct(fa.compliance_score)} "
                f"| {_pct(fa.acgs_lite_coverage)} "
                f"| {len(fa.gaps)} "
                f"| {badge} |"
            )
        lines += ["", ""]

        # Cross-framework gaps
        if r.cross_framework_gaps:
            lines += ["## ⚠️ Cross-Framework Gaps", ""]
            for gap in r.cross_framework_gaps:
                lines.append(f"- {gap}")
            lines += ["", ""]

        # Per-framework detail
        lines += ["## Framework Detail", ""]
        for fid in sorted(r.frameworks_assessed):
            fa = r.by_framework.get(fid)
            if fa is None:
                continue
            lines += _md_framework_section(fa)

        # Prioritised recommendations
        if r.recommendations:
            lines += ["## Prioritised Recommendations", ""]
            for i, rec in enumerate(r.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines += ["", ""]

        # Footer
        lines += [
            "---",
            "",
            "> **Disclaimer**: This is an indicative self-assessment only. "
            "It is not legal advice. Consult qualified legal counsel for "
            "binding compliance opinions.",
            "",
            f"*Generated by acgs-lite ComplianceReportExporter · "
            f"Constitutional Hash: `608508a9bd224290`*",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Return the full report as a JSON string."""
        data = self._report.to_dict()
        data["report_title"] = self._title
        data["generated_at"] = self._generated_at
        return json.dumps(data, indent=indent, default=str)

    # ------------------------------------------------------------------
    # File output helpers
    # ------------------------------------------------------------------

    def to_text_file(self, path: str | Path) -> Path:
        """Write plain-text report to *path*. Returns resolved Path."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_text(), encoding="utf-8")
        return p

    def to_markdown_file(self, path: str | Path) -> Path:
        """Write Markdown report to *path*. Returns resolved Path."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_markdown(), encoding="utf-8")
        return p

    def to_json_file(self, path: str | Path) -> Path:
        """Write JSON report to *path*. Returns resolved Path."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # Single-framework helper
    # ------------------------------------------------------------------

    @staticmethod
    def framework_summary_text(assessment: FrameworkAssessment) -> str:
        """Return a concise text summary for a single FrameworkAssessment."""
        lines = _text_framework_section(assessment)
        return "\n".join(lines)

    @staticmethod
    def framework_summary_markdown(assessment: FrameworkAssessment) -> str:
        """Return Markdown for a single FrameworkAssessment."""
        lines = _md_framework_section(assessment)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _text_framework_section(fa: FrameworkAssessment) -> list[str]:
    lines: list[str] = [
        f"  ┌─ {fa.framework_name}",
        f"  │  ID: {fa.framework_id}  │  "
        f"Score: {_pct(fa.compliance_score)}  │  "
        f"Coverage: {_pct(fa.acgs_lite_coverage)}  │  "
        f"Assessed: {fa.assessed_at[:10]}",
    ]
    if fa.gaps:
        lines.append("  │  GAPS:")
        for g in fa.gaps:
            lines.append(f"  │    - {g[:100]}")
    if fa.recommendations:
        lines.append("  │  RECOMMENDATIONS:")
        for rec in fa.recommendations[:3]:
            lines.append(f"  │    → {rec[:100]}")
    lines += ["  └─" + "─" * 66, ""]
    return lines


def _md_framework_section(fa: FrameworkAssessment) -> list[str]:
    lines: list[str] = [
        f"### {fa.framework_name}",
        "",
        f"**Score**: {_pct(fa.compliance_score)} {_md_score_badge(fa.compliance_score)} "
        f"| **ACGS coverage**: {_pct(fa.acgs_lite_coverage)} "
        f"| **Assessed**: {fa.assessed_at[:10]}",
        "",
    ]

    # Checklist items as a table (compliant only shown in summary mode)
    compliant_items = [i for i in fa.items if i.get("status") == "compliant"]
    gap_items = [i for i in fa.items if i.get("status") not in ("compliant", "not_applicable")]

    if gap_items:
        lines += [
            "<details><summary>⚠️ Open gaps</summary>",
            "",
            "| Ref | Requirement | Blocking |",
            "|-----|-------------|----------|",
        ]
        for item in gap_items:
            req = (item.get("requirement") or "")[:80]
            blocking = "🔴 Yes" if item.get("blocking") else "🟡 No"
            lines.append(f"| `{item['ref']}` | {req} | {blocking} |")
        lines += ["", "</details>", ""]

    if fa.recommendations:
        lines += ["**Recommendations:**", ""]
        for rec in fa.recommendations[:5]:
            lines.append(f"- {rec}")
        lines += ["", ""]

    return lines


def _md_score_badge(score: float) -> str:
    if score >= 0.9:
        return "🟢 Excellent"
    elif score >= 0.75:
        return "🔵 Good"
    elif score >= 0.5:
        return "🟡 Fair"
    elif score >= 0.25:
        return "🟠 Needs Improvement"
    else:
        return "🔴 Critical Gaps"
