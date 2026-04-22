"""Data models for the arc-kit to ACGS bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractedRule:
    """Governance rule extracted from an arc-kit artifact."""

    id: str
    text: str
    severity: str
    category: str
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    source_document_id: str = ""
    source_type: str = ""
    source_path: str = ""
    source_hash: str = ""
    source_rule_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArcKitSource:
    """Traceability metadata for parsed arc-kit artifacts."""

    project_id: str
    artifact_ids: list[str] = field(default_factory=list)
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    generated_at: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedProject:
    """Parsed arc-kit project output."""

    project_id: str
    source: ArcKitSource
    rules: list[ExtractedRule] = field(default_factory=list)


@dataclass(frozen=True)
class ConstitutionManifest:
    """Serializable ACGS constitution manifest generated from arc-kit."""

    name: str
    version: str
    rules: list[dict[str, Any]]
    metadata: dict[str, Any]
    compliance_mapping: dict[str, list[str]]
    constitutional_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_yaml(self, path: str | Path) -> None:
        import yaml  # type: ignore[import-untyped]

        Path(path).write_text(
            yaml.safe_dump(self.as_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
