#!/usr/bin/env python3
"""
Self-improvement benchmark for acgs-lite GovernanceEngine.
Measures validate() throughput (OPS) and construction cost.
Outputs JSON as last stdout line: {"primary": <float>, "sub_scores": {...}}
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # ACGS repo root
ACGS_LITE = REPO_ROOT / "packages" / "acgs-lite"

BENCHMARK_FILE = ACGS_LITE / "tests" / "test_benchmark_engine.py"


def run_benchmark() -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_path = f.name

    cmd = [
        sys.executable, "-m", "pytest",
        str(BENCHMARK_FILE),
        "-m", "benchmark",
        "--benchmark-json", output_path,
        "--import-mode=importlib",
        "-q", "--no-header",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ACGS_LITE))
    if result.returncode != 0:
        print(f"Benchmark failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    with open(output_path) as f:
        data = json.load(f)

    Path(output_path).unlink(missing_ok=True)
    return data


def extract_scores(data: dict) -> tuple[float, dict]:
    benchmarks = {b["name"].split("::")[-1]: b["stats"] for b in data.get("benchmarks", [])}

    allow_ops = benchmarks.get("test_validate_allow_path_default_constitution", {}).get("ops", 0.0)
    deny_ops = benchmarks.get("test_validate_deny_path_default_constitution", {}).get("ops", 0.0)
    construct_ops = benchmarks.get("test_engine_construction_default_constitution", {}).get("ops", 0.0)

    # Primary: weighted harmonic-style composite of the two hot paths (normalised to k-OPS)
    # Weight: 60% allow (main path), 40% deny (rejection path)
    primary = (0.6 * allow_ops + 0.4 * deny_ops) / 1_000.0

    sub_scores = {
        "allow_ops_k": round(allow_ops / 1_000.0, 3),
        "deny_ops_k": round(deny_ops / 1_000.0, 3),
        "construct_ops": round(construct_ops, 3),
    }
    return round(primary, 3), sub_scores


if __name__ == "__main__":
    data = run_benchmark()
    primary, sub_scores = extract_scores(data)
    print(json.dumps({"primary": primary, "sub_scores": sub_scores}))
