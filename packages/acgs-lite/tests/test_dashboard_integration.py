"""Tests for the governance dashboard integration module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.engine.core import ValidationResult, Violation
from acgs_lite.integrations.dashboard import (
    _CONSTITUTIONAL_HASH,
    DashboardMetrics,
    GovernanceDashboard,
    ViolationTimeline,
    create_dashboard_asgi_app,
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def constitution():
    return Constitution.default()


@pytest.fixture()
def audit_log():
    return AuditLog()


@pytest.fixture()
def engine(constitution, audit_log):
    return GovernanceEngine(
        constitution,
        audit_log=audit_log,
        strict=False,
    )


@pytest.fixture()
def dashboard(engine, audit_log, constitution):
    return GovernanceDashboard(engine, audit_log, constitution)


def _make_violation(
    rule_id: str = "R1",
    text: str = "test rule",
    severity: Severity = Severity.MEDIUM,
    content: str = "bad content",
    category: str = "safety",
) -> Violation:
    return Violation(
        rule_id=rule_id,
        rule_text=text,
        severity=severity,
        matched_content=content,
        category=category,
    )


# ── DashboardMetrics ──────────────────────────────────────────────────


class TestDashboardMetrics:
    def test_creation(self):
        ts = datetime.now(timezone.utc).isoformat()
        m = DashboardMetrics(
            timestamp=ts,
            engine_stats={"total_validations": 5},
            audit_chain_valid=True,
            total_rules=10,
            rules_by_severity={"high": 3, "medium": 7},
            rules_by_category={"safety": 6, "privacy": 4},
            compliance_score=0.95,
            recent_violations=[],
            constitutional_hash=_CONSTITUTIONAL_HASH,
        )
        assert m.timestamp == ts
        assert m.total_rules == 10
        assert m.compliance_score == 0.95

    def test_to_dict_keys(self):
        m = DashboardMetrics(
            timestamp="2026-01-01T00:00:00Z",
            engine_stats={},
            audit_chain_valid=True,
            total_rules=0,
            rules_by_severity={},
            rules_by_category={},
            compliance_score=1.0,
            recent_violations=[],
            constitutional_hash=_CONSTITUTIONAL_HASH,
        )
        d = m.to_dict()
        expected_keys = {
            "timestamp",
            "engine_stats",
            "audit_chain_valid",
            "total_rules",
            "rules_by_severity",
            "rules_by_category",
            "compliance_score",
            "recent_violations",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_serializable(self):
        m = DashboardMetrics(
            timestamp="2026-01-01T00:00:00Z",
            engine_stats={"count": 42},
            audit_chain_valid=False,
            total_rules=3,
            rules_by_severity={"critical": 1},
            rules_by_category={"safety": 2},
            compliance_score=0.8,
            recent_violations=[{"rule_id": "R1"}],
            constitutional_hash=_CONSTITUTIONAL_HASH,
        )
        serialized = json.dumps(m.to_dict())
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["total_rules"] == 3

    def test_compliance_score_bounds(self):
        m = DashboardMetrics(
            timestamp="t",
            engine_stats={},
            audit_chain_valid=True,
            total_rules=0,
            rules_by_severity={},
            rules_by_category={},
            compliance_score=0.0,
            recent_violations=[],
            constitutional_hash="",
        )
        assert m.compliance_score == 0.0
        m2 = DashboardMetrics(
            timestamp="t",
            engine_stats={},
            audit_chain_valid=True,
            total_rules=0,
            rules_by_severity={},
            rules_by_category={},
            compliance_score=1.0,
            recent_violations=[],
            constitutional_hash="",
        )
        assert m2.compliance_score == 1.0

    def test_to_dict_preserves_violations(self):
        violations = [
            {"rule_id": "R1", "severity": "high"},
            {"rule_id": "R2", "severity": "medium"},
        ]
        m = DashboardMetrics(
            timestamp="t",
            engine_stats={},
            audit_chain_valid=True,
            total_rules=0,
            rules_by_severity={},
            rules_by_category={},
            compliance_score=1.0,
            recent_violations=violations,
            constitutional_hash="",
        )
        d = m.to_dict()
        assert len(d["recent_violations"]) == 2
        assert d["recent_violations"][0]["rule_id"] == "R1"


# ── ViolationTimeline ─────────────────────────────────────────────────


class TestViolationTimeline:
    def test_empty_timeline(self):
        tl = ViolationTimeline()
        assert tl.get_timeline() == []
        assert tl.summary()["total"] == 0

    def test_record_single(self):
        tl = ViolationTimeline()
        v = _make_violation()
        tl.record(v, "agent-1")
        entries = tl.get_timeline()
        assert len(entries) == 1
        assert entries[0]["rule_id"] == "R1"
        assert entries[0]["agent_id"] == "agent-1"

    def test_record_with_timestamp(self):
        tl = ViolationTimeline()
        v = _make_violation()
        tl.record(v, "a1", timestamp="2026-01-01T00:00:00Z")
        assert tl.get_timeline()[0]["timestamp"] == "2026-01-01T00:00:00Z"

    def test_record_auto_timestamp(self):
        tl = ViolationTimeline()
        v = _make_violation()
        tl.record(v, "a1")
        ts = tl.get_timeline()[0]["timestamp"]
        assert ts  # non-empty
        # Should be parseable as ISO
        datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def test_record_from_result(self):
        tl = ViolationTimeline()
        result = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[
                _make_violation("R1"),
                _make_violation("R2", severity=Severity.HIGH),
            ],
            agent_id="bot-7",
            timestamp="2026-03-01T12:00:00Z",
        )
        tl.record_from_result(result)
        assert len(tl.get_timeline()) == 2
        assert tl.get_timeline()[0]["agent_id"] == "bot-7"

    def test_get_timeline_last_n(self):
        tl = ViolationTimeline()
        for i in range(10):
            tl.record(
                _make_violation(f"R{i}"),
                "a1",
                timestamp=f"2026-01-01T{i:02d}:00:00Z",
            )
        last3 = tl.get_timeline(last_n=3)
        assert len(last3) == 3
        assert last3[0]["rule_id"] == "R7"

    def test_get_by_severity(self):
        tl = ViolationTimeline()
        tl.record(_make_violation(severity=Severity.HIGH), "a1")
        tl.record(_make_violation(severity=Severity.LOW), "a1")
        tl.record(_make_violation(severity=Severity.HIGH), "a2")
        highs = tl.get_by_severity("high")
        assert len(highs) == 2
        lows = tl.get_by_severity("low")
        assert len(lows) == 1

    def test_get_by_agent(self):
        tl = ViolationTimeline()
        tl.record(_make_violation(), "agent-a")
        tl.record(_make_violation(), "agent-b")
        tl.record(_make_violation(), "agent-a")
        assert len(tl.get_by_agent("agent-a")) == 2
        assert len(tl.get_by_agent("agent-b")) == 1
        assert len(tl.get_by_agent("agent-c")) == 0

    def test_summary_by_severity(self):
        tl = ViolationTimeline()
        tl.record(_make_violation(severity=Severity.HIGH), "a")
        tl.record(_make_violation(severity=Severity.HIGH), "a")
        tl.record(_make_violation(severity=Severity.LOW), "a")
        s = tl.summary()
        assert s["total"] == 3
        assert s["by_severity"]["high"] == 2
        assert s["by_severity"]["low"] == 1

    def test_summary_by_hour(self):
        tl = ViolationTimeline()
        tl.record(
            _make_violation(),
            "a",
            timestamp="2026-01-01T10:00:00Z",
        )
        tl.record(
            _make_violation(),
            "a",
            timestamp="2026-01-01T10:30:00Z",
        )
        tl.record(
            _make_violation(),
            "a",
            timestamp="2026-01-01T11:00:00Z",
        )
        s = tl.summary()
        assert s["by_hour"]["2026-01-01T10"] == 2
        assert s["by_hour"]["2026-01-01T11"] == 1

    def test_max_entries_eviction(self):
        tl = ViolationTimeline(max_entries=5)
        for i in range(10):
            tl.record(_make_violation(f"R{i}"), "a")
        entries = tl.get_timeline()
        assert len(entries) == 5
        assert entries[0]["rule_id"] == "R5"

    def test_record_preserves_category(self):
        tl = ViolationTimeline()
        v = _make_violation(category="privacy")
        tl.record(v, "a")
        assert tl.get_timeline()[0]["category"] == "privacy"


# ── GovernanceDashboard ───────────────────────────────────────────────


class TestGovernanceDashboard:
    def test_get_metrics_returns_dashboard_metrics(self, dashboard):
        m = dashboard.get_metrics()
        assert isinstance(m, DashboardMetrics)
        assert m.total_rules > 0
        assert m.constitutional_hash

    def test_get_metrics_rules_by_severity(self, dashboard):
        m = dashboard.get_metrics()
        assert isinstance(m.rules_by_severity, dict)
        assert sum(m.rules_by_severity.values()) == m.total_rules

    def test_get_metrics_rules_by_category(self, dashboard):
        m = dashboard.get_metrics()
        assert isinstance(m.rules_by_category, dict)
        assert sum(m.rules_by_category.values()) == m.total_rules

    def test_get_metrics_audit_chain_valid(self, dashboard):
        m = dashboard.get_metrics()
        assert m.audit_chain_valid is True

    def test_get_metrics_compliance_score(self, dashboard):
        m = dashboard.get_metrics()
        assert 0.0 <= m.compliance_score <= 1.0

    def test_get_timeline_returns_timeline(self, dashboard):
        tl = dashboard.get_timeline()
        assert isinstance(tl, ViolationTimeline)

    def test_validate_and_record_clean(self, dashboard):
        result = dashboard.validate_and_record(
            "analyze the data",
            "agent-1",
        )
        assert isinstance(result, ValidationResult)
        assert dashboard.get_timeline().get_timeline() == []

    def test_validate_and_record_violation(self, dashboard):
        # "delete all user data" should trigger violations
        result = dashboard.validate_and_record(
            "delete all user data without consent",
            "agent-bad",
        )
        # In non-strict mode we get violations in the result
        if result.violations:
            tl = dashboard.get_timeline().get_timeline()
            assert len(tl) > 0

    def test_get_rule_coverage(self, dashboard):
        cov = dashboard.get_rule_coverage()
        assert "total_rules" in cov
        assert "categories" in cov
        assert "severities" in cov
        assert "tags" in cov
        assert cov["total_rules"] > 0
        assert isinstance(cov["categories"], list)
        assert cov["category_count"] == len(cov["categories"])

    def test_get_agent_summary_empty(self, dashboard):
        summary = dashboard.get_agent_summary()
        # No validations yet via the real AuditLog
        assert isinstance(summary, dict)

    def test_get_agent_summary_after_validation(
        self,
        engine,
        audit_log,
        constitution,
    ):
        dash = GovernanceDashboard(engine, audit_log, constitution)
        engine.validate("analyze data", agent_id="bot-1")
        engine.validate("process report", agent_id="bot-2")
        summary = dash.get_agent_summary()
        assert "bot-1" in summary
        assert "bot-2" in summary
        assert summary["bot-1"]["total_validations"] >= 1

    def test_health_check(self, dashboard):
        h = dashboard.health_check()
        assert h["status"] == "healthy"
        assert h["audit_chain_valid"] is True
        assert "rules_loaded" in h
        assert "constitutional_hash" in h

    def test_health_check_hash_match(self, dashboard, constitution):
        h = dashboard.health_check()
        assert h["constitutional_hash"] == constitution.hash

    def test_export_snapshot(self, dashboard):
        snap = dashboard.export_snapshot()
        assert "metrics" in snap
        assert "timeline" in snap
        assert "timeline_summary" in snap
        assert "rule_coverage" in snap
        assert "agent_summary" in snap
        assert "health" in snap

    def test_export_snapshot_serializable(self, dashboard):
        snap = dashboard.export_snapshot()
        serialized = json.dumps(snap, default=str)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert "metrics" in parsed

    def test_metrics_engine_stats_keys(self, dashboard):
        m = dashboard.get_metrics()
        assert "total_validations" in m.engine_stats

    def test_timeline_records_via_validate_and_record(self, dashboard):
        # Multiple validations
        for i in range(5):
            dashboard.validate_and_record(
                f"process item {i}",
                f"agent-{i}",
            )
        tl = dashboard.get_timeline()
        # clean actions produce no timeline entries
        assert isinstance(tl.get_timeline(), list)


# ── ASGI App ──────────────────────────────────────────────────────────


class TestASGIApp:
    @pytest.fixture()
    def app(self, dashboard):
        return create_dashboard_asgi_app(dashboard)

    @staticmethod
    def _scope(path: str, method: str = "GET") -> dict:
        return {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
        }

    @staticmethod
    async def _receive():
        return {"type": "http.request", "body": b""}

    async def _call(self, app, path, method="GET"):
        received = []

        async def send(msg):
            received.append(msg)

        scope = self._scope(path, method)
        await app(scope, self._receive, send)
        return received

    @pytest.mark.asyncio
    async def test_html_page(self, app):
        msgs = await self._call(app, "/")
        assert len(msgs) == 2
        assert msgs[0]["type"] == "http.response.start"
        assert msgs[0]["status"] == 200
        headers_dict = dict(msgs[0]["headers"])
        assert b"text/html" in headers_dict[b"content-type"]
        body = msgs[1]["body"]
        assert b"ACGS-Lite" in body
        assert b"<html" in body

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, app):
        msgs = await self._call(app, "/api/metrics")
        assert msgs[0]["status"] == 200
        headers_dict = dict(msgs[0]["headers"])
        assert b"application/json" in headers_dict[b"content-type"]
        data = json.loads(msgs[1]["body"])
        assert "timestamp" in data
        assert "engine_stats" in data
        assert "total_rules" in data

    @pytest.mark.asyncio
    async def test_timeline_endpoint(self, app):
        msgs = await self._call(app, "/api/timeline")
        assert msgs[0]["status"] == 200
        data = json.loads(msgs[1]["body"])
        assert "timeline" in data
        assert "summary" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app):
        msgs = await self._call(app, "/api/health")
        assert msgs[0]["status"] == 200
        data = json.loads(msgs[1]["body"])
        assert "status" in data
        assert data["audit_chain_valid"] is True

    @pytest.mark.asyncio
    async def test_rules_endpoint(self, app):
        msgs = await self._call(app, "/api/rules")
        assert msgs[0]["status"] == 200
        data = json.loads(msgs[1]["body"])
        assert "rules" in data
        assert "total" in data
        assert "coverage" in data
        assert len(data["rules"]) == data["total"]

    @pytest.mark.asyncio
    async def test_rules_entry_fields(self, app):
        msgs = await self._call(app, "/api/rules")
        data = json.loads(msgs[1]["body"])
        if data["rules"]:
            rule = data["rules"][0]
            assert "id" in rule
            assert "text" in rule
            assert "severity" in rule
            assert "category" in rule

    @pytest.mark.asyncio
    async def test_agents_endpoint(self, app):
        msgs = await self._call(app, "/api/agents")
        assert msgs[0]["status"] == 200
        data = json.loads(msgs[1]["body"])
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_not_found(self, app):
        msgs = await self._call(app, "/api/nonexistent")
        assert msgs[0]["status"] == 404
        data = json.loads(msgs[1]["body"])
        assert "error" in data

    @pytest.mark.asyncio
    async def test_method_not_allowed(self, app):
        msgs = await self._call(app, "/api/metrics", method="POST")
        assert msgs[0]["status"] == 405
        data = json.loads(msgs[1]["body"])
        assert "error" in data

    @pytest.mark.asyncio
    async def test_non_http_scope(self, app):
        received = []

        async def send(msg):
            received.append(msg)

        scope = {"type": "websocket", "path": "/"}
        await app(scope, self._receive, send)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_metrics_json_valid(self, app):
        msgs = await self._call(app, "/api/metrics")
        body = msgs[1]["body"]
        data = json.loads(body)
        # Re-serialize to prove round-trip
        reserialized = json.dumps(data)
        assert json.loads(reserialized) == data


# ── Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_constitution(self):
        c = Constitution(rules=[])
        log = AuditLog()
        eng = GovernanceEngine(c, audit_log=log, strict=False)
        dash = GovernanceDashboard(eng, log, c)
        m = dash.get_metrics()
        assert m.total_rules == 0
        assert m.rules_by_severity == {}
        assert m.compliance_score == 1.0

    def test_many_violations_timeline(self):
        tl = ViolationTimeline(max_entries=50)
        for i in range(200):
            tl.record(
                _make_violation(f"R{i}", severity=Severity.MEDIUM),
                f"agent-{i % 5}",
                timestamp=f"2026-01-01T{(i % 24):02d}:00:00Z",
            )
        entries = tl.get_timeline()
        assert len(entries) == 50
        summary = tl.summary()
        assert summary["total"] == 50

    def test_timeline_no_entries_last_n(self):
        tl = ViolationTimeline()
        assert tl.get_timeline(last_n=10) == []

    def test_dashboard_multiple_validate_and_record(
        self,
        engine,
        audit_log,
        constitution,
    ):
        dash = GovernanceDashboard(engine, audit_log, constitution)
        for _ in range(10):
            dash.validate_and_record("read the report", "agent-x")
        snap = dash.export_snapshot()
        assert snap["health"]["total_validations"] >= 10

    def test_health_check_expected_hash(self, dashboard):
        h = dashboard.health_check()
        assert h["expected_hash"] == _CONSTITUTIONAL_HASH

    def test_rule_coverage_has_sorted_lists(self, dashboard):
        cov = dashboard.get_rule_coverage()
        cats = cov["categories"]
        assert cats == sorted(cats)
        sevs = cov["severities"]
        assert sevs == sorted(sevs)
