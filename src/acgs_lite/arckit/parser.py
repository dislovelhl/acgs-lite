"""Lenient Markdown parser for arc-kit artifacts."""

from __future__ import annotations

import functools
import hashlib
import re
import warnings
from datetime import date
from pathlib import Path

from .models import ArcKitSource, ExtractedRule, ParsedProject

RECOGNIZED_TYPES = {"PRIN", "RISK", "DPIA", "REQ"}
FILENAME_RE = re.compile(
    r"^ARC-(?P<project_id>[A-Za-z0-9]+)-(?P<type>PRIN|RISK|DPIA|REQ)-v(?P<version>[\w.]+)\.md$",
    re.IGNORECASE,
)

SECURITY_TERMS = (
    "security",
    "secure",
    "zero-trust",
    "zero trust",
    "encryption",
    "threat",
    "authentication",
    "authorization",
    "least privilege",
    "vulnerability",
)

# 'security', 'secure', and 'encryption' appear in both sets; this is intentional —
# SECURITY_TERMS drives severity classification in parse_principles while
# COMPLIANCE_TERMS drives row filtering in parse_requirements.
COMPLIANCE_TERMS = (
    "security",
    "secure",
    "compliance",
    "gdpr",
    "eu ai act",
    "privacy",
    "audit",
    "encryption",
    "access control",
    "personal data",
)

PII_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    # Covers SSN text through the social-security term without a duplicate key.
    "social security": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "date of birth": r"\b\d{4}-\d{2}-\d{2}\b",
}

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024  # 2 MB

_CRITICAL_VERBS = frozenset({"must not", "shall not", "must never", "prohibited", "forbidden"})

_PRINCIPLE_BLOCK_RE = re.compile(
    r"^###\s+(?:(?P<id>P-\d+|\d+)[\.:]\s*)?(?P<title>[^\n]+)\n(?P<body>.*?)(?=^###\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def parse_principles(path: str | Path, text: str | None = None) -> list[ExtractedRule]:
    text = _read_text(path) if text is None else text
    if not text.strip():
        return []
    document_id = _document_id(text, path)
    blocks = _principle_blocks(text)
    if not blocks:
        _warn(f"{document_id}: no principle entries found")
        return []

    rules: list[ExtractedRule] = []
    for index, (source_id, title, body) in enumerate(blocks, start=1):
        rule_text = _compact(
            f"{title}: {body}"
            if body
            else title
        )
        severity = "high" if _contains_any(rule_text, SECURITY_TERMS) else "medium"
        rules.append(
            ExtractedRule(
                id=f"PRIN-{index:03d}",
                text=rule_text,
                severity=severity,
                category="principles",
                keywords=_keywords(rule_text),
                source_document_id=document_id,
                source_type="PRIN",
                source_path=str(path),
                source_hash=_hash_text(text),
                source_rule_id=source_id,
            )
        )
    return rules


def parse_risk_register(path: str | Path, text: str | None = None) -> list[ExtractedRule]:
    text = _read_text(path) if text is None else text
    if not text.strip():
        return []
    document_id = _document_id(text, path)
    tables = _markdown_tables(text)
    risk_rows = [
        row
        for table in tables
        for row in table
        if {"risk id", "description", "level"}.issubset(row)
    ]
    if not risk_rows:
        _warn(f"{document_id}: no risk table found")
        return []

    rules: list[ExtractedRule] = []
    for index, row in enumerate(risk_rows, start=1):
        risk_id = row.get("risk id") or f"R-{index:03d}"
        description = row.get("description", "")
        mitigation = row.get("mitigation", "")
        level = row.get("level", "")
        rule_text = _compact(f"{risk_id}: {description}. Mitigation: {mitigation}")
        rules.append(
            ExtractedRule(
                id=f"RISK-{index:03d}",
                text=rule_text,
                severity=_risk_severity(level),
                category="risk",
                keywords=_keywords(rule_text),
                patterns=_patterns_for_text(rule_text),
                source_document_id=document_id,
                source_type="RISK",
                source_path=str(path),
                source_hash=_hash_text(text),
                source_rule_id=risk_id,
            )
        )
    return rules


def parse_dpia(path: str | Path, text: str | None = None) -> list[ExtractedRule]:
    text = _read_text(path) if text is None else text
    if not text.strip():
        return []
    document_id = _document_id(text, path)
    categories = _extract_personal_data_categories(text)
    if not categories:
        _warn(f"{document_id}: no personal data categories found")
        return []

    rules: list[ExtractedRule] = []
    for index, category in enumerate(categories, start=1):
        keyword = category.lower()
        rules.append(
            ExtractedRule(
                id=f"DATA-{index:03d}",
                text=f"Agents must not expose personal data category: {category}",
                severity="critical",
                category="data-protection",
                keywords=list(dict.fromkeys([keyword, *keyword.split()])),
                patterns=_patterns_for_text(keyword),
                source_document_id=document_id,
                source_type="DPIA",
                source_path=str(path),
                source_hash=_hash_text(text),
                source_rule_id=f"DPIA-DATA-{index:03d}",
            )
        )
    return rules


def parse_requirements(path: str | Path, text: str | None = None) -> list[ExtractedRule]:
    text = _read_text(path) if text is None else text
    if not text.strip():
        return []
    document_id = _document_id(text, path)
    table_candidates = _candidates_from_tables(text)
    heading_candidates = _heading_requirements(text)
    seen_ids = {req_id for req_id, _ in table_candidates}
    candidates = list(table_candidates) + [
        (req_id, desc) for req_id, desc in heading_candidates if req_id not in seen_ids
    ]
    if not candidates:
        _warn(f"{document_id}: no security or compliance requirements found")
        return []
    return [
        _requirement_to_rule(req_id, description, index, document_id, text, path)
        for index, (req_id, description) in enumerate(candidates, start=1)
    ]


def parse_project(project_dir: str | Path) -> ParsedProject:
    base = Path(project_dir)
    if not base.exists() or not base.is_dir():
        raise FileNotFoundError(f"arc-kit project directory not found: {base}")

    rules: list[ExtractedRule] = []
    artifact_ids: list[str] = []
    artifact_hashes: dict[str, str] = {}
    project_id = ""
    warning_messages: list[str] = []

    for path in sorted(base.glob("ARC-*.md")):
        match = FILENAME_RE.fullmatch(path.name)
        if not match:
            continue
        artifact_type = match.group("type").upper()
        if artifact_type not in RECOGNIZED_TYPES:
            continue
        file_project_id = match.group("project_id")
        if not project_id:
            project_id = file_project_id
        elif file_project_id != project_id:
            warning_messages.append(
                f"{path.name}: project_id '{file_project_id}' does not match "
                f"established project_id '{project_id}', skipping"
            )
            continue

        oversized = path.stat().st_size > MAX_ARTIFACT_BYTES
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            text = _read_text(path)
        warning_messages.extend(str(item.message) for item in captured)
        if oversized:
            continue

        document_id = _document_id(text, path)
        artifact_ids.append(document_id)
        artifact_hashes[document_id] = _hash_text(text)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            parsed = {
                "PRIN": parse_principles,
                "RISK": parse_risk_register,
                "DPIA": parse_dpia,
                "REQ": parse_requirements,
            }[artifact_type](path, text)
        warning_messages.extend(str(item.message) for item in captured)
        rules.extend(parsed)

    source = ArcKitSource(
        project_id=project_id or "unknown",
        artifact_ids=artifact_ids,
        artifact_hashes=artifact_hashes,
        generated_at=date.today().isoformat(),
        warnings=warning_messages,
    )
    return ParsedProject(project_id=source.project_id, source=source, rules=rules)


def _candidates_from_tables(text: str) -> list[tuple[str, str]]:
    candidate_rows = [
        row
        for table in _markdown_tables(text)
        for row in table
        if ("requirement" in row or "description" in row) and ("id" in row or "requirement id" in row)
    ]
    candidates: list[tuple[str, str]] = []
    for row in candidate_rows:
        req_id = row.get("requirement id") or row.get("id") or ""
        description = row.get("requirement") or row.get("description") or ""
        scope_text = " ".join([req_id, row.get("type", ""), row.get("category", ""), description])
        if _contains_any(scope_text, COMPLIANCE_TERMS):
            candidates.append((req_id, description))
    return candidates


def _requirement_to_rule(
    req_id: str,
    description: str,
    index: int,
    document_id: str,
    text: str,
    path: str | Path,
) -> ExtractedRule:
    rule_text = _compact(f"{req_id}: {description}" if req_id else description)
    severity = "critical" if any(v in rule_text.lower() for v in _CRITICAL_VERBS) else "high"
    return ExtractedRule(
        id=f"COMP-{index:03d}",
        text=rule_text,
        severity=severity,
        category="compliance",
        keywords=_keywords(rule_text),
        patterns=_patterns_for_text(rule_text),
        source_document_id=document_id,
        source_type="REQ",
        source_path=str(path),
        source_hash=_hash_text(text),
        source_rule_id=req_id,
    )


def _read_text(path: str | Path) -> str:
    p = Path(path)
    size = p.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        _warn(f"{p.name}: file size {size} exceeds limit ({MAX_ARTIFACT_BYTES} bytes), skipping")
        return ""
    return p.read_text(encoding="utf-8")


def _warn(message: str) -> None:
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_id(text: str, path: str | Path) -> str:
    value = _header_value(text, "Document ID")
    return value or Path(path).stem


def _header_value(text: str, field: str) -> str:
    wanted = _normalize_cell(field)
    for raw_line in text.splitlines():
        if not raw_line.strip().startswith("|"):
            continue
        cells = [_normalize_cell(cell) for cell in raw_line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() == wanted.lower():
            return cells[1]
    return ""


def _normalize_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("**", "").replace("[", "").replace("]", "")).strip()


def _markdown_tables(text: str) -> list[list[dict[str, str]]]:
    lines = text.splitlines()
    tables: list[list[dict[str, str]]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip().startswith("|"):
            index += 1
            continue
        if index + 1 >= len(lines) or not _is_separator(lines[index + 1]):
            index += 1
            continue
        headers = [_normalize_cell(cell).lower() for cell in line.strip().strip("|").split("|")]
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            values = [_normalize_cell(cell) for cell in lines[index].strip().strip("|").split("|")]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values, strict=False)))
            index += 1
        tables.append(rows)
    return tables


def _is_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _principle_blocks(text: str) -> list[tuple[str, str, str]]:
    matches = list(_PRINCIPLE_BLOCK_RE.finditer(text))
    blocks: list[tuple[str, str, str]] = []
    for item in matches:
        body = item.group("body")
        statement = _labeled_value(body, "Principle Statement") or _labeled_value(body, "Rationale")
        if not statement:
            statement = _first_paragraph(body)
        blocks.append((item.group("id") or "", _strip_markdown(item.group("title")), statement))
    return blocks


@functools.lru_cache(maxsize=32)
def _compiled_label_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"\*\*{re.escape(label)}\*\*:\s*(?P<value>.*?)(?=\n\s*\*\*|\n\s*###|\n\s*---|\Z)",
        re.DOTALL | re.IGNORECASE,
    )


def _labeled_value(text: str, label: str) -> str:
    match = _compiled_label_pattern(label).search(text)
    return _strip_markdown(match.group("value")) if match else ""


def _first_paragraph(text: str) -> str:
    for paragraph in re.split(r"\n\s*\n", text):
        stripped = _strip_markdown(paragraph)
        if stripped and not stripped.startswith("-"):
            return stripped
    return ""


def _extract_personal_data_categories(text: str) -> list[str]:
    raw = [*_categories_from_tables(text), *_categories_from_section(text)]
    cleaned = filter(None, (_clean_category(c) for c in raw))
    return list(dict.fromkeys(cleaned))


def _categories_from_tables(text: str) -> list[str]:
    categories: list[str] = []
    for table in _markdown_tables(text):
        for row in table:
            for key in ("data categories", "data category", "data type", "personal data categories"):
                if key in row:
                    categories.extend(_split_categories(row[key]))
    return categories


def _categories_from_section(text: str) -> list[str]:
    section_match = re.search(
        r"(?:personal data categories|what data are we processing\??)(?P<section>.*?)(?=^#{2,3}\s+|\Z)",
        text,
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    if not section_match:
        return []
    categories: list[str] = []
    for line in section_match.group("section").splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            categories.extend(_split_categories(stripped.lstrip("- ")))
    return categories


def _clean_category(category: str) -> str:
    value = _strip_markdown(category).strip(" .;:")
    if not value or value.startswith("[") or value.lower() in {"yes", "no"}:
        return ""
    return value


def _split_categories(value: str) -> list[str]:
    return [part.strip() for part in re.split(r",|;|\band\b", value) if part.strip()]


def _heading_requirements(text: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for match in re.finditer(
        r"^#{3,4}\s+(?P<id>(?:NFR-)?(?:SEC|COMP|GDPR)[-\w]*):?\s*(?P<title>[^\n]*)\n(?P<body>.*?)(?=^#{3,4}\s+|\Z)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    ):
        body = _labeled_value(match.group("body"), "Requirement") or _first_paragraph(match.group("body"))
        results.append((match.group("id"), _compact(f"{match.group('title')} {body}")))
    return results


def _risk_severity(level: str) -> str:
    normalized = level.lower()
    if "accept" in normalized or "mitigat" in normalized:
        return "low"
    if "critical" in normalized or "high" in normalized:
        return "critical"
    if "medium" in normalized:
        return "high"
    if "low" in normalized:
        return "medium"
    return "low"


def _keywords(text: str) -> list[str]:
    terms = re.findall(r"[a-z0-9][a-z0-9\- ]{2,}", text.lower())
    words = []
    for token in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", " ".join(terms)):
        if token not in {"must", "the", "and", "for", "with", "from", "that", "this", "agents"}:
            words.append(token)
    special = [term for term in ("pii", "data breach", "gdpr", "eu ai act", "security") if term in text.lower()]
    return list(dict.fromkeys([*special, *words[:8]]))


def _patterns_for_text(text: str) -> list[str]:
    lower = text.lower()
    return list(dict.fromkeys(pattern for key, pattern in PII_PATTERNS.items() if key in lower))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    return _compact(text)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
