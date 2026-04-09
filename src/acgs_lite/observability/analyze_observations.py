#!/usr/bin/env python3
# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Deep observation pattern analysis.

Consumes ~/.acgs/observations.jsonl and produces statistical reports
matching the deep-observation-pattern-analysis skill methodology.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from acgs_lite.observability.session_observer import ToolObservation


def load_observations(path: Path) -> list[ToolObservation]:
    if not path.exists():
        return []
    return [
        ToolObservation.from_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def analyze(obs: list[ToolObservation]) -> dict:
    total = len(obs)
    if total == 0:
        return {"error": "no observations found"}

    tool_counts = Counter(o.tool_type for o in obs)
    success_count = sum(1 for o in obs if o.success)
    error_counts = Counter(o.error_type for o in obs if o.error_type)

    exploration_tools = frozenset(
        {
            "task",
            "grep",
            "glob",
            "bash",
            "ast_grep_search",
            "websearch",
            "webfetch",
            "context7_resolve",
            "context7_query",
            "claude-mem_mcp",
            "rg",
        }
    )
    production_tools = frozenset({"edit", "write"})
    preparation_tools = frozenset({"read", "skill"})
    coordination_tools = frozenset(
        {"todowrite", "background_output", "background_cancel", "question", "lsp_diagnostics"}
    )

    exploration = sum(tool_counts.get(t, 0) for t in exploration_tools)
    production = sum(tool_counts.get(t, 0) for t in production_tools)
    preparation = sum(tool_counts.get(t, 0) for t in preparation_tools)
    coordination = sum(tool_counts.get(t, 0) for t in coordination_tools)

    sessions = Counter(o.session_id for o in obs if o.session_id)

    edit_test_cycles: list[int] = []
    for sid in sessions:
        session_obs = [o for o in obs if o.session_id == sid]
        edits = 0
        for o in session_obs:
            if o.tool_type in production_tools:
                edits += 1
            elif o.tool_type == "test" or (
                o.metadata.get("command", "").startswith(("pytest", "make test"))
            ):
                if edits > 0:
                    edit_test_cycles.append(edits)
                    edits = 0

    grep_count = tool_counts.get("grep", 0)
    rg_count = tool_counts.get("rg", 0)
    simple_grep = sum(
        1 for o in obs if o.tool_type == "grep" and len(o.metadata.get("command", "")) < 200
    )
    complex_grep = sum(
        1 for o in obs if o.tool_type == "grep" and len(o.metadata.get("command", "")) >= 200
    )
    grep_errors = sum(1 for o in obs if o.tool_type == "grep" and not o.success)

    reads = tool_counts.get("read", 0)
    edits = tool_counts.get("edit", 0) + tool_counts.get("write", 0)

    sed_i = sum(
        1 for o in obs if o.tool_type == "bash" and "sed -i" in o.metadata.get("command", "")
    )

    return {
        "total": total,
        "sessions": dict(sessions),
        "success_rate": success_count / total,
        "tool_distribution": dict(tool_counts.most_common()),
        "exploration": exploration,
        "production": production,
        "preparation": preparation,
        "coordination": coordination,
        "exploration_to_production_ratio": exploration / production if production else float("inf"),
        "error_types": dict(error_counts.most_common(10)),
        "grep": {
            "total": grep_count,
            "ripgrep": rg_count,
            "simple": simple_grep,
            "complex": complex_grep,
            "errors": grep_errors,
            "complex_error_rate": (grep_errors / complex_grep if complex_grep else 0),
        },
        "read_before_edit": {
            "reads": reads,
            "edits": edits,
            "adequate": reads >= edits,
        },
        "sed_i_usage": sed_i,
        "edit_test_cycles": edit_test_cycles,
    }


def print_report(result: dict, verbose: bool = False) -> None:
    if "error" in result:
        print(result["error"])
        return

    print("=" * 60)
    print("DEEP OBSERVATION PATTERN ANALYSIS")
    print(f"Total observations: {result['total']}")
    print(f"Sessions: {len(result['sessions'])}")
    print("=" * 60)

    print("\n## 1. EXPLORATION vs PRODUCTION")
    print(f"  Exploration:  {result['exploration']}")
    print(f"  Production:   {result['production']}")
    print(f"  Preparation:  {result['preparation']}")
    print(f"  Coordination: {result['coordination']}")
    ratio = result["exploration_to_production_ratio"]
    print(f"\n  Ratio: {ratio:.1f}:1")
    if ratio < 4.1:
        print("  Status: IMPROVED vs baseline (4.1:1)")
    else:
        print("  Status: SAME/WORSE vs baseline (4.1:1)")

    print("\n## 2. TOOL DISTRIBUTION")
    for tool, count in sorted(result["tool_distribution"].items(), key=lambda x: -x[1])[:15]:
        pct = count / result["total"] * 100
        bar = "#" * int(pct / 2)
        print(f"  {tool:25s} {count:4d}  ({pct:5.1f}%) {bar}")

    print("\n## 3. GREP USAGE")
    g = result["grep"]
    print(f"  grep calls:      {g['total']}")
    print(f"  ripgrep (rg):    {g['ripgrep']}")
    print(f"  simple:          {g['simple']}")
    print(f"  complex:         {g['complex']}")
    print(f"  grep errors:     {g['errors']}")
    if g["complex"] > 0:
        print(f"  complex error rate: {g['complex_error_rate']:.0%}")
    if g["ripgrep"] == 0 and g["total"] > 0:
        print("  Status: FAIL — still zero ripgrep usage")
    else:
        print("  Status: OK")

    print("\n## 4. READ BEFORE EDIT")
    rbe = result["read_before_edit"]
    print(f"  Reads:  {rbe['reads']}")
    print(f"  Edits:  {rbe['edits']}")
    print(f"  Status: {'PASS' if rbe['adequate'] else 'FAIL'}")

    print("\n## 5. SED -I USAGE")
    print(f"  Instances: {result['sed_i_usage']}")
    print(f"  Status: {'FAIL' if result['sed_i_usage'] > 0 else 'PASS'}")

    print("\n## 6. ERROR TYPES")
    for err, count in result["error_types"].items():
        print(f"  {err:30s} {count}")

    if result["edit_test_cycles"]:
        print("\n## 7. EDIT-TEST CYCLES")
        cycles = result["edit_test_cycles"]
        print(f"  Average edits before test: {sum(cycles) / len(cycles):.1f}")
        print(f"  Max edits before test: {max(cycles)}")

    if verbose:
        print("\n## 8. SESSION BREAKDOWN")
        for sid, count in result["sessions"].items():
            print(f"  {sid}: {count} observations")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze AI coding session observations")
    parser.add_argument("--path", help="Path to observations.jsonl")
    parser.add_argument("--json", dest="json_out", action="store_true", help="JSON output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Include session breakdown")
    args = parser.parse_args()

    path = Path(args.path) if args.path else Path.home() / ".acgs" / "observations.jsonl"
    observations = load_observations(path)
    result = analyze(observations)

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        print_report(result, verbose=args.verbose)


if __name__ == "__main__":
    main()
