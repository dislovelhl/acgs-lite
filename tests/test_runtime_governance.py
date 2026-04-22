"""Unit tests for shared runtime-governance precedent helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from acgs_lite.constitution.experience_library import GovernanceExperienceLibrary
from acgs_lite.integrations._runtime_governance import (
    derive_precedent_decision,
    derive_precedent_rationale,
    highest_violation,
    record_validation_precedent,
)


def _make_violation(
    *,
    rule_id: str,
    severity: str,
    category: str = "general",
) -> SimpleNamespace:
    return SimpleNamespace(
        rule_id=rule_id,
        severity=SimpleNamespace(value=severity),
        category=category,
    )


class _StubEmbeddingProvider:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def embed(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == 1
        return [self.values]


@pytest.mark.unit
def test_derive_precedent_decision_maps_action_taken_to_escalate() -> None:
    result = SimpleNamespace(
        action_taken=SimpleNamespace(value="require_human_review"),
        warnings=[],
        valid=False,
    )

    assert derive_precedent_decision(result) == "escalate"


@pytest.mark.unit
def test_highest_violation_prefers_highest_severity() -> None:
    result = SimpleNamespace(
        violations=[
            _make_violation(rule_id="LOW-001", severity="low"),
            _make_violation(rule_id="CRIT-001", severity="critical"),
            _make_violation(rule_id="HIGH-001", severity="high"),
        ]
    )

    top = highest_violation(result)

    assert top is not None
    assert top.rule_id == "CRIT-001"


@pytest.mark.unit
def test_derive_precedent_rationale_uses_warning_rule_ids() -> None:
    result = SimpleNamespace(
        violations=[],
        warnings=[SimpleNamespace(rule_id="WARN-001"), SimpleNamespace(rule_id="WARN-002")],
    )

    assert derive_precedent_rationale(result, "warn") == "Warning from rules: WARN-001, WARN-002."


@pytest.mark.unit
def test_record_validation_precedent_records_decision_and_embedding() -> None:
    library = GovernanceExperienceLibrary()
    result = SimpleNamespace(
        action_taken=None,
        valid=False,
        warnings=[],
        violations=[
            _make_violation(rule_id="BLOCK-001", severity="high", category="safety"),
            _make_violation(rule_id="BLOCK-002", severity="medium", category="privacy"),
        ],
    )

    record_validation_precedent(
        experience_library=library,
        embedding_provider=_StubEmbeddingProvider([0.25, 0.75]),
        action="delete customer dataset",
        result=result,
        context={"env": "prod"},
    )

    assert len(library.precedents) == 1
    recorded = library.precedents[0]
    assert recorded.action == "delete customer dataset"
    assert recorded.decision == "deny"
    assert recorded.triggered_rules == ["BLOCK-001", "BLOCK-002"]
    assert recorded.context == {"env": "prod"}
    assert recorded.category == "safety"
    assert recorded.severity == "high"
    assert recorded.embedding == [0.25, 0.75]
    assert recorded.rationale == "Blocked by rules: BLOCK-001, BLOCK-002."
