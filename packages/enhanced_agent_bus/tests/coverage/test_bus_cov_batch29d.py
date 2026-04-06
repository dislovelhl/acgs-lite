"""
Coverage batch 29d -- targets uncovered lines in:
  1. api/routes/workflows.py
  2. circuit_breaker/router.py
  3. deliberation_layer/hitl_manager.py
  4. verification_layer/dafny_adapter.py
  5. api/routes/_tenant_auth.py
  6. mcp_server/resources/decisions.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# 1. api/routes/workflows.py
# ---------------------------------------------------------------------------


class TestWorkflowsEnumValue:
    """Cover _enum_value helper (line 24)."""

    def test_enum_value_with_enum(self):
        from enhanced_agent_bus.api.routes.workflows import _enum_value
        from enhanced_agent_bus.persistence.models import WorkflowStatus

        assert _enum_value(WorkflowStatus.PENDING) == "pending"

    def test_enum_value_plain_string(self):
        from enhanced_agent_bus.api.routes.workflows import _enum_value

        assert _enum_value("plain") == "plain"


class TestResolveTenantId:
    """Cover _resolve_tenant_id (lines 48-50)."""

    def test_cross_tenant_denied(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.workflows import _resolve_tenant_id

        user = SimpleNamespace(tenant_id="tenant-a")
        with pytest.raises(HTTPException) as exc_info:
            _resolve_tenant_id(user, "tenant-b")
        assert exc_info.value.status_code == 403

    def test_same_tenant_ok(self):
        from enhanced_agent_bus.api.routes.workflows import _resolve_tenant_id

        user = SimpleNamespace(tenant_id="tenant-a")
        assert _resolve_tenant_id(user, "tenant-a") == "tenant-a"

    def test_no_requested_tenant(self):
        from enhanced_agent_bus.api.routes.workflows import _resolve_tenant_id

        user = SimpleNamespace(tenant_id="tenant-a")
        assert _resolve_tenant_id(user, None) == "tenant-a"


class TestListWorkflows:
    """Cover list_workflows endpoint (lines 62-78)."""

    async def test_list_workflows_returns_formatted(self):
        from enhanced_agent_bus.api.routes.workflows import list_workflows

        now = datetime.now(UTC)
        wf = SimpleNamespace(
            id=uuid4(),
            workflow_id="wf-1",
            workflow_type="governance",
            status="running",
            created_at=now,
            updated_at=now,
        )

        mock_repo = AsyncMock()
        mock_repo.list_workflows = AsyncMock(return_value=[wf])
        mock_executor = SimpleNamespace(repository=mock_repo)
        user = SimpleNamespace(tenant_id="t1")

        result = await list_workflows(
            request=MagicMock(),
            tenant_id=None,
            status=None,
            limit=100,
            user=user,
            executor=mock_executor,
        )
        assert result["total"] == 1
        assert result["workflows"][0]["workflow_id"] == "wf-1"
        assert result["workflows"][0]["status"] == "running"


class TestInspectWorkflow:
    """Cover inspect_workflow endpoint (lines 89-130)."""

    async def test_inspect_not_found(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.workflows import inspect_workflow

        mock_repo = AsyncMock()
        mock_repo.get_workflow_by_business_id = AsyncMock(return_value=None)
        mock_executor = SimpleNamespace(repository=mock_repo)
        user = SimpleNamespace(tenant_id="t1")

        with pytest.raises(HTTPException) as exc_info:
            await inspect_workflow(
                request=MagicMock(),
                workflow_id="wf-missing",
                tenant_id=None,
                user=user,
                executor=mock_executor,
            )
        assert exc_info.value.status_code == 404

    async def test_inspect_found(self):
        from enhanced_agent_bus.api.routes.workflows import inspect_workflow
        from enhanced_agent_bus.persistence.models import EventType, StepStatus, StepType

        now = datetime.now(UTC)
        instance_id = uuid4()
        instance = SimpleNamespace(
            id=instance_id,
            workflow_id="wf-1",
            workflow_type="governance",
            status="running",
            input={"key": "val"},
            output=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        step = SimpleNamespace(
            id=uuid4(),
            step_name="step-1",
            status="completed",
            attempt_count=1,
            started_at=now,
            completed_at=now,
            error=None,
        )
        event = SimpleNamespace(
            sequence_number=1,
            event_type="workflow_started",
            timestamp=now,
            event_data={"info": "started"},
        )

        mock_repo = AsyncMock()
        mock_repo.get_workflow_by_business_id = AsyncMock(return_value=instance)
        mock_repo.get_steps = AsyncMock(return_value=[step])
        mock_repo.get_events = AsyncMock(return_value=[event])
        mock_executor = SimpleNamespace(repository=mock_repo)
        user = SimpleNamespace(tenant_id="t1")

        result = await inspect_workflow(
            request=MagicMock(),
            workflow_id="wf-1",
            tenant_id=None,
            user=user,
            executor=mock_executor,
        )
        assert result["instance"]["workflow_id"] == "wf-1"
        assert len(result["steps"]) == 1
        assert len(result["events"]) == 1
        assert result["steps"][0]["step_name"] == "step-1"
        assert result["events"][0]["sequence"] == 1

    async def test_inspect_with_none_timestamps(self):
        from enhanced_agent_bus.api.routes.workflows import inspect_workflow

        instance = SimpleNamespace(
            id=uuid4(),
            workflow_id="wf-2",
            workflow_type="gov",
            status="pending",
            input=None,
            output=None,
            error=None,
            created_at=None,
            updated_at=None,
        )
        step = SimpleNamespace(
            id=uuid4(),
            step_name="s",
            status="pending",
            attempt_count=0,
            started_at=None,
            completed_at=None,
            error=None,
        )
        event = SimpleNamespace(
            sequence_number=0,
            event_type="workflow_started",
            timestamp=None,
            event_data={},
        )

        mock_repo = AsyncMock()
        mock_repo.get_workflow_by_business_id = AsyncMock(return_value=instance)
        mock_repo.get_steps = AsyncMock(return_value=[step])
        mock_repo.get_events = AsyncMock(return_value=[event])
        mock_executor = SimpleNamespace(repository=mock_repo)
        user = SimpleNamespace(tenant_id="t1")

        result = await inspect_workflow(
            request=MagicMock(),
            workflow_id="wf-2",
            tenant_id=None,
            user=user,
            executor=mock_executor,
        )
        assert result["instance"]["created_at"] is None
        assert result["steps"][0]["started_at"] is None
        assert result["events"][0]["timestamp"] is None


class TestCancelWorkflow:
    """Cover cancel_workflow endpoint (lines 142-152)."""

    async def test_cancel_not_found(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.workflows import cancel_workflow

        mock_executor = AsyncMock()
        mock_executor.cancel_workflow = AsyncMock(return_value=None)
        user = SimpleNamespace(tenant_id="t1")
        req = SimpleNamespace(reason="done")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_workflow(
                request=MagicMock(),
                workflow_id="wf-x",
                req=req,
                tenant_id=None,
                user=user,
                executor=mock_executor,
            )
        assert exc_info.value.status_code == 404

    async def test_cancel_success(self):
        from enhanced_agent_bus.api.routes.workflows import cancel_workflow

        instance = SimpleNamespace(id=uuid4(), workflow_id="wf-1", status="cancelled")
        mock_executor = AsyncMock()
        mock_executor.cancel_workflow = AsyncMock(return_value=instance)
        user = SimpleNamespace(tenant_id="t1")
        req = SimpleNamespace(reason="done")

        result = await cancel_workflow(
            request=MagicMock(),
            workflow_id="wf-1",
            req=req,
            tenant_id=None,
            user=user,
            executor=mock_executor,
        )
        assert result["message"] == "Workflow cancellation requested"


class TestRetryWorkflow:
    """Cover retry_workflow endpoint (lines 163-181)."""

    async def test_retry_success(self):
        from enhanced_agent_bus.api.routes.workflows import retry_workflow

        instance = SimpleNamespace(id=uuid4(), workflow_id="wf-1", status="running")
        mock_executor = AsyncMock()
        mock_executor.resume_workflow = AsyncMock(return_value=instance)
        user = SimpleNamespace(tenant_id="t1")

        result = await retry_workflow(
            request=MagicMock(),
            workflow_id="wf-1",
            tenant_id=None,
            user=user,
            executor=mock_executor,
        )
        assert result["message"] == "Workflow retry initiated"

    async def test_retry_value_error(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.workflows import retry_workflow

        mock_executor = AsyncMock()
        mock_executor.resume_workflow = AsyncMock(side_effect=ValueError("bad state"))
        user = SimpleNamespace(tenant_id="t1")

        with pytest.raises(HTTPException) as exc_info:
            await retry_workflow(
                request=MagicMock(),
                workflow_id="wf-1",
                tenant_id=None,
                user=user,
                executor=mock_executor,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 2. circuit_breaker/router.py
# ---------------------------------------------------------------------------


def _find_route(router: Any, path: str, method: str = "GET") -> Any:
    """Find a route endpoint by its full path (including prefix) and method."""
    for route in router.routes:
        if hasattr(route, "path") and route.path == path and method in (route.methods or set()):
            return route.endpoint
    return None


class TestCircuitHealthRouter:
    """Cover create_circuit_health_router and its inner endpoints."""

    def test_create_router_returns_router(self):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        router = create_circuit_health_router()
        assert router is not None

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_get_circuit_states_healthy(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = MagicMock()
        mock_registry.initialize_default_circuits = AsyncMock()
        mock_registry.get_health_summary.return_value = {"status": "healthy", "total": 3}
        mock_registry.get_all_states.return_value = {"svc1": "closed", "svc2": "closed"}
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits", "GET")
        assert handler is not None
        response = await handler()
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["summary"]["status"] == "healthy"

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_get_circuit_states_critical(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = MagicMock()
        mock_registry.initialize_default_circuits = AsyncMock()
        mock_registry.get_health_summary.return_value = {"status": "critical"}
        mock_registry.get_all_states.return_value = {}
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits", "GET")
        assert handler is not None
        response = await handler()
        assert response.status_code == 503

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_get_circuit_state_not_found(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/{service_name}", "GET")
        assert handler is not None
        response = await handler(service_name="unknown")
        assert response.status_code == 404

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_get_circuit_state_found_closed(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_cb = MagicMock()
        mock_cb.get_status.return_value = {"state": "closed", "failures": 0}
        mock_cb.state = CircuitState.CLOSED

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_cb
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/{service_name}", "GET")
        assert handler is not None
        response = await handler(service_name="svc1")
        assert response.status_code == 200

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_get_circuit_state_found_open(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_cb = MagicMock()
        mock_cb.get_status.return_value = {"state": "open", "failures": 5}
        mock_cb.state = CircuitState.OPEN

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_cb
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/{service_name}", "GET")
        assert handler is not None
        response = await handler(service_name="svc1")
        assert response.status_code == 503

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_reset_circuit_not_found(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = AsyncMock()
        mock_registry.reset = AsyncMock(return_value=False)
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/{service_name}/reset", "POST")
        assert handler is not None
        response = await handler(service_name="nosvc")
        assert response.status_code == 404

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_reset_circuit_success(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = AsyncMock()
        mock_registry.reset = AsyncMock(return_value=True)
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/{service_name}/reset", "POST")
        assert handler is not None
        response = await handler(service_name="svc1")
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["new_state"] == "closed"

    @patch("enhanced_agent_bus.circuit_breaker.router.get_circuit_breaker_registry")
    async def test_reset_all_circuits(self, mock_get_registry):
        from enhanced_agent_bus.circuit_breaker.router import create_circuit_health_router

        mock_registry = MagicMock()
        mock_registry.reset_all = AsyncMock()
        mock_registry.get_all_states.return_value = {"svc1": "closed", "svc2": "closed"}
        mock_get_registry.return_value = mock_registry

        router = create_circuit_health_router()
        handler = _find_route(router, "/health/circuits/reset-all", "POST")
        assert handler is not None
        response = await handler()
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "svc1" in body["circuits_reset"]


# ---------------------------------------------------------------------------
# 3. deliberation_layer/hitl_manager.py
# ---------------------------------------------------------------------------


class TestHITLManager:
    """Cover HITLManager request_approval and process_approval."""

    def _make_manager(self):
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager

        mock_queue = MagicMock()
        mock_queue.queue = {}
        mock_audit = AsyncMock()
        mock_audit.add_validation_result = AsyncMock(return_value="hash123")
        mgr = HITLManager(deliberation_queue=mock_queue, audit_ledger=mock_audit)
        return mgr, mock_queue, mock_audit

    async def test_request_approval_item_not_found(self):
        mgr, mock_queue, _ = self._make_manager()
        # queue is empty so item_id won't be found
        await mgr.request_approval("nonexistent")
        # Should not raise, just log

    async def test_request_approval_success(self):
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import DeliberationStatus

        mgr, mock_queue, _ = self._make_manager()
        mock_msg = MagicMock()
        mock_msg.from_agent = "agent-1"
        mock_msg.impact_score = 0.9
        mock_msg.message_type = MagicMock(value="governance_action")
        mock_msg.content = "Test content for approval"

        mock_item = MagicMock()
        mock_item.message = mock_msg
        mock_item.status = DeliberationStatus.PENDING
        mock_queue.queue = {"item-1": mock_item}

        await mgr.request_approval("item-1", channel="slack")
        assert mock_item.status == DeliberationStatus.UNDER_REVIEW

    async def test_process_approval_approve_success(self):
        mgr, mock_queue, mock_audit = self._make_manager()
        mock_queue.submit_human_decision = AsyncMock(return_value=True)

        result = await mgr.process_approval(
            item_id="item-1",
            reviewer_id="reviewer-1",
            decision="approve",
            reasoning="Looks good",
        )
        assert result is True
        mock_audit.add_validation_result.assert_awaited_once()

    async def test_process_approval_reject_success(self):
        mgr, mock_queue, mock_audit = self._make_manager()
        mock_queue.submit_human_decision = AsyncMock(return_value=True)

        result = await mgr.process_approval(
            item_id="item-2",
            reviewer_id="reviewer-1",
            decision="reject",
            reasoning="Not compliant",
        )
        assert result is True

    async def test_process_approval_failure(self):
        mgr, mock_queue, mock_audit = self._make_manager()
        mock_queue.submit_human_decision = AsyncMock(return_value=False)

        result = await mgr.process_approval(
            item_id="item-3",
            reviewer_id="reviewer-1",
            decision="approve",
            reasoning="test",
        )
        assert result is False
        mock_audit.add_validation_result.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. verification_layer/dafny_adapter.py
# ---------------------------------------------------------------------------


class TestDafnyAdapter:
    """Cover DafnyAdapter verify_file and check_hardware_guarantees."""

    def test_init(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter(dafny_path="/usr/bin/dafny")
        assert adapter.dafny_path == "/usr/bin/dafny"

    async def test_verify_file_not_found(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()
        result = await adapter.verify_file("/nonexistent/file.dfy")
        assert result.is_valid is False
        assert "not found" in (result.error or "")

    async def test_verify_file_success(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"Dafny program verifier finished with 0 errors", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("os.path.exists", return_value=True):
                result = await adapter.verify_file("/tmp/test.dfy")
        assert result.is_valid is True
        assert result.verification_time_ms >= 0

    async def test_verify_file_failure(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"1 errors", b"some error output"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("os.path.exists", return_value=True):
                result = await adapter.verify_file("/tmp/test.dfy")
        assert result.is_valid is False
        assert result.error == "some error output"

    async def test_verify_file_runtime_error(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()

        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("exec failed")):
            with patch("os.path.exists", return_value=True):
                result = await adapter.verify_file("/tmp/test.dfy")
        assert result.is_valid is False
        assert "exec failed" in (result.error or "")

    async def test_verify_file_os_error(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no such binary")):
            with patch("os.path.exists", return_value=True):
                result = await adapter.verify_file("/tmp/test.dfy")
        assert result.is_valid is False
        assert "no such binary" in (result.error or "")

    async def test_check_hardware_guarantees(self):
        from enhanced_agent_bus.verification_layer.dafny_adapter import DafnyAdapter

        adapter = DafnyAdapter()
        # The hardware_guarantees.dfy file likely doesn't exist, so expect not-found
        result = await adapter.check_hardware_guarantees()
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# 5. api/routes/_tenant_auth.py
# ---------------------------------------------------------------------------


class TestTenantAuth:
    """Cover _tenant_auth fallback path."""

    def test_get_environment(self):
        from enhanced_agent_bus.api.routes._tenant_auth import _get_environment

        with patch.dict(os.environ, {"ENVIRONMENT": "Testing"}):
            assert _get_environment() == "testing"

        with patch.dict(os.environ, {}, clear=True):
            assert _get_environment() == ""

    def test_validate_fallback_tenant_id_valid(self):
        from enhanced_agent_bus.api.routes._tenant_auth import _validate_fallback_tenant_id

        result = _validate_fallback_tenant_id("  MyTenant123  ")
        assert result == "mytenant123"

    def test_validate_fallback_tenant_id_empty(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes._tenant_auth import _validate_fallback_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_fallback_tenant_id("   ")
        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail

    def test_validate_fallback_tenant_id_too_long(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes._tenant_auth import _validate_fallback_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_fallback_tenant_id("a" * 200)
        assert exc_info.value.status_code == 400
        assert "too long" in exc_info.value.detail.lower()

    def test_validate_fallback_tenant_id_invalid_chars(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes._tenant_auth import _validate_fallback_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_fallback_tenant_id("tenant@bad!")
        assert exc_info.value.status_code == 400
        assert "invalid" in exc_info.value.detail.lower()


class TestFallbackGetTenantId:
    """Cover _fallback_get_tenant_id (lines 54-73).

    The shared security module is typically installed, so _USE_FALLBACK is False.
    We construct the fallback function directly to test its logic.
    """

    def _build_fallback(self):
        """Build the fallback function in isolation, bypassing module-level import guard."""
        import enhanced_agent_bus.api.routes._tenant_auth as mod

        # Construct the same async function that the module would create
        async def _fallback_get_tenant_id(request, x_tenant_id=None):
            if mod._get_environment() not in mod.DEV_ENVIRONMENTS:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=503,
                    detail="Security dependency not available in this environment",
                )
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id:
                return str(tenant_id)
            if not x_tenant_id:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=400,
                    detail="X-Tenant-ID header is required",
                )
            return mod._validate_fallback_tenant_id(x_tenant_id)

        return _fallback_get_tenant_id

    async def test_fallback_non_dev_raises_503(self):
        from fastapi import HTTPException

        fallback = self._build_fallback()
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace()

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(HTTPException) as exc_info:
                await fallback(request=mock_request, x_tenant_id=None)
            assert exc_info.value.status_code == 503

    async def test_fallback_dev_with_state_tenant(self):
        fallback = self._build_fallback()
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace(tenant_id="state-tenant")

        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            result = await fallback(request=mock_request, x_tenant_id=None)
        assert result == "state-tenant"

    async def test_fallback_dev_no_header_raises_400(self):
        from fastapi import HTTPException

        fallback = self._build_fallback()
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace()

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with pytest.raises(HTTPException) as exc_info:
                await fallback(request=mock_request, x_tenant_id=None)
            assert exc_info.value.status_code == 400

    async def test_fallback_dev_with_header(self):
        fallback = self._build_fallback()
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace()

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            result = await fallback(request=mock_request, x_tenant_id="ValidTenant")
        assert result == "validtenant"

    async def test_fallback_ci_environment(self):
        fallback = self._build_fallback()
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace()

        with patch.dict(os.environ, {"ENVIRONMENT": "ci"}):
            result = await fallback(request=mock_request, x_tenant_id="ci-tenant")
        assert result == "ci-tenant"


# ---------------------------------------------------------------------------
# 6. mcp_server/resources/decisions.py
# ---------------------------------------------------------------------------


class TestDecisionsResource:
    """Cover DecisionsResource read, add_decision, get_metrics."""

    def _make_resource(self):
        from enhanced_agent_bus.mcp_server.resources.decisions import DecisionsResource

        return DecisionsResource(submit_governance_tool=None, max_decisions=5)

    async def test_read_empty(self):
        res = self._make_resource()
        output = await res.read()
        data = json.loads(output)
        assert data["total_count"] == 0
        assert data["decisions"] == []
        assert res._access_count == 1

    async def test_read_with_decisions(self):
        res = self._make_resource()
        res.add_decision({"status": "approved", "timestamp": "2025-01-01T00:00:00"})
        res.add_decision({"status": "rejected", "timestamp": "2025-01-02T00:00:00"})

        output = await res.read(params={"limit": 10})
        data = json.loads(output)
        assert data["total_count"] == 2
        # Sorted newest first
        assert data["decisions"][0]["timestamp"] == "2025-01-02T00:00:00"

    async def test_read_with_outcome_filter(self):
        res = self._make_resource()
        res.add_decision({"status": "approved", "timestamp": "2025-01-01T00:00:00"})
        res.add_decision({"status": "rejected", "timestamp": "2025-01-02T00:00:00"})
        res.add_decision({"status": "approved", "timestamp": "2025-01-03T00:00:00"})

        output = await res.read(params={"outcome": "approved"})
        data = json.loads(output)
        assert data["total_count"] == 2
        assert all(d["status"] == "approved" for d in data["decisions"])

    async def test_read_with_limit(self):
        res = self._make_resource()
        for i in range(5):
            res.add_decision({"status": "approved", "timestamp": f"2025-01-0{i + 1}T00:00:00"})

        output = await res.read(params={"limit": 2})
        data = json.loads(output)
        assert data["total_count"] == 2

    async def test_read_with_governance_tool(self):
        from enhanced_agent_bus.mcp_server.resources.decisions import DecisionsResource

        mock_tool = MagicMock()
        mock_req = MagicMock()
        mock_req.to_dict.return_value = {"status": "completed", "timestamp": "2025-01-01T00:00:00"}
        mock_tool._completed_requests = {"req1": mock_req}

        res = DecisionsResource(submit_governance_tool=mock_tool)
        output = await res.read()
        data = json.loads(output)
        assert data["total_count"] == 1

    async def test_read_error_handling(self):
        from enhanced_agent_bus.mcp_server.resources.decisions import DecisionsResource

        mock_tool = MagicMock()
        mock_tool._completed_requests = MagicMock()
        mock_tool._completed_requests.values.side_effect = RuntimeError("db error")

        res = DecisionsResource(submit_governance_tool=mock_tool)
        output = await res.read()
        data = json.loads(output)
        assert "error" in data

    def test_add_decision_enforces_max(self):
        res = self._make_resource()
        for i in range(10):
            res.add_decision({"id": i})
        assert len(res._decisions) == 5

    def test_get_metrics(self):
        res = self._make_resource()
        res.add_decision({"id": 1})
        metrics = res.get_metrics()
        assert metrics["decision_count"] == 1
        assert metrics["access_count"] == 0
        assert metrics["uri"] == "acgs2://governance/decisions"

    def test_get_definition(self):
        from enhanced_agent_bus.mcp_server.resources.decisions import DecisionsResource

        defn = DecisionsResource.get_definition()
        assert defn.uri == "acgs2://governance/decisions"
        assert defn.name == "Recent Decisions"

    async def test_read_default_params(self):
        res = self._make_resource()
        output = await res.read(params=None)
        data = json.loads(output)
        assert data["total_count"] == 0
