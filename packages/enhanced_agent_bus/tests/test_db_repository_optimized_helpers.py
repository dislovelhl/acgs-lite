from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
    DatabaseTenantRepository,
)
from enhanced_agent_bus.multi_tenancy.models import TenantStatus
from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum


def _make_repo() -> DatabaseTenantRepository:
    return DatabaseTenantRepository(MagicMock(), enable_caching=False)


def _make_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "tenant-1"
    tenant.name = "Tenant One"
    tenant.slug = "tenant-one"
    tenant.status = TenantStatus.ACTIVE
    tenant.config = MagicMock()
    tenant.config.model_dump.return_value = {"enable_batch_processing": True}
    tenant.quota = {"max_agents": 5}
    tenant.metadata = {"region": "ca"}
    tenant.parent_tenant_id = "parent-1"
    tenant.created_at = datetime.now(UTC)
    tenant.updated_at = datetime.now(UTC)
    tenant.activated_at = None
    tenant.suspended_at = None
    return tenant


class TestDatabaseTenantRepositoryOptimizedHelpers:
    def test_status_to_orm_defaults_to_pending(self):
        repo = _make_repo()
        assert repo._status_to_orm(None) == TenantStatusEnum.PENDING

    def test_dump_quota_supports_dict_and_model(self):
        repo = _make_repo()
        assert repo._dump_quota({"max_agents": 3}) == {"max_agents": 3}

        quota_model = MagicMock()
        quota_model.model_dump.return_value = {"max_agents": 7}
        assert repo._dump_quota(quota_model) == {"max_agents": 7}

    def test_tenantorm_kwargs_preserve_defaults_and_mapping(self):
        repo = _make_repo()
        tenant = _make_tenant()

        kwargs = repo._tenantorm_kwargs(tenant)

        assert kwargs["status"] == TenantStatusEnum.ACTIVE
        assert kwargs["config"] == {"enable_batch_processing": True}
        assert kwargs["quota"] == {"max_agents": 5}
        assert kwargs["metadata_"] == {"region": "ca"}
        assert kwargs["tenant_id"] == "tenant-1"
