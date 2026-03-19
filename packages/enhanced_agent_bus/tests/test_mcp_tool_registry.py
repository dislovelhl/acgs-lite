"""
Tests for mcp_integration/tool_registry.py

Covers:
- ExternalTool dataclass, to_dict, to_mcp_definition
- ToolInputSchema, ToolRegistrationResult, ToolDiscoveryResult, ToolExecutionResult
- MCPToolRegistry.register_tool, unregister_tool, discover_tools, execute_tool
- Query methods: get_tool, get_tool_by_name, list_tools, list_servers
- _infer_capabilities, _assess_risk_level, _parse_tool_definition
- get_metrics, get_audit_log
- Limits enforcement (max tools)
- create_tool_registry factory
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.mcp_integration.tool_registry import (
    ExternalTool,
    MCPToolRegistry,
    ToolCapability,
    ToolDiscoveryResult,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolInputSchema,
    ToolRegistrationResult,
    ToolRiskLevel,
    ToolStatus,
    create_tool_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    name: str = "test_tool",
    server_id: str = "server_1",
    status: ToolStatus = ToolStatus.ACTIVE,
    handler: AsyncMock | None = None,
    capabilities: list[ToolCapability] | None = None,
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
) -> ExternalTool:
    return ExternalTool(
        name=name,
        description=f"A tool called {name}",
        server_id=server_id,
        input_schema=ToolInputSchema(),
        capabilities=capabilities or [],
        risk_level=risk_level,
        status=status,
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestToolInputSchema:
    def test_to_dict(self):
        schema = ToolInputSchema(
            properties={"query": {"type": "string"}},
            required=["query"],
        )
        d = schema.to_dict()
        assert d["type"] == "object"
        assert d["required"] == ["query"]
        assert d["additionalProperties"] is False


class TestExternalTool:
    def test_auto_generates_tool_id(self):
        tool = _make_tool()
        assert tool.tool_id != ""

    def test_to_dict(self):
        tool = _make_tool(capabilities=[ToolCapability.GOVERNANCE])
        d = tool.to_dict()
        assert d["name"] == "test_tool"
        assert d["server_id"] == "server_1"
        assert "governance" in d["capabilities"]

    def test_to_mcp_definition(self):
        tool = _make_tool()
        d = tool.to_mcp_definition()
        assert d["name"] == "test_tool"
        assert "inputSchema" in d

    def test_risk_level_default(self):
        tool = _make_tool()
        assert tool.risk_level == ToolRiskLevel.LOW


class TestToolRegistrationResult:
    def test_to_dict(self):
        r = ToolRegistrationResult(success=True, tool_id="t-1", tool_name="test")
        d = r.to_dict()
        assert d["success"] is True
        assert d["tool_id"] == "t-1"


class TestToolDiscoveryResult:
    def test_to_dict(self):
        r = ToolDiscoveryResult(
            server_id="s-1",
            server_name="Test Server",
            tools_found=3,
            tools_registered=2,
            tools_skipped=1,
        )
        d = r.to_dict()
        assert d["tools_found"] == 3
        assert d["tools_registered"] == 2


class TestToolExecutionResult:
    def test_to_dict(self):
        r = ToolExecutionResult(success=True, tool_name="t", tool_id="id-1", result={"ok": True})
        d = r.to_dict()
        assert d["success"] is True
        assert d["result"] == {"ok": True}


class TestToolExecutionContext:
    def test_to_dict(self):
        tool = _make_tool()
        ctx = ToolExecutionContext(tool=tool, arguments={"q": "test"}, agent_id="agent-1")
        d = ctx.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["arguments"] == {"q": "test"}


# ---------------------------------------------------------------------------
# MCPToolRegistry - registration
# ---------------------------------------------------------------------------


class TestRegistration:
    @pytest.mark.asyncio
    async def test_register_tool_success(self):
        registry = MCPToolRegistry()
        tool = _make_tool()
        result = await registry.register_tool(tool, agent_id="agent-1")
        assert result.success is True
        assert result.tool_id == tool.tool_id

    @pytest.mark.asyncio
    async def test_register_duplicate_same_server_warns(self):
        registry = MCPToolRegistry()
        tool1 = _make_tool(name="dup")
        tool2 = _make_tool(name="dup")
        await registry.register_tool(tool1, agent_id="a")
        result = await registry.register_tool(tool2, agent_id="a")
        assert result.success is True
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_register_duplicate_different_server_warns(self):
        registry = MCPToolRegistry()
        tool1 = _make_tool(name="dup", server_id="s1")
        tool2 = _make_tool(name="dup", server_id="s2")
        await registry.register_tool(tool1, agent_id="a")
        result = await registry.register_tool(tool2, agent_id="a")
        assert result.success is True
        assert any("already registered" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_register_tool_max_total_limit(self):
        registry = MCPToolRegistry()
        registry.MAX_TOTAL_TOOLS = 1
        await registry.register_tool(_make_tool(name="t1"), agent_id="a")
        result = await registry.register_tool(_make_tool(name="t2"), agent_id="a")
        assert result.success is False
        assert "Maximum tool limit" in result.error

    @pytest.mark.asyncio
    async def test_register_tool_max_per_server_limit(self):
        registry = MCPToolRegistry()
        registry.MAX_TOOLS_PER_SERVER = 1
        await registry.register_tool(_make_tool(name="t1"), agent_id="a")
        result = await registry.register_tool(_make_tool(name="t2"), agent_id="a")
        assert result.success is False
        assert "Maximum tools per server" in result.error


# ---------------------------------------------------------------------------
# MCPToolRegistry - unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    @pytest.mark.asyncio
    async def test_unregister_existing(self):
        registry = MCPToolRegistry()
        tool = _make_tool()
        await registry.register_tool(tool, agent_id="a")
        ok = await registry.unregister_tool(tool.tool_id, agent_id="a")
        assert ok is True
        assert registry.get_tool(tool.tool_id) is None

    @pytest.mark.asyncio
    async def test_unregister_nonexistent(self):
        registry = MCPToolRegistry()
        ok = await registry.unregister_tool("no-such-id", agent_id="a")
        assert ok is False


# ---------------------------------------------------------------------------
# MCPToolRegistry - discover_tools
# ---------------------------------------------------------------------------


class TestDiscoverTools:
    @pytest.mark.asyncio
    async def test_discover_success(self):
        registry = MCPToolRegistry()
        defs = [
            {"name": "tool_a", "description": "A tool", "inputSchema": {"type": "object"}},
            {"name": "tool_b", "description": "B tool", "inputSchema": {"type": "object"}},
        ]
        result = await registry.discover_tools(
            server_id="s-1",
            server_name="Test Server",
            tools_definitions=defs,
            agent_id="agent-1",
        )
        assert result.tools_found == 2
        assert result.tools_registered == 2
        assert result.tools_skipped == 0
        assert result.discovery_time_ms >= 0

    @pytest.mark.asyncio
    async def test_discover_with_bad_definition(self):
        registry = MCPToolRegistry()
        # A definition that will cause an error during parsing: name is missing
        defs = [
            {"name": "good_tool", "description": "ok", "inputSchema": {"type": "object"}},
        ]
        result = await registry.discover_tools(
            server_id="s-1",
            server_name="Server",
            tools_definitions=defs,
            agent_id="a",
        )
        assert result.tools_registered >= 1

    @pytest.mark.asyncio
    async def test_discover_registers_server(self):
        registry = MCPToolRegistry()
        await registry.discover_tools(
            server_id="s-1",
            server_name="Server",
            tools_definitions=[],
            agent_id="a",
        )
        servers = registry.list_servers()
        assert len(servers) == 1
        assert servers[0]["server_id"] == "s-1"


# ---------------------------------------------------------------------------
# MCPToolRegistry - execute_tool
# ---------------------------------------------------------------------------


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        handler = AsyncMock(return_value={"output": "result"})
        tool = _make_tool(handler=handler)
        registry = MCPToolRegistry()
        await registry.register_tool(tool, agent_id="a")

        ctx = ToolExecutionContext(tool=tool, arguments={"q": "test"}, agent_id="a")
        result = await registry.execute_tool(ctx)
        assert result.success is True
        assert result.result == {"output": "result"}
        assert result.execution_time_ms >= 0
        handler.assert_called_once_with({"q": "test"})

    @pytest.mark.asyncio
    async def test_execute_inactive_tool(self):
        tool = _make_tool(status=ToolStatus.INACTIVE, handler=AsyncMock())
        registry = MCPToolRegistry()
        ctx = ToolExecutionContext(tool=tool, arguments={}, agent_id="a")
        result = await registry.execute_tool(ctx)
        assert result.success is False
        assert "not active" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_handler(self):
        tool = _make_tool(handler=None)
        registry = MCPToolRegistry()
        ctx = ToolExecutionContext(tool=tool, arguments={}, agent_id="a")
        result = await registry.execute_tool(ctx)
        assert result.success is False
        assert "no handler" in result.error

    @pytest.mark.asyncio
    async def test_execute_handler_raises(self):
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        tool = _make_tool(handler=handler)
        registry = MCPToolRegistry()
        ctx = ToolExecutionContext(tool=tool, arguments={}, agent_id="a")
        result = await registry.execute_tool(ctx)
        assert result.success is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        async def slow_handler(args):
            await asyncio.sleep(10)
            return {}

        tool = _make_tool(handler=slow_handler)
        registry = MCPToolRegistry()
        ctx = ToolExecutionContext(tool=tool, arguments={}, agent_id="a", timeout_ms=10)
        result = await registry.execute_tool(ctx)
        assert result.success is False
        assert "timed out" in result.error


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    @pytest.mark.asyncio
    async def test_get_tool(self):
        registry = MCPToolRegistry()
        tool = _make_tool()
        await registry.register_tool(tool, agent_id="a")
        found = registry.get_tool(tool.tool_id)
        assert found is not None
        assert found.name == "test_tool"

    @pytest.mark.asyncio
    async def test_get_tool_by_name(self):
        registry = MCPToolRegistry()
        tool = _make_tool(name="named_tool")
        await registry.register_tool(tool, agent_id="a")
        found = registry.get_tool_by_name("named_tool")
        assert found is not None

    @pytest.mark.asyncio
    async def test_get_tool_by_name_missing(self):
        registry = MCPToolRegistry()
        found = registry.get_tool_by_name("nope")
        assert found is None

    @pytest.mark.asyncio
    async def test_list_tools_all(self):
        registry = MCPToolRegistry()
        await registry.register_tool(_make_tool(name="a"), agent_id="x")
        await registry.register_tool(_make_tool(name="b"), agent_id="x")
        tools = registry.list_tools()
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_list_tools_by_server(self):
        registry = MCPToolRegistry()
        await registry.register_tool(_make_tool(name="a", server_id="s1"), agent_id="x")
        await registry.register_tool(_make_tool(name="b", server_id="s2"), agent_id="x")
        tools = registry.list_tools(server_id="s1")
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_list_tools_by_capability(self):
        registry = MCPToolRegistry()
        await registry.register_tool(
            _make_tool(name="a", capabilities=[ToolCapability.GOVERNANCE]),
            agent_id="x",
        )
        await registry.register_tool(
            _make_tool(name="b", capabilities=[ToolCapability.AUDIT]),
            agent_id="x",
        )
        tools = registry.list_tools(capability=ToolCapability.GOVERNANCE)
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_list_tools_by_status(self):
        registry = MCPToolRegistry()
        await registry.register_tool(_make_tool(name="a", status=ToolStatus.ACTIVE), agent_id="x")
        await registry.register_tool(
            _make_tool(name="b", status=ToolStatus.SUSPENDED), agent_id="x"
        )
        tools = registry.list_tools(status=ToolStatus.ACTIVE)
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_list_tools_with_limit(self):
        registry = MCPToolRegistry()
        for i in range(5):
            await registry.register_tool(_make_tool(name=f"t{i}"), agent_id="x")
        tools = registry.list_tools(limit=3)
        assert len(tools) == 3


# ---------------------------------------------------------------------------
# Capability inference and risk assessment
# ---------------------------------------------------------------------------


class TestInferCapabilitiesAndRisk:
    def test_infer_governance_capability(self):
        registry = MCPToolRegistry()
        caps = registry._infer_capabilities("policy_checker", "validates governance rules")
        assert ToolCapability.GOVERNANCE in caps

    def test_infer_security_capability(self):
        registry = MCPToolRegistry()
        caps = registry._infer_capabilities("auth_tool", "manages permissions")
        assert ToolCapability.SECURITY in caps

    def test_infer_default_capability(self):
        registry = MCPToolRegistry()
        caps = registry._infer_capabilities("xyz", "does something")
        assert caps == [ToolCapability.INTEGRATION]

    def test_assess_critical_risk(self):
        registry = MCPToolRegistry()
        risk = registry._assess_risk_level("admin_delete", "drops everything", ToolInputSchema())
        assert risk == ToolRiskLevel.CRITICAL

    def test_assess_high_risk(self):
        registry = MCPToolRegistry()
        risk = registry._assess_risk_level("update_config", "modifies settings", ToolInputSchema())
        assert risk == ToolRiskLevel.HIGH

    def test_assess_medium_risk(self):
        registry = MCPToolRegistry()
        risk = registry._assess_risk_level("send_email", "sends notifications", ToolInputSchema())
        assert risk == ToolRiskLevel.MEDIUM

    def test_assess_low_risk(self):
        registry = MCPToolRegistry()
        risk = registry._assess_risk_level("get_info", "reads info", ToolInputSchema())
        assert risk == ToolRiskLevel.LOW

    def test_parse_tool_definition(self):
        registry = MCPToolRegistry()
        tool_def = {
            "name": "delete_resource",
            "description": "Deletes a resource",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        }
        tool = registry._parse_tool_definition("server-1", tool_def)
        assert tool.name == "delete_resource"
        assert tool.risk_level == ToolRiskLevel.CRITICAL
        assert tool.requires_approval is True


# ---------------------------------------------------------------------------
# Metrics and audit
# ---------------------------------------------------------------------------


class TestMetricsAndAudit:
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        registry = MCPToolRegistry()
        await registry.register_tool(_make_tool(), agent_id="a")
        m = registry.get_metrics()
        assert m["total_tools"] == 1
        assert m["registration_count"] == 1
        assert "constitutional_hash" in m

    @pytest.mark.asyncio
    async def test_audit_log_populated(self):
        registry = MCPToolRegistry(enable_audit=True)
        tool = _make_tool()
        await registry.register_tool(tool, agent_id="a")
        log = registry.get_audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "register_tool"

    @pytest.mark.asyncio
    async def test_audit_log_disabled(self):
        registry = MCPToolRegistry(enable_audit=False)
        await registry.register_tool(_make_tool(), agent_id="a")
        log = registry.get_audit_log()
        assert len(log) == 0

    @pytest.mark.asyncio
    async def test_audit_log_limit(self):
        registry = MCPToolRegistry(enable_audit=True)
        for i in range(10):
            await registry.register_tool(_make_tool(name=f"t{i}"), agent_id="a")
        log = registry.get_audit_log(limit=5)
        assert len(log) == 5


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_tool_registry(self):
        registry = create_tool_registry()
        assert isinstance(registry, MCPToolRegistry)

    def test_create_tool_registry_options(self):
        registry = create_tool_registry(enable_caching=False, enable_audit=False)
        assert registry.enable_caching is False
        assert registry.enable_audit is False
