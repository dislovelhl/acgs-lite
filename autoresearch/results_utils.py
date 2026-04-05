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


# ---------------------------------------------------------------------------
# Ceiling detection, family classification, and data-quality helpers
# ---------------------------------------------------------------------------

# Hypothesis family signals — order matters, first match wins.
# Each entry: (family_name, [substrings_to_match_in_lowercase_description])
_FAMILY_SIGNALS: list[tuple[str, list[str]]] = [
    ("matcher", ["matcher:", "aho-corasick", "keyword"]),
    ("constitution", ["constitution:", "precompute", "rule tuple", "rule representation"]),
    ("rust", ["rust:", "bitmask", "pyo3", "maturin", "scan_hot", "zero-alloc"]),
    ("warmup", ["warmup", "gc.", "jit", "warm "]),
    ("engine", ["engine:", "validate", "dispatch", "fast-path", "hot-path:"]),
    ("method", ["method:", "baseline", "tie-band", "discipline"]),
]
_DEFAULT_FAMILY = "general"


def extract_family(description: str) -> str:
    """Classify an experiment description into a hypothesis family."""
    desc = description.lstrip(SIDECAR_MARKER).strip().lower()
    for family, signals in _FAMILY_SIGNALS:
        if any(s in desc for s in signals):
            return family
    return _DEFAULT_FAMILY


def ceiling_detected(
    rows: list[dict[str, str]],
    scope: str = "hot-path",
    window: int = 5,
) -> bool:
    """Return True if the last `window` runs in `scope` contain no 'improved' result.

    A ceiling means the current architecture has no low-hanging fruit left —
    it's time to pivot to a different experiment family or architectural approach.
    """
    scoped = [r for r in rows if infer_scope(r) == scope]
    if len(scoped) < window:
        return False
    recent = scoped[-window:]
    return not any(normalize_status(r.get("status")) == "improved" for r in recent)


def ceiling_tightness(
    rows: list[dict[str, str]],
    scope: str = "hot-path",
    window: int = 5,
    tight_band: float = 0.001,
) -> str | None:
    """Classify a detected ceiling as 'tight' or 'loose', or None if no ceiling.

    tight: composite spread across the window < tight_band.
        The system is at a true measurement floor — pivot family now.

    loose: composite spread >= tight_band.
        Measurement noise is masking the signal — run bench_stable.py first
        before declaring the ceiling real.
    """
    if not ceiling_detected(rows, scope, window):
        return None
    scoped = [r for r in rows if infer_scope(r) == scope]
    if len(scoped) < window:
        return None
    recent = scoped[-window:]
    composites = [float(r.get("composite", "0")) for r in recent]
    spread = max(composites) - min(composites)
    return "tight" if spread < tight_band else "loose"


def uncommitted_count(rows: list[dict[str, str]]) -> int:
    """Count rows where the commit SHA is the literal string 'uncommitted'.

    High counts mean experiments are unrecoverable — the code that produced
    those results cannot be checked out. Commit before logging.
    """
    return sum(1 for r in rows if r.get("commit", "").strip() == "uncommitted")
