"""Tests for offline constitution eval runner and CLI surface."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from acgs_lite.commands.eval_cmd import handler
from acgs_lite.evals import compare_eval_reports, load_scenarios, run_eval
from acgs_lite.evals.schema import EvalScenario

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "evals"
BASELINE = FIXTURES_DIR / "baseline.constitution.yaml"
CANDIDATE = FIXTURES_DIR / "candidate.constitution.yaml"
SCENARIOS = FIXTURES_DIR / "scenarios.yaml"


def test_eval_scenario_requires_id() -> None:
    with pytest.raises(ValueError, match="requires a non-empty 'id'"):
        EvalScenario.from_dict({"input_action": "test"})


def test_load_scenarios_fixture() -> None:
    scenarios = load_scenarios(SCENARIOS)
    assert len(scenarios) == 4
    assert scenarios[0].id == "workflow-action-notify"


def test_run_eval_matches_baseline_fixture() -> None:
    report = run_eval(BASELINE, SCENARIOS)

    assert report.success is True
    assert report.passed == 4
    assert report.failed == 0
    assert report.action_distribution["block"] == 1
    assert report.action_distribution["block_and_notify"] == 1
    assert report.action_distribution["require_human_review"] == 1
    assert report.action_distribution["halt_and_alert"] == 1


def test_compare_eval_reports_flags_candidate_regressions() -> None:
    baseline_report = run_eval(BASELINE, SCENARIOS)
    candidate_report = run_eval(CANDIDATE, SCENARIOS)

    comparison = compare_eval_reports(baseline_report, candidate_report)

    assert comparison.success is False
    assert {item.scenario_id for item in comparison.regressions} == {
        "privacy-pii",
        "eu-human-oversight",
    }
    assert {item.scenario_id for item in comparison.changed_actions} == {
        "privacy-pii",
        "eu-human-oversight",
    }
    assert comparison.action_distribution_delta["warn"] == 1
    assert comparison.action_distribution_delta["block"] == -1


def test_eval_report_to_dict_is_json_serializable() -> None:
    report = run_eval(BASELINE, SCENARIOS)
    payload = report.to_dict()
    assert payload["success"] is True
    json.dumps(payload)


def test_cli_eval_run_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    from acgs_lite.cli import build_parser, cmd_eval

    parser = build_parser()
    args = parser.parse_args(["eval", "run", str(BASELINE), str(SCENARIOS), "--json"])
    rc = cmd_eval(args)
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["success"] is True
    assert output["passed"] == 4


def test_cli_eval_compare_detects_regressions(capsys: pytest.CaptureFixture[str]) -> None:
    from acgs_lite.cli import build_parser, cmd_eval

    parser = build_parser()
    args = parser.parse_args(
        ["eval", "compare", str(BASELINE), str(CANDIDATE), str(SCENARIOS), "--json"]
    )
    rc = cmd_eval(args)
    output = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert output["success"] is False
    assert len(output["regressions"]) == 2


def test_eval_cmd_plain_text_output() -> None:
    args = Namespace(
        eval_action="run",
        constitution=str(BASELINE.resolve()),
        scenarios=str(SCENARIOS.resolve()),
        json_out=False,
    )

    assert handler(args) == 0
