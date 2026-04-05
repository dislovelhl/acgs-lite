# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/visual_studio/api.py
Target: ≥90% coverage of the API module.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.visual_studio.models import (
    ExportFormat,
    NodeType,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowListResponse,
    WorkflowNode,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SyncASGIClient:
    """Synchronous wrapper around httpx ASGI transport for deterministic tests."""

    def __init__(self, app, raise_server_exceptions: bool = True) -> None:
        self._app = app
        self._raise = raise_server_exceptions

    def request(self, method: str, url: str, **kwargs):
        async def _call():
            transport = httpx.ASGITransport(
                app=self._app,
                raise_app_exceptions=self._raise,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.request(method, url, **kwargs)

        return asyncio.run(_call())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


_NOW = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)


def _mock_user(tenant_id: str = "tenant-test") -> UserClaims:
    return UserClaims(
        sub="user-123",
        tenant_id=tenant_id,
        roles=["agent"],
        permissions=["read", "write"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


def _async_override(value):
    async def _dependency():
        return value

    return _dependency


def _make_node(
    node_id: str = "node-start",
    node_type: NodeType = NodeType.START,
    position: dict | None = None,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=node_type,
        position=position or {"x": 0.0, "y": 0.0},
        data={"label": node_id},
    )


def _make_workflow(
    workflow_id: str = "wf-abc12345",
    name: str = "Test Workflow",
    nodes: list[WorkflowNode] | None = None,
    edges: list[WorkflowEdge] | None = None,
    tenant_id: str | None = None,
) -> WorkflowDefinition:
    if nodes is None:
        nodes = [_make_node("node-start", NodeType.START), _make_node("node-end", NodeType.END)]
    return WorkflowDefinition(
        id=workflow_id,
        name=name,
        description="desc",
        nodes=nodes,
        edges=edges or [],
        tenant_id=tenant_id,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_summary(wf: WorkflowDefinition) -> WorkflowSummary:
    return WorkflowSummary(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        node_count=len(wf.nodes),
        edge_count=len(wf.edges),
        updated_at=wf.updated_at,
        version=wf.version,
        is_active=wf.is_active,
    )


def _make_validation_result(is_valid: bool = True) -> WorkflowValidationResult:
    return WorkflowValidationResult(is_valid=is_valid, errors=[], warnings=[])


def _make_simulation_result(wf_id: str = "wf-abc12345") -> WorkflowSimulationResult:
    return WorkflowSimulationResult(workflow_id=wf_id, success=True, steps=[], final_output={})


def _make_export_result(wf_id: str = "wf-abc12345") -> WorkflowExportResult:
    return WorkflowExportResult(
        workflow_id=wf_id,
        format=ExportFormat.JSON,
        content='{"id": "wf-abc12345"}',
        filename="test_workflow.json",
    )


# ---------------------------------------------------------------------------
# Fixture: FastAPI app with mocked service
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_service():
    svc = MagicMock()
    svc.create_workflow = AsyncMock()
    svc.get_workflow = AsyncMock()
    svc.save_workflow = AsyncMock()
    svc.delete_workflow = AsyncMock()
    svc.list_workflows = AsyncMock()
    svc.validate_workflow = MagicMock()
    svc.simulate_workflow = AsyncMock()
    svc.export_workflow = AsyncMock()
    return svc


@pytest.fixture()
def app(mock_service):
    """Build a FastAPI app with the vs router and mock service override."""
    from enhanced_agent_bus.visual_studio.api import get_service, router

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_service] = _async_override(mock_service)
    application.dependency_overrides[get_current_user] = _async_override(_mock_user())
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app):
    return SyncASGIClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /api/v1/visual/workflows  (create_workflow)
# ---------------------------------------------------------------------------


class TestCreateWorkflow:
    def test_create_workflow_success(self, client, mock_service):
        wf = _make_workflow()
        mock_service.create_workflow.return_value = wf

        resp = client.post("/api/v1/visual/workflows?name=Test+Workflow")
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == wf.id
        assert data["name"] == wf.name

    def test_create_workflow_with_optional_params(self, app, client, mock_service):
        app.dependency_overrides[get_current_user] = _async_override(
            _mock_user(tenant_id="tenant-1")
        )
        wf = _make_workflow(tenant_id="tenant-1")
        mock_service.create_workflow.return_value = wf

        resp = client.post(
            "/api/v1/visual/workflows?name=My+WF&description=some+desc&tenant_id=tenant-1"
        )
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == "tenant-1"

    def test_create_workflow_cross_tenant_forbidden(self, client, mock_service):
        resp = client.post("/api/v1/visual/workflows?name=My+WF&tenant_id=tenant-other")
        assert resp.status_code == 403

    def test_create_workflow_missing_name(self, client, mock_service):
        resp = client.post("/api/v1/visual/workflows")
        assert resp.status_code == 422

    def test_create_workflow_name_empty(self, client, mock_service):
        resp = client.post("/api/v1/visual/workflows?name=")
        assert resp.status_code == 422

    def test_create_workflow_service_raises_runtime_error(self, client, mock_service):
        mock_service.create_workflow.side_effect = RuntimeError("DB unavailable")

        resp = client.post("/api/v1/visual/workflows?name=Test")
        assert resp.status_code == 500
        assert "Failed to create workflow" in resp.json()["detail"]

    def test_create_workflow_service_raises_value_error(self, client, mock_service):
        mock_service.create_workflow.side_effect = ValueError("bad value")

        resp = client.post("/api/v1/visual/workflows?name=Test")
        assert resp.status_code == 500

    def test_create_workflow_service_raises_type_error(self, client, mock_service):
        mock_service.create_workflow.side_effect = TypeError("type issue")

        resp = client.post("/api/v1/visual/workflows?name=Test")
        assert resp.status_code == 500

    def test_create_workflow_service_raises_attribute_error(self, client, mock_service):
        mock_service.create_workflow.side_effect = AttributeError("attr issue")

        resp = client.post("/api/v1/visual/workflows?name=Test")
        assert resp.status_code == 500

    def test_create_workflow_service_raises_os_error(self, client, mock_service):
        mock_service.create_workflow.side_effect = OSError("io error")

        resp = client.post("/api/v1/visual/workflows?name=Test")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/visual/workflows/{workflow_id}  (get_workflow)
# ---------------------------------------------------------------------------


class TestGetWorkflow:
    def test_get_workflow_success(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf

        resp = client.get("/api/v1/visual/workflows/wf-abc12345")
        assert resp.status_code == 200
        assert resp.json()["id"] == wf.id

    def test_get_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.get("/api/v1/visual/workflows/missing-id")
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PUT /api/v1/visual/workflows/{workflow_id}  (update_workflow)
# ---------------------------------------------------------------------------


class TestUpdateWorkflow:
    def _wf_body(self, workflow_id: str = "wf-abc12345") -> dict:
        wf = _make_workflow(workflow_id=workflow_id)
        body = wf.model_dump(mode="json")
        return body

    def test_update_workflow_success(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.return_value = wf

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == wf.id

    def test_update_workflow_id_mismatch(self, client, mock_service):
        resp = client.put(
            "/api/v1/visual/workflows/different-id",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 400
        assert "does not match" in resp.json()["detail"]

    def test_update_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 404

    def test_update_workflow_save_raises_runtime_error(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.side_effect = RuntimeError("save failed")

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 500
        assert "Failed to update workflow" in resp.json()["detail"]

    def test_update_workflow_save_raises_value_error(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.side_effect = ValueError("v err")

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 500

    def test_update_workflow_save_raises_attribute_error(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.side_effect = AttributeError("attr err")

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 500

    def test_update_workflow_save_raises_type_error(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.side_effect = TypeError("type err")

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 500

    def test_update_workflow_save_raises_os_error(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.side_effect = OSError("os err")

        resp = client.put(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/v1/visual/workflows/{workflow_id}  (save_workflow alias)
# ---------------------------------------------------------------------------


class TestSaveWorkflow:
    def _wf_body(self, workflow_id: str = "wf-abc12345") -> dict:
        return _make_workflow(workflow_id=workflow_id).model_dump(mode="json")

    def test_save_workflow_success(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.save_workflow.return_value = wf

        resp = client.post(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == wf.id

    def test_save_workflow_id_mismatch(self, client, mock_service):
        resp = client.post(
            "/api/v1/visual/workflows/other-id",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 400

    def test_save_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.post(
            "/api/v1/visual/workflows/wf-abc12345",
            json=self._wf_body("wf-abc12345"),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/visual/workflows/{workflow_id}  (delete_workflow)
# ---------------------------------------------------------------------------


class TestDeleteWorkflow:
    def test_delete_workflow_success(self, client, mock_service):
        mock_service.delete_workflow.return_value = True

        resp = client.delete("/api/v1/visual/workflows/wf-abc12345")
        assert resp.status_code == 204

    def test_delete_workflow_not_found(self, client, mock_service):
        mock_service.delete_workflow.return_value = False

        resp = client.delete("/api/v1/visual/workflows/missing-id")
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/visual/workflows  (list_workflows)
# ---------------------------------------------------------------------------


class TestListWorkflows:
    def test_list_workflows_default(self, client, mock_service):
        wf = _make_workflow()
        summaries = [_make_summary(wf)]
        mock_service.list_workflows.return_value = (summaries, 1)

        resp = client.get("/api/v1/visual/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["workflows"]) == 1

    def test_list_workflows_with_tenant_filter(self, app, client, mock_service):
        app.dependency_overrides[get_current_user] = _async_override(_mock_user(tenant_id="t-123"))
        mock_service.list_workflows.return_value = ([], 0)

        resp = client.get("/api/v1/visual/workflows?tenant_id=t-123&page=2&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["page"] == 2
        assert data["page_size"] == 5

    def test_list_workflows_invalid_page(self, client, mock_service):
        resp = client.get("/api/v1/visual/workflows?page=0")
        assert resp.status_code == 422

    def test_list_workflows_page_size_too_large(self, client, mock_service):
        resp = client.get("/api/v1/visual/workflows?page_size=101")
        assert resp.status_code == 422

    def test_list_workflows_empty(self, client, mock_service):
        mock_service.list_workflows.return_value = ([], 0)

        resp = client.get("/api/v1/visual/workflows")
        assert resp.status_code == 200
        assert resp.json()["workflows"] == []


# ---------------------------------------------------------------------------
# POST /api/v1/visual/workflows/{workflow_id}/validate
# ---------------------------------------------------------------------------


class TestValidateWorkflow:
    def test_validate_workflow_valid(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.validate_workflow.return_value = _make_validation_result(is_valid=True)

        resp = client.post("/api/v1/visual/workflows/wf-abc12345/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["errors"] == []

    def test_validate_workflow_invalid(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.validate_workflow.return_value = _make_validation_result(is_valid=False)

        resp = client.post("/api/v1/visual/workflows/wf-abc12345/validate")
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False

    def test_validate_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.post("/api/v1/visual/workflows/missing/validate")
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/v1/visual/workflows/{workflow_id}/simulate
# ---------------------------------------------------------------------------


class TestSimulateWorkflow:
    def test_simulate_workflow_success(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.simulate_workflow.return_value = _make_simulation_result()

        resp = client.post("/api/v1/visual/workflows/wf-abc12345/simulate")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_simulate_workflow_with_input_data(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.simulate_workflow.return_value = _make_simulation_result()

        resp = client.post(
            "/api/v1/visual/workflows/wf-abc12345/simulate",
            json={"key": "value"},
        )
        assert resp.status_code == 200

    def test_simulate_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.post("/api/v1/visual/workflows/missing/simulate")
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]

    def test_simulate_workflow_failed_result(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        failed = WorkflowSimulationResult(
            workflow_id="wf-abc12345",
            success=False,
            error_message="No start node",
        )
        mock_service.simulate_workflow.return_value = failed

        resp = client.post("/api/v1/visual/workflows/wf-abc12345/simulate")
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert resp.json()["error_message"] == "No start node"


# ---------------------------------------------------------------------------
# POST /api/v1/visual/workflows/{workflow_id}/export
# ---------------------------------------------------------------------------


class TestExportWorkflow:
    def test_export_workflow_json(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        mock_service.export_workflow.return_value = _make_export_result()

        body = {"format": "json", "include_metadata": True}
        resp = client.post("/api/v1/visual/workflows/wf-abc12345/export", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "json"
        assert "content" in data

    def test_export_workflow_yaml(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        export_result = WorkflowExportResult(
            workflow_id="wf-abc12345",
            format=ExportFormat.YAML,
            content="id: wf-abc12345\n",
            filename="test_workflow.yaml",
        )
        mock_service.export_workflow.return_value = export_result

        body = {"format": "yaml", "include_metadata": True}
        resp = client.post("/api/v1/visual/workflows/wf-abc12345/export", json=body)
        assert resp.status_code == 200
        assert resp.json()["format"] == "yaml"

    def test_export_workflow_rego(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf
        export_result = WorkflowExportResult(
            workflow_id="wf-abc12345",
            format=ExportFormat.REGO,
            content="package acgs2\ndefault allow := false",
            filename="test_workflow.rego",
        )
        mock_service.export_workflow.return_value = export_result

        body = {"format": "rego", "include_metadata": False}
        resp = client.post("/api/v1/visual/workflows/wf-abc12345/export", json=body)
        assert resp.status_code == 200
        assert resp.json()["format"] == "rego"

    def test_export_workflow_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        body = {"format": "json", "include_metadata": True}
        resp = client.post("/api/v1/visual/workflows/missing/export", json=body)
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/visual/workflows/{workflow_id}/summary
# ---------------------------------------------------------------------------


class TestGetWorkflowSummary:
    def test_get_summary_success(self, client, mock_service):
        nodes = [
            _make_node("node-start", NodeType.START),
            _make_node("node-end", NodeType.END),
        ]
        edge = WorkflowEdge(id="e1", source="node-start", target="node-end")
        wf = _make_workflow(nodes=nodes, edges=[edge])
        mock_service.get_workflow.return_value = wf

        resp = client.get("/api/v1/visual/workflows/wf-abc12345/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == wf.id
        assert data["node_count"] == 2
        assert data["edge_count"] == 1
        assert data["version"] == wf.version
        assert data["is_active"] == wf.is_active

    def test_get_summary_not_found(self, client, mock_service):
        mock_service.get_workflow.return_value = None

        resp = client.get("/api/v1/visual/workflows/missing/summary")
        assert resp.status_code == 404
        assert "Workflow not found" in resp.json()["detail"]

    def test_get_summary_with_description(self, client, mock_service):
        wf = _make_workflow()
        mock_service.get_workflow.return_value = wf

        resp = client.get(f"/api/v1/visual/workflows/{wf.id}/summary")
        assert resp.status_code == 200
        assert resp.json()["description"] == "desc"

    def test_get_summary_no_description(self, client, mock_service):
        wf = WorkflowDefinition(
            id="wf-nodesc",
            name="No Desc",
            nodes=[_make_node("n1", NodeType.START), _make_node("n2", NodeType.END)],
            edges=[],
            created_at=_NOW,
            updated_at=_NOW,
        )
        mock_service.get_workflow.return_value = wf

        resp = client.get("/api/v1/visual/workflows/wf-nodesc/summary")
        assert resp.status_code == 200
        assert resp.json()["description"] is None


# ---------------------------------------------------------------------------
# Module-level: get_service dependency function
# ---------------------------------------------------------------------------


class TestGetServiceDependency:
    def test_get_service_returns_visual_studio_service(self):
        """get_service() should return a VisualStudioService instance."""
        from enhanced_agent_bus.visual_studio.api import get_service
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = get_service()
        assert isinstance(svc, VisualStudioService)

    def test_get_service_same_instance_as_global(self):
        """get_service() delegates to get_visual_studio_service()."""
        from enhanced_agent_bus.visual_studio.api import get_service
        from enhanced_agent_bus.visual_studio.service import get_visual_studio_service

        assert get_service() is get_visual_studio_service()


# ---------------------------------------------------------------------------
# __all__ and module-level exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        from enhanced_agent_bus.visual_studio import api

        expected = {
            "router",
            "create_workflow",
            "get_workflow",
            "update_workflow",
            "delete_workflow",
            "list_workflows",
            "validate_workflow",
            "simulate_workflow",
            "export_workflow",
        }
        assert set(api.__all__) == expected

    def test_router_prefix(self):
        from enhanced_agent_bus.visual_studio.api import router

        assert router.prefix == "/api/v1/visual"

    def test_router_tags(self):
        from enhanced_agent_bus.visual_studio.api import router

        assert "Visual Studio" in router.tags

    def test_visual_studio_operation_errors_tuple(self):
        from enhanced_agent_bus.visual_studio.api import (
            VISUAL_STUDIO_OPERATION_ERRORS,
        )

        assert AttributeError in VISUAL_STUDIO_OPERATION_ERRORS
        assert OSError in VISUAL_STUDIO_OPERATION_ERRORS
        assert RuntimeError in VISUAL_STUDIO_OPERATION_ERRORS
        assert TypeError in VISUAL_STUDIO_OPERATION_ERRORS
        assert ValueError in VISUAL_STUDIO_OPERATION_ERRORS
