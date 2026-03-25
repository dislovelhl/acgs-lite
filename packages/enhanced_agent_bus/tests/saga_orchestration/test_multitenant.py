"""
Tests for Multi-Tenant Saga Isolation.
Constitutional Hash: 608508a9bd224290
"""

import asyncio

import pytest

from enterprise_sso.saga_orchestration import (
    SagaDefinition,
    SagaOrchestrator,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMultiTenantSagas:
    """Tests for multi-tenant saga isolation."""

    async def test_saga_tenant_isolation(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test that sagas are isolated by tenant."""
        orchestrator.register_saga(simple_saga_definition)

        saga1 = await orchestrator.create_saga("simple_saga", "tenant-001")
        saga2 = await orchestrator.create_saga("simple_saga", "tenant-002")

        tenant1_sagas = await orchestrator.list_sagas("tenant-001")
        tenant2_sagas = await orchestrator.list_sagas("tenant-002")

        assert len(tenant1_sagas) == 1
        assert len(tenant2_sagas) == 1
        assert tenant1_sagas[0].saga_id != tenant2_sagas[0].saga_id

    async def test_saga_context_contains_tenant_id(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test that saga context contains tenant ID."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga("simple_saga", "tenant-001")

        assert saga.context is not None
        assert saga.context.tenant_id == "tenant-001"

    async def test_concurrent_tenant_sagas(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test concurrent saga execution across tenants."""
        orchestrator.register_saga(simple_saga_definition)

        saga1 = await orchestrator.create_saga("simple_saga", "tenant-001")
        saga2 = await orchestrator.create_saga("simple_saga", "tenant-002")

        # Execute concurrently
        results = await asyncio.gather(
            orchestrator.execute(saga1.saga_id),
            orchestrator.execute(saga2.saga_id),
        )

        assert all(r.success for r in results)
