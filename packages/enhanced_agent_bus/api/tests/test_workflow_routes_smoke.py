from __future__ import annotations

import importlib
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from enhanced_agent_bus.api.app import create_app
from enhanced_agent_bus.persistence.executor import DurableWorkflowExecutor
from enhanced_agent_bus.persistence.models import EventType
from enhanced_agent_bus.persistence.postgres_repository import (
    PostgresWorkflowRepository,
    asyncpg_module,
)
from src.core.shared.security.auth import UserClaims, get_current_user


pytestmark = pytest.mark.integration


def _postgres_dsn() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )


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


@pytest.mark.asyncio
async def test_workflow_routes_list_and_inspect_persisted_workflow() -> None:
    if asyncpg_module is None:
        pytest.skip("asyncpg not installed")

    repository = PostgresWorkflowRepository(dsn=_postgres_dsn(), min_connections=1, max_connections=2)
    try:
        await repository.initialize()
    except Exception as exc:  # pragma: no cover - environment dependent skip
        pytest.skip(f"PostgreSQL not available for workflow route smoke test: {exc}")

    executor = DurableWorkflowExecutor(repository=repository, max_retries=1, retry_delay=0.0)
    tenant_id = "smoke-tenant"
    instance = None
    app: FastAPI = create_app()
    app.state.workflow_executor = executor
    app.state.workflow_repository = repository
    app.dependency_overrides[get_current_user] = _override_current_user
    importlib.import_module("enhanced_agent_bus.api.app")._register_builtin_workflows(executor)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            workflow_id = f"http-smoke-{uuid4().hex[:12]}"
            create_response = await client.post(
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

            list_response = await client.get(
                "/workflows",
                params={"tenant_id": tenant_id},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Tenant-ID": tenant_id,
                },
            )
            assert list_response.status_code == 200
            list_payload = list_response.json()
            assert list_payload["total"] >= 1
            assert any(item["workflow_id"] == workflow_id for item in list_payload["workflows"])

            inspect_response = await client.get(
                f"/workflows/{workflow_id}",
                params={"tenant_id": tenant_id},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Tenant-ID": tenant_id,
                },
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
    finally:
        app.dependency_overrides.clear()
        if instance is not None and repository._pool is not None:
            async with repository._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM workflow_events WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute(
                    "DELETE FROM workflow_compensations WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute(
                    "DELETE FROM workflow_checkpoints WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute("DELETE FROM workflow_steps WHERE workflow_instance_id = $1", instance.id)
                await conn.execute("DELETE FROM workflow_instances WHERE id = $1", instance.id)
        await repository.close()
