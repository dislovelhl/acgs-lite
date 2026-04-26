"""Tests for the failure-mode catalog and the two grounded stabilizers.

F1 keystone PR — Stabilizer Telemetry Foundation.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import dataclasses

import pytest

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution.failure_modes import (
    FailureModeCatalog,
    Stabilizer,
    StabilizerOutcome,
    StabilizerResult,
    emit_from_fuzz_report,
)
from acgs_lite.constitution.rule_metrics import EvalReport, RuleMetrics
from acgs_lite.constitution.stabilizers import (
    AuditChainStabilizer,
    RuleFixtureStabilizer,
)

# ---------------------------------------------------------------------------
# StabilizerResult / StabilizerRecord
# ---------------------------------------------------------------------------


def test_stabilizer_result_is_frozen():
    result = StabilizerResult(stabilizer_id="S_x", outcome=StabilizerOutcome.PASS)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = StabilizerOutcome.FAIL  # type: ignore[misc]


def test_failure_mode_record_is_frozen():
    record = StabilizerResult(stabilizer_id="S_x", outcome=StabilizerOutcome.PASS).to_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.outcome = StabilizerOutcome.FAIL  # type: ignore[misc]


def test_failure_mode_record_to_dict_serialises_enum_as_string():
    record = StabilizerResult(stabilizer_id="S_x", outcome=StabilizerOutcome.FAIL).to_record()
    payload = record.to_dict()
    assert payload["outcome"] == "fail"
    assert payload["stabilizer_id"] == "S_x"
    assert isinstance(payload["emitted_at"], str)


def test_audit_entry_payload_pass_marks_valid_no_violations():
    record = StabilizerResult(stabilizer_id="S_x", outcome=StabilizerOutcome.PASS).to_record()
    payload = record.to_audit_entry_payload()
    assert payload["type"] == "stabilizer"
    assert payload["valid"] is True
    assert payload["violations"] == []


def test_audit_entry_payload_fail_marks_invalid_with_violation():
    record = StabilizerResult(stabilizer_id="S_y", outcome=StabilizerOutcome.FAIL).to_record()
    payload = record.to_audit_entry_payload()
    assert payload["type"] == "failure_mode"
    assert payload["valid"] is False
    assert payload["violations"] == ["S_y"]


# ---------------------------------------------------------------------------
# FailureModeCatalog
# ---------------------------------------------------------------------------


class _FakeStabilizer:
    id = "S_fake"

    def evaluate(self, **kwargs):
        return StabilizerResult(stabilizer_id=self.id, outcome=StabilizerOutcome.PASS)


def test_catalog_register_and_emit_appends_records():
    catalog = FailureModeCatalog()
    fake = _FakeStabilizer()
    catalog.register(fake)

    catalog.emit(fake.evaluate())
    catalog.emit(StabilizerResult(stabilizer_id=fake.id, outcome=StabilizerOutcome.FAIL))

    assert len(catalog.latest()) == 2
    assert catalog.registered_ids == ("S_fake",)


def test_catalog_get_returns_registered_stabilizer():
    catalog = FailureModeCatalog()
    fake = _FakeStabilizer()
    catalog.register(fake)
    assert catalog.get("S_fake") is fake
    assert catalog.get("S_unknown") is None


def test_catalog_isinstance_protocol_check_holds():
    fake = _FakeStabilizer()
    assert isinstance(fake, Stabilizer)


def test_catalog_by_stabilizer_filters_records():
    catalog = FailureModeCatalog()
    catalog.emit(StabilizerResult(stabilizer_id="S_a", outcome=StabilizerOutcome.PASS))
    catalog.emit(StabilizerResult(stabilizer_id="S_b", outcome=StabilizerOutcome.FAIL))
    catalog.emit(StabilizerResult(stabilizer_id="S_a", outcome=StabilizerOutcome.FAIL))
    assert len(catalog.by_stabilizer("S_a")) == 2
    assert len(catalog.by_stabilizer("S_b")) == 1


def test_syndrome_vector_returns_latest_outcome_per_registered_stabilizer():
    catalog = FailureModeCatalog()
    catalog.register(_FakeStabilizer())

    class _OtherStabilizer:
        id = "S_other"

        def evaluate(self, **kwargs):
            return StabilizerResult(stabilizer_id=self.id, outcome=StabilizerOutcome.PASS)

    catalog.register(_OtherStabilizer())

    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.PASS))
    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.FAIL))

    syndrome = catalog.syndrome_vector()
    assert syndrome["S_fake"] == StabilizerOutcome.FAIL  # most recent wins
    assert syndrome["S_other"] is None  # never emitted
    assert tuple(syndrome.keys()) == ("S_fake", "S_other")


def test_catalog_clear_removes_all_records_but_preserves_registry():
    catalog = FailureModeCatalog()
    catalog.register(_FakeStabilizer())
    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.PASS))
    catalog.clear()
    assert catalog.latest() == []
    assert catalog.registered_ids == ("S_fake",)


def test_catalog_audit_log_bridge_writes_audit_entry():
    audit_log = AuditLog()
    catalog = FailureModeCatalog(audit_log=audit_log)
    catalog.emit(
        StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.FAIL),
        agent_id="agent-007",
    )

    entries = audit_log.entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry.type == "failure_mode"
    assert entry.valid is False
    assert entry.agent_id == "agent-007"
    assert entry.violations == ["S_fake"]
    assert entry.metadata["stabilizer_id"] == "S_fake"
    assert audit_log.verify_chain() is True


def test_catalog_metrics_collector_bridge_invokes_recorder():
    captured: list[tuple[str, str]] = []

    class _FakeCollector:
        def record_stabilizer_result(self, stabilizer_id: str, outcome: str) -> None:
            captured.append((stabilizer_id, outcome))

    catalog = FailureModeCatalog(metrics_collector=_FakeCollector())
    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.PASS))
    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.FAIL))

    assert captured == [("S_fake", "pass"), ("S_fake", "fail")]


def test_catalog_metrics_collector_without_recorder_is_silent():
    catalog = FailureModeCatalog(metrics_collector=object())
    catalog.emit(StabilizerResult(stabilizer_id="S_fake", outcome=StabilizerOutcome.PASS))
    assert len(catalog.latest()) == 1


# ---------------------------------------------------------------------------
# RuleFixtureStabilizer
# ---------------------------------------------------------------------------


def _make_eval_report(rule_id: str, *, tp: int, fp: int, fn: int) -> EvalReport:
    rid = rule_id.upper()
    return EvalReport(
        rule_metrics={
            rid: RuleMetrics(
                rule_id=rid,
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn,
                true_negatives=0,
            )
        },
        suite_name="unit-test",
    )


def test_test_fixture_stabilizer_pass_when_f1_meets_threshold():
    report = _make_eval_report("RULE_X", tp=10, fp=0, fn=0)  # F1 = 1.0
    stab = RuleFixtureStabilizer(f1_threshold=0.7)
    result = stab.evaluate(rule_id="RULE_X", eval_report=report)
    assert result.outcome == StabilizerOutcome.PASS
    assert result.rule_id == "RULE_X"
    assert result.evidence["f1_score"] == 1.0


def test_test_fixture_stabilizer_fail_when_f1_below_threshold():
    report = _make_eval_report("RULE_X", tp=2, fp=10, fn=10)  # F1 ~ 0.17
    stab = RuleFixtureStabilizer(f1_threshold=0.7)
    result = stab.evaluate(rule_id="RULE_X", eval_report=report)
    assert result.outcome == StabilizerOutcome.FAIL
    assert result.evidence["false_positives"] == 10
    assert result.evidence["false_negatives"] == 10
    assert result.evidence["threshold"] == 0.7


def test_test_fixture_stabilizer_threshold_must_be_in_range():
    with pytest.raises(ValueError):
        RuleFixtureStabilizer(f1_threshold=1.5)
    with pytest.raises(ValueError):
        RuleFixtureStabilizer(f1_threshold=-0.1)


def test_test_fixture_stabilizer_raises_on_unknown_rule():
    report = _make_eval_report("RULE_X", tp=10, fp=0, fn=0)
    stab = RuleFixtureStabilizer()
    with pytest.raises(KeyError):
        stab.evaluate(rule_id="RULE_UNKNOWN", eval_report=report)


def test_test_fixture_stabilizer_satisfies_protocol():
    assert isinstance(RuleFixtureStabilizer(), Stabilizer)


# ---------------------------------------------------------------------------
# AuditChainStabilizer
# ---------------------------------------------------------------------------


def test_audit_chain_stabilizer_pass_on_intact_log():
    log = AuditLog()
    log.record(AuditEntry(id="a1", type="validation", agent_id="ag1"))
    log.record(AuditEntry(id="a2", type="validation", agent_id="ag1"))

    stab = AuditChainStabilizer()
    result = stab.evaluate(audit_log=log)
    assert result.outcome == StabilizerOutcome.PASS
    assert result.evidence["chain_valid"] is True
    assert result.evidence["entry_count"] == 2


def test_audit_chain_stabilizer_pass_on_empty_log():
    log = AuditLog()
    result = AuditChainStabilizer().evaluate(audit_log=log)
    assert result.outcome == StabilizerOutcome.PASS
    assert result.evidence["entry_count"] == 0


def test_audit_chain_stabilizer_fail_when_chain_tampered():
    log = AuditLog()
    log.record(AuditEntry(id="a1", type="validation"))
    log.record(AuditEntry(id="a2", type="validation"))

    # Tamper with an entry in place — entries property returns a *copy*, so
    # we have to reach into the private list to actually mutate.
    log._entries[0].agent_id = "evil"  # noqa: SLF001

    result = AuditChainStabilizer().evaluate(audit_log=log)
    assert result.outcome == StabilizerOutcome.FAIL
    assert result.evidence["chain_valid"] is False


def test_audit_chain_stabilizer_satisfies_protocol():
    assert isinstance(AuditChainStabilizer(), Stabilizer)


# ---------------------------------------------------------------------------
# emit_from_fuzz_report integration helper
# ---------------------------------------------------------------------------


class _FakeBypassCase:
    def __init__(self, rule_id: str | None) -> None:
        self.rule_id = rule_id


class _FakeFuzzReport:
    def __init__(self, rule_ids: list[str | None]) -> None:
        self.suspected_bypasses = [_FakeBypassCase(rid) for rid in rule_ids]


def test_emit_from_fuzz_report_emits_one_record_per_distinct_rule():
    eval_report = _make_eval_report("RULE_X", tp=2, fp=10, fn=10)  # F1 ~0.17 → FAIL
    catalog = FailureModeCatalog()
    catalog.register(RuleFixtureStabilizer(f1_threshold=0.7))
    fuzz_report = _FakeFuzzReport(["rule_x", "rule_x", "rule_x"])  # de-duped to 1

    emitted = emit_from_fuzz_report(
        catalog=catalog,
        fuzz_report=fuzz_report,
        eval_report=eval_report,
    )
    assert emitted == 1
    records = catalog.by_stabilizer("S_test_fixture")
    assert len(records) == 1
    assert records[0].outcome == StabilizerOutcome.FAIL
    assert records[0].rule_id == "RULE_X"


def test_emit_from_fuzz_report_skips_rules_without_metrics():
    eval_report = _make_eval_report("RULE_X", tp=10, fp=0, fn=0)
    catalog = FailureModeCatalog()
    catalog.register(RuleFixtureStabilizer())
    fuzz_report = _FakeFuzzReport(["rule_unknown"])

    emitted = emit_from_fuzz_report(
        catalog=catalog,
        fuzz_report=fuzz_report,
        eval_report=eval_report,
    )
    assert emitted == 0
    assert catalog.latest() == []


def test_emit_from_fuzz_report_no_op_when_stabilizer_missing():
    eval_report = _make_eval_report("RULE_X", tp=10, fp=0, fn=0)
    catalog = FailureModeCatalog()
    fuzz_report = _FakeFuzzReport(["rule_x"])

    emitted = emit_from_fuzz_report(
        catalog=catalog,
        fuzz_report=fuzz_report,
        eval_report=eval_report,
    )
    assert emitted == 0
