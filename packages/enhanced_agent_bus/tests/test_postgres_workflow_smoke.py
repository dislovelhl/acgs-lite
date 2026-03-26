from __future__ import annotations

import os
from uuid import uuid4

import pytest

from enhanced_agent_bus.persistence.executor import DurableWorkflowExecutor, WorkflowContext
from enhanced_agent_bus.persistence.models import EventType, WorkflowStatus
from enhanced_agent_bus.persistence.postgres_repository import (
    PostgresWorkflowRepository,
    asyncpg_module,
)

pytestmark = pytest.mark.integration


def _postgres_dsn() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )


@pytest.mark.asyncio
async def test_postgres_workflow_smoke_persists_end_to_end() -> None:
    if asyncpg_module is None:
        pytest.skip("asyncpg not installed")

    repository = PostgresWorkflowRepository(
        dsn=_postgres_dsn(), min_connections=1, max_connections=2
    )
    try:
        await repository.initialize()
    except Exception as exc:  # pragma: no cover - environment dependent skip
        pytest.skip(f"PostgreSQL not available for smoke test: {exc}")

    executor = DurableWorkflowExecutor(repository=repository, max_retries=1, retry_delay=0.0)
    workflow_id = f"smoke-{uuid4().hex[:12]}"
    tenant_id = "smoke-tenant"
    instance = None

    @executor.workflow("postgres-smoke")
    async def postgres_smoke_workflow(ctx: WorkflowContext) -> dict[str, str]:
        return {"result": "ok", "workflow_id": ctx.workflow_id}

    try:
        instance = await executor.start_workflow(
            workflow_type="postgres-smoke",
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            input_data={"source": "smoke-test"},
        )
        completed = await executor.execute_workflow(instance)

        persisted = await repository.get_workflow_by_business_id(workflow_id, tenant_id)
        assert persisted is not None
        assert completed.status == WorkflowStatus.COMPLETED
        assert persisted.status == WorkflowStatus.COMPLETED
        assert persisted.output == {"result": "ok", "workflow_id": workflow_id}

        events = await repository.get_events(instance.id)
        event_types = [event.event_type for event in events]
        assert EventType.WORKFLOW_STARTED in event_types
        assert EventType.WORKFLOW_COMPLETED in event_types
    finally:
        if instance is not None and repository._pool is not None:
            async with repository._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM workflow_events WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute(
                    "DELETE FROM workflow_compensations WHERE workflow_instance_id = $1",
                    instance.id,
                )
                await conn.execute(
                    "DELETE FROM workflow_checkpoints WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute(
                    "DELETE FROM workflow_steps WHERE workflow_instance_id = $1", instance.id
                )
                await conn.execute("DELETE FROM workflow_instances WHERE id = $1", instance.id)
        await repository.close()
