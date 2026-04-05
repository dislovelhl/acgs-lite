"""Static contract tests for Rego edge-case boundaries in bundled policies."""

from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"


def _read_policy(name: str) -> str:
    return (POLICY_DIR / name).read_text(encoding="utf-8")


def test_constitutional_rego_uses_transition_grace_hashes() -> None:
    text = _read_policy("constitutional.rego")
    assert "evolution.is_in_grace_period" in text
    assert "input.constitutional_hash in evolution.valid_hashes_during_transition" in text


def test_constitutional_evolution_grace_period_is_strict_boundary() -> None:
    text = _read_policy("constitutional_evolution.rego")
    assert "elapsed < grace_period_seconds" in text


def test_ratelimit_policy_denies_exact_thresholds() -> None:
    text = _read_policy("ratelimit.rego")
    assert "input.request_rate_qps < 100" in text
    assert "input.burst_count < 200" in text


def test_timebased_policy_business_hours_boundaries_are_explicit() -> None:
    text = _read_policy("timebased.rego")
    assert "hour >= 9" in text
    assert "hour < 18" in text


def test_rbac_policy_contains_privilege_escalation_guards() -> None:
    text = _read_policy("rbac.rego")
    assert 'input.required_role == "admin"' in text
    assert 'not user_roles_set["admin"]' in text
    assert 'input.action == "delete"' in text


def test_temporal_policy_requires_prerequisites_for_high_impact_actions() -> None:
    text = _read_policy("temporal.rego")
    assert 'input.action in {"execute_action", "commit_governance_decision"}' in text
    assert "input.impact_score >= 0.8" in text
    assert 'not history_set["maci_consensus_approved"]' in text


def test_compliance_policy_blocks_eval_exec_and_import_injection() -> None:
    text = _read_policy("compliance.rego")
    assert r"eval\s*\(" in text
    assert r"exec\s*\(" in text
    assert "__import__" in text
