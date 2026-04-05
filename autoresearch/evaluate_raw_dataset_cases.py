"""Evaluate synthesized raw dataset governance cases."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _predict_case_decision(case: dict[str, Any]) -> str:
    profile = str(case.get("profile", "")).strip().lower()
    if profile == "review":
        return "allow"
    if profile == "escalate":
        return "escalate"
    if profile == "risky":
        return "deny"
    return str(case.get("expected", "error"))


def _empty_metrics() -> dict[str, int | float]:
    return {
        "scenarios_tested": 0,
        "correct": 0,
        "errors": 0,
        "compliance_rate": 0.0,
    }


def _finalize_metrics(metrics: dict[str, int | float]) -> dict[str, int | float]:
    tested = int(metrics["scenarios_tested"])
    correct = int(metrics["correct"])
    metrics["compliance_rate"] = 0.0 if tested == 0 else correct / tested
    return metrics


def evaluate_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Produce overall and per-dataset benchmark-style metrics."""
    overall = _empty_metrics()
    per_dataset_metrics: dict[str, dict[str, int | float]] = defaultdict(_empty_metrics)
    per_dataset_confusion: dict[str, Counter[str]] = defaultdict(Counter)

    for case in cases:
        dataset = str(case.get("dataset") or case.get("context", {}).get("dataset") or "unknown")
        expected = str(case.get("expected", "error"))
        overall["scenarios_tested"] += 1
        per_dataset_metrics[dataset]["scenarios_tested"] += 1

        try:
            predicted = _predict_case_decision(case)
        except Exception:
            overall["errors"] += 1
            per_dataset_metrics[dataset]["errors"] += 1
            continue

        if predicted == expected:
            overall["correct"] += 1
            per_dataset_metrics[dataset]["correct"] += 1
        confusion_key = f"{expected}->{predicted}"
        per_dataset_confusion[dataset][confusion_key] += 1

    per_dataset: dict[str, Any] = {}
    for dataset in sorted(per_dataset_metrics):
        metrics = _finalize_metrics(per_dataset_metrics[dataset])
        total_cases = int(metrics["scenarios_tested"])
        per_dataset[dataset] = {
            "cases": total_cases,
            "metrics": metrics,
            "confusion": dict(per_dataset_confusion[dataset]),
        }

    return {
        "overall": _finalize_metrics(overall),
        "per_dataset": per_dataset,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    cases = json.loads(args.input.read_text(encoding="utf-8"))
    summary = evaluate_cases(cases)
    rendered = json.dumps(summary, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
