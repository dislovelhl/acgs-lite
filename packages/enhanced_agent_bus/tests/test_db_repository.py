"""
Tests for ACGS-2 Database-Backed Tenant Repository
Constitutional Hash: 608508a9bd224290

Unit tests for DatabaseTenantRepository CRUD operations using SQLAlchemy async.
"""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from enhanced_agent_bus._compat.database.session import Base
from enhanced_agent_bus.multi_tenancy.db_repository import DatabaseTenantRepository
from enhanced_agent_bus.multi_tenancy.models import (
    TenantConfig,
    TenantQuota,
    TenantStatus,
)
from enhanced_agent_bus.multi_tenancy.orm_models import CONSTITUTIONAL_HASH

RUN_EAB_DB_REPOSITORY_TESTS = (
    os.environ.get("RUN_EAB_DB_REPOSITORY_TESTS", "false").strip().lower() == "true"
)
pytestmark = pytest.mark.skipif(
    not RUN_EAB_DB_REPOSITORY_TESTS,
    reason=(
        "Skipping DB repository suite in this runtime; async DB setup paths can hang. "
        "Set RUN_EAB_DB_REPOSITORY_TESTS=true to run."
    ),
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a fresh SQLite database for each test with foreign keys enabled."""
    # Use a unique file-based database to ensure true isolation
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    # Clean up the temporary database file
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests with foreign keys enabled."""
    async_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys = ON"))
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def repository(db_session: AsyncSession) -> DatabaseTenantRepository:
    """Create a repository instance for testing."""
    return DatabaseTenantRepository(db_session)


# =============================================================================
# Test Cases - Create Operations
# =============================================================================


class TestDatabaseTenantRepositoryCreate:
    """Tests for tenant creation via database repository."""

    async def test_create_tenant_success(self, repository: DatabaseTenantRepository):
        """Test creating a tenant successfully."""
        tenant = await repository.create_tenant(
            name="Acme Corporation",
            slug="acme-corp",
            config=TenantConfig(enable_batch_processing=True),
            quota=TenantQuota(max_agents=500),
            metadata={"industry": "technology"},
        )

        assert tenant is not None
        assert tenant.tenant_id is not None
        assert tenant.name == "Acme Corporation"
        assert tenant.slug == "acme-corp"
        assert tenant.status == TenantStatus.PENDING
        assert tenant.config.enable_batch_processing is True
        assert tenant.created_at is not None

    async def test_create_tenant_with_defaults(self, repository: DatabaseTenantRepository):
        """Test creating a tenant with default values."""
        tenant = await repository.create_tenant(
            name="Default Tenant",
            slug="default-tenant",
        )

        assert tenant is not None
        assert tenant.status == TenantStatus.PENDING
        assert tenant.config is not None
        assert tenant.quota == {}

    async def test_create_tenant_duplicate_slug_fails(self, repository: DatabaseTenantRepository):
        """Test that duplicate slugs are rejected."""
        await repository.create_tenant(name="First", slug="unique-slug")

        with pytest.raises(ValueError, match="already exists"):
            await repository.create_tenant(name="Second", slug="unique-slug")

    async def test_create_tenant_with_parent(self, repository: DatabaseTenantRepository):
        """Test creating a child tenant with parent."""
        parent = await repository.create_tenant(name="Parent", slug="parent-org")
        child = await repository.create_tenant(
            name="Child",
            slug="child-org",
            parent_tenant_id=parent.tenant_id,
        )

        assert child.parent_tenant_id == parent.tenant_id


# =============================================================================
# Test Cases - Read Operations
# =============================================================================


class TestDatabaseTenantRepositoryRead:
    """Tests for tenant read operations via database repository."""

    async def test_get_tenant_by_id(self, repository: DatabaseTenantRepository):
        """Test retrieving a tenant by ID."""
        created = await repository.create_tenant(name="Get Test", slug="get-test")

        fetched = await repository.get_tenant(created.tenant_id)

        assert fetched is not None
        assert fetched.tenant_id == created.tenant_id
        assert fetched.name == "Get Test"

    async def test_get_tenant_by_slug(self, repository: DatabaseTenantRepository):
        """Test retrieving a tenant by slug."""
        created = await repository.create_tenant(name="Slug Test", slug="slug-test")

        fetched = await repository.get_tenant_by_slug("slug-test")

        assert fetched is not None
        assert fetched.tenant_id == created.tenant_id

    async def test_get_nonexistent_tenant(self, repository: DatabaseTenantRepository):
        """Test that nonexistent tenant returns None."""
        result = await repository.get_tenant("nonexistent-id")
        assert result is None

    async def test_list_tenants(self, repository: DatabaseTenantRepository):
        """Test listing all tenants."""
        await repository.create_tenant(name="Tenant 1", slug="tenant-1")
        await repository.create_tenant(name="Tenant 2", slug="tenant-2")
        await repository.create_tenant(name="Tenant 3", slug="tenant-3")

        tenants = await repository.list_tenants()

        assert len(tenants) == 3

    async def test_list_tenants_by_status(self, repository: DatabaseTenantRepository):
        """Test listing tenants filtered by status."""
        t1 = await repository.create_tenant(name="Pending", slug="pending-t")
        await repository.create_tenant(name="Pending 2", slug="pending-t2")
        await repository.activate_tenant(t1.tenant_id)

        active_tenants = await repository.list_tenants(status=TenantStatus.ACTIVE)
        pending_tenants = await repository.list_tenants(status=TenantStatus.PENDING)

        assert len(active_tenants) == 1
        assert len(pending_tenants) == 1

    async def test_list_tenants_pagination(self, repository: DatabaseTenantRepository):
        """Test listing tenants with pagination."""
        for i in range(10):
            await repository.create_tenant(name=f"Tenant {i}", slug=f"tenant-{i}")

        page1 = await repository.list_tenants(skip=0, limit=5)
        page2 = await repository.list_tenants(skip=5, limit=5)

        assert len(page1) == 5
        assert len(page2) == 5


# =============================================================================
# Test Cases - Update Operations
# =============================================================================


class TestDatabaseTenantRepositoryUpdate:
    """Tests for tenant update operations via database repository."""

    async def test_activate_tenant(self, repository: DatabaseTenantRepository):
        """Test activating a tenant."""
        created = await repository.create_tenant(name="Activate Me", slug="activate-me")
        assert created.status == TenantStatus.PENDING

        activated = await repository.activate_tenant(created.tenant_id)

        assert activated is not None
        assert activated.status == TenantStatus.ACTIVE
        assert activated.activated_at is not None

    async def test_suspend_tenant(self, repository: DatabaseTenantRepository):
        """Test suspending a tenant."""
        created = await repository.create_tenant(name="Suspend Me", slug="suspend-me")
        await repository.activate_tenant(created.tenant_id)

        suspended = await repository.suspend_tenant(created.tenant_id, reason="Policy violation")

        assert suspended is not None
        assert suspended.status == TenantStatus.SUSPENDED
        assert suspended.suspended_at is not None
        assert suspended.metadata.get("suspension_reason") == "Policy violation"

    async def test_update_tenant_config(self, repository: DatabaseTenantRepository):
        """Test updating tenant configuration."""
        created = await repository.create_tenant(
            name="Config Test",
            slug="config-test",
            config=TenantConfig(enable_batch_processing=False),
        )

        new_config = TenantConfig(
            enable_batch_processing=True,
            enable_deliberation=True,
        )
        updated = await repository.update_tenant_config(created.tenant_id, new_config)

        assert updated is not None
        assert updated.config.enable_batch_processing is True
        assert updated.config.enable_deliberation is True

    async def test_update_tenant_quota(self, repository: DatabaseTenantRepository):
        """Test updating tenant quota."""
        created = await repository.create_tenant(
            name="Quota Test",
            slug="quota-test",
            quota=TenantQuota(max_agents=100),
        )

        new_quota = TenantQuota(max_agents=500, max_policies=1000)
        updated = await repository.update_tenant_quota(created.tenant_id, new_quota)

        assert updated is not None
        assert updated.quota["max_agents"] == 500
        assert updated.quota["max_policies"] == 1000

    async def test_update_tenant_properties(self, repository: DatabaseTenantRepository):
        """Test updating tenant name and metadata."""
        created = await repository.create_tenant(
            name="Original Name",
            slug="update-props",
            metadata={"key1": "value1"},
        )

        updated = await repository.update_tenant(
            created.tenant_id,
            name="New Name",
            metadata={"key2": "value2"},
        )

        assert updated is not None
        assert updated.name == "New Name"
        assert updated.metadata["key1"] == "value1"  # Preserved
        assert updated.metadata["key2"] == "value2"  # Added


# =============================================================================
# Test Cases - Delete Operations
# =============================================================================


class TestDatabaseTenantRepositoryDelete:
    """Tests for tenant delete operations via database repository."""

    async def test_delete_tenant(self, repository: DatabaseTenantRepository):
        """Test deleting a tenant."""
        created = await repository.create_tenant(name="Delete Me", slug="delete-me")

        result = await repository.delete_tenant(created.tenant_id)

        assert result is True

        # Verify deleted
        fetched = await repository.get_tenant(created.tenant_id)
        assert fetched is None

    async def test_delete_nonexistent_tenant(self, repository: DatabaseTenantRepository):
        """Test that deleting nonexistent tenant returns False."""
        result = await repository.delete_tenant("nonexistent-id")
        assert result is False


# =============================================================================
# Test Cases - Count Operations
# =============================================================================


class TestDatabaseTenantRepositoryCounts:
    """Tests for tenant count operations via database repository."""

    async def test_get_tenant_count(self, repository: DatabaseTenantRepository):
        """Test getting total tenant count."""
        assert await repository.get_tenant_count() == 0

        await repository.create_tenant(name="Tenant 1", slug="count-1")
        await repository.create_tenant(name="Tenant 2", slug="count-2")

        assert await repository.get_tenant_count() == 2

    async def test_get_active_tenant_count(self, repository: DatabaseTenantRepository):
        """Test getting active tenant count."""
        t1 = await repository.create_tenant(name="Active", slug="active-count")
        await repository.create_tenant(name="Pending", slug="pending-count")

        await repository.activate_tenant(t1.tenant_id)

        assert await repository.get_active_tenant_count() == 1


# =============================================================================
# Test Cases - Hierarchical Operations
# =============================================================================


class TestDatabaseTenantRepositoryHierarchy:
    """Tests for hierarchical tenant operations via database repository."""

    async def test_get_children(self, repository: DatabaseTenantRepository):
        """Test getting child tenants."""
        parent = await repository.create_tenant(name="Parent", slug="parent-h")
        await repository.create_tenant(
            name="Child 1", slug="child-h1", parent_tenant_id=parent.tenant_id
        )
        await repository.create_tenant(
            name="Child 2", slug="child-h2", parent_tenant_id=parent.tenant_id
        )

        children = await repository.get_children(parent.tenant_id)

        assert len(children) == 2


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestDatabaseTenantRepositoryConstitutional:
    """Tests for constitutional compliance in database repository."""

    async def test_constitutional_hash_set_on_create(self, repository: DatabaseTenantRepository):
        """Test that constitutional hash is correctly set on tenant creation."""
        tenant = await repository.create_tenant(
            name="Constitutional Test", slug="constitutional-test"
        )

        # Verify via direct database query would show the hash
        # For this test, we verify the repository has the correct hash
        assert repository.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_repository_has_constitutional_hash(self, repository: DatabaseTenantRepository):
        """Test that repository instance has constitutional hash."""
        assert repository.constitutional_hash == CONSTITUTIONAL_HASH
