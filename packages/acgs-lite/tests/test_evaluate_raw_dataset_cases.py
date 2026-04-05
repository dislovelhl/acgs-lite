"""Tests for evaluating adapter-generated governance cases."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from autoresearch.evaluate_raw_dataset_cases import evaluate_cases
    from autoresearch.raw_dataset_adapter import (
        _load_rows,
        adapt_dataset_rows,
        synthesize_governance_cases,
    )

    _AUTORESEARCH_AVAILABLE = True
except ImportError:
    _AUTORESEARCH_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AUTORESEARCH_AVAILABLE,
    reason="autoresearch scripts not present (local dev tooling, not committed)",
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw_datasets"


def _sample_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for dataset, fixture_name in [
        ("cfpb", "cfpb_sample.csv"),
        ("civil_comments", "civil_comments_sample.jsonl"),
        ("bias_in_bios", "bias_in_bios_sample.jsonl"),
        ("mimic_bhc", "mimic_bhc_sample.jsonl"),
    ]:
        records = adapt_dataset_rows(dataset, _load_rows(FIXTURES / fixture_name))
        cases.extend(synthesize_governance_cases(records, profiles=("review", "escalate", "risky")))
    return cases


@pytest.mark.unit
def test_evaluate_cases_reports_overall_metrics_and_per_dataset_breakdown() -> None:
    summary = evaluate_cases(_sample_cases())

    overall = summary["overall"]
    per_dataset = summary["per_dataset"]

    assert overall["scenarios_tested"] == 24
    assert overall["correct"] == 24
    assert overall["errors"] == 0
    assert overall["compliance_rate"] == 1.0
    assert set(per_dataset) == {"bias_in_bios", "cfpb", "civil_comments", "mimic_bhc"}

    for dataset_summary in per_dataset.values():
        metrics = dataset_summary["metrics"]
        assert dataset_summary["cases"] == 6
        assert metrics["scenarios_tested"] == 6
        assert metrics["correct"] == 6
        assert metrics["errors"] == 0


@pytest.mark.unit
def test_evaluate_cases_reports_expected_confusion_counts() -> None:
    summary = evaluate_cases(_sample_cases())

    assert summary["per_dataset"]["cfpb"]["confusion"] == {
        "allow->allow": 2,
        "escalate->escalate": 2,
        "deny->deny": 2,
    }
    assert summary["per_dataset"]["civil_comments"]["confusion"] == {
        "allow->allow": 2,
        "escalate->escalate": 2,
        "deny->deny": 2,
    }
