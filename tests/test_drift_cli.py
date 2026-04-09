"""Tests for `acgs eval drift` CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from acgs_lite.cli import build_parser
from acgs_lite.commands import eval_cmd

_FIXTURES = Path(__file__).parent / "fixtures"


def test_eval_drift_clean_vs_clean_exits_zero() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "eval",
            "drift",
            "--baseline",
            str(_FIXTURES / "drift_clean.jsonl"),
            "--current",
            str(_FIXTURES / "drift_clean.jsonl"),
        ]
    )

    assert eval_cmd.handler(args) == 0


def test_eval_drift_clean_vs_probing_exits_one() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "eval",
            "drift",
            "--baseline",
            str(_FIXTURES / "drift_clean.jsonl"),
            "--current",
            str(_FIXTURES / "drift_probing.jsonl"),
        ]
    )

    assert eval_cmd.handler(args) == 1


def test_eval_drift_emit_baseline_writes_valid_jsonl(tmp_path) -> None:
    output_path = tmp_path / "baseline.jsonl"
    parser = build_parser()
    args = parser.parse_args(
        [
            "eval",
            "drift",
            "--baseline",
            str(_FIXTURES / "drift_clean.jsonl"),
            "--current",
            str(_FIXTURES / "drift_clean.jsonl"),
            "--emit-baseline",
            str(output_path),
        ]
    )

    assert eval_cmd.handler(args) == 0
    lines = output_path.read_text().splitlines()
    assert lines
    assert all(isinstance(json.loads(line), dict) for line in lines)
