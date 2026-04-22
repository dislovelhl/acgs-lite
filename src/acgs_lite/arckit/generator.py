"""ACGS constitution generation from parsed arc-kit artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from .compliance_bridge import map_rule_to_controls
from .models import ArcKitSource, ConstitutionManifest, ExtractedRule, ParsedProject
from .parser import parse_project


def rules_from_principles(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    return [rule for rule in rules if rule.source_type == "PRIN" or rule.category == "principles"]


def rules_from_risks(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    return [rule for rule in rules if rule.source_type == "RISK" or rule.category == "risk"]


def rules_from_dpia(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    return [
        rule
        for rule in rules
        if rule.source_type == "DPIA" or rule.category == "data-protection"
    ]


def rules_from_requirements(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    return [rule for rule in rules if rule.source_type == "REQ" or rule.category == "compliance"]


def generate_constitution(
    project: ParsedProject | str | Path,
    *,
    name: str | None = None,
    version: str = "1.0",
) -> ConstitutionManifest:
    """Parse an arc-kit project if needed and build a constitution manifest."""
    parsed = parse_project(project) if isinstance(project, str | Path) else project
    return build_constitution(parsed, name=name, version=version)


def build_constitution(
    project: ParsedProject | list[ExtractedRule],
    *,
    source: ArcKitSource | None = None,
    name: str | None = None,
    version: str = "1.0",
) -> ConstitutionManifest:
    """Build an ACGS-loadable constitution manifest."""
    if isinstance(project, ParsedProject):
        rules = project.rules
        resolved_source = project.source
        project_id = project.project_id
    else:
        rules = project
        resolved_source = source or ArcKitSource(project_id="unknown")
        project_id = resolved_source.project_id

    rule_dicts = [_rule_to_dict(rule) for rule in rules]
    rule_dicts = _dedupe_rules(rule_dicts)
    compliance_mapping = {
        rule["id"]: map_rule_to_controls(rule["category"]) for rule in rule_dicts
    }
    constitutional_hash = _runtime_constitutional_hash(rule_dicts)
    arc_kit_source_hash = _artifact_source_hash(rule_dicts, resolved_source)
    metadata = {
        "arc_kit_source": {
            "project_id": resolved_source.project_id,
            "artifact_ids": resolved_source.artifact_ids,
            "artifact_hashes": resolved_source.artifact_hashes,
            "generated_at": resolved_source.generated_at,
            "warnings": resolved_source.warnings,
            "source_hash": arc_kit_source_hash,
        },
    }
    return ConstitutionManifest(
        name=name or f"arc-{project_id}-constitution",
        version=version,
        rules=rule_dicts,
        metadata=metadata,
        compliance_mapping=compliance_mapping,
        constitutional_hash=constitutional_hash,
    )


def _rule_to_dict(rule: ExtractedRule) -> dict[str, Any]:
    metadata = {
        "source_document_id": rule.source_document_id,
        "source_type": rule.source_type,
        "source_rule_id": rule.source_rule_id,
        **rule.metadata,
    }
    payload = {
        "id": rule.id,
        "text": rule.text,
        "severity": rule.severity,
        "category": rule.category,
        "keywords": rule.keywords,
        "patterns": rule.patterns,
        "metadata": metadata,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _dedupe_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for rule in rules:
        rule_id = str(rule["id"])
        if rule_id in seen:
            prefix = rule_id.split("-", 1)[0]
            counters[prefix] = counters.get(prefix, 1) + 1
            candidate = f"{prefix}-{counters[prefix]:03d}"
            while candidate in seen:
                counters[prefix] += 1
                candidate = f"{prefix}-{counters[prefix]:03d}"
            rule = {**rule, "id": candidate}
            rule_id = candidate
        try:
            suffix = int(rule_id.rsplit("-", 1)[-1])
        except ValueError:
            suffix = 0
        counters.setdefault(rule_id.split("-", 1)[0], suffix)
        seen.add(rule_id)
        deduped.append(rule)
    return sorted(deduped, key=lambda item: item["id"])


def _runtime_constitutional_hash(rules: list[dict[str, Any]]) -> str:
    """Compute the hash using the same algorithm as Constitution.model_post_init.

    This ensures manifest.constitutional_hash == Constitution.from_dict(manifest.as_dict()).hash.
    """
    canonical = "|".join(
        f"{r['id']}:{r['text']}:{r.get('severity', 'high')}:{r.get('hardcoded', False)}:{','.join(sorted(r.get('keywords', [])))}"
        for r in sorted(rules, key=lambda item: item["id"])
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _artifact_source_hash(rules: list[dict[str, Any]], source: ArcKitSource) -> str:
    """Compute provenance hash over rule content and source artifact hashes."""
    payload = {
        "rules": sorted(rules, key=lambda item: item["id"]),
        "artifact_hashes": dict(sorted(source.artifact_hashes.items())),
    }
    sorted_yaml_bytes = yaml.safe_dump(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(sorted_yaml_bytes).hexdigest()[:16]


def manifest_to_yaml(manifest: ConstitutionManifest) -> str:
    return cast(str, yaml.safe_dump(manifest.as_dict(), sort_keys=False, allow_unicode=True))


def manifest_from_yaml(path: str | Path) -> ConstitutionManifest:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ConstitutionManifest(
        name=data["name"],
        version=str(data["version"]),
        rules=data["rules"],
        metadata=data.get("metadata", {}),
        compliance_mapping=data.get("compliance_mapping", {}),
        constitutional_hash=data.get("constitutional_hash", ""),
    )


def source_as_dict(source: ArcKitSource) -> dict[str, Any]:
    return asdict(source)
