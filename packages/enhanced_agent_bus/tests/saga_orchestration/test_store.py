"""
Tests for Saga Store.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    Saga,
    SagaStatus,
    SagaStore,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaStore:
    """Tests for saga persistence store."""

    async def test_save_and_get_saga(self, saga_store: SagaStore):
        """Test saving and retrieving a saga."""
        saga = Saga(
            saga_id="saga-001",
            tenant_id="tenant-001",
            name="test_saga",
            description="Test saga",
        )

        await saga_store.save(saga)
        retrieved = await saga_store.get("saga-001")

        assert retrieved is not None
        assert retrieved.saga_id == "saga-001"
        assert retrieved.tenant_id == "tenant-001"

    async def test_get_nonexistent_saga(self, saga_store: SagaStore):
        """Test retrieving a non-existent saga."""
        result = await saga_store.get("nonexistent")
        assert result is None

    async def test_list_sagas_by_tenant(self, saga_store: SagaStore):
        """Test listing sagas by tenant."""
        saga1 = Saga(
            saga_id="saga-001",
            tenant_id="tenant-001",
            name="saga1",
            description="First saga",
        )
        saga2 = Saga(
            saga_id="saga-002",
            tenant_id="tenant-001",
            name="saga2",
            description="Second saga",
        )
        saga3 = Saga(
            saga_id="saga-003",
            tenant_id="tenant-002",
            name="saga3",
            description="Third saga",
        )

        await saga_store.save(saga1)
        await saga_store.save(saga2)
        await saga_store.save(saga3)

        tenant1_sagas = await saga_store.list_by_tenant("tenant-001")
        assert len(tenant1_sagas) == 2

        tenant2_sagas = await saga_store.list_by_tenant("tenant-002")
        assert len(tenant2_sagas) == 1

    async def test_list_sagas_by_status(self, saga_store: SagaStore):
        """Test filtering sagas by status."""
        saga1 = Saga(
            saga_id="saga-001",
            tenant_id="tenant-001",
            name="saga1",
            description="First saga",
            status=SagaStatus.COMPLETED,
        )
        saga2 = Saga(
            saga_id="saga-002",
            tenant_id="tenant-001",
            name="saga2",
            description="Second saga",
            status=SagaStatus.FAILED,
        )

        await saga_store.save(saga1)
        await saga_store.save(saga2)

        completed = await saga_store.list_by_tenant("tenant-001", status=SagaStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0].saga_id == "saga-001"

    async def test_delete_saga(self, saga_store: SagaStore):
        """Test deleting a saga."""
        saga = Saga(
            saga_id="saga-001",
            tenant_id="tenant-001",
            name="test_saga",
            description="Test saga",
        )

        await saga_store.save(saga)
        assert await saga_store.get("saga-001") is not None

        deleted = await saga_store.delete("saga-001")
        assert deleted is True
        assert await saga_store.get("saga-001") is None

    async def test_delete_nonexistent_saga(self, saga_store: SagaStore):
        """Test deleting a non-existent saga."""
        result = await saga_store.delete("nonexistent")
        assert result is False

    async def test_get_pending_compensations(self, saga_store: SagaStore):
        """Test getting sagas pending compensation."""
        saga1 = Saga(
            saga_id="saga-001",
            tenant_id="tenant-001",
            name="saga1",
            description="First saga",
            status=SagaStatus.COMPENSATING,
        )
        saga2 = Saga(
            saga_id="saga-002",
            tenant_id="tenant-001",
            name="saga2",
            description="Second saga",
            status=SagaStatus.COMPLETED,
        )

        await saga_store.save(saga1)
        await saga_store.save(saga2)

        pending = await saga_store.get_pending_compensations()
        assert len(pending) == 1
        assert pending[0].saga_id == "saga-001"

    async def test_list_with_pagination(self, saga_store: SagaStore):
        """Test listing sagas with pagination."""
        for i in range(10):
            saga = Saga(
                saga_id=f"saga-{i:03d}",
                tenant_id="tenant-001",
                name=f"saga{i}",
                description=f"Saga {i}",
            )
            await saga_store.save(saga)

        page1 = await saga_store.list_by_tenant("tenant-001", limit=5, offset=0)
        page2 = await saga_store.list_by_tenant("tenant-001", limit=5, offset=5)

        assert len(page1) == 5
        assert len(page2) == 5
