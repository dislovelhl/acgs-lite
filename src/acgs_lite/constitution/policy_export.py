"""Multi-format policy export for governance constitutions.

Exports a ``Constitution`` to JSON, YAML, CSV (one row per rule), Markdown
table, and plain-text summary.  These formats serve audit, reporting, and
integration pipelines that consume tabular or structured rule data.

Example::

    from acgs_lite.constitution.policy_export import PolicyExporter

    exporter = PolicyExporter(constitution)

    json_str  = exporter.to_json()
    yaml_str  = exporter.to_yaml()
    csv_str   = exporter.to_csv()
    md_str    = exporter.to_markdown()
    txt_str   = exporter.to_text_summary()

    # Write to file
    exporter.export_file("/tmp/policy.csv", fmt="csv")

"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any

from .core import Constitution

_SUPPORTED_FORMATS = {"json", "yaml", "csv", "markdown", "text"}

_CSV_FIELDS = [
    "id",
    "text",
    "severity",
    "category",
    "workflow_action",
    "keywords",
    "patterns",
    "tags",
    "priority",
    "valid_from",
    "valid_until",
]


def _rule_to_row(rule: Any) -> dict[str, str]:
    """Convert a single Rule to a flat CSV-compatible dict."""
    return {
        "id": rule.id,
        "text": rule.text,
        "severity": rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity),
        "category": getattr(rule, "category", "") or "",
        "workflow_action": getattr(rule, "workflow_action", "") or "",
        "keywords": "|".join(getattr(rule, "keywords", []) or []),
        "patterns": "|".join(getattr(rule, "patterns", []) or []),
        "tags": "|".join(getattr(rule, "tags", []) or []),
        "priority": str(getattr(rule, "priority", 0)),
        "valid_from": str(getattr(rule, "valid_from", "") or ""),
        "valid_until": str(getattr(rule, "valid_until", "") or ""),
    }


class PolicyExporter:
    """Exports a :class:`~acgs_lite.constitution.core.Constitution` to multiple formats.

    Supported formats:

    - ``json`` — full structured JSON with metadata and rules array
    - ``yaml`` — YAML via the constitution's built-in ``to_yaml()``
    - ``csv`` — one row per rule, pipe-delimited multi-values (keywords, patterns, tags)
    - ``markdown`` — Markdown table with rule details
    - ``text`` — plain-text summary for human review

    Attributes:
        constitution: The constitution being exported.
    """

    def __init__(self, constitution: Constitution) -> None:
        self.constitution = constitution

    def to_json(self, *, indent: int = 2) -> str:
        """Return a JSON string representation of the constitution.

        Includes metadata (name, version, hash, rule count) and a rules array.

        Args:
            indent: JSON indentation level (default 2).

        Returns:
            Formatted JSON string.
        """
        rules = [_rule_to_row(r) for r in self.constitution.rules]
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "name": self.constitution.name,
            "version": getattr(self.constitution, "version", ""),
            "constitutional_hash": getattr(self.constitution, "hash", ""),
            "rule_count": len(rules),
            "rules": rules,
        }
        return json.dumps(payload, indent=indent, ensure_ascii=False)

    def to_yaml(self) -> str:
        """Return a YAML string via the constitution's built-in serialiser."""
        return self.constitution.to_yaml()

    def to_csv(self, *, delimiter: str = ",") -> str:
        """Return a CSV string with one row per rule.

        Multi-valued fields (keywords, patterns, tags) are pipe-separated (``|``).

        Args:
            delimiter: CSV column delimiter (default ``','``).

        Returns:
            CSV string with header row.
        """
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, delimiter=delimiter)
        writer.writeheader()
        for rule in self.constitution.rules:
            writer.writerow(_rule_to_row(rule))
        return buf.getvalue()

    def to_markdown(self) -> str:
        """Return a Markdown table of all rules.

        Columns: ID, Severity, Category, Workflow Action, Text.

        Returns:
            Markdown string.
        """
        lines: list[str] = []
        header = f"# {self.constitution.name} — Policy Rules\n"
        lines.append(header)
        lines.append("| ID | Severity | Category | Workflow | Text |")
        lines.append("|---|---|---|---|---|")
        for rule in self.constitution.rules:
            sev = rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity)
            cat = getattr(rule, "category", "") or ""
            wf = getattr(rule, "workflow_action", "") or ""
            text = rule.text.replace("|", "\\|")
            lines.append(f"| {rule.id} | {sev} | {cat} | {wf} | {text} |")
        return "\n".join(lines) + "\n"

    def to_text_summary(self) -> str:
        """Return a plain-text summary suitable for human review.

        Includes constitution metadata and a brief line per rule.

        Returns:
            Plain-text string.
        """
        c = self.constitution
        name = c.name
        version = getattr(c, "version", "")
        chash = getattr(c, "hash", "")
        rule_count = len(c.rules)

        lines: list[str] = [
            f"Constitution: {name}",
            f"Version:      {version}",
            f"Hash:         {chash}",
            f"Rules:        {rule_count}",
            "",
            "Rules:",
        ]
        for rule in c.rules:
            sev = rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity)
            cat = getattr(rule, "category", "") or "—"
            lines.append(f"  [{sev.upper():8s}] {rule.id:20s} {cat:20s} {rule.text}")
        return "\n".join(lines) + "\n"

    def export_file(self, path: str, *, fmt: str) -> None:
        """Write exported content to *path*.

        Args:
            path: Filesystem path to write.
            fmt: One of ``json``, ``yaml``, ``csv``, ``markdown``, ``text``.

        Raises:
            ValueError: If *fmt* is not a supported format.
        """
        if fmt not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{fmt}'. Choose from: {sorted(_SUPPORTED_FORMATS)}"
            )
        dispatch: dict[str, Callable[[], str]] = {
            "json": self.to_json,
            "yaml": self.to_yaml,
            "csv": self.to_csv,
            "markdown": self.to_markdown,
            "text": self.to_text_summary,
        }
        content = dispatch[fmt]()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def export_all(self, directory: str, *, stem: str | None = None) -> dict[str, str]:
        """Export all formats to *directory*, returning a map of fmt → file path.

        Args:
            directory: Directory to write files into.
            stem: Base filename without extension. Defaults to the constitution name.

        Returns:
            Dict mapping format name to written file path.
        """
        import os

        base = stem or self.constitution.name.replace(" ", "_")
        ext_map = {
            "json": "json",
            "yaml": "yaml",
            "csv": "csv",
            "markdown": "md",
            "text": "txt",
        }
        written: dict[str, str] = {}
        for fmt, ext in ext_map.items():
            out_path = os.path.join(directory, f"{base}.{ext}")
            self.export_file(out_path, fmt=fmt)
            written[fmt] = out_path
        return written
