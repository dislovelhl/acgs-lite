"""Direct invocation tests for Visual Studio API handlers (no HTTP transport)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.security.auth import UserClaims
from enhanced_agent_bus.visual_studio.api import (
    _resolve_tenant_id,
    create_workflow,
    delete_workflow,
    export_workflow,
    get_workflow,
    get_workflow_summary,
    list_workflows,
    simulate_workflow,
    update_workflow,
    validate_workflow,
)
from enhanced_agent_bus.visual_studio.models import (
    NodeType,
    WorkflowDefinition,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowNode,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)


def _user(tenant_id: str = "tenant-a") -> UserClaims:
    return UserClaims(
        sub="user-1",
        tenant_id=tenant_id,
        roles=["agent"],
        permissions=["read", "write"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


def _workflow(workflow_id: str = "wf-1", tenant_id: str = "tenant-a") -> WorkflowDefinition:
    now = datetime.now(UTC)
    return WorkflowDefinition(
        id=workflow_id,
        name="Workflow",
        description="desc",
        nodes=[
            WorkflowNode(id="start", type=NodeType.START, position={"x": 0.0, "y": 0.0}, data={}),
            WorkflowNode(id="end", type=NodeType.END, position={"x": 1.0, "y": 1.0}, data={}),
        ],
        edges=[],
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
    )


def test_resolve_tenant_id_allows_same_tenant() -> None:
    assert _resolve_tenant_id(_user("t1"), "t1") == "t1"


def test_resolve_tenant_id_rejects_cross_tenant() -> None:
    with pytest.raises(HTTPException) as exc:
        _resolve_tenant_id(_user("t1"), "t2")
    assert exc.value.status_code == 403


async def test_create_workflow_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.create_workflow = AsyncMock(return_value=wf)

    result = await create_workflow(
        name="Workflow",
        description="desc",
        tenant_id="tenant-a",
        user=_user("tenant-a"),
        service=service,
    )
    assert result.id == "wf-1"


async def test_get_workflow_not_found_raises_404() -> None:
    service = MagicMock()
    service.get_workflow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await get_workflow("missing", service=service)
    assert exc.value.status_code == 404


async def test_update_workflow_id_mismatch_raises_400() -> None:
    service = MagicMock()
    wf = _workflow(workflow_id="wf-real")

    with pytest.raises(HTTPException) as exc:
        await update_workflow("wf-other", wf, service=service)
    assert exc.value.status_code == 400


async def test_list_workflows_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.list_workflows = AsyncMock(
        return_value=(
            [
                WorkflowSummary(
                    id=wf.id,
                    name=wf.name,
                    description=wf.description,
                    node_count=len(wf.nodes),
                    edge_count=len(wf.edges),
                    updated_at=wf.updated_at,
                    version=wf.version,
                    is_active=wf.is_active,
                )
            ],
            1,
        )
    )

    result = await list_workflows(
        tenant_id="tenant-a",
        page=1,
        page_size=20,
        user=_user("tenant-a"),
        service=service,
    )
    assert result.total == 1
    assert len(result.workflows) == 1


async def test_delete_workflow_missing_raises_404() -> None:
    service = MagicMock()
    service.delete_workflow = AsyncMock(return_value=False)

    with pytest.raises(HTTPException) as exc:
        await delete_workflow("missing", service=service)
    assert exc.value.status_code == 404


async def test_validate_workflow_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.get_workflow = AsyncMock(return_value=wf)
    service.validate_workflow = MagicMock(return_value=WorkflowValidationResult(is_valid=True))

    result = await validate_workflow("wf-1", service=service)
    assert result.is_valid is True


async def test_validate_workflow_not_found_raises_404() -> None:
    service = MagicMock()
    service.get_workflow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await validate_workflow("missing", service=service)
    assert exc.value.status_code == 404


async def test_simulate_workflow_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.get_workflow = AsyncMock(return_value=wf)
    service.simulate_workflow = AsyncMock(
        return_value=WorkflowSimulationResult(workflow_id=wf.id, success=True)
    )

    result = await simulate_workflow("wf-1", input_data={"k": "v"}, service=service)
    assert result.success is True


async def test_export_workflow_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.get_workflow = AsyncMock(return_value=wf)
    service.export_workflow = AsyncMock(
        return_value=WorkflowExportResult(
            workflow_id=wf.id,
            format="json",
            content="{}",
            filename="wf.json",
        )
    )

    result = await export_workflow(
        "wf-1",
        request=WorkflowExportRequest(format="json"),
        service=service,
    )
    assert result.workflow_id == wf.id


async def test_get_workflow_summary_success() -> None:
    service = MagicMock()
    wf = _workflow()
    service.get_workflow = AsyncMock(return_value=wf)

    summary = await get_workflow_summary("wf-1", service=service)
    assert summary.id == wf.id
    assert summary.node_count == len(wf.nodes)
