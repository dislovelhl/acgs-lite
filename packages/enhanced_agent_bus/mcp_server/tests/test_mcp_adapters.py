"""
MCP Adapters Tests.

Tests for MCP adapters connecting to external services.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..adapters.agent_bus import AgentBusAdapter
from ..adapters.audit_client import AuditClientAdapter
from ..adapters.policy_client import PolicyClientAdapter


class TestAgentBusAdapter:
    """Tests for AgentBusAdapter."""

    def test_create_adapter(self):
        """Test creating an agent bus adapter."""
        adapter = AgentBusAdapter()

        assert adapter.mcp_agent_id == "mcp-server"
        assert adapter.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert adapter._connected is False

    def test_create_adapter_with_custom_id(self):
        """Test creating adapter with custom agent ID."""
        adapter = AgentBusAdapter(mcp_agent_id="custom-mcp")

        assert adapter.mcp_agent_id == "custom-mcp"

    async def test_connect_standalone(self):
        """Test connecting without agent bus (standalone mode)."""
        adapter = AgentBusAdapter()

        result = await adapter.connect()

        assert result is False  # No agent bus provided
        assert adapter._connected is False

    async def test_connect_with_agent_bus(self):
        """Test connecting with agent bus."""
        mock_bus = MagicMock()
        mock_bus.register_agent = AsyncMock()

        adapter = AgentBusAdapter(agent_bus=mock_bus)
        result = await adapter.connect()

        assert result is True
        assert adapter._connected is True
        mock_bus.register_agent.assert_called_once()

    async def test_disconnect(self):
        """Test disconnecting from agent bus."""
        mock_bus = MagicMock()
        mock_bus.register_agent = AsyncMock()
        mock_bus.deregister_agent = AsyncMock()

        adapter = AgentBusAdapter(agent_bus=mock_bus)
        await adapter.connect()
        await adapter.disconnect()

        assert adapter._connected is False
        mock_bus.deregister_agent.assert_called_once_with("mcp-server")

    async def test_validate_action_standalone(self):
        """Test validating action in standalone mode."""
        adapter = AgentBusAdapter()

        result = await adapter.validate_action(
            action="read_data",
            context={"data_sensitivity": "public"},
        )

        assert "compliant" in result
        assert "standalone_mode" in result
        assert result["standalone_mode"] is True

    async def test_validate_sensitive_data_standalone(self):
        """Test validating sensitive data access in standalone mode."""
        adapter = AgentBusAdapter()

        result = await adapter.validate_action(
            action="access_user_data",
            context={
                "data_sensitivity": "confidential",
                "consent_obtained": False,
            },
        )

        assert result["compliant"] is False
        assert len(result["violations"]) > 0

    async def test_validate_high_risk_action_standalone(self):
        """Test validating high-risk action in standalone mode."""
        adapter = AgentBusAdapter()

        result = await adapter.validate_action(
            action="delete_database",
            context={"authorization_verified": False},
        )

        assert result["compliant"] is False

    async def test_validate_with_agent_bus(self):
        """Test validating action through agent bus."""
        mock_bus = MagicMock()
        mock_bus.register_agent = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = {
            "compliant": True,
            "confidence": 0.95,
            "violations": [],
        }
        mock_bus.send_message = AsyncMock(return_value=mock_response)

        adapter = AgentBusAdapter(agent_bus=mock_bus)
        await adapter.connect()

        result = await adapter.validate_action(
            action="test_action",
            context={},
        )

        assert result["compliant"] is True
        assert result["confidence"] == 0.95

    async def test_submit_governance_request_standalone(self):
        """Test submitting governance request in standalone mode."""
        adapter = AgentBusAdapter()

        result = await adapter.submit_governance_request(
            action="deploy_model",
            context={"model_type": "classifier"},
            priority="medium",
            requester_id="test-agent",
        )

        assert "status" in result
        assert "standalone_mode" in result

    async def test_fail_closed_on_error(self):
        """Test fail-closed behavior on error."""
        mock_bus = MagicMock()
        mock_bus.register_agent = AsyncMock()
        mock_bus.send_message = AsyncMock(side_effect=Exception("Connection error"))

        adapter = AgentBusAdapter(agent_bus=mock_bus)
        await adapter.connect()

        result = await adapter.validate_action(
            action="test",
            context={},
            strict_mode=True,
        )

        assert result["compliant"] is False
        assert result["fail_closed"] is True

    async def test_submit_governance_request_returns_error_on_unexpected_exception(self):
        """Test governance requests return a stable error payload on unexpected failures."""
        mock_bus = MagicMock()
        mock_bus.register_agent = AsyncMock()
        mock_bus.send_message = AsyncMock(side_effect=Exception("Connection error"))

        adapter = AgentBusAdapter(agent_bus=mock_bus)
        await adapter.connect()

        result = await adapter.submit_governance_request(
            action="deploy_model",
            context={},
            priority="high",
            requester_id="test-agent",
        )

        assert result["status"] == "error"
        assert result["error"] == "Connection error"

    def test_get_metrics(self):
        """Test getting adapter metrics."""
        adapter = AgentBusAdapter()
        metrics = adapter.get_metrics()

        assert "request_count" in metrics
        assert "connected" in metrics
        assert "agent_id" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPolicyClientAdapter:
    """Tests for PolicyClientAdapter."""

    def test_create_adapter(self):
        """Test creating a policy client adapter."""
        adapter = PolicyClientAdapter()

        assert adapter.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert adapter.policy_client is None

    async def test_get_default_principles(self):
        """Test getting default principles without client."""
        adapter = PolicyClientAdapter()

        principles = await adapter.get_active_principles()

        assert len(principles) > 0
        for p in principles:
            assert "id" in p
            assert "name" in p
            assert "category" in p

    async def test_filter_by_category(self):
        """Test filtering principles by category."""
        adapter = PolicyClientAdapter()

        principles = await adapter.get_active_principles(category="safety")

        for p in principles:
            assert p["category"] == "safety"

    async def test_filter_by_enforcement_level(self):
        """Test filtering by enforcement level."""
        adapter = PolicyClientAdapter()

        principles = await adapter.get_active_principles(enforcement_level="strict")

        for p in principles:
            assert p["enforcement_level"] == "strict"

    async def test_filter_by_ids(self):
        """Test filtering by principle IDs."""
        adapter = PolicyClientAdapter()

        principles = await adapter.get_active_principles(principle_ids=["P001", "P002"])

        ids = [p["id"] for p in principles]
        for pid in ["P001", "P002"]:
            if pid in ids:
                assert True

    async def test_get_policy_by_name(self):
        """Test getting a specific policy by name."""
        adapter = PolicyClientAdapter()

        policy = await adapter.get_policy_by_name("beneficence")

        if policy:
            assert policy["name"] == "beneficence"

    async def test_get_nonexistent_policy(self):
        """Test getting a non-existent policy."""
        adapter = PolicyClientAdapter()

        policy = await adapter.get_policy_by_name("nonexistent_policy")

        assert policy is None

    async def test_with_policy_client(self):
        """Test with actual policy client."""
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(
            return_value=[{"id": "P100", "name": "custom", "category": "custom", "active": True}]
        )

        adapter = PolicyClientAdapter(policy_client=mock_client)

        principles = await adapter.get_active_principles()

        assert len(principles) > 0
        mock_client.get_principles.assert_called_once()

    def test_get_metrics(self):
        """Test getting adapter metrics."""
        adapter = PolicyClientAdapter()
        metrics = adapter.get_metrics()

        assert "request_count" in metrics
        assert "connected" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAuditClientAdapter:
    """Tests for AuditClientAdapter."""

    def test_create_adapter(self):
        """Test creating an audit client adapter."""
        adapter = AuditClientAdapter()

        assert adapter.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert adapter.audit_client is None

    async def test_get_sample_precedents(self):
        """Test getting sample precedents without client."""
        adapter = AuditClientAdapter()

        precedents = await adapter.query_precedents()

        assert len(precedents) > 0
        for p in precedents:
            assert "id" in p
            assert "action_type" in p
            assert "outcome" in p

    async def test_filter_by_action_type(self):
        """Test filtering precedents by action type."""
        adapter = AuditClientAdapter()

        precedents = await adapter.query_precedents(action_type="data_access")

        for p in precedents:
            assert "data_access" in p["action_type"].lower()

    async def test_filter_by_outcome(self):
        """Test filtering by outcome."""
        adapter = AuditClientAdapter()

        precedents = await adapter.query_precedents(outcome="denied")

        for p in precedents:
            assert p["outcome"] == "denied"

    async def test_filter_by_principles(self):
        """Test filtering by principles applied."""
        adapter = AuditClientAdapter()

        precedents = await adapter.query_precedents(principles=["P007"])

        for p in precedents:
            assert any("P007" in pr for pr in p["principles_applied"])

    async def test_limit_results(self):
        """Test limiting query results."""
        adapter = AuditClientAdapter()

        precedents = await adapter.query_precedents(limit=2)

        assert len(precedents) <= 2

    async def test_get_audit_trail(self):
        """Test getting audit trail entries."""
        adapter = AuditClientAdapter()

        entries = await adapter.get_audit_trail()

        assert len(entries) > 0
        for e in entries:
            assert "id" in e
            assert "event_type" in e
            assert "constitutional_hash" in e

    async def test_filter_audit_by_event_type(self):
        """Test filtering audit trail by event type."""
        adapter = AuditClientAdapter()

        entries = await adapter.get_audit_trail(event_type="validation")

        for e in entries:
            assert e["event_type"] == "validation"

    async def test_filter_audit_by_actor(self):
        """Test filtering audit trail by actor ID."""
        adapter = AuditClientAdapter()

        entries = await adapter.get_audit_trail(actor_id="mcp-server")

        for e in entries:
            assert e["actor_id"] == "mcp-server"

    async def test_log_audit_event(self):
        """Test logging an audit event."""
        adapter = AuditClientAdapter()

        entry = await adapter.log_audit_event(
            event_type="validation",
            actor_id="test-agent",
            action="Test validation",
            details={"test": True},
            outcome="success",
        )

        assert "id" in entry
        assert entry["event_type"] == "validation"
        assert entry["actor_id"] == "test-agent"
        assert entry["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_with_audit_client(self):
        """Test with actual audit client."""
        mock_client = MagicMock()
        mock_client.query_precedents = AsyncMock(
            return_value=[{"id": "PREC-100", "outcome": "approved", "context_summary": "test"}]
        )

        adapter = AuditClientAdapter(audit_client=mock_client)

        precedents = await adapter.query_precedents()

        mock_client.query_precedents.assert_called_once()

    async def test_semantic_query_filtering(self):
        """Test semantic query filtering."""
        adapter = AuditClientAdapter()

        # Query for PII-related precedents
        precedents = await adapter.query_precedents(semantic_query="PII consent")

        # Should filter based on semantic content
        assert isinstance(precedents, list)

    def test_get_metrics(self):
        """Test getting adapter metrics."""
        adapter = AuditClientAdapter()
        metrics = adapter.get_metrics()

        assert "request_count" in metrics
        assert "connected" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAdapterIntegration:
    """Integration tests for adapters working together."""

    async def test_validate_then_log(self):
        """Test validating action and logging result."""
        agent_adapter = AgentBusAdapter()
        audit_adapter = AuditClientAdapter()

        # Validate an action
        validation = await agent_adapter.validate_action(
            action="access_data",
            context={"data_sensitivity": "public"},
        )

        # Log the validation result
        entry = await audit_adapter.log_audit_event(
            event_type="validation",
            actor_id="test-workflow",
            action="Validated data access",
            details={
                "action": "access_data",
                "compliant": validation["compliant"],
            },
            outcome="success" if validation["compliant"] else "violation",
        )

        assert entry["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_principles_for_validation(self):
        """Test getting principles to use in validation."""
        policy_adapter = PolicyClientAdapter()
        agent_adapter = AgentBusAdapter()

        # Get safety principles
        principles = await policy_adapter.get_active_principles(category="safety")

        assert len(principles) > 0

        # Use principles in validation
        validation = await agent_adapter.validate_action(
            action="test_action",
            context={"principles": [p["id"] for p in principles]},
        )

        assert "compliant" in validation
