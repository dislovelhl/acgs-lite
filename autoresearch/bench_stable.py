#!/usr/bin/env python3
"""
Jitter-defeating multi-trial benchmark wrapper.

Runs benchmark.py N times and reports MEDIAN metrics — eliminating OS scheduling
jitter from p99 measurements. Critical near the optimization ceiling where the
improvement signal is smaller than run-to-run noise.

Usage (from repo root):
    python3 autoresearch/bench_stable.py                   # 5 trials → autoresearch/run.log
    python3 autoresearch/bench_stable.py --trials 7        # 7 trials (odd = clean median)
    python3 autoresearch/bench_stable.py --out my.log      # custom output path
    python3 autoresearch/bench_stable.py --quiet           # suppress per-trial output
    python3 autoresearch/bench_stable.py --no-resume       # ignore cached checkpoints

Features:
  Timeout:           each trial is killed after 30 s (configurable via --timeout)
  Cascade abort:     if trial 1 fails compliance or is clearly below best, skip the rest
  Checkpoint/resume: completed trials are saved to .bstable_*.json; ^C is recoverable
  Provenance:        spread statistics written alongside the median block
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

BENCHMARK = Path(__file__).parent / "benchmark.py"
PYTHON = sys.executable
_RESULTS_TSV = Path(__file__).parent / "results.tsv"

_BLOCK_RE = re.compile(r"---\n(.*?)\n---", re.DOTALL)
_METRIC_RE = re.compile(r"^(\w+):\s+([\d.]+)", re.MULTILINE)

_INT_METRICS = {"scenarios_tested", "correct", "errors", "rules_checked"}
_LOWER_IS_BETTER = {
    "p50_latency_ms", "p95_latency_ms", "p99_latency_ms",
    "mean_latency_ms", "false_positive_rate", "false_negative_rate",
}

DEFAULT_TRIAL_TIMEOUT = 30        # seconds; covers any realistic benchmark run
_CASCADE_TIE_MULTIPLIER = 3       # abort if trial 1 composite is > 3× tie_band below best
_DEFAULT_TIE_BAND = 0.005        # matches log_run.py COMPOSITE_TIE_BAND


# ---------------------------------------------------------------------------
# Checkpoint / resume helpers
# ---------------------------------------------------------------------------

def _artifact_path(out_path: Path, trial_num: int) -> Path:
    """Deterministic path for a single trial's checkpoint file."""
    return out_path.parent / f".bstable_{out_path.stem}_{trial_num}.json"


def _load_cached_trials(out_path: Path, n_trials: int) -> dict[int, dict[str, float]]:
    """Load previously completed trial results from disk (checkpoint/resume)."""
    cached: dict[int, dict[str, float]] = {}
    for i in range(1, n_trials + 1):
        p = _artifact_path(out_path, i)
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if "composite_score" in data:
                    cached[i] = data
            except Exception:
                pass
    return cached


def _save_trial(out_path: Path, trial_num: int, metrics: dict[str, float]) -> None:
    """Checkpoint a single completed trial to disk immediately."""
    _artifact_path(out_path, trial_num).write_text(json.dumps(metrics))


def _cleanup_trials(out_path: Path, n_trials: int) -> None:
    """Remove checkpoint artifacts after a successful run."""
    for i in range(1, n_trials + 1):
        p = _artifact_path(out_path, i)
        if p.exists():
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Cascade abort
# ---------------------------------------------------------------------------

def _cascade_check(t1: dict[str, float], tie_band: float = _DEFAULT_TIE_BAND) -> str | None:
    """Return a human-readable abort reason if remaining trials are pointless, else None.

    Cascade stages (in order):
      Stage 1 — compliance failure  → guaranteed discard, abort immediately
      Stage 2 — error count > 0     → guaranteed crash, abort immediately
      Stage 3 — composite far below best → clear miss, skip remaining trials
    """
    # Stage 1: correctness guardrails
    if t1.get("compliance_rate", 1.0) < 1.0:
        return "compliance_rate < 1.0 (guaranteed discard)"
    if t1.get("false_negative_rate", 0.0) > 0.0:
        return "false_negative_rate > 0 (guaranteed discard)"
    if int(t1.get("errors", 0)) > 0:
        return f"errors={int(t1['errors'])} (guaranteed crash)"

    # Stage 3: composite vs current best (requires results.tsv)
    # Skip cascade if best row appears to use a different formula version
    # (v1 composites are >0.99, v2 composites are <0.95).
    if _RESULTS_TSV.exists():
        try:
            _dir = str(Path(__file__).parent)
            if _dir not in sys.path:
                sys.path.insert(0, _dir)
            from results_utils import best_kept_row, load_rows  # noqa: PLC0415
            rows = load_rows(_RESULTS_TSV)
            best = best_kept_row(rows, "hot-path")
            if best:
                best_composite = float(best.get("composite", "0"))
                # Formula-transition guard: v1 composites are >0.99, v2 are <0.95.
                # Don't cascade-abort against a different formula's baseline.
                if best_composite > 0.95 and t1["composite_score"] < 0.95:
                    pass  # formula transition — skip cascade
                else:
                    gap = best_composite - t1["composite_score"]
                    if gap > _CASCADE_TIE_MULTIPLIER * tie_band:
                        return (
                            f"composite {t1['composite_score']:.6f} is {gap:.6f} below "
                            f"best {best_composite:.6f} (>{_CASCADE_TIE_MULTIPLIER}× tie_band)"
                        )
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Core trial execution
# ---------------------------------------------------------------------------

def _run_trial(
    trial_num: int,
    quiet: bool,
    timeout: int = DEFAULT_TRIAL_TIMEOUT,
) -> dict[str, float] | None:
    if not quiet:
        print(f"  trial {trial_num}...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [PYTHON, str(BENCHMARK)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if not quiet:
            print(f"TIMEOUT (>{timeout}s)")
        return None
    elapsed = time.perf_counter() - t0

    if not quiet:
        print(f"{elapsed:.1f}s")

    block_match = _BLOCK_RE.search(result.stdout)
    if not block_match:
        if not quiet:
            print(f"    WARNING: trial {trial_num} produced no parseable metrics block")
            if result.returncode != 0:
                print(f"    stderr: {result.stderr[:200]}")
        return None

    metrics: dict[str, float] = {}
    for m in _METRIC_RE.finditer(block_match.group(1)):
        metrics[m.group(1)] = float(m.group(2))

    return metrics if "composite_score" in metrics else None


# ---------------------------------------------------------------------------
# Aggregation and formatting
# ---------------------------------------------------------------------------

def _median_metrics(trials: list[dict[str, float]]) -> dict[str, float]:
    all_keys = list(trials[0].keys())
    return {k: statistics.median(t[k] for t in trials if k in t) for k in all_keys}


def _format_block(metrics: dict[str, float]) -> str:
    lines = ["---"]
    for key, value in metrics.items():
        if key in _INT_METRICS:
            lines.append(f"{key}: {int(round(value)):>14}")
        else:
            lines.append(f"{key}: {value:>14.6f}")
    lines.append("---")
    return "\n".join(lines)


def _variance_report(trials: list[dict[str, float]], medians: dict[str, float]) -> None:
    print("\nVariance report (signal vs noise — spread should be < your target delta):")
    key_metrics = [
        ("composite_score", "higher better"),
        ("p99_latency_ms",  "lower better"),
        ("throughput_rps",  "higher better"),
    ]
    for key, direction in key_metrics:
        if key not in trials[0]:
            continue
        vals = sorted(t[key] for t in trials)
        spread = vals[-1] - vals[0]
        med = medians[key]
        noise_pct = (spread / med * 100) if med > 0 else 0
        print(
            f"  {key:<22} median={med:.6f}  spread={spread:.6f}  "
            f"noise={noise_pct:.2f}%  ({direction})"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-trial jitter-defeating benchmark wrapper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 autoresearch/bench_stable.py
  python3 autoresearch/bench_stable.py --trials 7 --out autoresearch/run.log
  python3 autoresearch/bench_stable.py --quiet
  python3 autoresearch/bench_stable.py --no-resume  # start fresh
""",
    )
    parser.add_argument(
        "--trials", type=int, default=5,
        help="Number of trials. Odd numbers give a clean median (default: 5).",
    )
    parser.add_argument(
        "--out", default="autoresearch/run.log",
        help="Output log path (default: autoresearch/run.log)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-trial progress output",
    )
    parser.add_argument(
        "--no-resume", action="store_true", dest="no_resume",
        help="Ignore cached trial checkpoints and start fresh",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TRIAL_TIMEOUT,
        help=f"Per-trial timeout in seconds (default: {DEFAULT_TRIAL_TIMEOUT})",
    )
    args = parser.parse_args()

    if args.trials < 1:
        print("ERROR: --trials must be >= 1", file=sys.stderr)
        return 1
    if args.trials % 2 == 0:
        print(
            f"NOTE: even trial count ({args.trials}) — median is avg of two middle values",
            file=sys.stderr,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Checkpoint/resume: load already-completed trials
    trial_results: dict[int, dict[str, float]] = {}
    if not args.no_resume:
        cached = _load_cached_trials(out_path, args.trials)
        if cached:
            print(
                f"bench_stable: resuming — {len(cached)}/{args.trials} trials "
                f"already cached (use --no-resume to start fresh)"
            )
            trial_results = cached

    print(f"bench_stable: {args.trials} trials → median metrics → {args.out}")

    cascade_aborted = False
    for i in range(1, args.trials + 1):
        if i in trial_results:
            if not args.quiet:
                print(f"  trial {i}... (cached)")
            continue

        result = _run_trial(i, args.quiet, args.timeout)
        if result is not None:
            trial_results[i] = result
            _save_trial(out_path, i, result)   # checkpoint immediately

            # Cascade abort: check after first fresh successful trial
            fresh_results = [trial_results[j] for j in sorted(trial_results)]
            if len(fresh_results) == 1 or (len(trial_results) == 1):
                reason = _cascade_check(result)
                if reason:
                    print(f"  CASCADE ABORT after trial {i}: {reason}")
                    print("  Remaining trials skipped — result is a guaranteed discard.")
                    cascade_aborted = True
                    break
        else:
            print(f"  WARNING: trial {i} failed — skipping")

    results_list = [trial_results[i] for i in sorted(trial_results)]

    if not results_list:
        print("ERROR: all trials failed — check benchmark.py output", file=sys.stderr)
        return 1

    n_ok = len(results_list)
    if n_ok < args.trials and not cascade_aborted:
        print(f"WARNING: only {n_ok}/{args.trials} trials succeeded")

    medians = _median_metrics(results_list)

    if not args.quiet and n_ok > 1:
        _variance_report(results_list, medians)

    # Build provenance header (outside the --- block, ignored by log_run.py)
    composites = [r["composite_score"] for r in results_list]
    p99s = [r["p99_latency_ms"] for r in results_list]
    provenance = (
        f"=== bench_stable: {n_ok}/{args.trials} trials, medians ===\n"
        f"bench_stable_trials: {n_ok}\n"
        f"composite_spread: {max(composites) - min(composites):.6f}\n"
        f"p99_spread_ms: {max(p99s) - min(p99s):.6f}\n"
    )

    block = _format_block(medians)
    out_path.write_text(provenance + "\n" + block + "\n")

    # Clean up checkpoints on success (leave them on cascade abort for inspection)
    if not cascade_aborted:
        _cleanup_trials(out_path, args.trials)

    print(f"\nMedian results ({n_ok} trial{'s' if n_ok != 1 else ''}):")
    print(f"  composite_score: {medians['composite_score']:.6f}")
    print(f"  p99_latency_ms:  {medians['p99_latency_ms']:.6f}")
    print(f"  compliance_rate: {medians['compliance_rate']:.6f}")
    if cascade_aborted:
        print("\n→ CASCADE ABORTED — no need to log_run this result.")
    else:
        print(f"\nLog with:")
        print(f'  python3 autoresearch/log_run.py {args.out} \\')
        print(f'    --commit "$(git rev-parse --short HEAD)" \\')
        print(f'    --description "your hypothesis"')

    return 0


if __name__ == "__main__":
    sys.exit(main())
