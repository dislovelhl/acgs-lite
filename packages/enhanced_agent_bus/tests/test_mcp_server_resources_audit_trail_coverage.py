# Constitutional Hash: 608508a9bd224290
# Sprint 57 — mcp_server/resources/audit_trail.py coverage
"""
Comprehensive tests for mcp_server/resources/audit_trail.py.
Targets >=95% coverage of all classes, methods, and branches.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_server.protocol.types import ResourceDefinition
from enhanced_agent_bus.mcp_server.resources.audit_trail import (
    AUDIT_TRAIL_READ_ERRORS,
    AuditEntry,
    AuditEventType,
    AuditTrailResource,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str = "AUDIT-00000001",
    event_type: AuditEventType = AuditEventType.VALIDATION,
    timestamp: str = "2026-01-01T00:00:00+00:00",
    actor_id: str = "agent-001",
    action: str = "validate_policy",
    details: dict | None = None,
    outcome: str = "success",
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> AuditEntry:
    return AuditEntry(
        id=entry_id,
        event_type=event_type,
        timestamp=timestamp,
        actor_id=actor_id,
        action=action,
        details=details or {},
        outcome=outcome,
        constitutional_hash=constitutional_hash,
    )


# ---------------------------------------------------------------------------
# AuditEventType enum
# ---------------------------------------------------------------------------


class TestAuditEventType:
    def test_all_values_exist(self):
        assert AuditEventType.VALIDATION.value == "validation"
        assert AuditEventType.DECISION.value == "decision"
        assert AuditEventType.PRINCIPLE_ACCESS.value == "principle_access"
        assert AuditEventType.PRECEDENT_QUERY.value == "precedent_query"
        assert AuditEventType.ESCALATION.value == "escalation"
        assert AuditEventType.APPEAL.value == "appeal"
        assert AuditEventType.SYSTEM.value == "system"

    def test_enum_count(self):
        assert len(AuditEventType) == 7

    def test_lookup_by_value(self):
        assert AuditEventType("validation") is AuditEventType.VALIDATION
        assert AuditEventType("system") is AuditEventType.SYSTEM


# ---------------------------------------------------------------------------
# AuditEntry dataclass
# ---------------------------------------------------------------------------


class TestAuditEntry:
    def test_to_dict_contains_all_fields(self):
        entry = _make_entry(
            entry_id="AUDIT-00000099",
            event_type=AuditEventType.DECISION,
            timestamp="2026-02-01T12:00:00+00:00",
            actor_id="agent-xyz",
            action="approve_message",
            details={"score": 0.9},
            outcome="approved",
        )
        d = entry.to_dict()
        assert d["id"] == "AUDIT-00000099"
        assert d["event_type"] == "decision"
        assert d["timestamp"] == "2026-02-01T12:00:00+00:00"
        assert d["actor_id"] == "agent-xyz"
        assert d["action"] == "approve_message"
        assert d["details"] == {"score": 0.9}
        assert d["outcome"] == "approved"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_event_type_uses_value(self):
        for event_type in AuditEventType:
            entry = _make_entry(event_type=event_type)
            assert entry.to_dict()["event_type"] == event_type.value

    def test_to_dict_with_empty_details(self):
        entry = _make_entry(details={})
        d = entry.to_dict()
        assert d["details"] == {}

    def test_to_dict_with_nested_details(self):
        entry = _make_entry(details={"nested": {"key": "value"}, "count": 3})
        d = entry.to_dict()
        assert d["details"]["nested"]["key"] == "value"


# ---------------------------------------------------------------------------
# AUDIT_TRAIL_READ_ERRORS tuple
# ---------------------------------------------------------------------------


class TestAuditTrailReadErrors:
    def test_tuple_contains_expected_exceptions(self):
        assert RuntimeError in AUDIT_TRAIL_READ_ERRORS
        assert ValueError in AUDIT_TRAIL_READ_ERRORS
        assert TypeError in AUDIT_TRAIL_READ_ERRORS
        assert KeyError in AUDIT_TRAIL_READ_ERRORS
        assert AttributeError in AUDIT_TRAIL_READ_ERRORS


# ---------------------------------------------------------------------------
# AuditTrailResource — construction and class attributes
# ---------------------------------------------------------------------------


class TestAuditTrailResourceInit:
    def test_default_construction(self):
        r = AuditTrailResource()
        assert r.audit_client_adapter is None
        assert r.max_entries == 1000
        assert r._access_count == 0
        assert r._entries == []
        assert r._entry_counter == 0

    def test_custom_max_entries(self):
        r = AuditTrailResource(max_entries=5)
        assert r.max_entries == 5

    def test_custom_adapter(self):
        adapter = MagicMock()
        r = AuditTrailResource(audit_client_adapter=adapter)
        assert r.audit_client_adapter is adapter

    def test_uri_class_attribute(self):
        assert AuditTrailResource.URI == "acgs2://governance/audit-trail"

    def test_constitutional_hash_class_attribute(self):
        assert AuditTrailResource.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# AuditTrailResource.get_definition
# ---------------------------------------------------------------------------


class TestGetDefinition:
    def test_returns_resource_definition(self):
        defn = AuditTrailResource.get_definition()
        assert isinstance(defn, ResourceDefinition)

    def test_definition_uri(self):
        defn = AuditTrailResource.get_definition()
        assert defn.uri == AuditTrailResource.URI

    def test_definition_name(self):
        defn = AuditTrailResource.get_definition()
        assert defn.name == "Audit Trail"

    def test_definition_mime_type(self):
        defn = AuditTrailResource.get_definition()
        assert defn.mimeType == "application/json"

    def test_definition_constitutional_scope(self):
        defn = AuditTrailResource.get_definition()
        assert defn.constitutional_scope == "read"

    def test_definition_description_contains_key_terms(self):
        defn = AuditTrailResource.get_definition()
        assert "audit" in defn.description.lower()
        assert "compliance" in defn.description.lower()


# ---------------------------------------------------------------------------
# AuditTrailResource.log_event
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_creates_entry_with_correct_fields(self):
        r = AuditTrailResource()
        entry = r.log_event(
            event_type=AuditEventType.VALIDATION,
            actor_id="agent-001",
            action="validate",
            details={"policy": "p1"},
            outcome="pass",
        )
        assert entry.id == "AUDIT-00000001"
        assert entry.event_type == AuditEventType.VALIDATION
        assert entry.actor_id == "agent-001"
        assert entry.action == "validate"
        assert entry.details == {"policy": "p1"}
        assert entry.outcome == "pass"
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_increments_entry_counter(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "a", "b", {}, "ok")
        r.log_event(AuditEventType.VALIDATION, "a", "b", {}, "ok")
        assert r._entry_counter == 2

    def test_entry_id_zero_padded(self):
        r = AuditTrailResource()
        entry = r.log_event(AuditEventType.SYSTEM, "sys", "action", {}, "ok")
        assert entry.id == "AUDIT-00000001"

    def test_appends_to_entries_list(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.DECISION, "a1", "act", {}, "ok")
        r.log_event(AuditEventType.APPEAL, "a2", "act2", {}, "ok")
        assert len(r._entries) == 2

    def test_timestamp_is_set(self):
        r = AuditTrailResource()
        entry = r.log_event(AuditEventType.SYSTEM, "sys", "action", {}, "ok")
        assert entry.timestamp  # non-empty ISO string

    def test_max_entries_enforced(self):
        r = AuditTrailResource(max_entries=3)
        for i in range(5):
            r.log_event(AuditEventType.SYSTEM, "sys", f"act{i}", {}, "ok")
        # Should keep only the last 3
        assert len(r._entries) == 3
        # Last entry should be the most recent (act4)
        assert r._entries[-1].action == "act4"

    def test_max_entries_boundary_not_exceeded(self):
        r = AuditTrailResource(max_entries=2)
        r.log_event(AuditEventType.SYSTEM, "sys", "act0", {}, "ok")
        r.log_event(AuditEventType.SYSTEM, "sys", "act1", {}, "ok")
        r.log_event(AuditEventType.SYSTEM, "sys", "act2", {}, "ok")
        assert len(r._entries) == 2

    def test_entries_at_exactly_max_not_trimmed(self):
        r = AuditTrailResource(max_entries=3)
        for i in range(3):
            r.log_event(AuditEventType.SYSTEM, "sys", f"act{i}", {}, "ok")
        assert len(r._entries) == 3

    def test_returns_audit_entry_instance(self):
        r = AuditTrailResource()
        entry = r.log_event(AuditEventType.ESCALATION, "e1", "esc", {}, "escalated")
        assert isinstance(entry, AuditEntry)

    def test_all_event_types_logged(self):
        r = AuditTrailResource()
        for event_type in AuditEventType:
            entry = r.log_event(event_type, "actor", "action", {}, "ok")
            assert entry.event_type == event_type


# ---------------------------------------------------------------------------
# AuditTrailResource.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_empty_resource_metrics(self):
        r = AuditTrailResource()
        m = r.get_metrics()
        assert m["access_count"] == 0
        assert m["entry_count"] == 0
        assert m["event_type_distribution"] == {}
        assert m["uri"] == AuditTrailResource.URI
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_access_count_reflected(self):
        r = AuditTrailResource()
        r._access_count = 7
        m = r.get_metrics()
        assert m["access_count"] == 7

    def test_entry_count_reflected(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "a", "b", {}, "ok")
        r.log_event(AuditEventType.DECISION, "a", "b", {}, "ok")
        m = r.get_metrics()
        assert m["entry_count"] == 2

    def test_event_type_distribution(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "a", "b", {}, "ok")
        r.log_event(AuditEventType.VALIDATION, "a", "b", {}, "ok")
        r.log_event(AuditEventType.DECISION, "a", "b", {}, "ok")
        m = r.get_metrics()
        dist = m["event_type_distribution"]
        assert dist["validation"] == 2
        assert dist["decision"] == 1

    def test_all_event_types_counted(self):
        r = AuditTrailResource()
        for event_type in AuditEventType:
            r.log_event(event_type, "a", "b", {}, "ok")
        m = r.get_metrics()
        dist = m["event_type_distribution"]
        for event_type in AuditEventType:
            assert dist[event_type.value] == 1


# ---------------------------------------------------------------------------
# AuditTrailResource._read_locally
# ---------------------------------------------------------------------------


class TestReadLocally:
    def _setup(self) -> AuditTrailResource:
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "actor-1", "validate", {}, "pass")
        r.log_event(AuditEventType.DECISION, "actor-2", "decide", {}, "approved")
        r.log_event(AuditEventType.ESCALATION, "actor-1", "escalate", {}, "escalated")
        return r

    def test_no_filters_returns_all_sorted_newest_first(self):
        r = self._setup()
        results = r._read_locally(None, None, None, None, 100)
        assert len(results) == 3
        # Sorted newest first — timestamps increase with each log_event call,
        # so reversed order
        timestamps = [e.timestamp for e in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_limit_applied(self):
        r = self._setup()
        results = r._read_locally(None, None, None, None, 1)
        assert len(results) == 1

    def test_event_type_filter(self):
        r = self._setup()
        results = r._read_locally("validation", None, None, None, 100)
        assert len(results) == 1
        assert results[0].event_type == AuditEventType.VALIDATION

    def test_actor_filter(self):
        r = self._setup()
        results = r._read_locally(None, "actor-1", None, None, 100)
        assert len(results) == 2
        for e in results:
            assert e.actor_id == "actor-1"

    def test_start_date_filter(self):
        r = AuditTrailResource()
        # Manually inject entries with predictable timestamps
        r._entries = [
            _make_entry("A-1", timestamp="2026-01-01T00:00:00+00:00"),
            _make_entry("A-2", timestamp="2026-06-01T00:00:00+00:00"),
            _make_entry("A-3", timestamp="2026-12-01T00:00:00+00:00"),
        ]
        results = r._read_locally(None, None, "2026-06-01T00:00:00+00:00", None, 100)
        ids = {e.id for e in results}
        assert "A-1" not in ids
        assert "A-2" in ids
        assert "A-3" in ids

    def test_end_date_filter(self):
        r = AuditTrailResource()
        r._entries = [
            _make_entry("A-1", timestamp="2026-01-01T00:00:00+00:00"),
            _make_entry("A-2", timestamp="2026-06-01T00:00:00+00:00"),
            _make_entry("A-3", timestamp="2026-12-01T00:00:00+00:00"),
        ]
        results = r._read_locally(None, None, None, "2026-06-01T00:00:00+00:00", 100)
        ids = {e.id for e in results}
        assert "A-1" in ids
        assert "A-2" in ids
        assert "A-3" not in ids

    def test_combined_filters(self):
        r = AuditTrailResource()
        r._entries = [
            _make_entry(
                "A-1",
                event_type=AuditEventType.VALIDATION,
                actor_id="a1",
                timestamp="2026-01-01T00:00:00+00:00",
            ),
            _make_entry(
                "A-2",
                event_type=AuditEventType.VALIDATION,
                actor_id="a2",
                timestamp="2026-06-01T00:00:00+00:00",
            ),
            _make_entry(
                "A-3",
                event_type=AuditEventType.DECISION,
                actor_id="a1",
                timestamp="2026-06-01T00:00:00+00:00",
            ),
        ]
        results = r._read_locally("validation", "a1", None, None, 100)
        assert len(results) == 1
        assert results[0].id == "A-1"

    def test_empty_entries(self):
        r = AuditTrailResource()
        results = r._read_locally(None, None, None, None, 100)
        assert results == []


# ---------------------------------------------------------------------------
# AuditTrailResource.read — no adapter (local path)
# ---------------------------------------------------------------------------


class TestReadLocalPath:
    async def test_read_no_params_returns_json(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "a1", "validate", {}, "ok")
        result = await r.read()
        data = json.loads(result)
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert data["total_count"] == 1
        assert len(data["entries"]) == 1
        assert "timestamp" in data

    async def test_read_increments_access_count(self):
        r = AuditTrailResource()
        await r.read()
        assert r._access_count == 1

    async def test_read_with_none_params(self):
        r = AuditTrailResource()
        result = await r.read(None)
        data = json.loads(result)
        assert "entries" in data

    async def test_read_with_empty_params(self):
        r = AuditTrailResource()
        result = await r.read({})
        data = json.loads(result)
        assert "entries" in data

    async def test_read_with_event_type_filter(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.VALIDATION, "a1", "v", {}, "ok")
        r.log_event(AuditEventType.DECISION, "a1", "d", {}, "ok")
        result = await r.read({"event_type": "validation"})
        data = json.loads(result)
        assert data["total_count"] == 1
        assert data["entries"][0]["event_type"] == "validation"

    async def test_read_with_actor_filter(self):
        r = AuditTrailResource()
        r.log_event(AuditEventType.SYSTEM, "actor-A", "a", {}, "ok")
        r.log_event(AuditEventType.SYSTEM, "actor-B", "b", {}, "ok")
        result = await r.read({"actor_id": "actor-A"})
        data = json.loads(result)
        assert data["total_count"] == 1
        assert data["entries"][0]["actor_id"] == "actor-A"

    async def test_read_with_limit(self):
        r = AuditTrailResource()
        for i in range(10):
            r.log_event(AuditEventType.SYSTEM, "sys", f"act{i}", {}, "ok")
        result = await r.read({"limit": 3})
        data = json.loads(result)
        assert data["total_count"] == 3

    async def test_read_filters_applied_in_response(self):
        r = AuditTrailResource()
        result = await r.read({"event_type": "system", "limit": 5})
        data = json.loads(result)
        filters = data["filters_applied"]
        assert filters["event_type"] == "system"
        assert filters["limit"] == 5

    async def test_read_none_values_not_in_filters_applied(self):
        r = AuditTrailResource()
        # actor_id is None — should not appear in filters_applied
        result = await r.read({"limit": 10})
        data = json.loads(result)
        assert "actor_id" not in data["filters_applied"]

    async def test_read_with_date_filters(self):
        r = AuditTrailResource()
        r._entries = [
            _make_entry("A-1", timestamp="2026-01-01T00:00:00+00:00"),
            _make_entry("A-2", timestamp="2026-06-15T00:00:00+00:00"),
        ]
        result = await r.read(
            {
                "start_date": "2026-06-01T00:00:00+00:00",
                "end_date": "2026-12-31T00:00:00+00:00",
            }
        )
        data = json.loads(result)
        assert data["total_count"] == 1
        assert data["entries"][0]["id"] == "A-2"

    async def test_read_default_limit_is_50(self):
        r = AuditTrailResource()
        for i in range(60):
            r.log_event(AuditEventType.SYSTEM, "sys", f"act{i}", {}, "ok")
        result = await r.read({})
        data = json.loads(result)
        assert data["total_count"] == 50


# ---------------------------------------------------------------------------
# AuditTrailResource.read — adapter path
# ---------------------------------------------------------------------------


class TestReadAdapterPath:
    async def test_read_calls_adapter(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.return_value = [
            {
                "id": "A-001",
                "event_type": AuditEventType.VALIDATION,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "actor_id": "agent-001",
                "action": "validate",
                "details": {},
                "outcome": "pass",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        ]
        r = AuditTrailResource(audit_client_adapter=adapter)
        result = await r.read({"limit": 10})
        data = json.loads(result)
        adapter.get_audit_trail.assert_called_once_with(limit=10)
        assert data["total_count"] == 1

    async def test_read_adapter_returns_entries_correctly(self):
        adapter = AsyncMock()
        raw = {
            "id": "X-001",
            "event_type": AuditEventType.DECISION,
            "timestamp": "2026-02-01T00:00:00+00:00",
            "actor_id": "ag-x",
            "action": "decide",
            "details": {"val": 1},
            "outcome": "approved",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        adapter.get_audit_trail.return_value = [raw]
        r = AuditTrailResource(audit_client_adapter=adapter)
        result = await r.read()
        data = json.loads(result)
        assert data["entries"][0]["id"] == "X-001"
        assert data["entries"][0]["event_type"] == "decision"

    async def test_read_adapter_with_no_params(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.return_value = []
        r = AuditTrailResource(audit_client_adapter=adapter)
        result = await r.read()
        data = json.loads(result)
        assert data["total_count"] == 0
        adapter.get_audit_trail.assert_called_once()

    async def test_read_adapter_multiple_entries(self):
        adapter = AsyncMock()
        entries_raw = [
            {
                "id": f"E-{i:03d}",
                "event_type": AuditEventType.SYSTEM,
                "timestamp": f"2026-0{i + 1}-01T00:00:00+00:00",
                "actor_id": "sys",
                "action": f"action{i}",
                "details": {},
                "outcome": "ok",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            for i in range(1, 4)
        ]
        adapter.get_audit_trail.return_value = entries_raw
        r = AuditTrailResource(audit_client_adapter=adapter)
        result = await r.read()
        data = json.loads(result)
        assert data["total_count"] == 3


# ---------------------------------------------------------------------------
# AuditTrailResource.read — error handling
# ---------------------------------------------------------------------------


class TestReadErrorHandling:
    async def test_runtime_error_returns_error_json(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=RuntimeError("boom")):
            result = await r.read()
        data = json.loads(result)
        assert "error" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_value_error_returns_error_json(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=ValueError("bad value")):
            result = await r.read()
        data = json.loads(result)
        assert "error" in data
        assert "bad value" in data["error"]

    async def test_type_error_returns_error_json(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=TypeError("type mismatch")):
            result = await r.read()
        data = json.loads(result)
        assert "error" in data

    async def test_key_error_returns_error_json(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=KeyError("missing_key")):
            result = await r.read()
        data = json.loads(result)
        assert "error" in data

    async def test_attribute_error_returns_error_json(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=AttributeError("no attr")):
            result = await r.read()
        data = json.loads(result)
        assert "error" in data

    async def test_adapter_error_returns_error_json(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.side_effect = RuntimeError("adapter failure")
        r = AuditTrailResource(audit_client_adapter=adapter)
        result = await r.read()
        data = json.loads(result)
        assert "error" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_access_count_increments_even_on_error(self):
        r = AuditTrailResource()
        with patch.object(r, "_read_locally", side_effect=RuntimeError("err")):
            await r.read()
        assert r._access_count == 1


# ---------------------------------------------------------------------------
# AuditTrailResource._read_from_adapter
# ---------------------------------------------------------------------------


class TestReadFromAdapter:
    async def test_constructs_audit_entries_from_raw(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.return_value = [
            {
                "id": "RAW-001",
                "event_type": AuditEventType.PRINCIPLE_ACCESS,
                "timestamp": "2026-03-01T00:00:00+00:00",
                "actor_id": "agent-r",
                "action": "access_principle",
                "details": {},
                "outcome": "granted",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        ]
        r = AuditTrailResource(audit_client_adapter=adapter)
        entries = await r._read_from_adapter({"limit": 5})
        assert len(entries) == 1
        assert isinstance(entries[0], AuditEntry)
        assert entries[0].id == "RAW-001"

    async def test_passes_params_to_adapter(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.return_value = []
        r = AuditTrailResource(audit_client_adapter=adapter)
        await r._read_from_adapter({"event_type": "system", "limit": 20})
        adapter.get_audit_trail.assert_called_once_with(event_type="system", limit=20)

    async def test_returns_empty_list_when_adapter_returns_empty(self):
        adapter = AsyncMock()
        adapter.get_audit_trail.return_value = []
        r = AuditTrailResource(audit_client_adapter=adapter)
        entries = await r._read_from_adapter({})
        assert entries == []


# ---------------------------------------------------------------------------
# Integration-style: full round-trip log → read
# ---------------------------------------------------------------------------


class TestRoundTrip:
    async def test_log_then_read_returns_entry(self):
        r = AuditTrailResource()
        r.log_event(
            AuditEventType.ESCALATION, "agent-X", "escalate", {"reason": "score"}, "pending"
        )
        result = await r.read()
        data = json.loads(result)
        assert data["total_count"] == 1
        e = data["entries"][0]
        assert e["actor_id"] == "agent-X"
        assert e["event_type"] == "escalation"
        assert e["details"]["reason"] == "score"

    async def test_metrics_reflects_read_count(self):
        r = AuditTrailResource()
        await r.read()
        await r.read()
        m = r.get_metrics()
        assert m["access_count"] == 2

    async def test_max_entries_maintained_after_reads(self):
        r = AuditTrailResource(max_entries=5)
        for i in range(10):
            r.log_event(AuditEventType.SYSTEM, "sys", f"act{i}", {}, "ok")
        assert len(r._entries) == 5
        result = await r.read({"limit": 10})
        data = json.loads(result)
        assert data["total_count"] == 5
