#!/usr/bin/env python3
"""
MAP-Elites style feature grid for autoresearch experiments.

Tracks the best result per (hypothesis_family × scope) cell, revealing which
experiment families have been explored, where gains remain, and whether the
search has converged (ceiling) within any family.

Usage (from repo root):
    python3 autoresearch/feature_grid.py            # all scopes
    python3 autoresearch/feature_grid.py --scope hot-path
    python3 autoresearch/feature_grid.py --all      # include discard rows
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from results_utils import (
    KEPT_STATUSES,
    ceiling_tightness,
    extract_family,
    infer_scope,
    load_rows,
    normalize_status,
)

RESULTS_TSV = Path(__file__).parent / "results.tsv"

_ALL_FAMILIES = [
    "matcher",
    "constitution",
    "rust",
    "warmup",
    "engine",
    "method",
    "general",
]
_SCOPES = ["hot-path", "sidecar"]

# Recency penalty: families tried more than this many times in the last
# _RECENT_WINDOW rows are deprioritised in pivot suggestions.
_RECENT_WINDOW = 20
_RECENT_EXHAUSTION_THRESHOLD = 5


def build_grid(
    rows: list[dict[str, str]],
    *,
    kept_only: bool = True,
) -> dict[tuple[str, str], dict[str, str]]:
    """Return best row per (family, scope) cell."""
    grid: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if kept_only and normalize_status(row.get("status")) not in KEPT_STATUSES:
            continue
        scope = infer_scope(row)
        family = extract_family(row.get("description", ""))
        key = (family, scope)
        existing = grid.get(key)
        current_composite = float(row.get("composite", "0"))
        existing_composite = float(existing.get("composite", "0")) if existing else -1.0
        if current_composite > existing_composite:
            grid[key] = row
    return grid


def print_grid(
    rows: list[dict[str, str]],
    scope_filter: str = "any",
    *,
    kept_only: bool = True,
) -> None:
    grid = build_grid(rows, kept_only=kept_only)
    scopes = _SCOPES if scope_filter == "any" else [scope_filter]

    # Collect families that appear in results + any that are unexplored
    active_families = sorted({fam for fam, _ in grid.keys()})
    all_families = list(dict.fromkeys(active_families + _ALL_FAMILIES))  # preserve order, dedup

    col_w = 16
    header = f"  {'family':<14}" + "".join(f"{s:>{col_w}}" for s in scopes)
    sep = "  " + "-" * (14 + col_w * len(scopes))

    print("\n=== MAP-Elites Feature Grid (best composite per cell) ===")
    print(header)
    print(sep)

    for family in all_families:
        has_any = any((family, s) in grid for s in scopes)
        row_str = f"  {family:<14}"
        for scope in scopes:
            cell = grid.get((family, scope))
            if cell:
                composite = float(cell.get("composite", "0"))
                status = cell.get("status", "?")[:1].upper()  # I/N/B/D
                row_str += f"{composite:>{col_w - 3}.6f} ({status})"
            elif not has_any:
                row_str += f"{'(unexplored)':>{col_w}}"
            else:
                row_str += f"{'—':>{col_w}}"
        print(row_str)

    print(sep)
    print("  Status key: I=improved  N=neutral-kept  B=baseline  D=discard")

    # Ceiling warnings per scope — differentiate tight vs loose
    print()
    for scope in scopes:
        tightness = ceiling_tightness(rows, scope)
        if tightness is not None:
            best_family = _best_family_to_explore(grid, rows, scope)
            if tightness == "tight":
                print(f"  ⚠  CEILING in {scope} (TIGHT): composite spread < 0.0001 — true measurement floor.")
                if best_family:
                    print(f"     Pivot now: try '{best_family}' family.")
            else:
                print(f"  ⚠  CEILING in {scope} (LOOSE): composite spread ≥ 0.0001 — noise may mask signal.")
                print("     Run bench_stable.py --trials 7 to verify before pivoting.")
                if best_family:
                    print(f"     If ceiling confirmed: try '{best_family}' family.")
    print()


def _best_family_to_explore(
    grid: dict[tuple[str, str], dict[str, str]],
    rows: list[dict[str, str]],
    scope: str,
) -> str | None:
    """Suggest the most promising unexplored or under-explored family.

    Priority:
      1. Completely unexplored AND not recently exhausted
      2. Lowest best-composite, penalised for recent over-use
    """
    scoped = [r for r in rows if infer_scope(r) == scope]
    recent_counts: Counter[str] = Counter(
        extract_family(r.get("description", ""))
        for r in scoped[-_RECENT_WINDOW:]
    )

    # 1. Unexplored families that haven't been hammered recently
    for family in _ALL_FAMILIES:
        if (
            (family, scope) not in grid
            and recent_counts[family] < _RECENT_EXHAUSTION_THRESHOLD
        ):
            return family

    # 2. Explored families — lowest composite, penalised for recent exhaustion
    candidates: list[tuple[str, float]] = []
    for family in _ALL_FAMILIES:
        composite = (
            float(grid[(family, scope)].get("composite", "0"))
            if (family, scope) in grid
            else 0.0
        )
        excess = max(0, recent_counts[family] - _RECENT_EXHAUSTION_THRESHOLD)
        effective = composite - 0.001 * excess  # 0.001 penalty per excess attempt
        candidates.append((family, effective))

    return min(candidates, key=lambda x: x[1])[0] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MAP-Elites feature grid for autoresearch experiments.",
    )
    parser.add_argument(
        "--scope", default="any",
        choices=["any", "hot-path", "sidecar"],
        help="Scope filter (default: any)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Include discard rows in the grid (default: kept-only)",
    )
    args = parser.parse_args()

    rows = load_rows(RESULTS_TSV)
    if not rows:
        print("No results yet.", file=sys.stderr)
        return 1

    print_grid(rows, args.scope, kept_only=not args.all)
    return 0


if __name__ == "__main__":
    sys.exit(main())
