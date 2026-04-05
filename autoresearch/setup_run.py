#!/usr/bin/env python3
"""
Initialize an autoresearch benchmark run.

Usage:
    python3 autoresearch/setup_run.py --tag mar15

Actions:
  1. Checks branch cleanliness before any git mutation
  2. Creates (or switches to) branch autoresearch/<tag>
  3. Prints the best overall, hot-path, and sidecar comparable rows
  4. Prints recent wins/discards grouped by scope
  5. Prints the next benchmark/logging commands

Run from repo root.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from results_utils import best_kept_row, ensure_results_tsv, load_rows, recent_rows

RESULTS_TSV = Path(__file__).parent / "results.tsv"
_GIT_BIN = shutil.which("git") or "git"


def _git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603
        [_GIT_BIN, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _git_check(*args: str) -> bool:
    result = subprocess.run(  # noqa: S603
        [_GIT_BIN, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def format_row(row: dict[str, str]) -> str:
    return (
        f"  commit={row.get('commit', '?')[:12]}"
        f"  composite={float(row.get('composite', '0')):.6f}"
        f"  compliance={float(row.get('compliance', '0')):.6f}"
        f"  p99_ms={float(row.get('p99_ms', '0')):.3f}"
        f"  scope={row.get('scope', 'hot-path')}"
        f"  status={row.get('status', '?')}"
        f"  {row.get('description', '')}"
    )


def print_rows(title: str, rows: list[dict[str, str]]) -> None:
    print(f"\n{title}:")
    if not rows:
        print("  (none)")
        return
    for row in rows:
        print(format_row(row))


def ensure_ready_to_switch(*, branch_will_change: bool, dirty_allowed: bool) -> bool:
    status_out = _git("status", "--porcelain")
    if branch_will_change and status_out and not dirty_allowed:
        print(f"\nWorking tree: DIRTY ({len(status_out.splitlines())} modified/untracked)")
        print("  Refusing to switch branches with an unclaimed dirty tree.")
        print("  Use --dirty to keep local edits attached to the new branch, or stash first.")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an autoresearch benchmark run.")
    parser.add_argument("--tag", required=True, help="Run tag (e.g. mar15). Branch: autoresearch/<tag>")
    parser.add_argument("--dirty", action="store_true", help="Allow dirty working tree")
    parser.add_argument("--base", default="main", help="Base branch for new autoresearch branches")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without mutating git state")
    args = parser.parse_args()

    branch_name = f"autoresearch/{args.tag}"
    current_branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    print(f"\n=== autoresearch setup: {args.tag} ===\n")
    print(f"Target branch : {branch_name}")
    print(f"Current branch: {current_branch}")
    print(f"Base branch   : {args.base}")

    branch_will_change = current_branch != branch_name
    if not ensure_ready_to_switch(branch_will_change=branch_will_change, dirty_allowed=args.dirty):
        return 1

    if current_branch == branch_name:
        print("Already on target branch.")
    elif _git_check("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"):
        print(f"Branch exists — switching: git checkout {branch_name}")
        if not args.dry_run:
            subprocess.run([_GIT_BIN, "checkout", branch_name], check=True)  # noqa: S603
    else:
        if not _git_check("rev-parse", "--verify", args.base):
            print(f"ERROR: base branch not found: {args.base}", file=sys.stderr)
            return 1
        print(f"Creating branch: git checkout -b {branch_name} {args.base}")
        if not args.dry_run:
            subprocess.run(  # noqa: S603
                [_GIT_BIN, "checkout", "-b", branch_name, args.base],
                check=True,
            )

    status_out = _git("status", "--porcelain")
    if status_out:
        print(f"\nWorking tree: DIRTY ({len(status_out.splitlines())} modified/untracked)")
    else:
        print("\nWorking tree: CLEAN")

    ensure_results_tsv(RESULTS_TSV)
    rows = load_rows(RESULTS_TSV)
    print(f"\nresults.tsv  : {len(rows)} rows")

    for scope, label in (
        ("any", "Best kept row"),
        ("hot-path", "Best hot-path row"),
        ("sidecar", "Best sidecar row"),
    ):
        best = best_kept_row(rows, scope)
        if best:
            print(f"\n{label}:\n{format_row(best)}")
        else:
            print(f"\n{label}: (none)")

    print_rows(
        "Recent hot-path wins",
        recent_rows(rows, scope="hot-path", statuses={"improved", "neutral-kept", "baseline"}),
    )
    print_rows(
        "Recent sidecar wins",
        recent_rows(rows, scope="sidecar", statuses={"improved", "neutral-kept", "baseline"}),
    )
    print_rows("Recent hot-path discards", recent_rows(rows, scope="hot-path", statuses={"discard"}))

    print(
        f"""
=== Ready ===

Next steps:
  1. Read autoresearch/program.md and the hot-path files.
  2. Run baseline:
       cd autoresearch && python3 benchmark.py > run.log 2>&1
  3. Parse metrics:
       grep '^composite_score:\\|^compliance_rate:\\|^p99_latency_ms:\\|^false_positive_rate:\\|^false_negative_rate:' autoresearch/run.log
  4. Log baseline:
       python3 autoresearch/log_run.py autoresearch/run.log \\
         --commit "$(git rev-parse --short HEAD 2>/dev/null || echo uncommitted)" \\
         --description "baseline {args.tag}"
  5. Only keep a tie if it is simpler or materially faster:
       python3 autoresearch/log_run.py autoresearch/run.log --recommend --simpler
  6. Then iterate per autoresearch/program.md.
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
