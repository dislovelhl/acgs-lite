#!/usr/bin/env python3
"""
Parse benchmark output and append a row to autoresearch/results.tsv.

Usage:
    python3 autoresearch/log_run.py autoresearch/run.log \
        --commit "$(git rev-parse --short HEAD)" \
        --description "matcher: aho-corasick scanner"

    python3 autoresearch/log_run.py autoresearch/run.log --recommend

    # Mark as sidecar (won't affect hot-path comparable decisions):
    python3 autoresearch/log_run.py autoresearch/run.log \
        --commit abc1234 --description "audit: async flush" --scope sidecar

Scope values: hot-path (default) | sidecar | any
Status computed automatically; override with --status if needed.

Run from repo root.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from results_utils import (
    KEPT_STATUSES,
    best_kept_row,
    ensure_results_tsv,
    load_rows,
    scoped_description,
    serialize_row,
)

RESULTS_TSV = Path(__file__).parent / "results.tsv"

METRIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "composite_score": re.compile(r"^composite_score:\s+([\d.]+)", re.MULTILINE),
    "compliance_rate": re.compile(r"^compliance_rate:\s+([\d.]+)", re.MULTILINE),
    "p99_latency_ms": re.compile(r"^p99_latency_ms:\s+([\d.]+)", re.MULTILINE),
    "false_negative_rate": re.compile(r"^false_negative_rate:\s+([\d.]+)", re.MULTILINE),
    "false_positive_rate": re.compile(r"^false_positive_rate:\s+([\d.]+)", re.MULTILINE),
    "errors": re.compile(r"^errors:\s+(\d+)", re.MULTILINE),
}

COMPOSITE_TIE_BAND = 0.0005
MATERIAL_P99_IMPROVEMENT_MS = 0.0003


def parse_log(log_text: str) -> dict[str, float] | None:
    metrics: dict[str, float] = {}
    for key, pat in METRIC_PATTERNS.items():
        match = pat.search(log_text)
        if match:
            metrics[key] = float(match.group(1))
    if "composite_score" not in metrics:
        return None
    return metrics


def best_kept_composite(rows: list[dict[str, str]], scope: str) -> float | None:
    best = best_kept_row(rows, scope)
    if best is None:
        return None
    return float(best.get("composite", "0"))


def best_kept_p99(rows: list[dict[str, str]], scope: str) -> float | None:
    best = best_kept_row(rows, scope)
    if best is None:
        return None
    return float(best.get("p99_ms", "0"))


def compute_status(
    metrics: dict[str, float],
    rows: list[dict[str, str]],
    *,
    scope: str,
    simpler: bool,
    p99_material: bool,
    tie_band: float,
) -> str:
    if int(metrics.get("errors", 0)) > 0:
        return "crash"

    if metrics.get("compliance_rate", 1.0) < 1.0:
        return "discard"
    if metrics.get("false_negative_rate", 0.0) > 0.0:
        return "discard"
    if metrics.get("false_positive_rate", 0.0) > 0.0:
        return "discard"

    composite = metrics["composite_score"]
    best = best_kept_composite(rows, scope)
    if best is None:
        return "baseline"

    delta = composite - best
    if delta > tie_band:
        return "improved"
    if abs(delta) > tie_band:
        return "discard"

    best_p99 = best_kept_p99(rows, scope)
    p99_improved = best_p99 is not None and metrics.get("p99_latency_ms", 0.0) < (
        best_p99 - MATERIAL_P99_IMPROVEMENT_MS
    )
    if simpler or (p99_material and p99_improved):
        return "neutral-kept"
    return "discard"


def append_row(
    commit: str,
    composite: float,
    compliance: float,
    p99_ms: float,
    scope: str,
    status: str,
    description: str,
) -> None:
    ensure_results_tsv(RESULTS_TSV)
    row = serialize_row(
        {
            "commit": commit,
            "composite": f"{composite:.6f}",
            "compliance": f"{compliance:.6f}",
            "p99_ms": f"{p99_ms:.6f}",
            "scope": scope,
            "status": status,
            "description": description,
        }
    )
    with RESULTS_TSV.open("a") as f:
        f.write(row + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Log a benchmark run to results.tsv.")
    parser.add_argument("log", help="Path to benchmark output log (run.log)")
    parser.add_argument("--commit", default="uncommitted", help="Short git commit SHA")
    parser.add_argument("--description", default="", help="Short hypothesis description")
    parser.add_argument(
        "--scope",
        choices=["hot-path", "sidecar", "any"],
        default="hot-path",
        help="Run scope for comparable row selection",
    )
    parser.add_argument(
        "--status",
        choices=["baseline", "improved", "neutral-kept", "discard", "crash"],
        default=None,
        help="Override computed status",
    )
    parser.add_argument(
        "--recommend",
        action="store_true",
        help="Print shell-friendly recommendation (keep/discard) and exit without writing",
    )
    parser.add_argument(
        "--simpler",
        action="store_true",
        help="Allow tie-band keeps when the change is simpler or unlocks the next clean ablation",
    )
    parser.add_argument(
        "--p99-material",
        action="store_true",
        help="Allow tie-band keeps when p99 improves materially within the comparable scope",
    )
    parser.add_argument(
        "--tie-band",
        type=float,
        default=COMPOSITE_TIE_BAND,
        help="Composite-score band treated as effectively tied",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"ERROR: log file not found: {log_path}", file=sys.stderr)
        return 1

    log_text = log_path.read_text()
    metrics = parse_log(log_text)
    ensure_results_tsv(RESULTS_TSV)
    rows = load_rows(RESULTS_TSV)

    if metrics is None:
        if args.recommend:
            print("discard")
            return 0
        print(
            "ERROR: no parseable summary block in log. Benchmark may have crashed.", file=sys.stderr
        )
        print(f"  Check: tail -n 50 {log_path}", file=sys.stderr)
        description = scoped_description(args.description or "crash", args.scope)
        append_row(args.commit, 0.0, 0.0, 0.0, args.scope, "crash", description)
        print(f"Logged crash row for commit {args.commit}.", file=sys.stderr)
        return 1

    status = args.status or compute_status(
        metrics,
        rows,
        scope=args.scope,
        simpler=args.simpler,
        p99_material=args.p99_material,
        tie_band=args.tie_band,
    )

    composite = metrics["composite_score"]
    compliance = metrics.get("compliance_rate", 0.0)
    p99_ms = metrics.get("p99_latency_ms", 0.0)

    if args.recommend:
        print("keep" if status in KEPT_STATUSES else "discard")
        return 0

    description = scoped_description(args.description, args.scope)
    append_row(args.commit, composite, compliance, p99_ms, args.scope, status, description)

    best_before = best_kept_row(rows, args.scope)
    delta_str = ""
    if best_before is not None:
        best_before_composite = float(best_before.get("composite", "0"))
        delta = composite - best_before_composite
        delta_str = f" (Δ{delta:+.6f} vs best {best_before_composite:.6f})"

    print(f"Logged: commit={args.commit}  composite={composite:.6f}{delta_str}  status={status}")
    print(f"  compliance={compliance:.6f}  p99_ms={p99_ms:.3f}  scope={args.scope}")
    print(f"  description: {description}")

    if status in {"improved", "neutral-kept"}:
        print("\n→ KEEP commit and advance.")
    elif status == "baseline":
        print("\n→ BASELINE recorded. Begin experiments.")
    elif status == "crash":
        print("\n→ CRASH logged. Fix only if the cause is trivial; otherwise move on.")
    else:
        print("\n→ DISCARD. Revert the experiment cleanly before the next mutation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
