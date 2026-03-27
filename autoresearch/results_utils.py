from __future__ import annotations

from pathlib import Path

KEPT_STATUSES = {"improved", "neutral-kept", "baseline"}
RECENT_ROWS = 5
SIDECAR_MARKER = "[sidecar]"
TSV_COLUMNS = ("commit", "composite", "compliance", "p99_ms", "scope", "status", "description")
LEGACY_TSV_COLUMNS = ("commit", "composite", "compliance", "p99_ms", "status", "description")
DEFAULT_SCOPE = "hot-path"


def read_header(results_path: Path) -> tuple[str, ...]:
    with results_path.open() as handle:
        return tuple(handle.readline().rstrip("\n").split("\t"))


def normalize_status(status: str | None) -> str:
    if status in KEPT_STATUSES:
        return status
    if status in {"neutral", "reverted"}:
        return "discard"
    return status or ""


def infer_scope(row: dict[str, str]) -> str:
    explicit_scope = row.get("scope", "").strip()
    if explicit_scope in {"hot-path", "sidecar"}:
        return explicit_scope

    description = row.get("description", "").strip()
    if description.startswith(SIDECAR_MARKER):
        return "sidecar"
    if "zero hot-path overhead" in description.lower():
        return "sidecar"
    return DEFAULT_SCOPE


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {column: row.get(column, "") for column in TSV_COLUMNS}
    normalized["scope"] = infer_scope(row)
    normalized["status"] = normalize_status(row.get("status"))
    normalized["description"] = scoped_description(row.get("description", ""), normalized["scope"])
    return normalized


def scoped_description(description: str, scope: str) -> str:
    stripped = description.strip()
    if scope == "sidecar" and stripped and not stripped.startswith(SIDECAR_MARKER):
        return f"{SIDECAR_MARKER} {stripped}"
    return stripped


def load_rows(results_path: Path) -> list[dict[str, str]]:
    if not results_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with results_path.open() as handle:
        header = tuple(handle.readline().rstrip("\n").split("\t"))
        if header not in {TSV_COLUMNS, LEGACY_TSV_COLUMNS}:
            raise ValueError(f"Unsupported results.tsv header: {header}")

        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                if len(parts) == 1 and rows:
                    continuation = parts[0].strip()
                    if continuation:
                        prior = rows[-1]
                        merged = f"{prior.get('description', '').strip()} | {continuation}".strip(
                            " |"
                        )
                        prior["description"] = merged
                continue
            rows.append(normalize_row(dict(zip(header, parts, strict=False))))
    return rows


def serialize_row(row: dict[str, str]) -> str:
    normalized = normalize_row(row)
    return "\t".join(normalized[column] for column in TSV_COLUMNS)


def ensure_results_tsv(results_path: Path) -> None:
    if not results_path.exists() or results_path.stat().st_size == 0:
        results_path.write_text("\t".join(TSV_COLUMNS) + "\n")
        return

    header = read_header(results_path)
    if header == TSV_COLUMNS:
        return
    if header != LEGACY_TSV_COLUMNS:
        raise ValueError(f"Unsupported results.tsv header: {header}")

    rows = load_rows(results_path)
    payload = ["\t".join(TSV_COLUMNS), *(serialize_row(row) for row in rows)]
    results_path.write_text("\n".join(payload) + "\n")


def comparable_rows(rows: list[dict[str, str]], scope: str = "any") -> list[dict[str, str]]:
    kept = [row for row in rows if normalize_status(row.get("status")) in KEPT_STATUSES]
    if scope == "any":
        return kept
    return [row for row in kept if infer_scope(row) == scope]


def best_kept_row(rows: list[dict[str, str]], scope: str = "any") -> dict[str, str] | None:
    kept = comparable_rows(rows, scope)
    if not kept:
        return None
    return max(kept, key=lambda row: float(row.get("composite", "0")))


def recent_rows(
    rows: list[dict[str, str]],
    *,
    scope: str,
    statuses: set[str],
    limit: int = RECENT_ROWS,
) -> list[dict[str, str]]:
    filtered = [
        row
        for row in rows
        if infer_scope(row) == scope and normalize_status(row.get("status")) in statuses
    ]
    return filtered[-limit:]
