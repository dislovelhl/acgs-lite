"""
Tests for ACGS-2 Tenant Management API
Constitutional Hash: 608508a9bd224290

Comprehensive tests for tenant CRUD operations, lifecycle management,
quota enforcement, and hierarchical tenancy via the REST API.
"""

import uuid
from datetime import UTC, datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Constitutional hash for compliance verification
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ACGSBaseError
from enhanced_agent_bus._compat.types import JSONDict

# =============================================================================
# Mock Models and Manager
# =============================================================================


class MockTenantStatus:
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    MIGRATING = "migrating"


class MockTenantConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self):
        return self.__dict__.copy()


class MockTenantQuota:
    def __init__(
        self,
        max_agents: int = 100,
        max_policies: int = 1000,
        max_messages_per_minute: int = 10000,
        max_batch_size: int = 1000,
        max_storage_mb: int = 10240,
        max_concurrent_sessions: int = 100,
    ):
        self.max_agents = max_agents
        self.max_policies = max_policies
        self.max_messages_per_minute = max_messages_per_minute
        self.max_batch_size = max_batch_size
        self.max_storage_mb = max_storage_mb
        self.max_concurrent_sessions = max_concurrent_sessions

    def model_dump(self):
        return {
            "max_agents": self.max_agents,
            "max_policies": self.max_policies,
            "max_messages_per_minute": self.max_messages_per_minute,
            "max_batch_size": self.max_batch_size,
            "max_storage_mb": self.max_storage_mb,
            "max_concurrent_sessions": self.max_concurrent_sessions,
        }


class MockTenantUsage:
    def __init__(
        self,
        agents_count: int = 0,
        policies_count: int = 0,
        messages_this_minute: int = 0,
    ):
        self.agents_count = agents_count
        self.policies_count = policies_count
        self.messages_this_minute = messages_this_minute

    def model_dump(self):
        return {
            "agents_count": self.agents_count,
            "policies_count": self.policies_count,
            "messages_this_minute": self.messages_this_minute,
        }


class MockTenant:
    def __init__(
        self,
        tenant_id: str | None = None,
        name: str = "Test Tenant",
        slug: str = "test-tenant",
        status: str = MockTenantStatus.PENDING,
        parent_tenant_id: str | None = None,
        config: MockTenantConfig | None = None,
        quota: MockTenantQuota | None = None,
        usage: MockTenantUsage | None = None,
        metadata: JSONDict | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        activated_at: datetime | None = None,
        suspended_at: datetime | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.tenant_id = tenant_id or str(uuid.uuid4())
        self.name = name
        self.slug = slug
        self.status = status
        self.parent_tenant_id = parent_tenant_id
        self.config = config or MockTenantConfig()
        self.quota = quota or MockTenantQuota()
        self.usage = usage or MockTenantUsage()
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)
        self.activated_at = activated_at
        self.suspended_at = suspended_at
        self.constitutional_hash = constitutional_hash


class MockTenantNotFoundError(ACGSBaseError):
    """Mock tenant not found error for testing."""

    http_status_code = 404
    error_code = "TENANT_NOT_FOUND"


class MockTenantQuotaExceededError(ACGSBaseError):
    """Mock tenant quota exceeded error for testing."""

    http_status_code = 429
    error_code = "TENANT_QUOTA_EXCEEDED"


class MockTenantValidationError(ACGSBaseError):
    """Mock tenant validation error for testing."""

    http_status_code = 400
    error_code = "TENANT_VALIDATION_ERROR"


class MockTenantManager:
    """Mock TenantManager for testing."""

    def __init__(self):
        self.tenants: dict[str, MockTenant] = {}
        self.tenants_by_slug: dict[str, str] = {}

    async def create_tenant(
        self,
        name: str,
        slug: str,
        config=None,
        quota=None,
        metadata=None,
        parent_tenant_id=None,
        auto_activate=False,
    ) -> MockTenant:
        if slug in self.tenants_by_slug:
            raise ValueError(f"Tenant with slug '{slug}' already exists")

        tenant = MockTenant(
            name=name,
            slug=slug,
            config=config,
            quota=quota,
            metadata=metadata,
            parent_tenant_id=parent_tenant_id,
            status=MockTenantStatus.ACTIVE if auto_activate else MockTenantStatus.PENDING,
        )
        if auto_activate:
            tenant.activated_at = datetime.now(UTC)

        self.tenants[tenant.tenant_id] = tenant
        self.tenants_by_slug[slug] = tenant.tenant_id
        return tenant

    async def get_tenant(self, tenant_id: str) -> MockTenant | None:
        return self.tenants.get(tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> MockTenant | None:
        tenant_id = self.tenants_by_slug.get(slug)
        if tenant_id:
            return self.tenants.get(tenant_id)
        return None

    async def list_tenants(
        self,
        status=None,
        parent_id=None,
        skip: int = 0,
        limit: int = 100,
    ) -> list:
        tenants = list(self.tenants.values())

        if status:
            status_val = status.value if hasattr(status, "value") else str(status)
            tenants = [t for t in tenants if t.status == status_val]

        if parent_id:
            tenants = [t for t in tenants if t.parent_tenant_id == parent_id]

        return tenants[skip : skip + limit]

    async def activate_tenant(self, tenant_id: str) -> MockTenant | None:
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.status = MockTenantStatus.ACTIVE
            tenant.activated_at = datetime.now(UTC)
            tenant.updated_at = datetime.now(UTC)
        return tenant

    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: str | None = None,
        suspend_children: bool = True,
    ) -> MockTenant | None:
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.status = MockTenantStatus.SUSPENDED
            tenant.suspended_at = datetime.now(UTC)
            tenant.updated_at = datetime.now(UTC)
            if reason:
                tenant.metadata["suspension_reason"] = reason
        return tenant

    async def deactivate_tenant(self, tenant_id: str) -> MockTenant | None:
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.status = MockTenantStatus.DEACTIVATED
            tenant.updated_at = datetime.now(UTC)
        return tenant

    async def delete_tenant(self, tenant_id: str, force: bool = False) -> bool:
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return False

        # Check for children
        if not force:
            children = [t for t in self.tenants.values() if t.parent_tenant_id == tenant_id]
            if children:
                raise ValueError("Cannot delete tenant with children. Use force=True.")

        del self.tenants_by_slug[tenant.slug]
        del self.tenants[tenant_id]
        return True

    async def update_config(self, tenant_id: str, config) -> MockTenant | None:
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.config = config
            tenant.updated_at = datetime.now(UTC)
        return tenant

    async def update_quota(self, tenant_id: str, quota) -> MockTenant | None:
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.quota = quota
            tenant.updated_at = datetime.now(UTC)
        return tenant

    async def check_quota(
        self,
        tenant_id: str,
        resource: str,
        requested_amount: int = 1,
    ) -> bool:
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            raise MockTenantNotFoundError(f"Tenant {tenant_id} not found")

        resource_map = {
            "agents": ("agents_count", "max_agents"),
            "policies": ("policies_count", "max_policies"),
            "messages": ("messages_this_minute", "max_messages_per_minute"),
        }

        usage_key, quota_key = resource_map.get(resource, (f"{resource}_count", f"max_{resource}"))
        usage = getattr(tenant.usage, usage_key, 0)
        quota = getattr(tenant.quota, quota_key, 0)

        return usage + requested_amount <= quota

    async def increment_usage(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> MockTenantUsage:
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            raise MockTenantNotFoundError(f"Tenant {tenant_id} not found")

        resource_map = {
            "agents": "agents_count",
            "policies": "policies_count",
            "messages": "messages_this_minute",
        }

        usage_key = resource_map.get(resource, f"{resource}_count")
        current = getattr(tenant.usage, usage_key, 0)
        setattr(tenant.usage, usage_key, current + amount)

        return tenant.usage

    async def get_child_tenants(self, parent_id: str) -> list:
        return [t for t in self.tenants.values() if t.parent_tenant_id == parent_id]

    async def get_tenant_hierarchy(self, tenant_id: str) -> list:
        result = []
        current_id = tenant_id
        while current_id:
            tenant = self.tenants.get(current_id)
            if not tenant:
                break
            result.insert(0, tenant)
            current_id = tenant.parent_tenant_id
        return result

    async def get_all_descendants(self, tenant_id: str) -> list:
        descendants = []
        children = await self.get_child_tenants(tenant_id)
        for child in children:
            descendants.append(child)
            descendants.extend(await self.get_all_descendants(child.tenant_id))
        return descendants


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_manager():
    """Create mock tenant manager."""
    return MockTenantManager()


@pytest.fixture(autouse=True)
def _tenant_api_environment(monkeypatch):
    """Keep tenant API auth defaults test-local instead of process-global."""
    monkeypatch.setenv("TENANT_ADMIN_KEY", "test-admin-key")
    monkeypatch.setenv("TENANT_AUTH_MODE", "strict")
    monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "development")


@pytest.fixture
def app(mock_manager):
    """Create FastAPI test app with tenant routes."""

    app = FastAPI()

    # Import and include router
    try:
        from routes.tenants import get_manager, router
    except ImportError:
        from enhanced_agent_bus.routes.tenants import get_manager, router

    # Override dependency
    def get_test_manager():
        return mock_manager

    app.dependency_overrides[get_manager] = get_test_manager
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client(app):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_headers():
    """Standard admin headers for authenticated requests."""
    return {
        "X-Admin-Key": "test-admin-key",
        "X-Admin-Tenant-ID": "admin-tenant",
    }


# =============================================================================
# Test Cases - CRUD Operations
# =============================================================================


class TestCreateTenant:
    """Tests for tenant creation endpoint."""

    def test_create_tenant_success(self, client, admin_headers, mock_manager):
        """Test successful tenant creation."""
        response = client.post(
            "/api/v1/tenants",
            json={
                "name": "Acme Corp",
                "slug": "acme-corp",
                "config": {"theme": "dark"},
                "auto_activate": False,
            },
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Acme Corp"
        assert data["slug"] == "acme-corp"
        assert data["status"] == "pending"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_create_tenant_auto_activate(self, client, admin_headers, mock_manager):
        """Test tenant creation with auto-activation."""
        response = client.post(
            "/api/v1/tenants",
            json={
                "name": "Active Corp",
                "slug": "active-corp",
                "auto_activate": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["activated_at"] is not None

    def test_create_tenant_duplicate_slug(self, client, admin_headers, mock_manager):
        """Test creation with duplicate slug fails."""
        # Create first tenant
        client.post(
            "/api/v1/tenants",
            json={"name": "First", "slug": "duplicate"},
            headers=admin_headers,
        )

        # Try to create second with same slug
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Second", "slug": "duplicate"},
            headers=admin_headers,
        )

        assert response.status_code == 409

    def test_create_tenant_invalid_slug(self, client, admin_headers):
        """Test creation with invalid slug fails."""
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Invalid", "slug": "UPPERCASE"},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_create_tenant_missing_auth(self, client):
        """Test creation without admin key fails."""
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Test", "slug": "test"},
        )

        assert response.status_code == 401


class TestGetTenant:
    """Tests for tenant retrieval endpoints."""

    def test_get_tenant_by_id(self, client, admin_headers, mock_manager):
        """Test getting tenant by ID."""
        # Create tenant first
        create_response = client.post(
            "/api/v1/tenants",
            json={"name": "Get Test", "slug": "get-test"},
            headers=admin_headers,
        )
        tenant_id = create_response.json()["tenant_id"]

        # Get tenant
        response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == tenant_id
        assert data["slug"] == "get-test"

    def test_get_tenant_by_slug(self, client, admin_headers, mock_manager):
        """Test getting tenant by slug."""
        # Create tenant first
        client.post(
            "/api/v1/tenants",
            json={"name": "Slug Test", "slug": "slug-test"},
            headers=admin_headers,
        )

        # Get by slug
        response = client.get(
            "/api/v1/tenants/by-slug/slug-test",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "slug-test"

    def test_get_tenant_not_found(self, client, admin_headers):
        """Test getting non-existent tenant."""
        response = client.get(
            f"/api/v1/tenants/{uuid.uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestListTenants:
    """Tests for tenant listing endpoint."""

    def test_list_tenants(self, client, admin_headers, mock_manager):
        """Test listing all tenants."""
        # Create some tenants
        for i in range(3):
            client.post(
                "/api/v1/tenants",
                json={"name": f"Tenant {i}", "slug": f"tenant-{i}"},
                headers=admin_headers,
            )

        # list tenants
        response = client.get(
            "/api/v1/tenants",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tenants"]) == 3
        assert data["total_count"] == 3

    def test_list_tenants_with_status_filter(self, client, admin_headers, mock_manager):
        """Test listing tenants filtered by status."""
        # Create active tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Active", "slug": "active-test", "auto_activate": True},
            headers=admin_headers,
        )

        # Create pending tenant
        client.post(
            "/api/v1/tenants",
            json={"name": "Pending", "slug": "pending-test"},
            headers=admin_headers,
        )

        # list only active
        response = client.get(
            "/api/v1/tenants?status=active",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tenants"]) == 1
        assert data["tenants"][0]["status"] == "active"

    def test_list_tenants_pagination(self, client, admin_headers, mock_manager):
        """Test tenant listing with pagination."""
        # Create 5 tenants
        for i in range(5):
            client.post(
                "/api/v1/tenants",
                json={"name": f"Tenant {i}", "slug": f"tenant-page-{i}"},
                headers=admin_headers,
            )

        # Get first page
        response = client.get(
            "/api/v1/tenants?skip=0&limit=2",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tenants"]) == 2
        assert data["has_more"] is True


class TestUpdateTenant:
    """Tests for tenant update endpoint."""

    def test_update_tenant_name(self, client, admin_headers, mock_manager):
        """Test updating tenant name."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Original", "slug": "update-test"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Update name
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}",
            json={"name": "Updated"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"

    def test_update_tenant_not_found(self, client, admin_headers):
        """Test updating non-existent tenant."""
        response = client.patch(
            f"/api/v1/tenants/{uuid.uuid4()}",
            json={"name": "Updated"},
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestDeleteTenant:
    """Tests for tenant deletion endpoint."""

    def test_delete_tenant(self, client, admin_headers, mock_manager):
        """Test deleting a tenant."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Delete Me", "slug": "delete-me"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Delete tenant
        response = client.delete(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
        )

        assert response.status_code == 204

        # Verify deleted
        get_resp = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
        )
        assert get_resp.status_code == 404

    def test_delete_tenant_with_children_fails(self, client, admin_headers, mock_manager):
        """Test deleting tenant with children fails without force."""
        # Create parent tenant
        parent_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Parent", "slug": "parent-del"},
            headers=admin_headers,
        )
        parent_id = parent_resp.json()["tenant_id"]

        # Create child tenant
        client.post(
            "/api/v1/tenants",
            json={
                "name": "Child",
                "slug": "child-del",
                "parent_tenant_id": parent_id,
            },
            headers=admin_headers,
        )

        # Try to delete parent (should fail)
        response = client.delete(
            f"/api/v1/tenants/{parent_id}",
            headers=admin_headers,
        )

        assert response.status_code == 409

    def test_delete_tenant_force(self, client, admin_headers, mock_manager):
        """Test force deleting tenant with children."""
        # Create parent tenant
        parent_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Parent Force", "slug": "parent-force"},
            headers=admin_headers,
        )
        parent_id = parent_resp.json()["tenant_id"]

        # Create child tenant
        client.post(
            "/api/v1/tenants",
            json={
                "name": "Child Force",
                "slug": "child-force",
                "parent_tenant_id": parent_id,
            },
            headers=admin_headers,
        )

        # Force delete parent
        response = client.delete(
            f"/api/v1/tenants/{parent_id}?force=true",
            headers=admin_headers,
        )

        assert response.status_code == 204


# =============================================================================
# Test Cases - Lifecycle Management
# =============================================================================


class TestTenantLifecycle:
    """Tests for tenant lifecycle management endpoints."""

    def test_activate_tenant(self, client, admin_headers, mock_manager):
        """Test activating a pending tenant."""
        # Create pending tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Activate Me", "slug": "activate-me"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]
        assert create_resp.json()["status"] == "pending"

        # Activate
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/activate",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["activated_at"] is not None

    def test_suspend_tenant(self, client, admin_headers, mock_manager):
        """Test suspending an active tenant."""
        # Create and activate tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Suspend Me", "slug": "suspend-me", "auto_activate": True},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Suspend
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            json={"reason": "Non-payment"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "suspended"
        assert data["suspended_at"] is not None

    def test_deactivate_tenant(self, client, admin_headers, mock_manager):
        """Test deactivating a tenant."""
        # Create and activate tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Deactivate Me", "slug": "deactivate-me", "auto_activate": True},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Deactivate
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/deactivate",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deactivated"


# =============================================================================
# Test Cases - Quota Management
# =============================================================================


class TestQuotaManagement:
    """Tests for quota management endpoints."""

    def test_update_quota(self, client, admin_headers, mock_manager):
        """Test updating tenant quota."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Quota Test", "slug": "quota-test"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Update quota
        response = client.put(
            f"/api/v1/tenants/{tenant_id}/quota",
            json={"max_agents": 200, "max_policies": 2000},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["quota"]["max_agents"] == 200
        assert data["quota"]["max_policies"] == 2000

    def test_check_quota_available(self, client, admin_headers, mock_manager):
        """Test checking quota when available."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Check Quota", "slug": "check-quota"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Check quota
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/quota/check",
            json={"resource": "agents", "requested_amount": 1},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["resource"] == "agents"

    def test_get_usage(self, client, admin_headers, mock_manager):
        """Test getting tenant usage."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Usage Test", "slug": "usage-test"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Get usage
        response = client.get(
            f"/api/v1/tenants/{tenant_id}/usage",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert "quota" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_increment_usage(self, client, admin_headers, mock_manager):
        """Test incrementing tenant usage."""
        # Create tenant
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Increment Test", "slug": "increment-test"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["tenant_id"]

        # Increment usage
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/usage/increment",
            json={"resource": "agents", "amount": 5},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["usage"]["agents_count"] == 5


# =============================================================================
# Test Cases - Hierarchy Management
# =============================================================================


class TestHierarchyManagement:
    """Tests for hierarchical tenancy endpoints."""

    def test_get_tenant_hierarchy(self, client, admin_headers, mock_manager):
        """Test getting tenant hierarchy."""
        # Create parent tenant
        parent_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Parent", "slug": "parent-hier"},
            headers=admin_headers,
        )
        parent_id = parent_resp.json()["tenant_id"]

        # Create child tenant
        child_resp = client.post(
            "/api/v1/tenants",
            json={
                "name": "Child",
                "slug": "child-hier",
                "parent_tenant_id": parent_id,
            },
            headers=admin_headers,
        )
        child_id = child_resp.json()["tenant_id"]

        # Get hierarchy for child
        response = client.get(
            f"/api/v1/tenants/{child_id}/hierarchy",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == child_id
        assert len(data["ancestors"]) >= 0
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_child_tenants(self, client, admin_headers, mock_manager):
        """Test getting child tenants."""
        # Create parent tenant
        parent_resp = client.post(
            "/api/v1/tenants",
            json={"name": "Parent", "slug": "parent-child"},
            headers=admin_headers,
        )
        parent_id = parent_resp.json()["tenant_id"]

        # Create child tenants
        for i in range(3):
            client.post(
                "/api/v1/tenants",
                json={
                    "name": f"Child {i}",
                    "slug": f"child-{i}",
                    "parent_tenant_id": parent_id,
                },
                headers=admin_headers,
            )

        # Get children
        response = client.get(
            f"/api/v1/tenants/{parent_id}/children",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tenants"]) == 3


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_response_includes_constitutional_hash(self, client, admin_headers, mock_manager):
        """Test that responses include constitutional hash."""
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Hash Test", "slug": "hash-test"},
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_list_response_includes_constitutional_hash(self, client, admin_headers, mock_manager):
        """Test that list responses include constitutional hash."""
        response = client.get(
            "/api/v1/tenants",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Test Cases - Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_invalid_json_body(self, client, admin_headers):
        """Test handling of invalid JSON body."""
        response = client.post(
            "/api/v1/tenants",
            content="not valid json",
            headers={**admin_headers, "Content-type": "application/json"},
        )

        assert response.status_code == 422

    def test_missing_required_fields(self, client, admin_headers):
        """Test handling of missing required fields."""
        response = client.post(
            "/api/v1/tenants",
            json={"name": "No Slug"},  # Missing slug
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_invalid_status_filter(self, client, admin_headers):
        """Test handling of invalid status filter."""
        response = client.get(
            "/api/v1/tenants?status=invalid_status",
            headers=admin_headers,
        )

        assert response.status_code == 400


class TestAuthenticationConfiguration:
    def test_production_auth_misconfiguration_returns_503(self, client, admin_headers, monkeypatch):
        try:
            import routes.tenants as tenants_module
        except ImportError:
            import enhanced_agent_bus.routes.tenants as tenants_module

        monkeypatch.setattr(tenants_module, "ENVIRONMENT", "Production")
        monkeypatch.setattr(tenants_module, "NORMALIZED_ENVIRONMENT", "production")
        monkeypatch.setattr(tenants_module, "TENANT_ADMIN_KEY", "")
        monkeypatch.setattr(tenants_module, "JWT_SECRET_KEY", "")

        response = client.get(
            "/api/v1/tenants",
            headers=admin_headers,
        )

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == "AUTH_CONFIGURATION_ERROR"
        assert detail["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_development_mode_not_honored_in_production(self, client, monkeypatch):
        try:
            import routes.tenants as tenants_module
        except ImportError:
            import enhanced_agent_bus.routes.tenants as tenants_module

        monkeypatch.setattr(tenants_module, "ENVIRONMENT", "Production")
        monkeypatch.setattr(tenants_module, "NORMALIZED_ENVIRONMENT", "production")
        monkeypatch.setattr(tenants_module, "TENANT_AUTH_MODE", "Development")
        monkeypatch.setattr(tenants_module, "TENANT_ADMIN_KEY", "prod-admin-key")
        monkeypatch.setattr(tenants_module, "JWT_SECRET_KEY", "")

        response = client.get(
            "/api/v1/tenants",
            headers={"X-Admin-Key": "wrong-key", "X-Admin-Tenant-ID": "admin-tenant"},
        )

        assert response.status_code == 401
        detail = response.json()["detail"]
        assert detail["code"] == "INVALID_CREDENTIALS"
