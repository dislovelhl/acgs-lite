"""Compliance report exporter — text, markdown, and JSON output formats.

Converts MultiFrameworkReport and individual FrameworkAssessment objects
into human-readable and machine-readable formats for auditors, executives,
and automated pipelines.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.compliance import MultiFrameworkAssessor
    from acgs_lite.compliance.report_exporter import ComplianceReportExporter

    report = MultiFrameworkAssessor().assess({"system_id": "my-ai", ...})
    exporter = ComplianceReportExporter(report, title="Q1 Compliance Report")

    exporter.to_text()               # plain text
    exporter.to_markdown()           # GitHub-flavoured markdown
    exporter.to_json()               # machine-readable JSON string
    exporter.to_text_file("out.txt")
    exporter.to_markdown_file("out.md")
    exporter.to_json_file("out.json")
"""

from __future__ import annotations

import json
from pathlib import Path

from acgs_lite.compliance.base import FrameworkAssessment, MultiFrameworkReport


class ComplianceReportExporter:
    """Export compliance reports to text, markdown, and JSON formats.

    Args:
        report: A MultiFrameworkReport to export.
        title: Optional report title.
    """

    def __init__(
        self,
        report: MultiFrameworkReport,
        title: str = "Multi-Framework Compliance Report",
    ) -> None:
        self._report = report
        self._title = title

    # ------------------------------------------------------------------
    # Plain text
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        """Render the report as plain text."""
        lines: list[str] = []
        r = self._report

        lines.append(f"{'=' * 72}")
        lines.append(f"  {self._title}")
        lines.append(f"{'=' * 72}")
        lines.append(f"System:           {r.system_id}")
        lines.append(f"Assessed at:      {r.assessed_at}")
        lines.append(f"Overall score:    {r.overall_score:.1%}")
        lines.append(f"ACGS-lite coverage: {r.acgs_lite_total_coverage:.1%}")
        lines.append(f"Frameworks:       {len(r.frameworks_assessed)}")
        lines.append("")

        for fid in r.frameworks_assessed:
            a = r.by_framework[fid]
            lines.append(self.framework_summary_text(a))
            lines.append("")

        if r.cross_framework_gaps:
            lines.append("CROSS-FRAMEWORK GAPS")
            lines.append("-" * 40)
            for gap in r.cross_framework_gaps:
                lines.append(f"  • {gap}")
            lines.append("")

        if r.recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 40)
            for rec in r.recommendations:
                lines.append(f"  {rec}")
            lines.append("")

        lines.append(
            "DISCLAIMER: Indicative self-assessment only. Not legal advice. "
            "Consult qualified legal counsel for binding compliance opinions."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the report as GitHub-flavoured markdown."""
        lines: list[str] = []
        r = self._report

        lines.append(f"# {self._title}")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------||")
        lines.append(f"| System | `{r.system_id}` |")
        lines.append(f"| Assessed at | {r.assessed_at} |")
        lines.append(f"| Overall score | **{r.overall_score:.1%}** |")
        lines.append(f"| ACGS-lite coverage | {r.acgs_lite_total_coverage:.1%} |")
        lines.append(f"| Frameworks assessed | {len(r.frameworks_assessed)} |")
        lines.append("")

        for fid in r.frameworks_assessed:
            a = r.by_framework[fid]
            lines.append(self.framework_summary_markdown(a))
            lines.append("")

        if r.cross_framework_gaps:
            lines.append("## Cross-Framework Gaps")
            lines.append("")
            for gap in r.cross_framework_gaps:
                lines.append(f"- {gap}")
            lines.append("")

        if r.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in r.recommendations:
                lines.append(f"1. {rec}")
            lines.append("")

        lines.append(
            "> **Disclaimer:** Indicative self-assessment only. Not legal advice. "
            "Consult qualified legal counsel for binding compliance opinions."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Render the report as a JSON string."""
        data = self._report.to_dict()
        data["title"] = self._title
        return json.dumps(data, indent=indent, ensure_ascii=False)

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    def to_text_file(self, path: str | Path) -> None:
        """Write the text report to a file, creating directories as needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_text(), encoding="utf-8")

    def to_markdown_file(self, path: str | Path) -> None:
        """Write the markdown report to a file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_markdown(), encoding="utf-8")

    def to_json_file(self, path: str | Path) -> None:
        """Write the JSON report to a file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    # ------------------------------------------------------------------
    # Single-framework helpers
    # ------------------------------------------------------------------

    @staticmethod
    def framework_summary_text(assessment: FrameworkAssessment) -> str:
        """Render a single framework assessment as plain text."""
        lines: list[str] = []
        a = assessment
        lines.append(f"--- {a.framework_name} ({a.framework_id}) ---")
        lines.append(f"  Score:          {a.compliance_score:.1%}")
        lines.append(f"  ACGS coverage:  {a.acgs_lite_coverage:.1%}")
        lines.append(f"  Items:          {len(a.items)}")
        lines.append(f"  Gaps:           {len(a.gaps)}")
        if a.gaps:
            for gap in a.gaps[:5]:
                lines.append(f"    ✗ {gap}")
            if len(a.gaps) > 5:
                lines.append(f"    ... and {len(a.gaps) - 5} more")
        return "\n".join(lines)

    @staticmethod
    def framework_summary_markdown(assessment: FrameworkAssessment) -> str:
        """Render a single framework assessment as markdown."""
        lines: list[str] = []
        a = assessment
        lines.append(f"### {a.framework_name} (`{a.framework_id}`)")
        lines.append("")
        lines.append(f"- **Score:** {a.compliance_score:.1%}")
        lines.append(f"- **ACGS coverage:** {a.acgs_lite_coverage:.1%}")
        lines.append(f"- **Items:** {len(a.items)}")
        lines.append(f"- **Gaps:** {len(a.gaps)}")
        if a.gaps:
            lines.append("")
            for gap in a.gaps[:5]:
                lines.append(f"  - ✗ {gap}")
            if len(a.gaps) > 5:
                lines.append(f"  - ... and {len(a.gaps) - 5} more")
        return "\n".join(lines)
