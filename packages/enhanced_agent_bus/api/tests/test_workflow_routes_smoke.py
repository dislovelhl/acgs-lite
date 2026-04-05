from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.api.dependencies import get_workflow_executor
from enhanced_agent_bus.api.routes.governance import (
    InMemoryPQCConfigBackend,
    MACIRecordStore,
)
from enhanced_agent_bus.api.routes.governance import (
    router as governance_router,
)
from enhanced_agent_bus.api.routes.workflows import router as workflows_router
from enhanced_agent_bus.api_exceptions import maci_error_handler
from enhanced_agent_bus.exceptions import MACIError
from enhanced_agent_bus.maci_enforcement import MACIEnforcer, MACIRoleRegistry
from enhanced_agent_bus.persistence.models import (
    EventType,
    StepType,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from enhanced_agent_bus.pqc_enforcement_config import EnforcementModeConfigService

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


def _build_governance_app() -> tuple[FastAPI, EnforcementModeConfigService]:
    app = FastAPI()
    app.state.maci_record_store = MACIRecordStore()
    app.state.maci_role_registry = MACIRoleRegistry()
    app.state.maci_enforcer = MACIEnforcer(registry=app.state.maci_role_registry, strict_mode=True)
    enforcement_service = EnforcementModeConfigService(redis_client=InMemoryPQCConfigBackend())
    app.state.pqc_enforcement_service = enforcement_service
    app.add_exception_handler(MACIError, maci_error_handler)
    app.include_router(governance_router)
    return app, enforcement_service


@pytest.mark.asyncio
async def test_governance_routes_execute_maci_validation_flow(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, _service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register_exec = await _route_request(
            client.post(
                "/api/v1/maci/agents",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "exec-1", "role": "executive"},
            ),
            label="register executive maci agent request",
        )
        assert register_exec.status_code == 201
        assert register_exec.json()["role"] == "EXECUTIVE"

        register_judicial = await _route_request(
            client.post(
                "/api/v1/maci/agents",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "jud-1", "role": "judicial"},
            ),
            label="register judicial maci agent request",
        )
        assert register_judicial.status_code == 201
        assert register_judicial.json()["role"] == "JUDICIAL"

        record_exec_output = await _route_request(
            client.post(
                "/api/v1/maci/outputs",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "exec-1", "output_id": "proposal-1"},
            ),
            label="record executive maci output request",
        )
        assert record_exec_output.status_code == 201
        record_exec_payload = record_exec_output.json()
        assert record_exec_payload["agent_id"] == "exec-1"
        assert record_exec_payload["output_id"] == "proposal-1"

        validate_proposal = await _route_request(
            client.post(
                "/api/v1/maci/actions/validate",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "exec-1", "action": "propose"},
            ),
            label="validate executive propose maci action request",
        )
        assert validate_proposal.status_code == 200
        validate_proposal_payload = validate_proposal.json()
        assert validate_proposal_payload["allowed"] is True
        assert validate_proposal_payload["action"] == "propose"

        validate_review = await _route_request(
            client.post(
                "/api/v1/maci/actions/validate",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "agent_id": "jud-1",
                    "action": "validate",
                    "target_output_id": "proposal-1",
                },
            ),
            label="validate judicial review maci action request",
        )
        assert validate_review.status_code == 200
        validate_review_payload = validate_review.json()
        assert validate_review_payload["allowed"] is True
        assert validate_review_payload["target_output_id"] == "proposal-1"


@pytest.mark.asyncio
async def test_governance_routes_block_self_validation_and_cross_tenant_access(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, _service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register_judicial = await _route_request(
            client.post(
                "/api/v1/maci/agents",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "jud-1", "role": "judicial"},
            ),
            label="register self-validating judicial maci agent request",
        )
        assert register_judicial.status_code == 201

        record_judicial_output = await _route_request(
            client.post(
                "/api/v1/maci/outputs",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"agent_id": "jud-1", "output_id": "judgment-1"},
            ),
            label="record judicial maci output request",
        )
        assert record_judicial_output.status_code == 201

        self_validation = await _route_request(
            client.post(
                "/api/v1/maci/actions/validate",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "agent_id": "jud-1",
                    "action": "validate",
                    "target_output_id": "judgment-1",
                },
            ),
            label="validate self review maci action request",
        )
        assert self_validation.status_code == 403
        self_validation_payload = self_validation.json()
        assert self_validation_payload["code"] == "MACI_SELF_VALIDATION"

        cross_tenant_validation = await _route_request(
            client.post(
                "/api/v1/maci/actions/validate",
                headers={"X-Tenant-ID": "tenant-b"},
                json={
                    "agent_id": "jud-1",
                    "action": "validate",
                    "target_output_id": "judgment-1",
                },
            ),
            label="validate cross tenant maci action request",
        )
        assert cross_tenant_validation.status_code == 403
        cross_tenant_payload = cross_tenant_validation.json()
        assert cross_tenant_payload["code"] == "MACI_ROLE_NOT_ASSIGNED"


@pytest.mark.asyncio
async def test_governance_routes_persist_maci_record_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, _service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "record_id": "rec-001",
                    "key_type": "pqc",
                    "key_algorithm": "ML-DSA-65",
                    "data": {"step": "draft"},
                },
            ),
            label="create maci record request",
        )
        assert create_response.status_code == 201
        create_payload = create_response.json()
        assert create_payload["record_id"] == "rec-001"
        assert create_payload["tenant_id"] == "tenant-a"
        assert create_payload["key_type"] == "pqc"
        assert create_payload["data"] == {"step": "draft"}

        duplicate_response = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"record_id": "rec-001", "data": {"step": "duplicate"}},
            ),
            label="duplicate maci record request",
        )
        assert duplicate_response.status_code == 409

        get_response = await _route_request(
            client.get(
                "/api/v1/maci/records/rec-001",
                headers={"X-Tenant-ID": "tenant-a"},
            ),
            label="get maci record request",
        )
        assert get_response.status_code == 200
        assert get_response.json()["data"] == {"step": "draft"}

        update_response = await _route_request(
            client.patch(
                "/api/v1/maci/records/rec-001",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"data": {"step": "approved"}},
            ),
            label="update maci record request",
        )
        assert update_response.status_code == 200
        update_payload = update_response.json()
        assert update_payload["data"] == {"step": "approved"}
        assert update_payload["key_type"] == "pqc"

        delete_response = await _route_request(
            client.delete(
                "/api/v1/maci/records/rec-001",
                headers={"X-Tenant-ID": "tenant-a"},
            ),
            label="delete maci record request",
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["data"] == {"step": "approved"}

        missing_response = await _route_request(
            client.get(
                "/api/v1/maci/records/rec-001",
                headers={"X-Tenant-ID": "tenant-a"},
            ),
            label="missing maci record request",
        )
        assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_governance_routes_isolate_maci_records_by_tenant(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, _service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"record_id": "shared-id", "data": {"owner": "tenant-a"}},
            ),
            label="tenant a create maci record request",
        )
        assert create_response.status_code == 201

        tenant_b_get = await _route_request(
            client.get(
                "/api/v1/maci/records/shared-id",
                headers={"X-Tenant-ID": "tenant-b"},
            ),
            label="tenant b get maci record request",
        )
        assert tenant_b_get.status_code == 404

        tenant_b_update = await _route_request(
            client.patch(
                "/api/v1/maci/records/shared-id",
                headers={"X-Tenant-ID": "tenant-b"},
                json={"data": {"owner": "tenant-b"}},
            ),
            label="tenant b update maci record request",
        )
        assert tenant_b_update.status_code == 404

        tenant_b_delete = await _route_request(
            client.delete(
                "/api/v1/maci/records/shared-id",
                headers={"X-Tenant-ID": "tenant-b"},
            ),
            label="tenant b delete maci record request",
        )
        assert tenant_b_delete.status_code == 404

        tenant_a_get = await _route_request(
            client.get(
                "/api/v1/maci/records/shared-id",
                headers={"X-Tenant-ID": "tenant-a"},
            ),
            label="tenant a get maci record request",
        )
        assert tenant_a_get.status_code == 200
        assert tenant_a_get.json()["data"] == {"owner": "tenant-a"}


@pytest.mark.asyncio
async def test_governance_routes_enforce_stored_key_type_on_update(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, enforcement_service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        pqc_create = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "record_id": "pqc-record",
                    "key_type": "pqc",
                    "key_algorithm": "ML-DSA-65",
                    "data": {"version": 1},
                },
            ),
            label="create pqc maci record request",
        )
        assert pqc_create.status_code == 201

        classical_create = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "record_id": "classical-record",
                    "key_type": "classical",
                    "key_algorithm": "RSA-2048",
                    "data": {"version": 1},
                },
            ),
            label="create classical maci record request",
        )
        assert classical_create.status_code == 201

        await enforcement_service.set_mode(mode="strict", activated_by="test-suite")

        pqc_update = await _route_request(
            client.patch(
                "/api/v1/maci/records/pqc-record",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"data": {"version": 2}},
            ),
            label="update pqc maci record request",
        )
        assert pqc_update.status_code == 200
        assert pqc_update.json()["data"] == {"version": 2}

        classical_update = await _route_request(
            client.patch(
                "/api/v1/maci/records/classical-record",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"data": {"version": 2}},
            ),
            label="update classical maci record request",
        )
        assert classical_update.status_code == 422
        detail = classical_update.json()["detail"]
        assert detail["error_code"] == "MIGRATION_REQUIRED"


@pytest.mark.asyncio
async def test_governance_routes_report_duplicate_record_before_strict_pqc_validation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    app, enforcement_service = _build_governance_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={
                    "record_id": "dup-pqc-record",
                    "key_type": "pqc",
                    "key_algorithm": "ML-DSA-65",
                    "data": {"version": 1},
                },
            ),
            label="create pqc maci record before duplicate request",
        )
        assert create_response.status_code == 201

        await enforcement_service.set_mode(mode="strict", activated_by="test-suite")

        duplicate_response = await _route_request(
            client.post(
                "/api/v1/maci/records",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"record_id": "dup-pqc-record", "data": {"version": 2}},
            ),
            label="duplicate maci record under strict mode request",
        )
        assert duplicate_response.status_code == 409
