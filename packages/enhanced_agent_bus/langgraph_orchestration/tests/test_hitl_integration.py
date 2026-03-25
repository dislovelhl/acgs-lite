"""
ACGS-2 LangGraph Orchestration - HITL Integration Tests
Constitutional Hash: 608508a9bd224290
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.langgraph_orchestration.exceptions import InterruptError, TimeoutError
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    ExecutionContext,
    GraphState,
    InterruptType,
)

from ..hitl_integration import (
    HITLAction,
    HITLConfig,
    HITLHandler,
    HITLInterruptHandler,
    HITLRequest,
    HITLResponse,
    InMemoryHITLHandler,
    create_hitl_handler,
)


class TestHITLAction:
    """Tests for HITLAction enum."""

    def test_action_values(self):
        """Test action enum values."""
        assert HITLAction.CONTINUE.value == "continue"
        assert HITLAction.ABORT.value == "abort"
        assert HITLAction.MODIFY.value == "modify"
        assert HITLAction.RETRY.value == "retry"
        assert HITLAction.SKIP.value == "skip"
        assert HITLAction.ESCALATE.value == "escalate"


class TestHITLConfig:
    """Tests for HITLConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = HITLConfig()
        assert config.enabled is True
        assert config.default_timeout_ms == 300000.0
        assert config.auto_continue_on_timeout is False
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        """Test custom configuration."""
        config = HITLConfig(
            enabled=False,
            default_timeout_ms=60000.0,
            auto_continue_on_timeout=True,
            max_requests_per_workflow=50,
        )
        assert config.enabled is False
        assert config.default_timeout_ms == 60000.0
        assert config.auto_continue_on_timeout is True
        assert config.max_requests_per_workflow == 50


class TestHITLRequest:
    """Tests for HITLRequest."""

    def test_create_request(self):
        """Test creating HITL request."""
        state = GraphState(data={"test": "value"})
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            interrupt_type=InterruptType.HITL,
            current_state=state,
            reason="Approval needed",
        )

        assert request.workflow_id == "wf1"
        assert request.node_id == "node1"
        assert request.reason == "Approval needed"
        assert request.constitutional_hash == CONSTITUTIONAL_HASH

    def test_request_expiration(self):
        """Test request expiration calculation."""
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=1000.0,  # 1 second
        )

        assert request.expires_at is not None
        assert request.expires_at > request.created_at

    def test_is_expired_false(self):
        """Test is_expired returns false for valid request."""
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=300000.0,  # 5 minutes
        )

        assert request.is_expired() is False

    def test_is_expired_true(self):
        """Test is_expired returns true for expired request."""
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=1.0,  # 1 ms
            created_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        request.expires_at = request.created_at + timedelta(milliseconds=1)

        assert request.is_expired() is True

    def test_to_dict(self):
        """Test request serialization."""
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            reason="Test reason",
        )

        result = request.to_dict()

        assert result["workflow_id"] == "wf1"
        assert result["node_id"] == "node1"
        assert result["reason"] == "Test reason"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestHITLResponse:
    """Tests for HITLResponse."""

    def test_create_response(self):
        """Test creating HITL response."""
        response = HITLResponse(
            request_id="req1",
            action=HITLAction.CONTINUE,
            responded_by="user@example.com",
            reason="Approved",
        )

        assert response.request_id == "req1"
        assert response.action == HITLAction.CONTINUE
        assert response.responded_by == "user@example.com"

    def test_response_with_modified_state(self):
        """Test response with modified state."""
        new_state = GraphState(data={"modified": True})
        response = HITLResponse(
            request_id="req1",
            action=HITLAction.MODIFY,
            modified_state=new_state,
        )

        assert response.action == HITLAction.MODIFY
        assert response.modified_state is not None
        assert response.modified_state.data["modified"] is True

    def test_to_dict(self):
        """Test response serialization."""
        response = HITLResponse(
            request_id="req1",
            action=HITLAction.ABORT,
            reason="Rejected",
        )

        result = response.to_dict()

        assert result["request_id"] == "req1"
        assert result["action"] == "abort"
        assert result["reason"] == "Rejected"


class TestInMemoryHITLHandler:
    """Tests for InMemoryHITLHandler."""

    def test_create_handler(self):
        """Test creating in-memory handler."""
        handler = InMemoryHITLHandler()
        assert len(handler.pending_requests) == 0
        assert handler.auto_response is None

    def test_create_with_auto_response(self):
        """Test creating handler with auto response."""
        handler = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        assert handler.auto_response == HITLAction.CONTINUE

    async def test_auto_response(self):
        """Test automatic response."""
        handler = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
        )

        response = await handler.request_human_input(request)

        assert response.action == HITLAction.CONTINUE
        assert response.responded_by == "auto_responder"

    async def test_manual_response(self):
        """Test manual response through respond method."""
        handler = InMemoryHITLHandler()
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=5000.0,
        )

        # Start request in background
        async def request_and_wait():
            return await handler.request_human_input(request)

        task = asyncio.create_task(request_and_wait())

        # Give time for request to register
        await asyncio.sleep(0.01)

        # Provide response
        response = HITLResponse(
            request_id=request.id,
            action=HITLAction.ABORT,
            responded_by="tester",
        )
        handler.respond(request.id, response)

        result = await task

        assert result.action == HITLAction.ABORT
        assert result.responded_by == "tester"

    async def test_timeout(self):
        """Test request timeout."""
        handler = InMemoryHITLHandler()
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=10.0,  # 10ms timeout
        )

        with pytest.raises(TimeoutError):
            await handler.request_human_input(request)

    async def test_notify_timeout(self):
        """Test timeout notification."""
        handler = InMemoryHITLHandler()
        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
        )

        handler.pending_requests[request.id] = request
        await handler.notify_timeout(request)

        assert request.id not in handler.pending_requests


class TestHITLInterruptHandler:
    """Tests for HITLInterruptHandler."""

    def test_create_handler(self):
        """Test creating interrupt handler."""
        handler = HITLInterruptHandler()
        assert handler.constitutional_hash == CONSTITUTIONAL_HASH
        assert handler.config is not None

    def test_create_with_config(self):
        """Test creating with custom config."""
        config = HITLConfig(enabled=False)
        handler = HITLInterruptHandler(config=config)
        assert handler.config.enabled is False

    async def test_create_interrupt(self):
        """Test creating interrupt request."""
        handler = HITLInterruptHandler()
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={"test": "data"})

        request = await handler.create_interrupt(
            context=context,
            node_id="node1",
            interrupt_type=InterruptType.HITL,
            reason="Approval required",
            state=state,
        )

        assert request.workflow_id == context.workflow_id
        assert request.node_id == "node1"
        assert request.reason == "Approval required"

    async def test_create_interrupt_disabled(self):
        """Test creating interrupt when HITL disabled."""
        config = HITLConfig(enabled=False)
        handler = HITLInterruptHandler(config=config)
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={})

        with pytest.raises(InterruptError):
            await handler.create_interrupt(
                context=context,
                node_id="node1",
                interrupt_type=InterruptType.HITL,
                reason="Test",
                state=state,
            )

    async def test_rate_limit(self):
        """Test rate limiting."""
        config = HITLConfig(max_requests_per_workflow=2, cooldown_ms=1.0)
        inner_handler = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        handler = HITLInterruptHandler(handler=inner_handler, config=config)
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={})

        # First two should succeed
        for _ in range(2):
            await handler.create_interrupt(
                context=context,
                node_id="node1",
                interrupt_type=InterruptType.HITL,
                reason="Test",
                state=state,
            )

        # Third should fail due to rate limit
        with pytest.raises(InterruptError):
            await handler.create_interrupt(
                context=context,
                node_id="node1",
                interrupt_type=InterruptType.HITL,
                reason="Test",
                state=state,
            )

    async def test_handle_interrupt_success(self):
        """Test handling interrupt successfully."""
        inner_handler = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        handler = HITLInterruptHandler(handler=inner_handler)
        context = ExecutionContext(graph_id="graph1")
        state = GraphState(data={})

        request = await handler.create_interrupt(
            context=context,
            node_id="node1",
            interrupt_type=InterruptType.HITL,
            reason="Test",
            state=state,
        )

        response = await handler.handle_interrupt(request)

        assert response.action == HITLAction.CONTINUE

    async def test_handle_interrupt_auto_continue_on_timeout(self):
        """Test auto-continue on timeout."""
        inner_handler = InMemoryHITLHandler()  # No auto-response
        config = HITLConfig(
            default_timeout_ms=10.0,
            auto_continue_on_timeout=True,
        )
        handler = HITLInterruptHandler(handler=inner_handler, config=config)

        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=10.0,
        )

        response = await handler.handle_interrupt(request)

        assert response.action == HITLAction.CONTINUE
        assert response.responded_by == "timeout_handler"

    async def test_handle_interrupt_auto_abort_on_timeout(self):
        """Test auto-abort on timeout."""
        inner_handler = InMemoryHITLHandler()
        config = HITLConfig(
            default_timeout_ms=10.0,
            auto_abort_on_timeout=True,
        )
        handler = HITLInterruptHandler(handler=inner_handler, config=config)

        request = HITLRequest(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            timeout_ms=10.0,
        )

        response = await handler.handle_interrupt(request)

        assert response.action == HITLAction.ABORT

    def test_get_active_requests(self):
        """Test getting active requests."""
        handler = HITLInterruptHandler()

        request1 = HITLRequest(workflow_id="wf1", run_id="run1", node_id="node1")
        request2 = HITLRequest(workflow_id="wf2", run_id="run2", node_id="node2")

        handler._active_requests[request1.id] = request1
        handler._active_requests[request2.id] = request2

        all_requests = handler.get_active_requests()
        assert len(all_requests) == 2

        wf1_requests = handler.get_active_requests(workflow_id="wf1")
        assert len(wf1_requests) == 1

    def test_audit_log(self):
        """Test audit log functionality."""
        handler = HITLInterruptHandler()

        handler._audit_log.append(
            {
                "event": "test_event",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        log = handler.get_audit_log()
        assert len(log) == 1
        assert log[0]["event"] == "test_event"

    def test_clear_audit_log(self):
        """Test clearing audit log."""
        handler = HITLInterruptHandler()

        handler._audit_log.append({"event": "event1"})
        handler._audit_log.append({"event": "event2"})

        cleared = handler.clear_audit_log()

        assert cleared == 2
        assert len(handler._audit_log) == 0


class TestCreateHITLHandler:
    """Tests for create_hitl_handler factory."""

    def test_create_default_handler(self):
        """Test creating default handler."""
        handler = create_hitl_handler()
        assert isinstance(handler, HITLInterruptHandler)

    def test_create_with_auto_response(self):
        """Test creating handler with auto response."""
        handler = create_hitl_handler(auto_response=HITLAction.CONTINUE)
        assert isinstance(handler.handler, InMemoryHITLHandler)
        assert handler.handler.auto_response == HITLAction.CONTINUE

    def test_create_with_config(self):
        """Test creating handler with config."""
        config = HITLConfig(enabled=False)
        handler = create_hitl_handler(config=config)
        assert handler.config.enabled is False

    def test_create_with_custom_hash(self):
        """Test creating handler with custom hash."""
        handler = create_hitl_handler(constitutional_hash="custom")
        assert handler.constitutional_hash == "custom"
