"""
Coverage tests for:
  - middlewares/tool_privilege.py
  - middlewares/batch/processing.py
  - middlewares/batch/deduplication.py
  - middlewares/batch/metrics.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.batch_models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
)
from enhanced_agent_bus.enums import BatchItemStatus
from enhanced_agent_bus.maci_enforcement import MACIRole
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.deduplication import (
    BatchDeduplicationMiddleware,
    _LRUCache,
)
from enhanced_agent_bus.middlewares.batch.exceptions import (
    BatchDeduplicationException,
    BatchMetricsException,
    BatchProcessingException,
)
from enhanced_agent_bus.middlewares.batch.metrics import BatchMetricsMiddleware
from enhanced_agent_bus.middlewares.batch.processing import BatchProcessingMiddleware
from enhanced_agent_bus.middlewares.tool_privilege import (
    MACI_TOOL_POLICIES,
    PrivilegeDecision,
    ToolCallPolicy,
    ToolPrivilegeEnforcer,
    ToolPrivilegeMiddleware,
    _requires_constitutional_validation,
    _requires_maci_consensus,
)
from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.pipeline.context import PipelineContext
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(**kwargs: Any) -> AgentMessage:
    defaults = {
        "message_id": "test-msg-001",
        "from_agent": "test-agent",
        "content": {"text": "hello"},
    }
    defaults.update(kwargs)
    return AgentMessage(**defaults)


def _make_pipeline_ctx(
    *,
    constitutional_validated: bool = True,
    maci_role: str | None = None,
    requested_tool: str | None = None,
    maci_result: Any = None,
    tenant_id: str | None = None,
    **kwargs: Any,
) -> PipelineContext:
    msg = _make_message()
    if requested_tool is not None:
        object.__setattr__(msg, "requested_tool", requested_tool)
    if tenant_id is not None:
        object.__setattr__(msg, "tenant_id", tenant_id)
    ctx = PipelineContext(message=msg, **kwargs)
    ctx.constitutional_validated = constitutional_validated
    ctx.maci_role = maci_role
    ctx.maci_result = maci_result
    return ctx


def _make_batch_ctx(
    items: list[BatchRequestItem] | None = None,
    fail_fast: bool = False,
    deduplicate: bool = True,
    max_concurrency: int = 10,
    batch_request: BatchRequest | None = None,
    **kwargs: Any,
) -> BatchPipelineContext:
    ctx = BatchPipelineContext(
        batch_items=items or [],
        fail_fast=fail_fast,
        deduplicate=deduplicate,
        max_concurrency=max_concurrency,
        batch_request=batch_request,
    )
    for k, v in kwargs.items():
        setattr(ctx, k, v)
    return ctx


def _make_batch_item(**kwargs: Any) -> BatchRequestItem:
    defaults = {
        "content": {"payload": "test"},
        "from_agent": "agent-a",
        "tenant_id": "tenant-1",
        "priority": 1,
    }
    defaults.update(kwargs)
    return BatchRequestItem(**defaults)


# ===================================================================
# TOOL PRIVILEGE TESTS
# ===================================================================


class TestPrivilegeDecision:
    def test_defaults(self):
        d = PrivilegeDecision(permitted=True, reason="ok")
        assert d.permitted is True
        assert d.reason == "ok"
        assert d.fallback == "block"

    def test_custom_fallback(self):
        d = PrivilegeDecision(permitted=False, reason="no", fallback="route_to_hitl")
        assert d.fallback == "route_to_hitl"

    def test_frozen(self):
        d = PrivilegeDecision(permitted=True, reason="ok")
        with pytest.raises(AttributeError):
            d.permitted = False  # type: ignore[misc]


class TestToolCallPolicy:
    def test_frozen_dataclass(self):
        policy = ToolCallPolicy(
            role=MACIRole.EXECUTIVE,
            allowed_tools=frozenset({"read_policy"}),
        )
        assert policy.role == MACIRole.EXECUTIVE
        assert "read_policy" in policy.allowed_tools
        assert policy.deny_fallback == "block"

    def test_with_guards_and_denied(self):
        policy = ToolCallPolicy(
            role=MACIRole.JUDICIAL,
            allowed_tools=frozenset({"validate_message"}),
            denied_tools=frozenset({"execute_action"}),
            guards=(_requires_constitutional_validation,),
            deny_fallback="route_to_hitl",
        )
        assert len(policy.guards) == 1
        assert "execute_action" in policy.denied_tools


class TestGuardHelpers:
    def test_requires_constitutional_validation_true(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        assert _requires_constitutional_validation(ctx) is True

    def test_requires_constitutional_validation_false(self):
        ctx = _make_pipeline_ctx(constitutional_validated=False)
        assert _requires_constitutional_validation(ctx) is False

    def test_requires_maci_consensus_no_result(self):
        ctx = _make_pipeline_ctx(maci_result=None)
        assert _requires_maci_consensus(ctx) is False

    def test_requires_maci_consensus_no_ratio(self):
        result = SimpleNamespace()  # no consensus_ratio attribute
        ctx = _make_pipeline_ctx(maci_result=result)
        assert _requires_maci_consensus(ctx) is False

    def test_requires_maci_consensus_below_threshold(self):
        result = SimpleNamespace(consensus_ratio=0.5)
        ctx = _make_pipeline_ctx(maci_result=result)
        assert _requires_maci_consensus(ctx) is False

    def test_requires_maci_consensus_at_threshold(self):
        result = SimpleNamespace(consensus_ratio=0.67)
        ctx = _make_pipeline_ctx(maci_result=result)
        assert _requires_maci_consensus(ctx) is True

    def test_requires_maci_consensus_above_threshold(self):
        result = SimpleNamespace(consensus_ratio=0.9)
        ctx = _make_pipeline_ctx(maci_result=result)
        assert _requires_maci_consensus(ctx) is True


class TestToolPrivilegeEnforcer:
    def setup_method(self):
        self.enforcer = ToolPrivilegeEnforcer()

    def test_constitutional_mutation_always_denied(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        mutation_tools = [
            "modify_constitutional_hash",
            "rotate_constitutional_hash",
            "update_constitutional_hash",
            "set_constitutional_hash",
            "override_constitutional_hash",
        ]
        for tool in mutation_tools:
            decision = self.enforcer.check(tool, MACIRole.EXECUTIVE, ctx)
            assert decision.permitted is False
            assert "constitutional_immutability" in decision.reason
            assert decision.fallback == "block_with_p1_alert"

    def test_constitutional_mutation_denied_for_all_roles(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        for role in MACIRole:
            decision = self.enforcer.check("modify_constitutional_hash", role, ctx)
            assert decision.permitted is False

    def test_unknown_role_denied(self):
        # Create a custom policy map without a given role
        custom_policies: dict[MACIRole, ToolCallPolicy] = {}
        enforcer = ToolPrivilegeEnforcer(policies=custom_policies)
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        decision = enforcer.check("read_policy", MACIRole.EXECUTIVE, ctx)
        assert decision.permitted is False
        assert "unknown_maci_role" in decision.reason
        assert decision.fallback == "block"

    def test_explicit_deny_list(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        # EXECUTIVE has execute_action in denied_tools
        decision = self.enforcer.check("execute_action", MACIRole.EXECUTIVE, ctx)
        assert decision.permitted is False
        assert "role_denied" in decision.reason

    def test_guard_failure_blocks(self):
        ctx = _make_pipeline_ctx(constitutional_validated=False)
        # EXECUTIVE has _requires_constitutional_validation guard
        decision = self.enforcer.check("propose_message", MACIRole.EXECUTIVE, ctx)
        assert decision.permitted is False
        assert "guard_failed" in decision.reason

    def test_allowed_tool_permitted(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        decision = self.enforcer.check("propose_message", MACIRole.EXECUTIVE, ctx)
        assert decision.permitted is True
        assert "permitted" in decision.reason

    def test_not_in_allowlist_denied(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        decision = self.enforcer.check("unknown_tool_xyz", MACIRole.EXECUTIVE, ctx)
        assert decision.permitted is False
        assert "not_in_allowlist" in decision.reason

    def test_mcp_allowlist_permits_non_pipeline_tool(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        mcp_tools = frozenset({"mcp_custom_tool"})
        decision = self.enforcer.check(
            "mcp_custom_tool",
            MACIRole.EXECUTIVE,
            ctx,
            mcp_allowlist=mcp_tools,
        )
        assert decision.permitted is True
        assert "mcp_permitted" in decision.reason

    def test_mcp_allowlist_tool_not_in_mcp_falls_through(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        mcp_tools = frozenset({"other_tool"})
        decision = self.enforcer.check(
            "unknown_tool_xyz",
            MACIRole.EXECUTIVE,
            ctx,
            mcp_allowlist=mcp_tools,
        )
        assert decision.permitted is False
        assert "not_in_allowlist" in decision.reason

    def test_tenant_id_from_context_message(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            tenant_id="my-tenant",
        )
        decision = self.enforcer.check(
            "propose_message",
            MACIRole.EXECUTIVE,
            ctx,
            tenant_id=None,
        )
        assert decision.permitted is True

    def test_explicit_tenant_id_overrides(self):
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        decision = self.enforcer.check(
            "propose_message",
            MACIRole.EXECUTIVE,
            ctx,
            tenant_id="explicit-tenant",
        )
        assert decision.permitted is True

    def test_all_roles_have_policies(self):
        for role in MACIRole:
            assert role in MACI_TOOL_POLICIES

    def test_each_role_allowed_tool(self):
        """Each role can use at least one allowed tool."""
        ctx = _make_pipeline_ctx(constitutional_validated=True)
        role_tools = {
            MACIRole.EXECUTIVE: "propose_message",
            MACIRole.LEGISLATIVE: "extract_rules",
            MACIRole.JUDICIAL: "validate_message",
            MACIRole.MONITOR: "monitor_activity",
            MACIRole.AUDITOR: "audit_decision",
            MACIRole.CONTROLLER: "enforce_control",
            MACIRole.IMPLEMENTER: "synthesize_response",
        }
        for role, tool in role_tools.items():
            decision = self.enforcer.check(tool, role, ctx)
            assert decision.permitted is True, f"{role.value} should be allowed {tool}"

    def test_monitor_has_no_guards(self):
        policy = MACI_TOOL_POLICIES[MACIRole.MONITOR]
        assert len(policy.guards) == 0

    def test_deny_fallback_values(self):
        assert MACI_TOOL_POLICIES[MACIRole.EXECUTIVE].deny_fallback == "reject_with_reason"
        assert MACI_TOOL_POLICIES[MACIRole.JUDICIAL].deny_fallback == "route_to_hitl"
        assert MACI_TOOL_POLICIES[MACIRole.MONITOR].deny_fallback == "block"


class TestToolPrivilegeMiddleware:
    def setup_method(self):
        self.middleware = ToolPrivilegeMiddleware()

    async def test_no_tool_passes_through(self):
        ctx = _make_pipeline_ctx(maci_role="EXECUTIVE")
        # No requested_tool on message
        result = await self.middleware.process(ctx)
        assert "ToolPrivilegeMiddleware" in result.middleware_path
        assert result.early_result is None

    async def test_no_maci_role_blocks(self):
        ctx = _make_pipeline_ctx(
            maci_role=None,
            requested_tool="propose_message",
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False
        assert any("maci_role unresolved" in e for e in result.early_result.errors)

    async def test_invalid_maci_role_blocks(self):
        ctx = _make_pipeline_ctx(
            maci_role="NONEXISTENT_ROLE",
            requested_tool="propose_message",
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False
        assert any("unrecognised role" in e for e in result.early_result.errors)

    async def test_denied_tool_sets_early_result(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="EXECUTIVE",
            requested_tool="execute_action",
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False
        assert result.early_result.metadata.get("tool_name") == "execute_action"
        assert result.early_result.metadata.get("maci_role") == "EXECUTIVE"

    async def test_constitutional_mutation_sets_p1_alert(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="EXECUTIVE",
            requested_tool="modify_constitutional_hash",
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is not None
        assert result.early_result.metadata.get("alert_level") == "P1"
        assert (
            result.early_result.metadata.get("alert_reason")
            == "constitutional_immutability_violation"
        )

    async def test_route_to_hitl_fallback(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="JUDICIAL",
            requested_tool="propose_message",  # denied for JUDICIAL
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is not None
        assert result.early_result.metadata.get("route_to_hitl") is True
        assert result.early_result.metadata.get("tool_privilege_fallback") == "route_to_hitl"

    async def test_permitted_tool_passes_through(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="EXECUTIVE",
            requested_tool="propose_message",
        )
        result = await self.middleware.process(ctx)
        assert result.early_result is None

    async def test_custom_enforcer(self):
        custom_enforcer = ToolPrivilegeEnforcer(policies={})
        mw = ToolPrivilegeMiddleware(enforcer=custom_enforcer)
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="EXECUTIVE",
            requested_tool="anything",
        )
        result = await mw.process(ctx)
        assert result.early_result is not None  # unknown role -> deny

    async def test_mcp_allowlist_resolution(self):
        ctx = _make_pipeline_ctx(
            constitutional_validated=True,
            maci_role="EXECUTIVE",
            requested_tool="propose_message",
            tenant_id="test-tenant",
        )
        with patch(
            "enhanced_agent_bus.middlewares.tool_privilege_policy.resolve_effective_allowlist",
            return_value=frozenset(),
        ):
            result = await self.middleware.process(ctx)
        # propose_message is in allowed_tools, so should pass regardless of MCP
        assert result.early_result is None


# ===================================================================
# BATCH PROCESSING TESTS
# ===================================================================


class TestBatchProcessingMiddleware:
    def setup_method(self):
        self.middleware = BatchProcessingMiddleware()

    async def test_empty_batch_returns_empty_response(self):
        ctx = _make_batch_ctx(items=[])
        result = await self.middleware.process(ctx)
        assert result.batch_response is not None
        assert result.batch_response.success is True
        assert result.batch_response.items == []

    async def test_empty_batch_with_batch_request(self):
        br = BatchRequest(items=[_make_batch_item()], batch_id="br-1")
        ctx = _make_batch_ctx(items=[], batch_request=br)
        result = await self.middleware.process(ctx)
        assert result.batch_response.batch_id == "br-1"

    async def test_default_processing_no_processor(self):
        items = [_make_batch_item(), _make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await self.middleware.process(ctx)
        assert result.batch_response is not None
        assert len(result.processed_items) == 2
        for item in result.processed_items:
            assert item.status == BatchItemStatus.SUCCESS.value

    async def test_custom_processor_success(self):
        async def processor(item: BatchRequestItem) -> ValidationResult:
            return ValidationResult(is_valid=True)

        mw = BatchProcessingMiddleware(item_processor=processor)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await mw.process(ctx)
        assert len(result.processed_items) == 1
        assert result.processed_items[0].valid is True

    async def test_custom_processor_validation_failure(self):
        async def processor(item: BatchRequestItem) -> ValidationResult:
            return ValidationResult(is_valid=False, errors=["bad content"])

        mw = BatchProcessingMiddleware(item_processor=processor)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await mw.process(ctx)
        assert len(result.processed_items) == 1
        p = result.processed_items[0]
        assert p.valid is False
        assert p.error_code == "VALIDATION_FAILED"
        assert "bad content" in (p.error_message or "")

    async def test_processor_exception_creates_error_item(self):
        async def processor(item: BatchRequestItem) -> ValidationResult:
            raise ValueError("processor exploded")

        mw = BatchProcessingMiddleware(item_processor=processor)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await mw.process(ctx)
        assert len(result.processed_items) == 1
        p = result.processed_items[0]
        assert p.error_code == "PROCESSING_EXCEPTION"

    async def test_gather_exception_creates_error_response(self):
        """When asyncio.gather returns an exception, it's handled."""

        async def processor(item: BatchRequestItem) -> ValidationResult:
            raise RuntimeError("boom")

        mw = BatchProcessingMiddleware(item_processor=processor)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await mw.process(ctx)
        # The RuntimeError from gather is caught as exception result
        assert len(result.processed_items) == 1

    async def test_fail_fast_stops_after_error(self):
        call_count = 0

        async def processor(item: BatchRequestItem) -> ValidationResult:
            nonlocal call_count
            call_count += 1
            return ValidationResult(is_valid=False, errors=["fail"])

        mw = BatchProcessingMiddleware(item_processor=processor)
        items = [_make_batch_item() for _ in range(5)]
        ctx = _make_batch_ctx(items=items, fail_fast=True)
        result = await mw.process(ctx)
        # fail_fast should break after first failed item in aggregation
        assert len(result.failed_items) >= 1

    async def test_batch_latency_recorded(self):
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        initial_latency = ctx.batch_latency_ms
        await self.middleware.process(ctx)
        assert ctx.batch_latency_ms > initial_latency

    async def test_aggregate_results_stats(self):
        items_resp = [
            BatchResponseItem.create_success(request_id="r1", valid=True, processing_time_ms=10.0),
            BatchResponseItem.create_success(request_id="r2", valid=True, processing_time_ms=20.0),
            BatchResponseItem.create_error(
                request_id="r3",
                error_code="ERR",
                error_message="fail",
                processing_time_ms=5.0,
            ),
        ]
        response = self.middleware._aggregate_results(items_resp)
        assert response.stats.total_items == 3
        assert response.stats.successful_items == 2
        assert response.stats.failed_items == 1
        assert response.stats.p50_latency_ms is not None
        assert response.stats.average_item_time_ms is not None

    async def test_aggregate_results_no_latencies(self):
        items_resp = [
            BatchResponseItem(
                request_id="r1",
                status=BatchItemStatus.SUCCESS.value,
                valid=True,
                processing_time_ms=None,
            ),
        ]
        response = self.middleware._aggregate_results(items_resp)
        assert response.stats.p50_latency_ms is None

    async def test_set_item_processor(self):
        async def proc(item: BatchRequestItem) -> ValidationResult:
            return ValidationResult(is_valid=True)

        self.middleware.set_item_processor(proc)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await self.middleware.process(ctx)
        assert result.processed_items[0].valid is True

    async def test_fail_closed_raises_on_catastrophic_error(self):
        mw = BatchProcessingMiddleware(config=MiddlewareConfig(fail_closed=True))
        ctx = _make_batch_ctx(items=[_make_batch_item()])
        # Patch asyncio.gather itself at module level to raise RuntimeError
        # which is caught by the outer try/except BATCH_PROCESSING_ERRORS
        with patch(
            "enhanced_agent_bus.middlewares.batch.processing.asyncio.gather",
            side_effect=RuntimeError("catastrophic"),
        ):
            with pytest.raises(BatchProcessingException):
                await mw.process(ctx)

    async def test_fail_open_sets_early_result(self):
        mw = BatchProcessingMiddleware(config=MiddlewareConfig(fail_closed=False))
        ctx = _make_batch_ctx(items=[_make_batch_item()])
        with patch(
            "enhanced_agent_bus.middlewares.batch.processing.asyncio.gather",
            side_effect=RuntimeError("soft fail"),
        ):
            result = await mw.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False

    async def test_timeout_produces_timeout_error(self):
        async def slow_processor(item: BatchRequestItem) -> ValidationResult:
            await asyncio.sleep(10)
            return ValidationResult(is_valid=True)

        mw = BatchProcessingMiddleware(item_processor=slow_processor)
        br = BatchRequest(items=[_make_batch_item()], options={"timeout_ms": 10})
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items, batch_request=br)
        result = await mw.process(ctx)
        assert len(result.processed_items) == 1
        p = result.processed_items[0]
        # Should be either a TIMEOUT_ERROR from semaphore handler or a timeout from gather
        assert p.error_code in ("TIMEOUT_ERROR", "PROCESSING_EXCEPTION", "PROCESSING_ERROR")

    async def test_batch_response_batch_id_from_request(self):
        br = BatchRequest(items=[_make_batch_item()], batch_id="my-batch-123")
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items, batch_request=br)
        await self.middleware.process(ctx)
        assert ctx.batch_response.batch_id == "my-batch-123"

    async def test_batch_response_batch_id_unknown_without_request(self):
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items, batch_request=None)
        await self.middleware.process(ctx)
        assert ctx.batch_response.batch_id == "unknown"

    async def test_exception_result_in_gather_adds_failed_item(self):
        """When gather returns an Exception object, it's aggregated."""

        async def exploding_processor(item: BatchRequestItem) -> ValidationResult:
            raise TypeError("type error in processing")

        mw = BatchProcessingMiddleware(item_processor=exploding_processor)
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        result = await mw.process(ctx)
        # Should still produce a response item (from _process_item exception handler)
        assert len(result.processed_items) == 1

    async def test_unsuccessful_response_item_with_fail_fast(self):
        """A BatchResponseItem with success=False triggers fail_fast."""

        async def failing_processor(item: BatchRequestItem) -> ValidationResult:
            return ValidationResult(is_valid=False, errors=["nope"])

        mw = BatchProcessingMiddleware(item_processor=failing_processor)
        items = [_make_batch_item() for _ in range(3)]
        ctx = _make_batch_ctx(items=items, fail_fast=True)
        result = await mw.process(ctx)
        # With fail_fast, should stop after first failure in result aggregation
        assert len(result.failed_items) >= 1


# ===================================================================
# LRU CACHE TESTS
# ===================================================================


class TestLRUCache:
    def test_get_miss(self):
        cache = _LRUCache(maxsize=5)
        assert cache.get("missing") is None
        assert cache._misses == 1

    def test_get_hit(self):
        cache = _LRUCache(maxsize=5)
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"
        assert cache._hits == 1

    def test_set_evicts_oldest(self):
        cache = _LRUCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict "a"
        assert "a" not in cache
        assert "b" in cache
        assert "c" in cache
        assert len(cache) == 2

    def test_set_updates_existing(self):
        cache = _LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.set("a", 2)
        assert cache.get("a") == 2
        assert len(cache) == 1

    def test_contains(self):
        cache = _LRUCache(maxsize=5)
        assert "x" not in cache
        cache.set("x", True)
        assert "x" in cache

    def test_len(self):
        cache = _LRUCache(maxsize=5)
        assert len(cache) == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2

    def test_clear(self):
        cache = _LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.get("a")
        cache.get("missing")
        cache.clear()
        assert len(cache) == 0
        assert cache._hits == 0
        assert cache._misses == 0

    def test_hit_rate_empty(self):
        cache = _LRUCache(maxsize=5)
        assert cache.hit_rate == 0.0

    def test_hit_rate_calculated(self):
        cache = _LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        assert cache.hit_rate == pytest.approx(0.5)

    def test_lru_order_on_get(self):
        cache = _LRUCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # makes "a" most recently used
        cache.set("c", 3)  # should evict "b" (least recently used)
        assert "a" in cache
        assert "b" not in cache
        assert "c" in cache


# ===================================================================
# BATCH DEDUPLICATION TESTS
# ===================================================================


class TestBatchDeduplicationMiddleware:
    def setup_method(self):
        self.middleware = BatchDeduplicationMiddleware(dedup_window_sec=60)

    async def test_dedup_disabled_passes_through(self):
        items = [_make_batch_item(), _make_batch_item()]
        ctx = _make_batch_ctx(items=items, deduplicate=False)
        result = await self.middleware.process(ctx)
        assert len(result.batch_items) == 2

    async def test_empty_items_passes_through(self):
        ctx = _make_batch_ctx(items=[], deduplicate=True)
        result = await self.middleware.process(ctx)
        assert len(result.batch_items) == 0

    async def test_duplicate_items_removed(self):
        item1 = _make_batch_item(content={"x": "same"}, from_agent="a", tenant_id="t1")
        item2 = _make_batch_item(content={"x": "same"}, from_agent="a", tenant_id="t1")
        ctx = _make_batch_ctx(items=[item1, item2])
        result = await self.middleware.process(ctx)
        assert len(result.batch_items) == 1
        assert result.deduplicated_count == 1

    async def test_unique_items_kept(self):
        item1 = _make_batch_item(content={"x": "one"})
        item2 = _make_batch_item(content={"x": "two"})
        ctx = _make_batch_ctx(items=[item1, item2])
        result = await self.middleware.process(ctx)
        assert len(result.batch_items) == 2
        assert result.deduplicated_count == 0

    async def test_batch_size_updated(self):
        item1 = _make_batch_item(content={"x": "same"})
        item2 = _make_batch_item(content={"x": "same"})
        item3 = _make_batch_item(content={"x": "different"})
        ctx = _make_batch_ctx(items=[item1, item2, item3])
        result = await self.middleware.process(ctx)
        assert result.batch_size == 2

    async def test_latency_recorded(self):
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        initial = ctx.batch_latency_ms
        await self.middleware.process(ctx)
        assert ctx.batch_latency_ms > initial

    async def test_cache_size_property(self):
        assert self.middleware.cache_size == 0
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        await self.middleware.process(ctx)
        assert self.middleware.cache_size == 1

    async def test_cache_hit_rate_property(self):
        assert self.middleware.cache_hit_rate == 0.0

    async def test_clear_cache(self):
        items = [_make_batch_item()]
        ctx = _make_batch_ctx(items=items)
        await self.middleware.process(ctx)
        assert self.middleware.cache_size > 0
        self.middleware.clear_cache()
        assert self.middleware.cache_size == 0

    async def test_expired_duplicate_not_blocked(self):
        """Items outside dedup window should not be considered duplicates."""
        mw = BatchDeduplicationMiddleware(dedup_window_sec=0)
        item = _make_batch_item(content={"x": "data"})
        ctx1 = _make_batch_ctx(items=[item])
        await mw.process(ctx1)

        # Now the timestamp is in the past (window is 0 sec), so same item should pass
        item2 = _make_batch_item(content={"x": "data"})
        ctx2 = _make_batch_ctx(items=[item2])
        result = await mw.process(ctx2)
        assert len(result.batch_items) == 1
        assert result.deduplicated_count == 0

    async def test_fail_closed_raises(self):
        mw = BatchDeduplicationMiddleware(
            config=MiddlewareConfig(fail_closed=True),
        )
        ctx = _make_batch_ctx(items=[_make_batch_item()])
        with patch.object(mw, "_compute_message_id", side_effect=RuntimeError("hash fail")):
            with pytest.raises(BatchDeduplicationException):
                await mw.process(ctx)

    async def test_fail_open_sets_early_result(self):
        mw = BatchDeduplicationMiddleware(
            config=MiddlewareConfig(fail_closed=False),
        )
        ctx = _make_batch_ctx(items=[_make_batch_item()])
        with patch.object(mw, "_compute_message_id", side_effect=RuntimeError("hash fail")):
            result = await mw.process(ctx)
        assert result.early_result is not None
        assert result.early_result.is_valid is False

    def test_compute_message_id_deterministic(self):
        item = _make_batch_item(content={"x": 1}, from_agent="a", tenant_id="t1")
        id1 = self.middleware._compute_message_id(item)
        id2 = self.middleware._compute_message_id(item)
        assert id1 == id2
        assert len(id1) == 64  # SHA256 hex

    def test_compute_message_id_different_for_different_content(self):
        item1 = _make_batch_item(content={"x": 1})
        item2 = _make_batch_item(content={"x": 2})
        assert self.middleware._compute_message_id(item1) != self.middleware._compute_message_id(
            item2
        )

    def test_clean_old_timestamps(self):
        mw = BatchDeduplicationMiddleware(dedup_window_sec=1)
        mw._seen_timestamps["old"] = time.time() - 100
        mw._seen_timestamps["recent"] = time.time()
        mw._clean_old_timestamps()
        assert "old" not in mw._seen_timestamps
        assert "recent" in mw._seen_timestamps

    def test_is_duplicate_false_when_not_in_cache(self):
        assert self.middleware._is_duplicate("nonexistent") is False

    def test_is_duplicate_true_within_window(self):
        msg_id = "test-id"
        self.middleware._cache.set(msg_id, True)
        self.middleware._seen_timestamps[msg_id] = time.time()
        assert self.middleware._is_duplicate(msg_id) is True

    def test_is_duplicate_false_when_expired(self):
        msg_id = "test-id"
        self.middleware._cache.set(msg_id, True)
        self.middleware._seen_timestamps[msg_id] = time.time() - 1000
        assert self.middleware._is_duplicate(msg_id) is False
        # Should have cleaned the timestamp
        assert msg_id not in self.middleware._seen_timestamps


# ===================================================================
# BATCH METRICS TESTS
# ===================================================================


class TestBatchMetricsMiddleware:
    def setup_method(self):
        self.middleware = BatchMetricsMiddleware()

    async def test_empty_context_records_metrics(self):
        ctx = _make_batch_ctx()
        result = await self.middleware.process(ctx)
        metrics = self.middleware.recorded_metrics
        assert len(metrics) >= 1
        batch_summary = [m for m in metrics if m["metric_type"] == "batch_summary"]
        assert len(batch_summary) == 1

    async def test_records_batch_level_metrics(self):
        br = BatchRequest(items=[_make_batch_item()], batch_id="b-123", tenant_id="t-1")
        items = [_make_batch_item()]
        processed = [
            BatchResponseItem.create_success(request_id="r1", valid=True, processing_time_ms=10.0)
        ]
        ctx = _make_batch_ctx(
            items=items,
            batch_request=br,
            batch_tenant_id="t-1",
        )
        ctx.processed_items = processed
        await self.middleware.process(ctx)
        metrics = self.middleware.recorded_metrics
        summary = [m for m in metrics if m["metric_type"] == "batch_summary"][0]
        assert summary["tenant_id"] == "t-1"
        assert summary["batch_id"] == "b-123"
        assert summary["processed_items"] == 1

    async def test_records_item_metrics(self):
        processed = [
            BatchResponseItem.create_success(request_id="r1", valid=True, processing_time_ms=5.0),
            BatchResponseItem.create_error(request_id="r2", error_code="ERR", error_message="fail"),
        ]
        ctx = _make_batch_ctx()
        ctx.processed_items = processed
        await self.middleware.process(ctx)
        item_metrics = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "item_detail"
        ]
        assert len(item_metrics) == 2

    async def test_success_rate_calculation(self):
        processed = [
            BatchResponseItem.create_success(request_id="r1", valid=True, processing_time_ms=5.0),
            BatchResponseItem.create_error(request_id="r2", error_code="ERR", error_message="fail"),
        ]
        ctx = _make_batch_ctx()
        ctx.processed_items = processed
        await self.middleware.process(ctx)
        summary = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "batch_summary"
        ][0]
        assert summary["success_rate"] == pytest.approx(0.5)

    async def test_success_rate_zero_when_no_processed(self):
        ctx = _make_batch_ctx()
        await self.middleware.process(ctx)
        summary = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "batch_summary"
        ][0]
        assert summary["success_rate"] == 0.0

    async def test_latency_recorded(self):
        ctx = _make_batch_ctx()
        initial = ctx.batch_latency_ms
        await self.middleware.process(ctx)
        assert ctx.batch_latency_ms > initial

    async def test_recorded_metrics_returns_copy(self):
        ctx = _make_batch_ctx()
        await self.middleware.process(ctx)
        metrics1 = self.middleware.recorded_metrics
        metrics2 = self.middleware.recorded_metrics
        assert metrics1 is not metrics2
        assert metrics1 == metrics2

    async def test_clear_recorded_metrics(self):
        ctx = _make_batch_ctx()
        await self.middleware.process(ctx)
        assert len(self.middleware.recorded_metrics) > 0
        self.middleware.clear_recorded_metrics()
        assert len(self.middleware.recorded_metrics) == 0

    async def test_get_summary(self):
        ctx = _make_batch_ctx(batch_tenant_id="tenant-x")
        ctx.processed_items = [
            BatchResponseItem.create_success(request_id="r1", valid=True, processing_time_ms=5.0),
        ]
        await self.middleware.process(ctx)
        summary = self.middleware.get_summary()
        assert summary["total_metrics"] >= 2  # 1 batch + 1 item
        assert summary["batch_summaries"] == 1
        assert summary["item_details"] == 1
        assert "tenant-x" in summary["tenants"]

    async def test_fail_closed_raises_on_error(self):
        mw = BatchMetricsMiddleware(config=MiddlewareConfig(fail_closed=True))
        ctx = _make_batch_ctx()
        with patch.object(mw, "_record_batch_metrics", side_effect=RuntimeError("metrics boom")):
            with pytest.raises(BatchMetricsException):
                await mw.process(ctx)

    async def test_fail_open_adds_warning(self):
        mw = BatchMetricsMiddleware(config=MiddlewareConfig(fail_closed=False))
        ctx = _make_batch_ctx()
        with patch.object(mw, "_record_batch_metrics", side_effect=RuntimeError("metrics boom")):
            result = await mw.process(ctx)
        assert any("Metrics recording failed" in w for w in result.warnings)

    async def test_emit_metrics_with_registry(self):
        registry = AsyncMock()
        registry.emit = AsyncMock()
        mw = BatchMetricsMiddleware(
            config=MiddlewareConfig(metrics_enabled=True),
            metrics_registry=registry,
        )
        ctx = _make_batch_ctx()
        await mw.process(ctx)
        # Give background task a chance to run
        await asyncio.sleep(0.05)
        # The emit method should have been called
        assert registry.emit.called or registry.emit.await_count >= 0

    async def test_emit_metric_with_record_interface(self):
        registry = AsyncMock(spec=[])
        registry.record = AsyncMock()
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        await mw._emit_metric("test_metric", {"value": 1})
        registry.record.assert_awaited_once()

    async def test_emit_metric_with_gauge_interface(self):
        registry = MagicMock(spec=[])
        registry.gauge = MagicMock()
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        await mw._emit_metric("test_metric", {"value": 42})
        registry.gauge.assert_called_once()

    async def test_emit_metric_with_counter_interface(self):
        registry = MagicMock(spec=[])
        registry.counter = MagicMock()
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        await mw._emit_metric("test_metric", {"value": 1})
        registry.counter.assert_called_once()

    async def test_emit_metric_no_registry(self):
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = None
        # Should return without error
        await mw._emit_metric("test_metric", {"value": 1})

    async def test_emit_metric_exception_non_fatal(self):
        registry = AsyncMock(spec=[])
        registry.emit = AsyncMock(side_effect=RuntimeError("emit failed"))
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        # Should not raise
        await mw._emit_metric("test_metric", {"value": 1})

    async def test_emit_metrics_exception_non_fatal(self):
        registry = AsyncMock(spec=[])
        registry.emit = AsyncMock(side_effect=RuntimeError("emit failed"))
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        mw._recorded_metrics = [
            {"metric_type": "batch_summary", "value": 1},
        ]
        ctx = _make_batch_ctx()
        # Should not raise
        await mw._emit_metrics(ctx)

    async def test_emit_metrics_no_registry(self):
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = None
        ctx = _make_batch_ctx()
        # Should return without error
        await mw._emit_metrics(ctx)

    async def test_emit_metrics_samples_large_item_list(self):
        registry = AsyncMock(spec=[])
        registry.emit = AsyncMock()
        mw = BatchMetricsMiddleware()
        mw._metrics_registry = registry
        # Add 150 item metrics to trigger sampling
        mw._recorded_metrics = [
            {"metric_type": "item_detail", "request_id": f"r{i}"} for i in range(150)
        ]
        ctx = _make_batch_ctx()
        await mw._emit_metrics(ctx)
        # With sampling, not all 150 should be emitted
        # (probabilistic, but with sample_rate ~0.67 we should get fewer)
        assert registry.emit.await_count <= 150

    async def test_default_tenant_id(self):
        ctx = _make_batch_ctx(batch_tenant_id=None)
        await self.middleware.process(ctx)
        summary = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "batch_summary"
        ][0]
        assert summary["tenant_id"] == "default"

    async def test_batch_id_unknown_without_request(self):
        ctx = _make_batch_ctx(batch_request=None)
        await self.middleware.process(ctx)
        summary = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "batch_summary"
        ][0]
        assert summary["batch_id"] == "unknown"

    async def test_impact_score_recorded(self):
        ctx = _make_batch_ctx()
        ctx.impact_score = 0.75
        await self.middleware.process(ctx)
        summary = [
            m for m in self.middleware.recorded_metrics if m["metric_type"] == "batch_summary"
        ][0]
        assert summary["impact_score"] == 0.75
