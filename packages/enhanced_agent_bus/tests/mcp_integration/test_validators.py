"""
MCP Validator Tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPValidationResult:
    """Tests for MCPValidationResult."""

    def test_create_valid_result(self):
        """Test creating a valid validation result."""
        from ...mcp_integration.validators import (
            MCPValidationResult,
            OperationType,
        )

        result = MCPValidationResult(
            is_valid=True,
            operation_type=OperationType.TOOL_CALL,
        )

        assert result.is_valid is True
        assert result.operation_type == OperationType.TOOL_CALL
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(result.issues) == 0
        assert len(result.warnings) == 0

    def test_add_issue_invalidates_result(self):
        """Test that adding an error issue invalidates the result."""
        from ...mcp_integration.validators import (
            MCPValidationResult,
            OperationType,
            ValidationSeverity,
        )

        result = MCPValidationResult(
            is_valid=True,
            operation_type=OperationType.TOOL_CALL,
        )

        result.add_issue(
            code="TEST_ERROR",
            message="Test error message",
            severity=ValidationSeverity.ERROR,
        )

        assert result.is_valid is False
        assert len(result.issues) == 1
        assert result.issues[0].code == "TEST_ERROR"

    def test_add_warning_keeps_result_valid(self):
        """Test that adding a warning keeps the result valid."""
        from ...mcp_integration.validators import (
            MCPValidationResult,
            OperationType,
        )

        result = MCPValidationResult(
            is_valid=True,
            operation_type=OperationType.TOOL_CALL,
        )

        result.add_warning("Test warning")

        assert result.is_valid is True
        assert len(result.warnings) == 1

    def test_to_dict_serialization(self):
        """Test dictionary serialization."""
        from ...mcp_integration.validators import (
            MCPValidationResult,
            OperationType,
        )

        result = MCPValidationResult(
            is_valid=True,
            operation_type=OperationType.TOOL_CALL,
        )
        result.add_warning("Test warning")
        result.add_recommendation("Test recommendation")

        data = result.to_dict()

        assert data["is_valid"] is True
        assert data["operation_type"] == "tool_call"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(data["warnings"]) == 1
        assert len(data["recommendations"]) == 1


class TestMCPOperationContext:
    """Tests for MCPOperationContext."""

    def test_create_context(self):
        """Test creating an operation context."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            tool_name="test-tool",
            session_id="session-123",
        )

        assert context.operation_type == OperationType.TOOL_CALL
        assert context.agent_id == "test-agent"
        assert context.tool_name == "test-tool"
        assert context.session_id == "session-123"
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_context_to_dict(self):
        """Test context serialization."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.RESOURCE_READ,
            agent_id="test-agent",
            resource_uri="test://resource",
        )

        data = context.to_dict()

        assert data["operation_type"] == "resource_read"
        assert data["agent_id"] == "test-agent"
        assert data["resource_uri"] == "test://resource"


class TestMCPConstitutionalValidator:
    """Tests for MCPConstitutionalValidator."""

    @pytest.fixture
    def validator(self):
        """Create validator fixture."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPValidationConfig,
        )

        config = MCPValidationConfig(
            strict_mode=True,
            enable_maci=False,  # test-only: MACI off — testing MCP integration
            enable_rate_limiting=True,
            max_requests_per_minute=1000,
        )
        return MCPConstitutionalValidator(config=config)

    async def test_validate_valid_operation(self, validator):
        """Test validating a valid operation."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            tool_name="safe_tool",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await validator.validate(context)

        assert result.is_valid is True
        assert len(result.issues) == 0

    async def test_validate_missing_hash(self, validator):
        """Test validation fails with missing constitutional hash."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            constitutional_hash="",
        )

        result = await validator.validate(context)

        assert result.is_valid is False
        assert any(i.code == "HASH_MISSING" for i in result.issues)

    async def test_validate_invalid_hash(self, validator):
        """Test validation fails with invalid constitutional hash."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            constitutional_hash="invalid_hash",
        )

        result = await validator.validate(context)

        assert result.is_valid is False
        assert any(i.code == "HASH_MISMATCH" for i in result.issues)

    async def test_validate_blocked_operation(self):
        """Test validation fails for blocked operations."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPOperationContext,
            MCPValidationConfig,
            OperationType,
        )

        config = MCPValidationConfig(
            blocked_operations={OperationType.TOOL_UNREGISTER},
        )
        validator = MCPConstitutionalValidator(config=config)

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_UNREGISTER,
            agent_id="test-agent",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await validator.validate(context)

        assert result.is_valid is False
        assert any(i.code == "OPERATION_BLOCKED" for i in result.issues)

    async def test_validate_blocked_tool(self):
        """Test validation fails for blocked tools."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPOperationContext,
            MCPValidationConfig,
            OperationType,
        )

        config = MCPValidationConfig(
            blocked_tools={"dangerous_tool"},
        )
        validator = MCPConstitutionalValidator(config=config)

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            tool_name="dangerous_tool",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await validator.validate(context)

        assert result.is_valid is False
        assert any(i.code == "TOOL_BLOCKED" for i in result.issues)

    async def test_validate_high_risk_tool_warning(self, validator):
        """Test validation adds warning for high-risk tools."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            tool_name="execute_command",  # High-risk tool
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await validator.validate(context)

        assert any("high-risk" in w for w in result.warnings)

    async def test_batch_validation(self, validator):
        """Test batch validation."""
        from ...mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        contexts = [
            MCPOperationContext(
                operation_type=OperationType.TOOL_CALL,
                agent_id=f"agent-{i}",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            for i in range(5)
        ]

        results = await validator.validate_batch(contexts)

        assert len(results) == 5
        assert all(r.is_valid for r in results)

    def test_get_metrics(self, validator):
        """Test getting validator metrics."""
        metrics = validator.get_metrics()

        assert "validation_count" in metrics
        assert "violation_count" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH
