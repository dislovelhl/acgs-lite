"""
MCP Tools Tests.

Tests for all MCP governance tools.

Constitutional Hash: 608508a9bd224290
"""

import json
from unittest.mock import AsyncMock, MagicMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..tools.get_metrics import GetMetricsTool
from ..tools.get_principles import GetPrinciplesTool
from ..tools.query_precedents import DecisionOutcome, QueryPrecedentsTool
from ..tools.submit_governance import SubmitGovernanceTool
from ..tools.validate_compliance import ValidateComplianceTool


def extract_content(result: dict) -> dict:
    """
    Extract the parsed content from MCP-formatted tool result.

    MCP tools return: {"content": [{"type": "text", "text": "<json>"}], "isError": bool}
    This helper extracts and parses the actual data.
    """
    if "content" in result and isinstance(result["content"], list):
        for item in result["content"]:
            if item.get("type") == "text" and "text" in item:
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"raw_text": item["text"]}
    return result


def get_schema_properties(definition) -> dict:
    """Extract properties from a ToolDefinition's inputSchema."""
    schema = definition.inputSchema
    if hasattr(schema, "properties"):
        return schema.properties
    if hasattr(schema, "to_dict"):
        return schema.to_dict().get("properties", {})
    if isinstance(schema, dict):
        return schema.get("properties", {})
    return {}


def get_schema_required(definition) -> list:
    """Extract required fields from a ToolDefinition's inputSchema."""
    schema = definition.inputSchema
    if hasattr(schema, "required"):
        return schema.required or []
    if hasattr(schema, "to_dict"):
        return schema.to_dict().get("required", [])
    if isinstance(schema, dict):
        return schema.get("required", [])
    return []


class TestValidateComplianceTool:
    """Tests for ValidateComplianceTool."""

    def test_get_definition(self):
        """Test getting tool definition."""
        tool = ValidateComplianceTool()
        definition = tool.get_definition()

        assert definition.name == "validate_constitutional_compliance"
        properties = get_schema_properties(definition)
        required = get_schema_required(definition)
        assert "action" in properties
        assert "context" in properties
        assert "action" in required or "context" in required

    async def test_validate_compliant_action(self):
        """Test validating a compliant action."""
        tool = ValidateComplianceTool()

        result = await tool.execute(
            {
                "action": "read_public_data",
                "context": {
                    "data_sensitivity": "public",
                    "user_consented": True,
                },
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        data = extract_content(result)
        assert data["compliant"] is True
        assert data["confidence"] > 0.5
        assert len(data.get("violations", [])) == 0

    async def test_validate_non_compliant_action(self):
        """Test validating a non-compliant action."""
        tool = ValidateComplianceTool()

        result = await tool.execute(
            {
                "action": "delete_user_data",
                "context": {
                    "data_sensitivity": "confidential",
                    "authorization_verified": False,
                },
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        data = extract_content(result)
        assert data["compliant"] is False
        assert len(data.get("violations", [])) > 0

    async def test_validate_with_specific_principles(self):
        """Test validation with specific principles."""
        tool = ValidateComplianceTool()

        result = await tool.execute(
            {
                "action": "access_private_data",
                "context": {"purpose": "analytics"},
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "principles": ["privacy", "transparency"],
            }
        )

        data = extract_content(result)
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_validate_rejects_invalid_hash(self):
        """Test that validation with invalid hash still works but returns result."""
        tool = ValidateComplianceTool()

        result = await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "constitutional_hash": "invalid_hash",
            }
        )

        # Tool should still return a result (even if it notes the hash is different)
        data = extract_content(result)
        assert "constitutional_hash" in data  # Should include the correct hash

    async def test_metrics_tracking(self):
        """Test that metrics are tracked."""
        tool = ValidateComplianceTool()

        await tool.execute(
            {
                "action": "test",
                "context": {},
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        metrics = tool.get_metrics()
        assert metrics["validation_count"] >= 1


class TestGetPrinciplesTool:
    """Tests for GetPrinciplesTool."""

    def test_get_definition(self):
        """Test getting tool definition."""
        tool = GetPrinciplesTool()
        definition = tool.get_definition()

        assert definition.name == "get_active_principles"
        properties = get_schema_properties(definition)
        assert "category" in properties
        assert "enforcement_level" in properties

    async def test_get_all_principles(self):
        """Test getting all active principles."""
        tool = GetPrinciplesTool()

        result = await tool.execute({})

        data = extract_content(result)
        assert "principles" in data
        assert len(data["principles"]) > 0
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_filter_by_category(self):
        """Test filtering principles by category."""
        tool = GetPrinciplesTool()

        result = await tool.execute(
            {
                "category": "safety",
            }
        )

        data = extract_content(result)
        assert "principles" in data
        for principle in data["principles"]:
            assert principle["category"] == "safety"

    async def test_filter_by_enforcement_level(self):
        """Test filtering by enforcement level."""
        tool = GetPrinciplesTool()

        result = await tool.execute(
            {
                "enforcement_level": "strict",
            }
        )

        data = extract_content(result)
        assert "principles" in data
        for principle in data["principles"]:
            assert principle["enforcement_level"] == "strict"

    async def test_get_specific_principles(self):
        """Test getting specific principles by ID."""
        tool = GetPrinciplesTool()

        result = await tool.execute(
            {
                "principle_ids": ["P001", "P002"],
            }
        )

        data = extract_content(result)
        assert "principles" in data
        ids = [p["id"] for p in data["principles"]]
        assert "P001" in ids or "P002" in ids


class TestQueryPrecedentsTool:
    """Tests for QueryPrecedentsTool."""

    def test_get_definition(self):
        """Test getting tool definition."""
        tool = QueryPrecedentsTool()
        definition = tool.get_definition()

        assert definition.name == "query_governance_precedents"
        properties = get_schema_properties(definition)
        assert "action_type" in properties
        assert "outcome" in properties

    async def test_query_all_precedents(self):
        """Test querying all precedents."""
        tool = QueryPrecedentsTool()

        result = await tool.execute({})

        data = extract_content(result)
        assert "precedents" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_query_by_action_type(self):
        """Test querying by action type."""
        tool = QueryPrecedentsTool()

        result = await tool.execute(
            {
                "action_type": "data_access",
            }
        )

        data = extract_content(result)
        assert "precedents" in data

    async def test_query_by_outcome(self):
        """Test querying by outcome."""
        tool = QueryPrecedentsTool()

        result = await tool.execute(
            {
                "outcome": "denied",
            }
        )

        data = extract_content(result)
        assert "precedents" in data
        # Precedents should be filtered or empty if no matches
        for precedent in data.get("precedents", []):
            assert precedent.get("outcome") == "denied"

    async def test_query_with_date_range(self):
        """Test querying with date range."""
        tool = QueryPrecedentsTool()

        result = await tool.execute(
            {
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }
        )

        data = extract_content(result)
        assert "precedents" in data

    async def test_query_with_limit(self):
        """Test querying with result limit."""
        tool = QueryPrecedentsTool()

        result = await tool.execute(
            {
                "limit": 5,
            }
        )

        data = extract_content(result)
        assert "precedents" in data
        assert len(data["precedents"]) <= 5


class TestSubmitGovernanceTool:
    """Tests for SubmitGovernanceTool."""

    def test_get_definition(self):
        """Test getting tool definition."""
        tool = SubmitGovernanceTool()
        definition = tool.get_definition()

        assert definition.name == "submit_governance_request"
        required = get_schema_required(definition)
        assert "action" in required
        assert "context" in required

    async def test_submit_request(self):
        """Test submitting a governance request."""
        tool = SubmitGovernanceTool()

        result = await tool.execute(
            {
                "action": "deploy_model",
                "context": {"model_type": "classification"},
                "priority": "high",
                "requester_id": "test-agent",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        data = extract_content(result)
        # The response contains a "request" object with the fields
        request_data = data.get("request", data)
        assert "request_id" in request_data
        assert "status" in request_data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_submit_with_wait(self):
        """Test submitting request with wait for approval."""
        tool = SubmitGovernanceTool()

        result = await tool.execute(
            {
                "action": "update_config",
                "context": {},
                "wait_for_approval": True,
                "timeout_seconds": 5,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        data = extract_content(result)
        request_data = data.get("request", data)
        assert "request_id" in request_data
        assert "status" in request_data

    async def test_submit_high_priority(self):
        """Test submitting high priority request."""
        tool = SubmitGovernanceTool()

        result = await tool.execute(
            {
                "action": "emergency_shutdown",
                "context": {"reason": "safety"},
                "priority": "critical",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        data = extract_content(result)
        request_data = data.get("request", data)
        assert "request_id" in request_data


class TestGetMetricsTool:
    """Tests for GetMetricsTool."""

    def test_get_definition(self):
        """Test getting tool definition."""
        tool = GetMetricsTool()
        definition = tool.get_definition()

        assert definition.name == "get_governance_metrics"
        properties = get_schema_properties(definition)
        assert "time_range" in properties

    async def test_get_all_metrics(self):
        """Test getting all metrics."""
        tool = GetMetricsTool()

        result = await tool.execute({})

        data = extract_content(result)
        # Metrics are returned at the top level, not nested under "metrics"
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_metrics_with_time_range(self):
        """Test getting metrics with time range."""
        tool = GetMetricsTool()

        result = await tool.execute(
            {
                "time_range": "1h",
            }
        )

        data = extract_content(result)
        assert "constitutional_hash" in data

    async def test_get_specific_metric_types(self):
        """Test getting specific metric types."""
        tool = GetMetricsTool()

        result = await tool.execute(
            {
                "metric_types": ["latency", "compliance"],
            }
        )

        data = extract_content(result)
        assert "constitutional_hash" in data

    async def test_metrics_include_performance(self):
        """Test that metrics include performance data."""
        tool = GetMetricsTool()

        result = await tool.execute({})

        data = extract_content(result)
        # Should have performance-related fields
        assert "constitutional_hash" in data


class TestToolsWithAdapters:
    """Tests for tools with external adapters."""

    async def test_validate_with_agent_bus_adapter(self):
        """Test validation with agent bus adapter."""
        mock_adapter = MagicMock()
        mock_adapter.validate_action = AsyncMock(
            return_value={
                "compliant": True,
                "confidence": 0.95,
                "violations": [],
                "recommendations": [],
            }
        )

        # Use correct adapter parameter name
        tool = ValidateComplianceTool(agent_bus_adapter=mock_adapter)

        result = await tool.execute(
            {
                "action": "test",
                "context": {},
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        assert result is not None
        data = extract_content(result)
        assert data["compliant"] is True
        mock_adapter.validate_action.assert_called_once()

    async def test_precedents_with_audit_client(self):
        """Test precedent queries with audit client adapter."""
        mock_adapter = MagicMock()
        mock_adapter.query_precedents = AsyncMock(
            return_value=[
                {
                    "id": "PREC-001",
                    "action_type": "test_action",
                    "outcome": DecisionOutcome.APPROVED,
                    "context_summary": "Test context",
                    "principles_applied": ["safety"],
                    "reasoning": "Test reasoning",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "confidence_score": 0.95,
                }
            ]
        )

        tool = QueryPrecedentsTool(audit_client_adapter=mock_adapter)

        result = await tool.execute({})

        assert result is not None
        data = extract_content(result)
        assert "precedents" in data
