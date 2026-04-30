#!/usr/bin/env python3
"""Build a provenance-preserving self-evolution action corpus from decision logs.

Input can be JSONL or a JSON array of decision records. Output is JSONL where
each row is stable, de-duplicated, and traceable back to source audit records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_OUTPUT_FIELDS = {
    "id",
    "text",
    "source_field",
    "source_audit_entry_ids",
    "decisions",
    "labels",
    "coverage_category",
}


def _load_records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list of records")
        return [_as_record(item) for item in data]
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(_as_record(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
    return records


def _as_record(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Decision record must be an object, got {type(item).__name__}")
    return item


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _stable_id(text: str, source_field: str) -> str:
    digest = hashlib.sha256(f"{source_field}\0{text}".encode()).hexdigest()[:16]
    return f"EC-{digest}"


def _labels(record: dict[str, Any]) -> list[str]:
    labels = {str(record.get("decision", "unknown")).lower() or "unknown"}
    if record.get("violations"):
        labels.add("has_violation_evidence")
    if record.get("triggered_rules"):
        labels.add("has_triggered_rules")
    confidence = record.get("confidence")
    try:
        if confidence is not None and float(confidence) < 0.6:
            labels.add("low_confidence")
    except (TypeError, ValueError):
        labels.add("invalid_confidence")
    return sorted(labels)


def _coverage_category(record: dict[str, Any], source_field: str) -> str:
    if source_field != "action":
        return "evidence"
    decision = str(record.get("decision", "")).lower()
    if decision == "deny" and not record.get("triggered_rules"):
        return "uncovered_denial_candidate"
    if decision == "allow":
        return "allow_regression_guard"
    return "historical_decision"


def _iter_texts(record: dict[str, Any], include_evidence: bool) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    action = _normalize(str(record.get("action", "")))
    if action:
        items.append(("action", action))
    if include_evidence:
        for violation in record.get("violations") or []:
            if isinstance(violation, dict):
                text = _normalize(str(violation.get("message") or violation.get("reason") or ""))
            else:
                text = _normalize(str(violation))
            if text:
                items.append(("violation", text))
    return items


def build_corpus(
    records: list[dict[str, Any]], *, include_evidence: bool = True
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, record in enumerate(records):
        audit_id = str(record.get("audit_entry_id") or record.get("id") or f"record-{index}")
        for source_field, text in _iter_texts(record, include_evidence):
            key = (source_field, text)
            row = by_key.setdefault(
                key,
                {
                    "id": _stable_id(text, source_field),
                    "text": text,
                    "source_field": source_field,
                    "source_audit_entry_ids": [],
                    "decisions": [],
                    "labels": [],
                    "coverage_category": _coverage_category(record, source_field),
                },
            )
            row["source_audit_entry_ids"].append(audit_id)
            row["decisions"].append(str(record.get("decision", "unknown")).lower() or "unknown")
            row["labels"] = sorted(set(row["labels"]).union(_labels(record)))
    for row in by_key.values():
        row["source_audit_entry_ids"] = sorted(set(row["source_audit_entry_ids"]))
        row["decisions"] = sorted(set(row["decisions"]))
    return sorted(by_key.values(), key=lambda item: item["id"])


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        missing = REQUIRED_OUTPUT_FIELDS - set(row)
        if missing:
            errors.append(f"row {index} missing fields: {sorted(missing)}")
        if not row.get("id") or row["id"] in seen_ids:
            errors.append(f"row {index} has missing or duplicate id")
        seen_ids.add(str(row.get("id", "")))
        if not row.get("text"):
            errors.append(f"row {index} has empty text")
        if not row.get("source_audit_entry_ids"):
            errors.append(f"row {index} lacks source audit IDs")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Decision log JSONL or JSON array")
    parser.add_argument("--output", "-o", type=Path, help="Output JSONL path; defaults to stdout")
    parser.add_argument(
        "--no-evidence", action="store_true", help="Do not include violation text rows"
    )
    parser.add_argument(
        "--validate-schema", action="store_true", help="Validate generated rows before writing"
    )
    args = parser.parse_args(argv)

    rows = build_corpus(_load_records(args.input), include_evidence=not args.no_evidence)
    if args.validate_schema:
        errors = validate_rows(rows)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 2

    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
