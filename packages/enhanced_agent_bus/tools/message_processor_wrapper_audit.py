"""Audit remaining MessageProcessor wrapper usage.

This script is a pre-delete gate for the post-refactor wrapper cleanup plan. It scans the
repository for remaining references to `MessageProcessor` compatibility wrappers, classifies those
references by source (coverage shards, non-coverage tests, runtime code, docs), and can fail fast
when wrappers marked as retired or delete-ready drift back into active use.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

UsageCategory = Literal["coverage", "test", "runtime", "docs", "other"]
WrapperDisposition = Literal[
    "delete_after_coverage_regeneration",
    "keep_for_compat",
    "keep_for_orchestration",
    "deleted_now",
]
BatchName = Literal["batch1", "batch2", "batch3"]


@dataclass(frozen=True)
class WrapperPolicy:
    name: str
    disposition: WrapperDisposition
    rationale: str


@dataclass(frozen=True)
class UsageHit:
    path: Path
    line_number: int
    line: str
    category: UsageCategory


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "enhanced_agent_bus"
COVERAGE_ROOT = PACKAGE_ROOT / "tests" / "coverage"

WRAPPER_POLICIES: tuple[WrapperPolicy, ...] = (
    WrapperPolicy(
        name="_extract_session_context",
        disposition="delete_after_coverage_regeneration",
        rationale="Coordinator coverage exists; remaining blockers are coverage-driven facade calls.",
    ),
    WrapperPolicy(
        name="_perform_security_scan",
        disposition="delete_after_coverage_regeneration",
        rationale="GateCoordinator coverage exists; remaining blockers are coverage-driven facade calls.",
    ),
    WrapperPolicy(
        name="_requires_independent_validation",
        disposition="delete_after_coverage_regeneration",
        rationale="Policy-threshold behavior is covered at GateCoordinator level already.",
    ),
    WrapperPolicy(
        name="_enforce_independent_validator_gate",
        disposition="delete_after_coverage_regeneration",
        rationale="Independent-validator behavior is covered at GateCoordinator level already.",
    ),
    WrapperPolicy(
        name="_enforce_autonomy_tier",
        disposition="delete_after_coverage_regeneration",
        rationale="Autonomy delegation is covered at GateCoordinator level already.",
    ),
    WrapperPolicy(
        name="_extract_message_session_id",
        disposition="delete_after_coverage_regeneration",
        rationale="Session-id extraction is covered at SessionCoordinator level already.",
    ),
    WrapperPolicy(
        name="_attach_session_context",
        disposition="delete_after_coverage_regeneration",
        rationale="Mainline no longer uses the wrapper; coverage shards still exercise the legacy signature.",
    ),
    WrapperPolicy(
        name="_send_to_dlq",
        disposition="keep_for_compat",
        rationale="Still owns facade-level Redis reset semantics and non-coverage compat usage.",
    ),
    WrapperPolicy(
        name="_detect_prompt_injection",
        disposition="keep_for_compat",
        rationale="Explicit downstream compatibility requirement remains in non-coverage tests.",
    ),
    WrapperPolicy(
        name="_handle_successful_processing",
        disposition="keep_for_orchestration",
        rationale="Useful facade-owned sink seam used by VerificationCoordinator.",
    ),
    WrapperPolicy(
        name="_handle_failed_processing",
        disposition="keep_for_orchestration",
        rationale="Useful facade-owned sink seam used by VerificationCoordinator.",
    ),
    WrapperPolicy(
        name="_execute_verification_and_processing",
        disposition="deleted_now",
        rationale="Removed already; should only appear in docs/history, not active code/tests.",
    ),
    WrapperPolicy(
        name="_persist_flywheel_decision_event",
        disposition="deleted_now",
        rationale="Removed already; should only appear in docs/history, not active code/tests.",
    ),
)

IGNORED_DIR_NAMES = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", ".mypy_cache"}
SCAN_SUFFIXES = {".py", ".md"}
EXCLUDED_RELATIVE_PATHS = {
    Path("packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py"),
}
IGNORED_ACTIVE_USAGE_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "_requires_independent_validation": ("self._requires_independent_validation(",),
}
BATCH_WRAPPERS: dict[BatchName, tuple[str, ...]] = {
    "batch1": (
        "_requires_independent_validation",
        "_enforce_independent_validator_gate",
    ),
    "batch2": (
        "_extract_session_context",
        "_perform_security_scan",
        "_attach_session_context",
    ),
    "batch3": (
        "_enforce_autonomy_tier",
        "_extract_message_session_id",
    ),
}


def iter_repo_files() -> list[Path]:
    paths: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if path.relative_to(REPO_ROOT) in EXCLUDED_RELATIVE_PATHS:
            continue
        paths.append(path)
    return sorted(paths)


def categorize_path(path: Path) -> UsageCategory:
    relative = path.relative_to(REPO_ROOT).as_posix()
    if relative.startswith("packages/enhanced_agent_bus/tests/coverage/"):
        return "coverage"
    if "/tests/" in f"/{relative}":
        return "test"
    if path.suffix == ".md":
        return "docs"
    if relative.startswith("packages/enhanced_agent_bus/"):
        return "runtime"
    return "other"


@lru_cache(maxsize=1)
def collect_all_hits() -> dict[str, list[UsageHit]]:
    hit_index = {policy.name: [] for policy in WRAPPER_POLICIES}
    wrapper_names = tuple(hit_index.keys())
    for path in iter_repo_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        category = categorize_path(path)
        relative_path = path.relative_to(REPO_ROOT)
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for wrapper_name in wrapper_names:
                if wrapper_name not in stripped:
                    continue
                hit_index[wrapper_name].append(
                    UsageHit(
                        path=relative_path,
                        line_number=line_number,
                        line=stripped,
                        category=category,
                    )
                )
    return hit_index


def collect_hits(wrapper_name: str) -> list[UsageHit]:
    return collect_all_hits()[wrapper_name]


def summarize_hits(hits: list[UsageHit]) -> dict[UsageCategory, int]:
    summary: dict[UsageCategory, int] = {
        "coverage": 0,
        "test": 0,
        "runtime": 0,
        "docs": 0,
        "other": 0,
    }
    for hit in hits:
        summary[hit.category] += 1
    return summary


def format_summary_table() -> str:
    rows = [
        "| Wrapper | Disposition | Coverage | Tests | Runtime | Docs | Other |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy in WRAPPER_POLICIES:
        summary = summarize_hits(collect_hits(policy.name))
        rows.append(
            f"| `{policy.name}(...)` | {policy.disposition} | {summary['coverage']} | {summary['test']} | {summary['runtime']} | {summary['docs']} | {summary['other']} |"
        )
    return "\n".join(rows)


def format_detailed_report() -> str:
    sections: list[str] = []
    for policy in WRAPPER_POLICIES:
        hits = collect_hits(policy.name)
        summary = summarize_hits(hits)
        sections.append(f"## {policy.name}")
        sections.append("")
        sections.append(f"- Disposition: `{policy.disposition}`")
        sections.append(f"- Rationale: {policy.rationale}")
        sections.append(
            "- Usage counts: "
            f"coverage={summary['coverage']}, tests={summary['test']}, runtime={summary['runtime']}, docs={summary['docs']}, other={summary['other']}"
        )
        sections.append("")
        if not hits:
            sections.append("No remaining references found.")
            sections.append("")
            continue
        for hit in hits:
            sections.append(f"- `{hit.path}:{hit.line_number}` [{hit.category}] — {hit.line}")
        sections.append("")
    return "\n".join(sections)


def _is_wrapper_definition(wrapper_name: str, hit: UsageHit) -> bool:
    return hit.line.startswith(f"def {wrapper_name}(") or hit.line.startswith(
        f"async def {wrapper_name}("
    )


def _is_active_usage_hit(wrapper_name: str, hit: UsageHit) -> bool:
    if hit.category == "docs":
        return False
    line = hit.line
    if any(
        ignored_substring in line
        for ignored_substring in IGNORED_ACTIVE_USAGE_SUBSTRINGS.get(wrapper_name, ())
    ):
        return False
    active_markers = (
        f".{wrapper_name}(",
        f'"{wrapper_name}"',
        f"'{wrapper_name}'",
        "hasattr(",
    )
    return any(marker in line for marker in active_markers)


def check_policy_violations() -> list[str]:
    violations: list[str] = []
    for policy in WRAPPER_POLICIES:
        hits = collect_hits(policy.name)
        active_hits = [hit for hit in hits if _is_active_usage_hit(policy.name, hit)]
        coverage_hits = [hit for hit in active_hits if hit.category == "coverage"]
        non_coverage_active_hits = [hit for hit in active_hits if hit.category != "coverage"]
        definition_hits = [hit for hit in hits if _is_wrapper_definition(policy.name, hit)]

        if policy.disposition == "deleted_now" and (active_hits or definition_hits):
            violations.append(
                f"{policy.name}: expected deleted; found active references at "
                + ", ".join(
                    f"{hit.path}:{hit.line_number}" for hit in (*definition_hits, *active_hits)[:8]
                )
            )
        if policy.disposition == "delete_after_coverage_regeneration" and non_coverage_active_hits:
            violations.append(
                f"{policy.name}: expected only coverage/doc blockers, found non-coverage active references at "
                + ", ".join(f"{hit.path}:{hit.line_number}" for hit in non_coverage_active_hits[:8])
            )
        if policy.disposition == "delete_after_coverage_regeneration" and not coverage_hits:
            violations.append(
                f"{policy.name}: marked delete-after-coverage-regeneration but no coverage blockers remain; reclassify it."
            )
    return violations


def check_batch_readiness(batch: BatchName) -> list[str]:
    violations: list[str] = []
    for wrapper_name in BATCH_WRAPPERS[batch]:
        hits = collect_hits(wrapper_name)
        active_hits = [hit for hit in hits if _is_active_usage_hit(wrapper_name, hit)]
        coverage_hits = [hit for hit in active_hits if hit.category == "coverage"]
        non_coverage_active_hits = [hit for hit in active_hits if hit.category != "coverage"]

        if coverage_hits:
            violations.append(
                f"{wrapper_name}: coverage blockers remain at "
                + ", ".join(f"{hit.path}:{hit.line_number}" for hit in coverage_hits[:8])
            )
        if non_coverage_active_hits:
            violations.append(
                f"{wrapper_name}: non-coverage active callers remain at "
                + ", ".join(f"{hit.path}:{hit.line_number}" for hit in non_coverage_active_hits[:8])
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("table", "detail"),
        default="table",
        help="Output style for the audit report.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if wrapper usage drifts away from the cleanup policy.",
    )
    parser.add_argument(
        "--ready-batch",
        choices=("batch1", "batch2", "batch3"),
        help="Fail until the selected deletion batch has no remaining active callers beyond docs/definitions.",
    )
    args = parser.parse_args()

    if args.format == "table":
        print(format_summary_table())
    else:
        print(format_detailed_report())

    exit_code = 0

    if args.check:
        violations = check_policy_violations()
        if not violations:
            print("\nPolicy check passed.")
        else:
            print("\nPolicy check failed:")
            for violation in violations:
                print(f"- {violation}")
            exit_code = 1

    if args.ready_batch is not None:
        violations = check_batch_readiness(args.ready_batch)
        if not violations:
            print(f"\n{args.ready_batch} readiness check passed.")
        else:
            print(f"\n{args.ready_batch} readiness check failed:")
            for violation in violations:
                print(f"- {violation}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
