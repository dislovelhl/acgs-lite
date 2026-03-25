"""
Shared fixtures for Saga Orchestration tests.
Constitutional Hash: 608508a9bd224290
"""

from typing import Optional

import pytest

from enterprise_sso.saga_orchestration import (
    CONSTITUTIONAL_HASH,
    Saga,
    SagaContext,
    SagaDefinition,
    SagaEventPublisher,
    SagaOrchestrator,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
    SagaStore,
)


class InMemorySagaStore(SagaStore):
    """In-memory saga store for tests (no Redis required)."""

    def __init__(self):
        super().__init__()
        self._sagas: dict[str, Saga] = {}
        self._tenant_index: dict[str, set[str]] = {}

    async def _get_redis(self):
        raise RuntimeError("InMemorySagaStore should not use Redis")

    async def save(self, saga: Saga) -> None:
        self._sagas[saga.saga_id] = saga
        if saga.tenant_id not in self._tenant_index:
            self._tenant_index[saga.tenant_id] = set()
        self._tenant_index[saga.tenant_id].add(saga.saga_id)

    async def get(self, saga_id: str) -> Saga | None:
        return self._sagas.get(saga_id)

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: SagaStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Saga]:
        saga_ids = list(self._tenant_index.get(tenant_id, set()))[offset : offset + limit]
        sagas = []
        for sid in saga_ids:
            saga = self._sagas.get(sid)
            if saga and (status is None or saga.status == status):
                sagas.append(saga)
        return sagas

    async def delete(self, saga_id: str) -> bool:
        saga = self._sagas.pop(saga_id, None)
        if not saga:
            return False
        tenant_ids = self._tenant_index.get(saga.tenant_id, set())
        tenant_ids.discard(saga_id)
        return True

    async def get_pending_compensations(self) -> list[Saga]:
        return [
            saga
            for saga in self._sagas.values()
            if saga.status in (SagaStatus.COMPENSATING, SagaStatus.PARTIALLY_COMPENSATED)
        ]


@pytest.fixture
def saga_store() -> SagaStore:
    """Create an in-memory saga store for testing (no Redis required)."""
    return InMemorySagaStore()


@pytest.fixture
def event_publisher() -> SagaEventPublisher:
    """Create an event publisher for testing."""
    return SagaEventPublisher()


@pytest.fixture
def orchestrator(saga_store: SagaStore, event_publisher: SagaEventPublisher) -> SagaOrchestrator:
    """Create a saga orchestrator for testing."""
    return SagaOrchestrator(
        store=saga_store,
        event_publisher=event_publisher,
    )


@pytest.fixture
def simple_saga_definition() -> SagaDefinition:
    """Create a simple saga definition for testing."""

    async def step1_action(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step1_executed"] = True
        return SagaStepResult(success=True, data={"step1": "completed"})

    async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step1_compensated"] = True
        return SagaStepResult(success=True, data={"step1": "compensated"})

    async def step2_action(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step2_executed"] = True
        return SagaStepResult(success=True, data={"step2": "completed"})

    async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step2_compensated"] = True
        return SagaStepResult(success=True, data={"step2": "compensated"})

    return SagaDefinition(
        name="simple_saga",
        description="A simple saga for testing",
        steps=[
            SagaStepDefinition(
                name="step1",
                description="First step",
                action=step1_action,
                compensation=step1_compensation,
                order=0,
            ),
            SagaStepDefinition(
                name="step2",
                description="Second step",
                action=step2_action,
                compensation=step2_compensation,
                order=1,
            ),
        ],
    )


@pytest.fixture
def failing_saga_definition() -> SagaDefinition:
    """Create a saga that fails on the second step."""

    async def step1_action(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step1_executed"] = True
        return SagaStepResult(success=True, data={"step1": "completed"})

    async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
        ctx.data["step1_compensated"] = True
        return SagaStepResult(success=True)

    async def step2_action(ctx: SagaContext) -> SagaStepResult:
        return SagaStepResult(success=False, error="Simulated failure")

    async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
        return SagaStepResult(success=True)

    return SagaDefinition(
        name="failing_saga",
        description="A saga that fails on step 2",
        steps=[
            SagaStepDefinition(
                name="step1",
                description="First step",
                action=step1_action,
                compensation=step1_compensation,
                max_retries=0,
                order=0,
            ),
            SagaStepDefinition(
                name="step2",
                description="Failing step",
                action=step2_action,
                compensation=step2_compensation,
                max_retries=0,
                order=1,
            ),
        ],
    )
