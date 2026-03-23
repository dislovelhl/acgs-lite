from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from enhanced_agent_bus.api.dependencies import get_workflow_executor
from enhanced_agent_bus.api.routes.workflows import router as workflows_router
from enhanced_agent_bus.persistence.models import (
    EventType,
    StepType,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from src.core.shared.security.auth import UserClaims, get_current_user


pytestmark = pytest.mark.integration
_ROUTE_TIMEOUT_SECONDS = 2.0


def _claims_for(tenant_id: str) -> UserClaims:
    now = int(datetime.now(UTC).timestamp())
    return UserClaims(
        sub="workflow-smoke-user",
        tenant_id=tenant_id,
        roles=["admin"],
        permissions=["workflow:read"],
        exp=now + 3600,
        iat=now,
    )


async def _override_current_user() -> UserClaims:
    return _claims_for("smoke-tenant")


async def _route_request(awaitable: object, *, label: str):
    try:
        return await asyncio.wait_for(awaitable, timeout=_ROUTE_TIMEOUT_SECONDS)  # type: ignore[arg-type]
    except TimeoutError as exc:
        pytest.fail(f"{label} timed out in workflow route smoke test")  # pragma: no cover
        raise exc


class _FakeWorkflowRepository:
    def __init__(self) -> None:
        self.instances: dict[tuple[str, str], WorkflowInstance] = {}
        self.steps: dict[UUID, list[WorkflowStep]] = {}
        self.events: dict[UUID, list[WorkflowEvent]] = {}

    async def get_workflow_by_business_id(
        self, workflow_id: str, tenant_id: str
    ) -> WorkflowInstance | None:
        return self.instances.get((workflow_id, tenant_id))

    async def list_workflows(
        self,
        tenant_id: str,
        status: WorkflowStatus | None,
        limit: int,
    ) -> list[WorkflowInstance]:
        items = [
            instance
            for instance in self.instances.values()
            if instance.tenant_id == tenant_id and (status is None or instance.status == status)
        ]
        return items[:limit]

    async def get_steps(self, workflow_instance_id: UUID) -> list[WorkflowStep]:
        return list(self.steps.get(workflow_instance_id, []))

    async def get_events(self, workflow_instance_id: UUID) -> list[WorkflowEvent]:
        return list(self.events.get(workflow_instance_id, []))


class _FakeWorkflowExecutor:
    def __init__(self, repository: _FakeWorkflowRepository) -> None:
        self.repository = repository

    async def start_workflow(
        self,
        workflow_type: str,
        workflow_id: str,
        tenant_id: str,
        input_data: dict[str, object] | None = None,
    ) -> WorkflowInstance:
        instance = WorkflowInstance(
            workflow_type=workflow_type,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            input=input_data,
            status=WorkflowStatus.PENDING,
        )
        self.repository.instances[(workflow_id, tenant_id)] = instance
        self.repository.events[instance.id] = [
            WorkflowEvent(
                workflow_instance_id=instance.id,
                event_type=EventType.WORKFLOW_STARTED,
                event_data={"workflow_type": workflow_type, "input": input_data or {}},
                sequence_number=1,
            )
        ]
        self.repository.steps[instance.id] = [
            WorkflowStep(
                workflow_instance_id=instance.id,
                step_name="echo",
                step_type=StepType.ACTIVITY,
                status="completed",
                output={"source": (input_data or {}).get("source")},
                attempt_count=1,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        ]
        return instance

    async def execute_workflow(self, instance: WorkflowInstance) -> WorkflowInstance:
        instance.status = WorkflowStatus.COMPLETED
        instance.output = {
            "echo": instance.input or {},
            "workflow_id": instance.workflow_id,
            "tenant_id": instance.tenant_id,
        }
        instance.completed_at = datetime.now(UTC)
        instance.updated_at = datetime.now(UTC)
        events = self.repository.events.setdefault(instance.id, [])
        events.append(
            WorkflowEvent(
                workflow_instance_id=instance.id,
                event_type=EventType.WORKFLOW_COMPLETED,
                event_data={"output": instance.output},
                sequence_number=len(events) + 1,
            )
        )
        return instance


@pytest.mark.asyncio
async def test_workflow_routes_list_and_inspect_persisted_workflow() -> None:
    tenant_id = "smoke-tenant"
    repository = _FakeWorkflowRepository()
    executor = _FakeWorkflowExecutor(repository)

    async def _override_workflow_executor() -> _FakeWorkflowExecutor:
        return executor

    app = FastAPI()
    app.include_router(workflows_router)
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_workflow_executor] = _override_workflow_executor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        workflow_id = f"http-smoke-{uuid4().hex[:12]}"
        create_response = await _route_request(
            client.post(
                "/workflows",
                params={"tenant_id": tenant_id},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "workflow_type": "builtin.echo",
                    "workflow_id": workflow_id,
                    "input_data": {"source": "http-smoke-test"},
                    "execute_immediately": True,
                },
            ),
            label="create workflow request",
        )
        assert create_response.status_code == 200
        create_payload = create_response.json()
        assert create_payload["workflow_id"] == workflow_id
        assert create_payload["workflow_type"] == "builtin.echo"
        assert create_payload["tenant_id"] == tenant_id
        assert create_payload["status"] == "completed"
        assert create_payload["output"] == {
            "echo": {"source": "http-smoke-test"},
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
        }

        instance = await repository.get_workflow_by_business_id(workflow_id, tenant_id)
        assert instance is not None

        list_response = await _route_request(
            client.get(
                "/workflows",
                params={"tenant_id": tenant_id},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Tenant-ID": tenant_id,
                },
            ),
            label="list workflows request",
        )
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["total"] == 1
        assert list_payload["workflows"][0]["workflow_id"] == workflow_id

        inspect_response = await _route_request(
            client.get(
                f"/workflows/{workflow_id}",
                params={"tenant_id": tenant_id},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Tenant-ID": tenant_id,
                },
            ),
            label="inspect workflow request",
        )
        assert inspect_response.status_code == 200
        inspect_payload = inspect_response.json()
        assert inspect_payload["instance"]["workflow_id"] == workflow_id
        assert inspect_payload["instance"]["status"] == "completed"
        assert inspect_payload["instance"]["output"] == {
            "echo": {"source": "http-smoke-test"},
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
        }
        event_types = {event["event_type"] for event in inspect_payload["events"]}
        assert EventType.WORKFLOW_STARTED in event_types
        assert EventType.WORKFLOW_COMPLETED in event_types
