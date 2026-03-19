"""Tests for acgs_lite.constitution.metrics module.

Covers GovernanceEvent, create_governance_event, GovernanceMetrics,
GovernanceSession, RuleEffectiveness, AuditEntry, AuditLedger,
GovernanceSLO, GovernanceCostModel, and GovernanceForecaster.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from acgs_lite.constitution.metrics import (
    AuditEntry,
    AuditLedger,
    GovernanceCostModel,
    GovernanceEvent,
    GovernanceForecaster,
    GovernanceMetrics,
    GovernanceSession,
    GovernanceSLO,
    RuleEffectiveness,
    create_governance_event,
)


# ── GovernanceEvent ──────────────────────────────────────────────────────────


class TestGovernanceEvent:
    def test_creation_with_defaults(self) -> None:
        event = GovernanceEvent(
            event_type="validation_allow",
            action="read data",
            decision="allow",
            timestamp_ns=123456,
        )
        assert event.event_type == "validation_allow"
        assert event.action == "read data"
        assert event.decision == "allow"
        assert event.timestamp_ns == 123456
        assert event.rule_ids == ()
        assert event.severity == ""
        assert event.workflow_action == ""
        assert event.context_risk_score == 0.0
        assert event.agent_id == ""
        assert event.metadata == {}

    def test_creation_with_all_fields(self) -> None:
        event = GovernanceEvent(
            event_type="validation_deny",
            action="delete records",
            decision="deny",
            timestamp_ns=999,
            rule_ids=("ACGS-001", "ACGS-002"),
            severity="critical",
            workflow_action="block",
            context_risk_score=0.95,
            agent_id="agent-42",
            metadata={"reason": "policy violation"},
        )
        assert event.rule_ids == ("ACGS-001", "ACGS-002")
        assert event.severity == "critical"
        assert event.context_risk_score == 0.95
        assert event.metadata == {"reason": "policy violation"}

    def test_frozen_immutability(self) -> None:
        event = GovernanceEvent(
            event_type="validation_allow",
            action="read",
            decision="allow",
            timestamp_ns=1,
        )
        with pytest.raises(AttributeError):
            event.action = "write"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        event = GovernanceEvent(
            event_type="validation_deny",
            action="drop table",
            decision="deny",
            timestamp_ns=42,
            rule_ids=("R1",),
            severity="high",
            workflow_action="block",
            context_risk_score=0.8,
            agent_id="a1",
            metadata={"k": "v"},
        )
        d = event.to_dict()
        assert d["event_type"] == "validation_deny"
        assert d["action"] == "drop table"
        assert d["rule_ids"] == ["R1"]  # tuple -> list
        assert d["timestamp_ns"] == 42
        assert d["severity"] == "high"
        assert d["context_risk_score"] == 0.8
        assert d["metadata"] == {"k": "v"}

    def test_to_dict_rule_ids_is_list(self) -> None:
        """rule_ids should be serialized as a list, not a tuple."""
        event = GovernanceEvent(
            event_type="t", action="a", decision="d", timestamp_ns=0,
            rule_ids=("A", "B"),
        )
        assert isinstance(event.to_dict()["rule_ids"], list)


# ── create_governance_event ──────────────────────────────────────────────────


class TestCreateGovernanceEvent:
    def test_creates_allow_event(self) -> None:
        event = create_governance_event("read data", "allow")
        assert event.event_type == "validation_allow"
        assert event.action == "read data"
        assert event.decision == "allow"
        assert event.timestamp_ns > 0
        assert event.rule_ids == ()
        assert event.metadata == {}

    def test_creates_deny_event_with_rule_ids(self) -> None:
        event = create_governance_event(
            "delete all",
            "deny",
            rule_ids=["ACGS-001", "ACGS-002"],
            severity="critical",
            agent_id="agent-1",
        )
        assert event.event_type == "validation_deny"
        assert event.rule_ids == ("ACGS-001", "ACGS-002")
        assert event.severity == "critical"
        assert event.agent_id == "agent-1"

    def test_creates_escalate_event(self) -> None:
        event = create_governance_event("ambiguous action", "escalate")
        assert event.event_type == "validation_escalate"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        event = create_governance_event("a", "allow", metadata=None)
        assert event.metadata == {}

    def test_metadata_passed_through(self) -> None:
        event = create_governance_event("a", "allow", metadata={"key": "val"})
        assert event.metadata == {"key": "val"}

    def test_timestamp_is_monotonic(self) -> None:
        e1 = create_governance_event("a", "allow")
        e2 = create_governance_event("b", "allow")
        assert e2.timestamp_ns >= e1.timestamp_ns

    def test_workflow_action_and_risk_score(self) -> None:
        event = create_governance_event(
            "a", "deny",
            workflow_action="require_human_review",
            context_risk_score=0.75,
        )
        assert event.workflow_action == "require_human_review"
        assert event.context_risk_score == 0.75


# ── GovernanceMetrics ────────────────────────────────────────────────────────


class TestGovernanceMetrics:
    def test_initial_state(self) -> None:
        m = GovernanceMetrics()
        snap = m.snapshot()
        assert snap["total_decisions"] == 0
        assert snap["by_decision"] == {"allow": 0, "deny": 0, "escalate": 0}
        assert snap["rule_hit_counts"] == {}
        assert snap["latency"] == {}
        assert snap["rates"] == {}

    def test_record_allow(self) -> None:
        m = GovernanceMetrics()
        m.record("allow", latency_us=3.2)
        snap = m.snapshot()
        assert snap["total_decisions"] == 1
        assert snap["by_decision"]["allow"] == 1
        assert snap["rates"]["allow_rate"] == 1.0

    def test_record_deny_with_rules(self) -> None:
        m = GovernanceMetrics()
        m.record("deny", latency_us=5.0, rule_ids=["R1", "R2"])
        snap = m.snapshot()
        assert snap["by_decision"]["deny"] == 1
        assert snap["rule_hit_counts"]["R1"] == 1
        assert snap["rule_hit_counts"]["R2"] == 1

    def test_latency_stats(self) -> None:
        m = GovernanceMetrics()
        for lat in [1.0, 2.0, 3.0, 4.0, 5.0]:
            m.record("allow", latency_us=lat)
        snap = m.snapshot()
        assert snap["latency"]["p50_us"] == 3.0
        assert snap["latency"]["mean_us"] == 3.0
        assert snap["latency"]["count"] == 5.0

    def test_zero_latency_not_recorded(self) -> None:
        m = GovernanceMetrics()
        m.record("allow", latency_us=0.0)
        assert m.snapshot()["latency"] == {}

    def test_rates_computation(self) -> None:
        m = GovernanceMetrics()
        m.record("allow")
        m.record("allow")
        m.record("deny")
        m.record("escalate")
        snap = m.snapshot()
        assert snap["rates"]["allow_rate"] == 0.5
        assert snap["rates"]["deny_rate"] == 0.25
        assert snap["rates"]["escalate_rate"] == 0.25

    def test_rule_hit_counts_sorted_desc(self) -> None:
        m = GovernanceMetrics()
        m.record("deny", rule_ids=["R1"])
        m.record("deny", rule_ids=["R2"])
        m.record("deny", rule_ids=["R2"])
        snap = m.snapshot()
        keys = list(snap["rule_hit_counts"].keys())
        assert keys == ["R2", "R1"]

    def test_reset(self) -> None:
        m = GovernanceMetrics()
        m.record("allow", latency_us=1.0)
        m.record("deny", rule_ids=["R1"])
        m.reset()
        snap = m.snapshot()
        assert snap["total_decisions"] == 0
        assert snap["rule_hit_counts"] == {}
        assert snap["latency"] == {}

    def test_unknown_decision_type(self) -> None:
        m = GovernanceMetrics()
        m.record("custom_decision")
        snap = m.snapshot()
        assert snap["by_decision"]["custom_decision"] == 1
        assert snap["total_decisions"] == 1

    def test_merge(self) -> None:
        a = GovernanceMetrics()
        a.record("allow", latency_us=1.0)
        a.record("deny", rule_ids=["R1"])

        b = GovernanceMetrics()
        b.record("allow", latency_us=2.0)
        b.record("escalate", rule_ids=["R1"])

        merged = a.merge(b)
        snap = merged.snapshot()
        assert snap["total_decisions"] == 4
        assert snap["by_decision"]["allow"] == 2
        assert snap["by_decision"]["deny"] == 1
        assert snap["by_decision"]["escalate"] == 1
        assert snap["rule_hit_counts"]["R1"] == 2
        assert snap["latency"]["count"] == 2.0

    def test_merge_does_not_mutate_originals(self) -> None:
        a = GovernanceMetrics()
        a.record("allow")
        b = GovernanceMetrics()
        b.record("deny")
        merged = a.merge(b)
        assert a.snapshot()["total_decisions"] == 1
        assert b.snapshot()["total_decisions"] == 1
        assert merged.snapshot()["total_decisions"] == 2

    def test_from_snapshot_roundtrip(self) -> None:
        m = GovernanceMetrics()
        m.record("allow", latency_us=3.0)
        m.record("deny", latency_us=5.0, rule_ids=["R1"])
        snap = m.snapshot()
        restored = GovernanceMetrics.from_snapshot(snap)
        r_snap = restored.snapshot()
        assert r_snap["total_decisions"] == snap["total_decisions"]
        assert r_snap["by_decision"] == snap["by_decision"]
        assert r_snap["rule_hit_counts"] == snap["rule_hit_counts"]

    def test_from_snapshot_empty(self) -> None:
        restored = GovernanceMetrics.from_snapshot({})
        assert restored.snapshot()["total_decisions"] == 0

    def test_from_snapshot_no_latency(self) -> None:
        restored = GovernanceMetrics.from_snapshot({"total_decisions": 5, "by_decision": {"allow": 5}})
        assert restored.snapshot()["total_decisions"] == 5


# ── GovernanceSession ────────────────────────────────────────────────────────


class TestGovernanceSession:
    def test_initial_analyze_empty(self) -> None:
        s = GovernanceSession("agent-1")
        report = s.analyze()
        assert report["agent_id"] == "agent-1"
        assert report["total_decisions"] == 0
        assert report["deny_rate"] == 0.0
        assert report["anomalies"] == []
        assert report["recent_denials"] == []

    def test_record_and_analyze(self) -> None:
        s = GovernanceSession("agent-1")
        s.record("allow", action="read data")
        s.record("deny", action="delete all", rule_ids=["R1"], severity="high")
        report = s.analyze()
        assert report["total_decisions"] == 2
        assert report["by_decision"]["allow"] == 1
        assert report["by_decision"]["deny"] == 1
        assert report["deny_rate"] == 0.5

    def test_max_history_eviction(self) -> None:
        s = GovernanceSession("a", max_history=5)
        for i in range(10):
            s.record("allow", action=f"action-{i}")
        report = s.analyze()
        assert report["total_decisions"] == 5

    def test_deny_rate_anomaly(self) -> None:
        s = GovernanceSession("a", deny_threshold=0.3)
        for _ in range(3):
            s.record("allow")
        for _ in range(7):
            s.record("deny", rule_ids=["R1"])
        report = s.analyze()
        assert report["deny_rate"] == 0.7
        assert any("High deny rate" in a for a in report["anomalies"])

    def test_consecutive_denials_anomaly(self) -> None:
        s = GovernanceSession("a", deny_threshold=1.0)  # high threshold so only consecutive triggers
        # Need >= 10 total decisions and last 5 all denials
        for _ in range(10):
            s.record("allow")
        for _ in range(5):
            s.record("deny", rule_ids=["R1"])
        report = s.analyze()
        assert any("consecutive denials" in a for a in report["anomalies"])

    def test_escalation_spike_anomaly(self) -> None:
        s = GovernanceSession("a", deny_threshold=1.0)
        for _ in range(6):
            s.record("escalate")
        for _ in range(4):
            s.record("allow")
        report = s.analyze()
        assert any("Escalation spike" in a for a in report["anomalies"])

    def test_top_triggered_rules(self) -> None:
        s = GovernanceSession("a")
        for _ in range(5):
            s.record("deny", rule_ids=["R1", "R2"])
        for _ in range(3):
            s.record("deny", rule_ids=["R3"])
        report = s.analyze()
        top = report["top_triggered_rules"]
        assert len(top) > 0
        assert top[0]["rule_id"] == "R1"  # or R2, both have 5 hits

    def test_recent_denials_limited_to_5(self) -> None:
        s = GovernanceSession("a")
        for i in range(10):
            s.record("deny", action=f"bad-{i}", rule_ids=["R1"])
        report = s.analyze()
        assert len(report["recent_denials"]) == 5

    def test_no_anomalies_when_all_allow(self) -> None:
        s = GovernanceSession("a")
        for _ in range(20):
            s.record("allow", action="good")
        report = s.analyze()
        assert report["anomalies"] == []
        assert report["deny_rate"] == 0.0


# ── RuleEffectiveness ────────────────────────────────────────────────────────


class TestRuleEffectiveness:
    def test_empty_report(self) -> None:
        t = RuleEffectiveness()
        report = t.report()
        assert report["rules"] == []
        assert report["silent_rules"] == []
        assert report["noisy_rules"] == []
        assert report["effective_rules"] == []

    def test_effective_rule(self) -> None:
        t = RuleEffectiveness()
        for _ in range(10):
            t.record_fire("R1", overridden=False)
        report = t.report(total_validations=100)
        assert len(report["rules"]) == 1
        r = report["rules"][0]
        assert r["rule_id"] == "R1"
        assert r["fires"] == 10
        assert r["overrides"] == 0
        assert r["override_rate"] == 0.0
        assert r["fire_rate"] == 0.1
        assert "R1" in report["effective_rules"]
        assert report["noisy_rules"] == []

    def test_noisy_rule(self) -> None:
        t = RuleEffectiveness()
        for _ in range(10):
            t.record_fire("R1", overridden=True)
        for _ in range(5):
            t.record_fire("R1", overridden=False)
        report = t.report()
        r = report["rules"][0]
        assert r["overrides"] == 10
        assert r["override_rate"] == pytest.approx(10 / 15)
        assert "R1" in report["noisy_rules"]
        assert len(report["tuning_recommendations"]) > 0

    def test_fire_rate_omitted_when_total_zero(self) -> None:
        t = RuleEffectiveness()
        t.record_fire("R1")
        report = t.report(total_validations=0)
        assert "fire_rate" not in report["rules"][0]

    def test_sorted_by_fire_count(self) -> None:
        t = RuleEffectiveness()
        t.record_fire("R1")
        for _ in range(5):
            t.record_fire("R2")
        report = t.report()
        assert report["rules"][0]["rule_id"] == "R2"
        assert report["rules"][1]["rule_id"] == "R1"

    def test_reset(self) -> None:
        t = RuleEffectiveness()
        t.record_fire("R1")
        t.reset()
        assert t.report()["rules"] == []


# ── AuditEntry ───────────────────────────────────────────────────────────────


class TestAuditEntry:
    def test_creation_and_to_dict(self) -> None:
        entry = AuditEntry(
            timestamp="2026-03-19T10:00:00Z",
            action="read",
            decision="allow",
            rule_ids=("R1",),
            agent_id="a1",
            severity="low",
            workflow_action="log",
        )
        d = entry.to_dict()
        assert d["timestamp"] == "2026-03-19T10:00:00Z"
        assert d["rule_ids"] == ["R1"]
        assert d["agent_id"] == "a1"

    def test_frozen(self) -> None:
        entry = AuditEntry(timestamp="t", action="a", decision="d")
        with pytest.raises(AttributeError):
            entry.action = "x"  # type: ignore[misc]


# ── AuditLedger ──────────────────────────────────────────────────────────────


class TestAuditLedger:
    def test_record_and_len(self) -> None:
        ledger = AuditLedger()
        ledger.record("read", "allow", agent_id="a1")
        ledger.record("write", "deny", rule_ids=["R1"])
        assert len(ledger) == 2

    def test_record_returns_entry(self) -> None:
        ledger = AuditLedger()
        entry = ledger.record("act", "allow")
        assert isinstance(entry, AuditEntry)
        assert entry.action == "act"
        assert entry.decision == "allow"

    def test_record_auto_timestamp(self) -> None:
        ledger = AuditLedger()
        entry = ledger.record("a", "allow")
        assert entry.timestamp  # non-empty ISO string

    def test_record_custom_timestamp(self) -> None:
        ledger = AuditLedger()
        entry = ledger.record("a", "allow", timestamp="2026-01-01T00:00:00Z")
        assert entry.timestamp == "2026-01-01T00:00:00Z"

    def test_max_entries_eviction(self) -> None:
        ledger = AuditLedger(max_entries=5)
        for i in range(10):
            ledger.record(f"action-{i}", "allow")
        assert len(ledger) == 5

    def test_query_by_decision(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow")
        ledger.record("b", "deny", rule_ids=["R1"])
        ledger.record("c", "allow")
        results = ledger.query(decision="deny")
        assert len(results) == 1
        assert results[0].action == "b"

    def test_query_by_agent_id(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow", agent_id="a1")
        ledger.record("b", "allow", agent_id="a2")
        results = ledger.query(agent_id="a1")
        assert len(results) == 1

    def test_query_by_rule_id(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "deny", rule_ids=["R1", "R2"])
        ledger.record("b", "deny", rule_ids=["R3"])
        results = ledger.query(rule_id="R1")
        assert len(results) == 1
        assert results[0].action == "a"

    def test_query_by_time_range(self) -> None:
        ledger = AuditLedger()
        ledger.record("old", "allow", timestamp="2026-01-01T00:00:00Z")
        ledger.record("mid", "allow", timestamp="2026-06-01T00:00:00Z")
        ledger.record("new", "allow", timestamp="2026-12-01T00:00:00Z")
        results = ledger.query(since="2026-05-01T00:00:00Z", until="2026-07-01T00:00:00Z")
        assert len(results) == 1
        assert results[0].action == "mid"

    def test_query_no_filters_returns_all(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow")
        ledger.record("b", "deny")
        assert len(ledger.query()) == 2

    def test_summary_empty(self) -> None:
        ledger = AuditLedger()
        s = ledger.summary()
        assert s["total"] == 0
        assert s["time_range"] is None

    def test_summary_with_entries(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow", agent_id="a1", timestamp="2026-01-01T00:00:00Z")
        ledger.record("b", "deny", agent_id="a2", rule_ids=["R1"], timestamp="2026-01-02T00:00:00Z")
        s = ledger.summary()
        assert s["total"] == 2
        assert s["by_decision"]["allow"] == 1
        assert s["by_decision"]["deny"] == 1
        assert sorted(s["agents"]) == ["a1", "a2"]
        assert s["time_range"]["earliest"] == "2026-01-01T00:00:00Z"
        assert s["time_range"]["latest"] == "2026-01-02T00:00:00Z"
        assert len(s["top_rules"]) == 1

    def test_export(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow", timestamp="2026-01-01T00:00:00Z")
        exported = ledger.export()
        assert len(exported) == 1
        assert exported[0]["action"] == "a"
        assert isinstance(exported[0], dict)

    def test_clear(self) -> None:
        ledger = AuditLedger()
        ledger.record("a", "allow")
        ledger.clear()
        assert len(ledger) == 0


# ── GovernanceSLO ────────────────────────────────────────────────────────────


class TestGovernanceSLO:
    def _make_metrics(
        self,
        allow: int = 0,
        deny: int = 0,
        escalate: int = 0,
        latency_us: float = 0.0,
    ) -> GovernanceMetrics:
        m = GovernanceMetrics()
        for _ in range(allow):
            m.record("allow", latency_us=latency_us)
        for _ in range(deny):
            m.record("deny", latency_us=latency_us)
        for _ in range(escalate):
            m.record("escalate", latency_us=latency_us)
        return m

    def test_healthy_status(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=10.0, compliance_rate=0.90, max_deny_rate=0.10)
        metrics = self._make_metrics(allow=95, deny=5, latency_us=5.0)
        assert slo.status(metrics) == "healthy"

    def test_breached_latency(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=5.0)
        metrics = self._make_metrics(allow=100, latency_us=10.0)
        report = slo.evaluate(metrics)
        assert report["breached"] is True
        assert any(a["alert_type"] == "p99_latency_breach" for a in report["alerts"])
        assert slo.status(metrics) == "breached"

    def test_degraded_compliance(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=100.0, compliance_rate=0.90, max_deny_rate=0.50)
        metrics = self._make_metrics(allow=80, deny=20, latency_us=1.0)
        status = slo.status(metrics)
        assert status == "degraded"

    def test_deny_rate_breach(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=100.0, max_deny_rate=0.05)
        metrics = self._make_metrics(allow=80, deny=20, latency_us=1.0)
        report = slo.evaluate(metrics)
        assert any(a["alert_type"] == "deny_rate_breach" for a in report["alerts"])

    def test_no_decisions_is_healthy(self) -> None:
        slo = GovernanceSLO("test")
        metrics = GovernanceMetrics()
        assert slo.status(metrics) == "healthy"

    def test_evaluate_report_structure(self) -> None:
        slo = GovernanceSLO("prod")
        metrics = self._make_metrics(allow=10, latency_us=1.0)
        report = slo.evaluate(metrics)
        assert report["slo_name"] == "prod"
        assert "evaluated_at" in report
        assert "total_decisions" in report
        assert "objectives" in report
        assert len(report["objectives"]) == 3

    def test_breach_history(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=1.0)
        metrics = self._make_metrics(allow=10, latency_us=5.0)
        slo.evaluate(metrics)
        slo.evaluate(metrics)
        history = slo.breach_history()
        assert len(history) == 2

    def test_clear_history(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=1.0)
        metrics = self._make_metrics(allow=10, latency_us=5.0)
        slo.evaluate(metrics)
        slo.clear_history()
        assert slo.breach_history() == []

    def test_summary(self) -> None:
        slo = GovernanceSLO("test", p99_latency_us=100.0)
        metrics = self._make_metrics(allow=10, latency_us=1.0)
        s = slo.summary(metrics)
        assert s["slo_name"] == "test"
        assert s["status"] == "healthy"
        assert "objectives" in s
        assert "breach_count" in s

    def test_repr(self) -> None:
        slo = GovernanceSLO("my-slo", p99_latency_us=10.0, compliance_rate=0.95, max_deny_rate=0.05)
        r = repr(slo)
        assert "my-slo" in r
        assert "10.0" in r


# ── GovernanceCostModel ──────────────────────────────────────────────────────


class TestGovernanceCostModel:
    def test_default_costs(self) -> None:
        model = GovernanceCostModel()
        assert model.cost_per_allow == 0.0
        assert model.cost_per_deny == 0.0
        assert model.cost_per_escalate == 5.0
        assert model.cost_per_human_review == 30.0

    def test_record_allow_zero_cost(self) -> None:
        model = GovernanceCostModel()
        cost = model.record("allow")
        assert cost == 0.0
        assert model.total_cost() == 0.0

    def test_record_escalate_cost(self) -> None:
        model = GovernanceCostModel(cost_per_escalate=10.0)
        cost = model.record("escalate", rule_id="R1", agent_id="a1")
        assert cost == 10.0
        assert model.total_cost() == 10.0

    def test_record_human_review_via_workflow_action(self) -> None:
        model = GovernanceCostModel(cost_per_deny=1.0, cost_per_human_review=50.0)
        cost = model.record("deny", workflow_action="require_human_review")
        assert cost == 50.0  # workflow_action overrides decision

    def test_unknown_decision_zero_cost(self) -> None:
        model = GovernanceCostModel()
        cost = model.record("unknown_type")
        assert cost == 0.0

    def test_attribution_report(self) -> None:
        model = GovernanceCostModel(cost_per_escalate=5.0)
        model.record("allow", agent_id="a1")
        model.record("escalate", rule_id="R1", agent_id="a1")
        model.record("escalate", rule_id="R2", agent_id="a2")
        report = model.attribution_report()
        assert report["total_cost"] == 10.0
        assert report["event_count"] == 3
        assert len(report["by_decision"]) == 2
        assert len(report["by_rule"]) == 2
        assert len(report["by_agent"]) == 2
        assert report["cost_model"]["escalate"] == 5.0

    def test_top_cost_rules(self) -> None:
        model = GovernanceCostModel(cost_per_escalate=5.0)
        for _ in range(3):
            model.record("escalate", rule_id="R1")
        model.record("escalate", rule_id="R2")
        top = model.top_cost_rules(n=2)
        assert top[0]["rule_id"] == "R1"
        assert top[0]["cost"] == 15.0

    def test_top_cost_agents(self) -> None:
        model = GovernanceCostModel(cost_per_escalate=5.0)
        for _ in range(3):
            model.record("escalate", agent_id="a1")
        model.record("escalate", agent_id="a2")
        top = model.top_cost_agents(n=1)
        assert len(top) == 1
        assert top[0]["agent_id"] == "a1"

    def test_reset(self) -> None:
        model = GovernanceCostModel()
        model.record("escalate", rule_id="R1", agent_id="a1")
        model.reset()
        assert model.total_cost() == 0.0
        assert model.event_log() == []
        assert model.attribution_report()["event_count"] == 0

    def test_event_log(self) -> None:
        model = GovernanceCostModel()
        model.record("deny", rule_id="R1", metadata={"extra": "info"})
        log = model.event_log()
        assert len(log) == 1
        assert log[0]["decision"] == "deny"
        assert log[0]["extra"] == "info"

    def test_repr(self) -> None:
        model = GovernanceCostModel()
        model.record("escalate")
        r = repr(model)
        assert "5.00" in r
        assert "events=1" in r


# ── GovernanceForecaster ─────────────────────────────────────────────────────


class TestGovernanceForecaster:
    def test_empty_forecast(self) -> None:
        f = GovernanceForecaster()
        result = f.forecast(steps=3)
        assert result["steps"] == 3
        assert result["history_windows"] == 0
        assert len(result["forecast"]["deny_rate"]) == 3

    def test_record_window_returns_rates(self) -> None:
        f = GovernanceForecaster()
        rates = f.record_window("w1", allow=80, deny=15, escalate=5)
        assert rates["deny_rate"] == pytest.approx(0.15)
        assert rates["escalate_rate"] == pytest.approx(0.05)
        assert rates["compliance_rate"] == pytest.approx(0.80)

    def test_record_window_zero_total(self) -> None:
        f = GovernanceForecaster()
        rates = f.record_window("empty", allow=0, deny=0, escalate=0)
        assert rates["deny_rate"] == 0.0
        assert rates["compliance_rate"] == 1.0

    def test_max_windows_eviction(self) -> None:
        f = GovernanceForecaster(max_windows=5)
        for i in range(10):
            f.record_window(f"w{i}", allow=10, deny=0, escalate=0)
        assert f.summary()["windows_recorded"] == 5

    def test_linear_trend_stable(self) -> None:
        slope, intercept = GovernanceForecaster._linear_trend([0.5, 0.5, 0.5])
        assert slope == pytest.approx(0.0)
        assert intercept == pytest.approx(0.5)

    def test_linear_trend_increasing(self) -> None:
        slope, intercept = GovernanceForecaster._linear_trend([0.1, 0.2, 0.3])
        assert slope == pytest.approx(0.1)
        assert intercept == pytest.approx(0.1)

    def test_linear_trend_single_value(self) -> None:
        slope, intercept = GovernanceForecaster._linear_trend([0.5])
        assert slope == 0.0
        assert intercept == 0.5

    def test_linear_trend_empty(self) -> None:
        slope, intercept = GovernanceForecaster._linear_trend([])
        assert slope == 0.0
        assert intercept == 0.0

    def test_forecast_increasing_deny(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=90, deny=10, escalate=0)
        f.record_window("w2", allow=80, deny=20, escalate=0)
        f.record_window("w3", allow=70, deny=30, escalate=0)
        result = f.forecast(steps=3)
        assert result["trend"]["deny_rate"] == "increasing"
        assert result["trend"]["compliance_rate"] == "decreasing"
        # Projected deny rates should be higher than last observed
        assert result["forecast"]["deny_rate"][0] >= 0.3

    def test_forecast_alerts_deny_threshold(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=80, deny=20, escalate=0)
        f.record_window("w2", allow=70, deny=30, escalate=0)
        f.record_window("w3", allow=60, deny=40, escalate=0)
        result = f.forecast(steps=3)
        deny_alerts = [a for a in result["alerts"] if a["type"] == "deny_rate_rising"]
        assert len(deny_alerts) >= 1

    def test_forecast_clamps_to_0_1(self) -> None:
        f = GovernanceForecaster()
        # Extreme trend that would extrapolate beyond [0,1]
        f.record_window("w1", allow=0, deny=100, escalate=0)
        f.record_window("w2", allow=0, deny=100, escalate=0)
        result = f.forecast(steps=10)
        for v in result["forecast"]["deny_rate"]:
            assert 0.0 <= v <= 1.0
        for v in result["forecast"]["compliance_rate"]:
            assert 0.0 <= v <= 1.0

    def test_forecast_steps_clamped(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=50, deny=50, escalate=0)
        result_min = f.forecast(steps=0)
        assert result_min["steps"] == 1  # clamped to minimum 1
        result_max = f.forecast(steps=100)
        assert result_max["steps"] == 50  # clamped to maximum 50

    def test_summary_empty(self) -> None:
        f = GovernanceForecaster()
        s = f.summary()
        assert s["windows_recorded"] == 0
        assert s["latest"] == {}
        assert s["average"] == {}

    def test_summary_with_data(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=80, deny=10, escalate=10)
        f.record_window("w2", allow=60, deny=30, escalate=10)
        s = f.summary()
        assert s["windows_recorded"] == 2
        assert "deny_rate" in s["latest"]
        assert "deny_rate" in s["average"]

    def test_history(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=10, deny=0, escalate=0)
        h = f.history()
        assert len(h) == 1
        assert h[0]["label"] == "w1"

    def test_repr(self) -> None:
        f = GovernanceForecaster(max_windows=50)
        assert "max_windows=50" in repr(f)

    def test_metadata_stored_in_window(self) -> None:
        f = GovernanceForecaster()
        f.record_window("w1", allow=10, deny=0, escalate=0, metadata={"env": "prod"})
        h = f.history()
        assert h[0]["env"] == "prod"
