"""Tests for mcp.router module.

Covers ToolCategory, _classify_tool, _ServerCircuitBreaker,
ToolRequest/ToolResponse models, MCPRouter lifecycle/discovery/execution/intent,
and helper functions.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp.router import (
    _CB_COOLDOWN_SECONDS,
    _CB_FAILURE_THRESHOLD,
    MCPRouter,
    ToolCategory,
    ToolRequest,
    ToolResponse,
    _build_error_response,
    _CircuitState,
    _classify_tool,
    _elapsed_ms,
    _ServerCircuitBreaker,
    pool_size_attr,
)
from enhanced_agent_bus.mcp.types import MCPTool, MCPToolResult, MCPToolStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    name: str = "test_tool",
    tags: list[str] | None = None,
    server_id: str = "srv1",
    description: str = "A test tool",
) -> MCPTool:
    return MCPTool(
        name=name,
        description=description,
        input_schema={},
        server_id=server_id,
        tags=tags or [],
    )


def _make_pool_mock(
    tools: list[MCPTool] | None = None, server_ids: list[str] | None = None
) -> MagicMock:
    pool = MagicMock()
    pool.client_count = len(server_ids or ["srv1"])
    pool.server_ids = MagicMock(return_value=server_ids or ["srv1"])
    pool.list_tools = AsyncMock(return_value=tools or [])
    pool.connect_all = AsyncMock()
    pool.disconnect_all = AsyncMock()
    pool.call_tool = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# Tool classification
# ---------------------------------------------------------------------------


class TestClassifyTool:
    def test_database_tool(self):
        tool = _make_tool(name="query_database")
        assert _classify_tool(tool) == ToolCategory.DATABASE

    def test_neural_tool(self):
        tool = _make_tool(name="predict_pattern")
        assert _classify_tool(tool) == ToolCategory.NEURAL

    def test_hitl_tool(self):
        tool = _make_tool(name="human_review")
        assert _classify_tool(tool) == ToolCategory.HITL

    def test_general_tool(self):
        tool = _make_tool(name="send_email")
        assert _classify_tool(tool) == ToolCategory.GENERAL

    def test_tag_based_classification(self):
        tool = _make_tool(name="do_something", tags=["neural"])
        assert _classify_tool(tool) == ToolCategory.NEURAL

    def test_precedence_database_over_neural(self):
        tool = _make_tool(name="query_model")
        # "query" is database keyword, "model" is neural
        # database has higher precedence
        assert _classify_tool(tool) == ToolCategory.DATABASE


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestServerCircuitBreaker:
    def test_initial_state_closed(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        assert cb.state == _CircuitState.CLOSED
        assert cb.is_open() is False
        assert cb.allow_request() is True

    def test_failures_below_threshold_stay_closed(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == _CircuitState.CLOSED

    def test_failures_at_threshold_open(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.state == _CircuitState.OPEN
        assert cb.is_open() is True
        assert cb.allow_request() is False

    def test_success_resets_to_closed(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        cb.record_success()
        assert cb.state == _CircuitState.CLOSED

    def test_half_open_after_cooldown(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        # Simulate cooldown elapsed
        cb._last_failure_at = time.monotonic() - _CB_COOLDOWN_SECONDS - 1
        assert cb.state == _CircuitState.HALF_OPEN
        # First caller gets through (probe)
        assert cb.allow_request() is True
        # Second concurrent caller rejected
        assert cb.allow_request() is False

    def test_as_dict(self):
        cb = _ServerCircuitBreaker(server_id="s1")
        d = cb.as_dict()
        assert d["server_id"] == "s1"
        assert d["state"] == "closed"
        assert d["failure_count"] == 0


# ---------------------------------------------------------------------------
# ToolRequest / ToolResponse
# ---------------------------------------------------------------------------


class TestToolRequestResponse:
    def test_tool_request_defaults(self):
        r = ToolRequest(tool_name="my_tool")
        assert r.tool_name == "my_tool"
        assert r.arguments == {}
        assert r.agent_id == ""

    def test_tool_response_is_success(self):
        r = ToolResponse(
            tool_name="t",
            server_id="s",
            status=MCPToolStatus.SUCCESS.value,
        )
        assert r.is_success is True

    def test_tool_response_is_not_success(self):
        r = ToolResponse(
            tool_name="t",
            server_id="s",
            status=MCPToolStatus.ERROR.value,
        )
        assert r.is_success is False


# ---------------------------------------------------------------------------
# MCPRouter lifecycle
# ---------------------------------------------------------------------------


class TestMCPRouterLifecycle:
    @pytest.mark.asyncio
    async def test_start_connects_and_discovers(self):
        pool = _make_pool_mock(tools=[_make_tool()])
        router = MCPRouter(pool=pool)
        await router.start()
        pool.connect_all.assert_awaited_once()
        pool.list_tools.assert_awaited()
        assert router._started is True

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        await router.start()
        await router.start()
        assert pool.connect_all.await_count == 1

    @pytest.mark.asyncio
    async def test_stop(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        await router.start()
        await router.stop()
        pool.disconnect_all.assert_awaited_once()
        assert router._started is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        await router.stop()
        pool.disconnect_all.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        async with router.lifespan() as r:
            assert r is router
            assert router._started is True
        assert router._started is False


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------


class TestMCPRouterDiscovery:
    @pytest.mark.asyncio
    async def test_discover_categorises_tools(self):
        tools = [
            _make_tool(name="query_db"),
            _make_tool(name="predict_score"),
            _make_tool(name="human_review"),
            _make_tool(name="send_email"),
        ]
        pool = _make_pool_mock(tools=tools)
        router = MCPRouter(pool=pool)
        categories = await router.discover_tools()
        assert len(categories["database"]) == 1
        assert len(categories["neural"]) == 1
        assert len(categories["hitl"]) == 1
        assert len(categories["general"]) == 1

    @pytest.mark.asyncio
    async def test_discover_skips_open_circuit_server(self):
        tool = _make_tool(name="query_db", server_id="bad_srv")
        pool = _make_pool_mock(tools=[tool])
        router = MCPRouter(pool=pool)
        # Trip the breaker for bad_srv
        breaker = router._get_breaker("bad_srv")
        for _ in range(_CB_FAILURE_THRESHOLD):
            breaker.record_failure()
        categories = await router.discover_tools()
        assert len(categories["database"]) == 0

    @pytest.mark.asyncio
    async def test_discover_handles_pool_error(self):
        pool = _make_pool_mock()
        pool.list_tools = AsyncMock(side_effect=RuntimeError("pool down"))
        router = MCPRouter(pool=pool)
        categories = await router.discover_tools()
        assert all(len(v) == 0 for v in categories.values())


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


class TestMCPRouterExecution:
    @pytest.mark.asyncio
    async def test_execute_tool_requires_maci_role(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        resp = await router.execute_tool(ToolRequest(tool_name="my_tool"))
        assert resp.status == MCPToolStatus.FORBIDDEN.value
        error = resp.error or ""
        assert "maci role" in error.lower()
        assert "required" in error or "unknown or unmapped" in error
        pool.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_tool_rejects_unknown_maci_role(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        req = ToolRequest(tool_name="my_tool", maci_role="unknown_role")
        resp = await router.execute_tool(req)
        assert resp.status == MCPToolStatus.FORBIDDEN.value
        assert "unknown or unmapped" in (resp.error or "")
        pool.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        req = ToolRequest(tool_name="nonexistent", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.status == MCPToolStatus.ERROR.value
        assert "not found" in (resp.error or "")

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        pool.call_tool = AsyncMock(
            return_value=MCPToolResult(
                tool_name="my_tool",
                status=MCPToolStatus.SUCCESS,
                content={"result": 42},
            )
        )
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        req = ToolRequest(tool_name="my_tool", agent_id="a1", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.is_success is True
        assert resp.content == {"result": 42}

    @pytest.mark.asyncio
    async def test_execute_tool_error_triggers_circuit_breaker(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        pool.call_tool = AsyncMock(
            return_value=MCPToolResult(
                tool_name="my_tool",
                status=MCPToolStatus.ERROR,
                error="backend failure",
            )
        )
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        req = ToolRequest(tool_name="my_tool", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.status == MCPToolStatus.ERROR.value

        breaker = router._get_breaker("srv1")
        assert breaker._failure_count == 1

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        pool.call_tool = AsyncMock(side_effect=RuntimeError("connection refused"))
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        req = ToolRequest(tool_name="my_tool", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.status == MCPToolStatus.ERROR.value
        assert "connection refused" in (resp.error or "")

    @pytest.mark.asyncio
    async def test_execute_tool_circuit_open_rejects(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        breaker = router._get_breaker("srv1")
        for _ in range(_CB_FAILURE_THRESHOLD):
            breaker.record_failure()

        req = ToolRequest(tool_name="my_tool", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.status == MCPToolStatus.ERROR.value
        assert "Circuit breaker OPEN" in (resp.error or "")

    @pytest.mark.asyncio
    async def test_execute_tool_with_server_hint(self):
        tool = _make_tool(name="my_tool", server_id="specific")
        pool = _make_pool_mock(tools=[tool], server_ids=["specific"])
        pool.call_tool = AsyncMock(
            return_value=MCPToolResult(
                tool_name="my_tool",
                status=MCPToolStatus.SUCCESS,
                content="ok",
            )
        )
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        req = ToolRequest(tool_name="my_tool", server_id="specific", maci_role="executive")
        resp = await router.execute_tool(req)
        assert resp.is_success

    @pytest.mark.asyncio
    async def test_execute_tool_forbidden_resets_breaker(self):
        tool = _make_tool(name="my_tool")
        pool = _make_pool_mock(tools=[tool])
        pool.call_tool = AsyncMock(
            return_value=MCPToolResult(
                tool_name="my_tool",
                status=MCPToolStatus.FORBIDDEN,
                error="role restriction",
            )
        )
        router = MCPRouter(pool=pool)
        await router.discover_tools()
        # Add a failure first
        router._get_breaker("srv1").record_failure()

        req = ToolRequest(tool_name="my_tool", maci_role="executive")
        await router.execute_tool(req)
        assert router._get_breaker("srv1")._failure_count == 0


# ---------------------------------------------------------------------------
# Intent-based lookup
# ---------------------------------------------------------------------------


class TestMCPRouterIntent:
    @pytest.mark.asyncio
    async def test_get_tools_for_intent(self):
        tools = [
            _make_tool(name="query_database", description="Query the main database"),
            _make_tool(name="send_email", description="Send notification email"),
        ]
        pool = _make_pool_mock(tools=tools)
        router = MCPRouter(pool=pool)
        await router.discover_tools()

        results = await router.get_tools_for_intent("query database for policies")
        assert len(results) >= 1
        assert results[0].name == "query_database"

    @pytest.mark.asyncio
    async def test_get_tools_for_intent_empty_tokens(self):
        pool = _make_pool_mock(tools=[_make_tool()])
        router = MCPRouter(pool=pool)
        await router.discover_tools()
        # Short tokens (<=2 chars) are filtered out
        results = await router.get_tools_for_intent("a b c")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_tools_for_intent_triggers_discover(self):
        pool = _make_pool_mock(tools=[_make_tool(name="send_email")])
        router = MCPRouter(pool=pool)
        # Do NOT call discover_tools first
        results = await router.get_tools_for_intent("send email notification")
        # discover_tools should have been triggered
        pool.list_tools.assert_awaited()


# ---------------------------------------------------------------------------
# Circuit breaker introspection
# ---------------------------------------------------------------------------


class TestMCPRouterCircuitIntrospection:
    def test_circuit_breaker_metrics_empty(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        assert router.circuit_breaker_metrics() == {}

    def test_circuit_breaker_metrics_with_data(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        router._get_breaker("s1").record_failure()
        metrics = router.circuit_breaker_metrics()
        assert "s1" in metrics

    def test_reset_circuit_breaker(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        breaker = router._get_breaker("s1")
        for _ in range(_CB_FAILURE_THRESHOLD):
            breaker.record_failure()
        router.reset_circuit_breaker("s1")
        assert breaker.state == _CircuitState.CLOSED

    def test_reset_circuit_breaker_noop(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        # Should not raise
        router.reset_circuit_breaker("nonexistent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestRouterHelpers:
    def test_elapsed_ms(self):
        t = time.monotonic()
        ms = _elapsed_ms(t)
        assert ms >= 0

    def test_pool_size_attr(self):
        pool = MagicMock()
        pool.client_count = 5
        assert pool_size_attr(pool) == "5"

    def test_build_error_response(self):
        req = ToolRequest(tool_name="t1", agent_id="a1")
        resp = _build_error_response(
            request=req,
            server_id="s1",
            error="fail",
            latency_ms=5.0,
            request_id="r1",
            tool=None,
        )
        assert resp.status == MCPToolStatus.ERROR.value
        assert resp.error == "fail"

    def test_repr(self):
        pool = _make_pool_mock()
        router = MCPRouter(pool=pool)
        r = repr(router)
        assert "MCPRouter" in r
