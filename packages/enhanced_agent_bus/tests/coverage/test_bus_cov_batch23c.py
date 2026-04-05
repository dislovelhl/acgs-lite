"""
Coverage tests for batch tenant isolation, audit client adapter,
get_metrics tool, and query_precedents tool.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.batch_models import BatchRequestItem
from enhanced_agent_bus.mcp_server.adapters.audit_client import AuditClientAdapter
from enhanced_agent_bus.mcp_server.tools.get_metrics import (
    GetMetricsTool,
    GovernanceMetrics,
)
from enhanced_agent_bus.mcp_server.tools.query_precedents import (
    DecisionOutcome,
    GovernancePrecedent,
    QueryPrecedentsTool,
)
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.exceptions import BatchTenantIsolationException
from enhanced_agent_bus.middlewares.batch.tenant_isolation import (
    BatchTenantIsolationMiddleware,
)
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(tenant_id: str = "default", content: dict | None = None) -> BatchRequestItem:
    return BatchRequestItem(
        content=content or {"action": "test"},
        tenant_id=tenant_id,
    )


def _make_context(
    items: list[BatchRequestItem] | None = None,
    fail_closed: bool = True,
    batch_tenant_id: str | None = None,
) -> BatchPipelineContext:
    ctx = BatchPipelineContext(
        batch_items=items or [],
    )
    ctx.batch_tenant_id = batch_tenant_id
    return ctx


# ===========================================================================
# 1. BatchTenantIsolationMiddleware
# ===========================================================================


class TestTenantIsolationMiddlewareProcess:
    """Tests for BatchTenantIsolationMiddleware.process()."""

    async def test_empty_items_calls_next(self):
        mw = BatchTenantIsolationMiddleware(config=MiddlewareConfig(fail_closed=True))
        ctx = _make_context(items=[])
        result = await mw.process(ctx)
        assert result is ctx

    async def test_all_default_tenants_passes(self):
        items = [_make_item("default"), _make_item("default")]
        mw = BatchTenantIsolationMiddleware()
        ctx = _make_context(items=items)
        result = await mw.process(ctx)
        assert result.batch_tenant_id == "default"

    async def test_all_same_non_default_tenant_passes(self):
        items = [_make_item("acme"), _make_item("acme")]
        mw = BatchTenantIsolationMiddleware()
        ctx = _make_context(items=items)
        result = await mw.process(ctx)
        assert result.batch_tenant_id == "acme"

    async def test_mixed_tenants_fail_closed_raises(self):
        items = [_make_item("acme"), _make_item("globex")]
        mw = BatchTenantIsolationMiddleware(config=MiddlewareConfig(fail_closed=True))
        ctx = _make_context(items=items)
        with pytest.raises(BatchTenantIsolationException) as exc_info:
            await mw.process(ctx)
        assert "acme" in str(exc_info.value)

    async def test_mixed_tenants_non_fail_closed_sets_early_result(self):
        items = [_make_item("acme"), _make_item("globex")]
        mw = BatchTenantIsolationMiddleware(config=MiddlewareConfig(fail_closed=False))
        ctx = _make_context(items=items)
        result = await mw.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False
        assert "tenant_isolation" in result.early_result.metadata.get("validation_stage", "")

    async def test_conflicting_tenants_listed_in_exception(self):
        items = [_make_item("acme"), _make_item("globex"), _make_item("acme")]
        mw = BatchTenantIsolationMiddleware(config=MiddlewareConfig(fail_closed=True))
        ctx = _make_context(items=items)
        with pytest.raises(BatchTenantIsolationException) as exc_info:
            await mw.process(ctx)
        exc = exc_info.value
        assert set(exc.conflicting_tenants) == {"acme", "globex"}

    async def test_default_and_non_default_mixed_passes(self):
        """Items with 'default' tenant inherit; only non-default must match."""
        items = [_make_item("default"), _make_item("acme")]
        mw = BatchTenantIsolationMiddleware()
        ctx = _make_context(items=items)
        result = await mw.process(ctx)
        assert result.batch_tenant_id == "acme"

    async def test_none_tenant_treated_as_default(self):
        item = _make_item("default")
        item.tenant_id = ""
        items = [item, _make_item("acme")]
        mw = BatchTenantIsolationMiddleware()
        ctx = _make_context(items=items)
        result = await mw.process(ctx)
        assert result.batch_tenant_id == "acme"

    async def test_latency_recorded(self):
        items = [_make_item("acme")]
        mw = BatchTenantIsolationMiddleware()
        ctx = _make_context(items=items)
        ctx.batch_latency_ms = 0.0
        await mw.process(ctx)
        assert ctx.batch_latency_ms > 0.0

    async def test_next_middleware_called(self):
        """Verify _call_next is invoked when validation passes."""
        items = [_make_item("acme")]
        mw = BatchTenantIsolationMiddleware()
        next_mw = MagicMock()
        next_mw.config = MiddlewareConfig(enabled=True)
        next_mw.process = AsyncMock(side_effect=lambda ctx: ctx)
        mw.set_next(next_mw)
        ctx = _make_context(items=items)
        await mw.process(ctx)
        next_mw.process.assert_awaited_once()


class TestTenantIsolationHelpers:
    """Tests for private helper methods."""

    def test_validate_tenant_consistency_empty(self):
        mw = BatchTenantIsolationMiddleware()
        is_valid, msg = mw._validate_tenant_consistency([])
        assert is_valid is True
        assert msg == ""

    def test_validate_tenant_consistency_all_default(self):
        mw = BatchTenantIsolationMiddleware()
        items = [_make_item("default"), _make_item("default")]
        is_valid, _ = mw._validate_tenant_consistency(items)
        assert is_valid is True

    def test_validate_tenant_consistency_conflict(self):
        mw = BatchTenantIsolationMiddleware()
        items = [_make_item("a"), _make_item("b")]
        is_valid, msg = mw._validate_tenant_consistency(items)
        assert is_valid is False
        assert "Cross-tenant" in msg

    def test_extract_tenants(self):
        mw = BatchTenantIsolationMiddleware()
        items = [_make_item("acme"), _make_item("")]
        tenants = mw._extract_tenants(items)
        assert tenants == ["acme", "default"]

    def test_determine_effective_tenant_empty(self):
        mw = BatchTenantIsolationMiddleware()
        assert mw._determine_effective_tenant([]) is None

    def test_determine_effective_tenant_all_default(self):
        mw = BatchTenantIsolationMiddleware()
        items = [_make_item("default")]
        assert mw._determine_effective_tenant(items) == "default"

    def test_determine_effective_tenant_picks_first_non_default(self):
        mw = BatchTenantIsolationMiddleware()
        items = [_make_item("default"), _make_item("acme"), _make_item("globex")]
        assert mw._determine_effective_tenant(items) == "acme"

    def test_normalize_tenant_id_none(self):
        mw = BatchTenantIsolationMiddleware()
        assert mw._normalize_tenant_id(None) == "default"

    def test_normalize_tenant_id_empty(self):
        mw = BatchTenantIsolationMiddleware()
        assert mw._normalize_tenant_id("") == "default"

    def test_normalize_tenant_id_strips_and_lowercases(self):
        mw = BatchTenantIsolationMiddleware()
        assert mw._normalize_tenant_id("  ACME  ") == "acme"


# ===========================================================================
# 2. AuditClientAdapter
# ===========================================================================


class TestAuditClientAdapterNoClient:
    """Tests for AuditClientAdapter with no real audit client (sample data)."""

    async def test_query_precedents_no_client_returns_samples(self):
        adapter = AuditClientAdapter(audit_client=None)
        result = await adapter.query_precedents()
        assert len(result) == 3
        assert result[0]["id"] == "PREC-001"

    async def test_query_precedents_filter_action_type(self):
        adapter = AuditClientAdapter()
        result = await adapter.query_precedents(action_type="data_access")
        assert len(result) == 1
        assert result[0]["action_type"] == "data_access"

    async def test_query_precedents_filter_outcome(self):
        adapter = AuditClientAdapter()
        result = await adapter.query_precedents(outcome="denied")
        assert len(result) == 1
        assert result[0]["outcome"] == "denied"

    async def test_query_precedents_filter_principles(self):
        adapter = AuditClientAdapter()
        result = await adapter.query_precedents(principles=["P008"])
        assert len(result) == 1
        assert "P008" in result[0]["principles_applied"]

    async def test_query_precedents_limit(self):
        adapter = AuditClientAdapter()
        result = await adapter.query_precedents(limit=1)
        assert len(result) == 1

    async def test_query_precedents_no_match(self):
        adapter = AuditClientAdapter()
        result = await adapter.query_precedents(action_type="nonexistent")
        assert len(result) == 0

    async def test_get_audit_trail_no_client(self):
        adapter = AuditClientAdapter()
        result = await adapter.get_audit_trail()
        assert len(result) == 2
        assert result[0]["event_type"] == "validation"

    async def test_get_audit_trail_filter_event_type(self):
        adapter = AuditClientAdapter()
        result = await adapter.get_audit_trail(event_type="decision")
        assert len(result) == 1
        assert result[0]["event_type"] == "decision"

    async def test_get_audit_trail_filter_actor_id(self):
        adapter = AuditClientAdapter()
        result = await adapter.get_audit_trail(actor_id="governance-engine")
        assert len(result) == 1

    async def test_get_audit_trail_filter_no_match(self):
        adapter = AuditClientAdapter()
        result = await adapter.get_audit_trail(event_type="nonexistent")
        assert len(result) == 0

    async def test_get_audit_trail_limit(self):
        adapter = AuditClientAdapter()
        result = await adapter.get_audit_trail(limit=1)
        assert len(result) == 1

    async def test_log_audit_event_no_client(self):
        adapter = AuditClientAdapter()
        result = await adapter.log_audit_event(
            event_type="test",
            actor_id="test-agent",
            action="test action",
            details={"key": "value"},
            outcome="success",
        )
        assert result["event_type"] == "test"
        assert result["actor_id"] == "test-agent"
        assert "constitutional_hash" in result

    def test_get_metrics_no_client(self):
        adapter = AuditClientAdapter()
        metrics = adapter.get_metrics()
        assert metrics["request_count"] == 0
        assert metrics["connected"] is False
        assert "constitutional_hash" in metrics

    async def test_request_count_increments(self):
        adapter = AuditClientAdapter()
        await adapter.query_precedents()
        await adapter.get_audit_trail()
        await adapter.log_audit_event("t", "a", "x", {}, "ok")
        assert adapter.get_metrics()["request_count"] == 3


class TestAuditClientAdapterWithClient:
    """Tests for AuditClientAdapter with a mocked audit client."""

    async def test_query_precedents_delegates_to_client(self):
        mock_client = AsyncMock()
        mock_client.query_precedents = AsyncMock(
            return_value=[
                {"context_summary": "test item", "reasoning": "reason"},
            ]
        )
        adapter = AuditClientAdapter(audit_client=mock_client)
        result = await adapter.query_precedents(action_type="test")
        mock_client.query_precedents.assert_awaited_once()
        assert len(result) == 1

    async def test_query_precedents_with_semantic_query_filters(self):
        mock_client = AsyncMock()
        mock_client.query_precedents = AsyncMock(
            return_value=[
                {"context_summary": "PII access request", "reasoning": "privacy"},
                {"context_summary": "Config change", "reasoning": "safety"},
            ]
        )
        adapter = AuditClientAdapter(audit_client=mock_client)
        result = await adapter.query_precedents(semantic_query="PII")
        assert len(result) == 1
        assert "PII" in result[0]["context_summary"]

    async def test_query_precedents_semantic_no_match(self):
        mock_client = AsyncMock()
        mock_client.query_precedents = AsyncMock(
            return_value=[
                {"context_summary": "Config change", "reasoning": "safety"},
            ]
        )
        adapter = AuditClientAdapter(audit_client=mock_client)
        result = await adapter.query_precedents(semantic_query="nonexistent")
        assert len(result) == 0

    async def test_query_precedents_client_error_raises(self):
        mock_client = AsyncMock()
        mock_client.query_precedents = AsyncMock(side_effect=RuntimeError("db down"))
        adapter = AuditClientAdapter(audit_client=mock_client)
        with pytest.raises(RuntimeError, match="db down"):
            await adapter.query_precedents()

    async def test_get_audit_trail_delegates_to_client(self):
        mock_client = AsyncMock()
        mock_client.get_audit_trail = AsyncMock(return_value=[{"id": "A1"}])
        adapter = AuditClientAdapter(audit_client=mock_client)
        result = await adapter.get_audit_trail(event_type="test")
        assert result == [{"id": "A1"}]

    async def test_get_audit_trail_client_error_raises(self):
        mock_client = AsyncMock()
        mock_client.get_audit_trail = AsyncMock(side_effect=ValueError("bad"))
        adapter = AuditClientAdapter(audit_client=mock_client)
        with pytest.raises(ValueError, match="bad"):
            await adapter.get_audit_trail()

    async def test_log_audit_event_delegates_to_client(self):
        mock_client = AsyncMock()
        mock_client.log_event = AsyncMock(return_value={"id": "logged"})
        adapter = AuditClientAdapter(audit_client=mock_client)
        result = await adapter.log_audit_event("t", "a", "x", {}, "ok")
        assert result == {"id": "logged"}

    async def test_log_audit_event_client_error_raises(self):
        mock_client = AsyncMock()
        mock_client.log_event = AsyncMock(side_effect=OSError("network"))
        adapter = AuditClientAdapter(audit_client=mock_client)
        with pytest.raises(OSError, match="network"):
            await adapter.log_audit_event("t", "a", "x", {}, "ok")

    def test_get_metrics_connected(self):
        adapter = AuditClientAdapter(audit_client=MagicMock())
        assert adapter.get_metrics()["connected"] is True


# ===========================================================================
# 3. GetMetricsTool
# ===========================================================================


class TestGetMetricsToolDefinition:
    def test_get_definition_returns_tool_definition(self):
        defn = GetMetricsTool.get_definition()
        assert defn.name == "get_governance_metrics"
        assert defn.constitutional_required is False


class TestGetMetricsToolExecute:
    async def test_execute_no_adapter_returns_local_metrics(self):
        tool = GetMetricsTool()
        result = await tool.execute({})
        assert result["isError"] is False
        content = json.loads(result["content"][0]["text"])
        assert "constitutional_hash" in content

    async def test_execute_with_metric_type_filter(self):
        tool = GetMetricsTool()
        result = await tool.execute({"metric_types": ["requests"]})
        content = json.loads(result["content"][0]["text"])
        assert "requests" in content
        assert "performance" not in content

    async def test_execute_with_historical(self):
        tool = GetMetricsTool()
        result = await tool.execute({"include_historical": True, "time_range": "7d"})
        content = json.loads(result["content"][0]["text"])
        assert "historical" in content
        assert content["historical"]["time_range"] == "7d"

    async def test_execute_with_adapter(self):
        mock_adapter = AsyncMock()
        mock_adapter.get_metrics = AsyncMock(
            return_value={
                "total_requests": 100,
                "approved_count": 80,
                "denied_count": 10,
                "conditional_count": 5,
                "escalated_count": 5,
                "avg_latency_ms": 2.5,
                "p99_latency_ms": 10.0,
                "throughput_rps": 500.0,
                "validation_count": 100,
                "violation_count": 2,
                "compliance_rate": 0.98,
                "active_principles": 8,
                "precedent_count": 5,
                "cache_hit_rate": 0.9,
                "system_health": "healthy",
                "constitutional_hash": "608508a9bd224290",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        )
        tool = GetMetricsTool(metrics_adapter=mock_adapter)
        result = await tool.execute({})
        assert result["isError"] is False
        mock_adapter.get_metrics.assert_awaited_once()

    async def test_execute_adapter_error_returns_error(self):
        mock_adapter = AsyncMock()
        mock_adapter.get_metrics = AsyncMock(side_effect=RuntimeError("metrics unavailable"))
        tool = GetMetricsTool(metrics_adapter=mock_adapter)
        result = await tool.execute({})
        assert result["isError"] is True
        content = json.loads(result["content"][0]["text"])
        assert "metrics unavailable" in content["error"]

    async def test_request_count_increments(self):
        tool = GetMetricsTool()
        await tool.execute({})
        await tool.execute({})
        assert tool._request_count == 2


class TestGetMetricsToolRecordRequest:
    def test_record_approved(self):
        tool = GetMetricsTool()
        tool.record_request("approved", 1.0)
        assert tool._internal_metrics["approved_count"] == 1
        assert tool._internal_metrics["total_requests"] == 1

    def test_record_denied(self):
        tool = GetMetricsTool()
        tool.record_request("denied", 2.0)
        assert tool._internal_metrics["denied_count"] == 1

    def test_record_conditional(self):
        tool = GetMetricsTool()
        tool.record_request("conditional", 3.0)
        assert tool._internal_metrics["conditional_count"] == 1

    def test_record_escalated(self):
        tool = GetMetricsTool()
        tool.record_request("escalated", 4.0)
        assert tool._internal_metrics["escalated_count"] == 1

    def test_record_with_violation(self):
        tool = GetMetricsTool()
        tool.record_request("approved", 1.0, had_violation=True)
        assert tool._internal_metrics["violation_count"] == 1

    def test_latency_cap_at_1000(self):
        tool = GetMetricsTool()
        for i in range(1050):
            tool.record_request("approved", float(i))
        assert len(tool._internal_metrics["latencies"]) == 1000

    def test_unknown_status_no_crash(self):
        tool = GetMetricsTool()
        tool.record_request("unknown_status", 1.0)
        assert tool._internal_metrics["total_requests"] == 1
        assert tool._internal_metrics["approved_count"] == 0


class TestGetMetricsToolLocal:
    def test_get_locally_with_violations(self):
        tool = GetMetricsTool()
        tool.record_request("approved", 1.0)
        tool.record_request("denied", 2.0, had_violation=True)
        metrics = tool._get_locally()
        assert metrics.total_requests == 2
        assert metrics.violation_count == 1
        assert metrics.compliance_rate < 1.0

    def test_get_locally_empty_state(self):
        tool = GetMetricsTool()
        metrics = tool._get_locally()
        assert metrics.total_requests == 0
        assert metrics.compliance_rate == 1.0

    def test_get_metrics_method(self):
        tool = GetMetricsTool()
        m = tool.get_metrics()
        assert m["request_count"] == 0
        assert "constitutional_hash" in m

    def test_governance_metrics_to_dict(self):
        gm = GovernanceMetrics(
            total_requests=10,
            approved_count=8,
            denied_count=1,
            conditional_count=1,
            escalated_count=0,
            avg_latency_ms=2.0,
            p99_latency_ms=5.0,
            throughput_rps=100.0,
            validation_count=10,
            violation_count=0,
            compliance_rate=1.0,
            active_principles=8,
            precedent_count=5,
            cache_hit_rate=0.9,
            system_health="healthy",
            constitutional_hash="608508a9bd224290",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = gm.to_dict()
        assert d["requests"]["total"] == 10
        assert d["performance"]["avg_latency_ms"] == 2.0
        assert d["compliance"]["compliance_rate"] == 1.0
        assert d["governance"]["active_principles"] == 8
        assert d["system"]["health"] == "healthy"

    def test_historical_trends_24h(self):
        tool = GetMetricsTool()
        trends = tool._get_historical_trends("24h")
        assert trends["data_points"] == 24

    def test_historical_trends_7d(self):
        tool = GetMetricsTool()
        trends = tool._get_historical_trends("7d")
        assert trends["data_points"] == 7


# ===========================================================================
# 4. QueryPrecedentsTool
# ===========================================================================


class TestQueryPrecedentsToolDefinition:
    def test_get_definition(self):
        defn = QueryPrecedentsTool.get_definition()
        assert defn.name == "query_governance_precedents"
        assert defn.constitutional_required is False


class TestQueryPrecedentsToolInit:
    def test_initializes_sample_precedents(self):
        tool = QueryPrecedentsTool()
        assert len(tool._precedent_cache) == 5


class TestQueryPrecedentsToolExecuteLocal:
    async def test_execute_no_filters(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({})
        assert result["isError"] is False
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 5

    async def test_execute_filter_action_type(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"action_type": "data_access"})
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 1
        assert content["precedents"][0]["action_type"] == "data_access"

    async def test_execute_filter_outcome(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"outcome": "denied"})
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 2

    async def test_execute_filter_principles(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"principles": ["P007"]})
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 2

    async def test_execute_filter_min_confidence(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"min_confidence": 0.95})
        content = json.loads(result["content"][0]["text"])
        for p in content["precedents"]:
            assert p["confidence_score"] >= 0.95

    async def test_execute_semantic_query(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"semantic_query": "PII"})
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] >= 1

    async def test_execute_limit(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({"limit": 2})
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 2

    async def test_execute_include_overruled_false_default(self):
        tool = QueryPrecedentsTool()
        # Add an overruled precedent
        overruled = GovernancePrecedent(
            id="PREC-OVERRULED",
            action_type="test",
            context_summary="overruled test",
            outcome=DecisionOutcome.DENIED,
            principles_applied=["P001"],
            reasoning="was overruled",
            timestamp="2024-12-25T00:00:00Z",
            confidence_score=0.9,
            overruled=True,
        )
        tool.add_precedent(overruled)
        result = await tool.execute({})
        content = json.loads(result["content"][0]["text"])
        ids = [p["id"] for p in content["precedents"]]
        assert "PREC-OVERRULED" not in ids

    async def test_execute_include_overruled_true(self):
        tool = QueryPrecedentsTool()
        overruled = GovernancePrecedent(
            id="PREC-OVERRULED",
            action_type="test",
            context_summary="overruled test",
            outcome=DecisionOutcome.DENIED,
            principles_applied=["P001"],
            reasoning="was overruled",
            timestamp="2024-12-25T00:00:00Z",
            confidence_score=0.9,
            overruled=True,
        )
        tool.add_precedent(overruled)
        result = await tool.execute({"include_overruled": True})
        content = json.loads(result["content"][0]["text"])
        ids = [p["id"] for p in content["precedents"]]
        assert "PREC-OVERRULED" in ids

    async def test_execute_request_count_increments(self):
        tool = QueryPrecedentsTool()
        await tool.execute({})
        await tool.execute({})
        assert tool._request_count == 2

    async def test_execute_sorted_by_timestamp_desc(self):
        tool = QueryPrecedentsTool()
        result = await tool.execute({})
        content = json.loads(result["content"][0]["text"])
        timestamps = [p["timestamp"] for p in content["precedents"]]
        assert timestamps == sorted(timestamps, reverse=True)


class TestQueryPrecedentsToolWithAdapter:
    async def test_execute_delegates_to_audit_client(self):
        mock_adapter = AsyncMock()
        mock_adapter.query_precedents = AsyncMock(
            return_value=[
                {
                    "id": "PREC-REMOTE",
                    "action_type": "test",
                    "context_summary": "remote test",
                    "outcome": DecisionOutcome.APPROVED,
                    "principles_applied": ["P001"],
                    "reasoning": "ok",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "confidence_score": 0.9,
                    "appeal_count": 0,
                    "overruled": False,
                    "related_precedents": [],
                }
            ]
        )
        tool = QueryPrecedentsTool(audit_client_adapter=mock_adapter)
        result = await tool.execute({"action_type": "test"})
        assert result["isError"] is False
        content = json.loads(result["content"][0]["text"])
        assert content["total_count"] == 1

    async def test_execute_adapter_error_returns_error_response(self):
        mock_adapter = AsyncMock()
        mock_adapter.query_precedents = AsyncMock(side_effect=RuntimeError("connection refused"))
        tool = QueryPrecedentsTool(audit_client_adapter=mock_adapter)
        result = await tool.execute({})
        assert result["isError"] is True
        content = json.loads(result["content"][0]["text"])
        assert "connection refused" in content["error"]


class TestQueryPrecedentsToolHelpers:
    def test_add_precedent(self):
        tool = QueryPrecedentsTool()
        p = GovernancePrecedent(
            id="PREC-NEW",
            action_type="new",
            context_summary="new",
            outcome=DecisionOutcome.APPROVED,
            principles_applied=[],
            reasoning="new",
            timestamp="2024-01-01T00:00:00Z",
            confidence_score=1.0,
        )
        tool.add_precedent(p)
        assert "PREC-NEW" in tool._precedent_cache

    def test_get_metrics(self):
        tool = QueryPrecedentsTool()
        m = tool.get_metrics()
        assert m["total_precedents"] == 5
        assert "outcome_distribution" in m
        assert "constitutional_hash" in m
        assert m["overruled_count"] == 0

    def test_governance_precedent_to_dict(self):
        p = GovernancePrecedent(
            id="X",
            action_type="test",
            context_summary="summary",
            outcome=DecisionOutcome.CONDITIONAL,
            principles_applied=["P1"],
            reasoning="reason",
            timestamp="2024-01-01T00:00:00Z",
            confidence_score=0.5,
            appeal_count=2,
            overruled=True,
            related_precedents=["Y"],
        )
        d = p.to_dict()
        assert d["outcome"] == "conditional"
        assert d["appeal_count"] == 2
        assert d["overruled"] is True
        assert d["related_precedents"] == ["Y"]

    def test_decision_outcome_values(self):
        assert DecisionOutcome.APPROVED.value == "approved"
        assert DecisionOutcome.DENIED.value == "denied"
        assert DecisionOutcome.CONDITIONAL.value == "conditional"
        assert DecisionOutcome.DEFERRED.value == "deferred"
        assert DecisionOutcome.ESCALATED.value == "escalated"
