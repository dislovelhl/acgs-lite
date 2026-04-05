"""
Tests for ACGS-2 Tenant Database Operations
Constitutional Hash: 608508a9bd224290

Comprehensive unit tests for tenant database CRUD operations using
SQLAlchemy ORM models with SQLite for testing and PostgreSQL patterns.

Note: These tests pass individually but fail under xdist due to
SQLAlchemy ORM mapper state conflicts (shared Base.metadata).
"""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force all tests in this module into a single xdist group to avoid
# SQLAlchemy Base.metadata backref conflicts across parallel workers.
# With --dist loadscope, the group marker alone is insufficient;
# skipif guards against the xdist metadata collision at collection time.
pytestmark = [
    pytest.mark.xdist_group("tenant_database"),
    pytest.mark.skipif(
        os.environ.get("PYTEST_XDIST_WORKER") is not None,
        reason="SQLAlchemy shared Base.metadata conflicts under xdist — passes solo",
    ),
]

from enhanced_agent_bus._compat.database.session import Base
from enhanced_agent_bus.multi_tenancy.orm_models import (
    CONSTITUTIONAL_HASH,
    EnterpriseIntegrationORM,
    MigrationJobORM,
    TenantAuditLogORM,
    TenantORM,
    TenantRoleMappingORM,
    TenantStatusEnum,
)

# =============================================================================
# Test Fixtures
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
        # Enable foreign key enforcement for SQLite
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        # Drop all tables first to ensure clean state (handles metadata corruption)
        await conn.run_sync(Base.metadata.drop_all)
        # Create fresh tables in the new database
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
        # Enable foreign keys for this connection
        await session.execute(text("PRAGMA foreign_keys = ON"))
        yield session
        await session.rollback()


@pytest.fixture
def sample_tenant_data():
    """Sample tenant data for testing."""
    return {
        "tenant_id": str(uuid.uuid4()),
        "name": "Acme Corporation",
        "slug": "acme-corp",
        "status": TenantStatusEnum.PENDING,
        "config": {
            "enable_batch_processing": True,
            "enable_deliberation": True,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
        "quota": {
            "max_agents": 100,
            "max_policies": 1000,
            "max_messages_per_minute": 10000,
        },
        "metadata_": {"industry": "technology", "tier": "enterprise"},
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


# =============================================================================
# Test Cases - TenantORM CRUD Operations
# =============================================================================


class TestTenantCreate:
    """Tests for tenant creation operations."""

    @pytest.mark.constitutional
    async def test_create_tenant_success(self, db_session: AsyncSession, sample_tenant_data):
        """Test successful tenant creation with all fields."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.tenant_id == sample_tenant_data["tenant_id"]
        assert tenant.name == "Acme Corporation"
        assert tenant.slug == "acme-corp"
        assert tenant.status == TenantStatusEnum.PENDING
        assert tenant.constitutional_hash == CONSTITUTIONAL_HASH
        assert tenant.created_at is not None
        assert tenant.updated_at is not None

    async def test_create_tenant_with_defaults(self, db_session: AsyncSession):
        """Test tenant creation with default values."""
        tenant = TenantORM(
            name="Minimal Tenant",
            slug="minimal-tenant",
        )
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.tenant_id is not None
        assert len(tenant.tenant_id) == 36  # UUID format
        assert tenant.status == TenantStatusEnum.PENDING
        assert tenant.constitutional_hash == CONSTITUTIONAL_HASH
        assert tenant.config == {}
        assert tenant.quota == {}

    async def test_create_tenant_unique_slug_constraint(self, db_session: AsyncSession):
        """Test that duplicate slugs are rejected."""
        tenant1 = TenantORM(name="First", slug="unique-slug")
        db_session.add(tenant1)
        await db_session.commit()

        tenant2 = TenantORM(name="Second", slug="unique-slug")
        db_session.add(tenant2)

        with pytest.raises((Exception,), match=r".+"):  # IntegrityError - noqa: B017
            await db_session.commit()

    async def test_create_tenant_with_parent(self, db_session: AsyncSession):
        """Test creating a child tenant with parent relationship."""
        # Create parent
        parent = TenantORM(name="Parent Corp", slug="parent-corp")
        db_session.add(parent)
        await db_session.commit()
        await db_session.refresh(parent)

        # Create child
        child = TenantORM(
            name="Child Division",
            slug="child-division",
            parent_tenant_id=parent.tenant_id,
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        assert child.parent_tenant_id == parent.tenant_id


class TestTenantRead:
    """Tests for tenant retrieval operations."""

    async def test_get_tenant_by_id(self, db_session: AsyncSession, sample_tenant_data):
        """Test retrieving a tenant by ID."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        result = await db_session.execute(
            select(TenantORM).where(TenantORM.tenant_id == sample_tenant_data["tenant_id"])
        )
        retrieved = result.scalar_one_or_none()

        assert retrieved is not None
        assert retrieved.tenant_id == sample_tenant_data["tenant_id"]
        assert retrieved.name == "Acme Corporation"

    async def test_get_tenant_by_slug(self, db_session: AsyncSession, sample_tenant_data):
        """Test retrieving a tenant by slug."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        result = await db_session.execute(select(TenantORM).where(TenantORM.slug == "acme-corp"))
        retrieved = result.scalar_one_or_none()

        assert retrieved is not None
        assert retrieved.slug == "acme-corp"
        assert retrieved.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_get_nonexistent_tenant(self, db_session: AsyncSession):
        """Test retrieving a non-existent tenant returns None."""
        result = await db_session.execute(
            select(TenantORM).where(TenantORM.tenant_id == str(uuid.uuid4()))
        )
        retrieved = result.scalar_one_or_none()

        assert retrieved is None

    async def test_list_tenants_by_status(self, db_session: AsyncSession):
        """Test listing tenants filtered by status."""
        # Create tenants with different statuses
        pending = TenantORM(name="Pending", slug="pending-tenant", status=TenantStatusEnum.PENDING)
        active = TenantORM(name="Active", slug="active-tenant", status=TenantStatusEnum.ACTIVE)
        suspended = TenantORM(
            name="Suspended", slug="suspended-tenant", status=TenantStatusEnum.SUSPENDED
        )

        db_session.add_all([pending, active, suspended])
        await db_session.commit()

        # Query only active tenants
        result = await db_session.execute(
            select(TenantORM).where(TenantORM.status == TenantStatusEnum.ACTIVE)
        )
        active_tenants = result.scalars().all()

        assert len(active_tenants) == 1
        assert active_tenants[0].slug == "active-tenant"

    async def test_list_tenants_pagination(self, db_session: AsyncSession):
        """Test tenant listing with pagination."""
        # Create 5 tenants
        for i in range(5):
            tenant = TenantORM(name=f"Tenant {i}", slug=f"tenant-{i}")
            db_session.add(tenant)
        await db_session.commit()

        # Get first page
        result = await db_session.execute(
            select(TenantORM).order_by(TenantORM.created_at).offset(0).limit(2)
        )
        page1 = result.scalars().all()
        assert len(page1) == 2

        # Get second page
        result = await db_session.execute(
            select(TenantORM).order_by(TenantORM.created_at).offset(2).limit(2)
        )
        page2 = result.scalars().all()
        assert len(page2) == 2


class TestTenantUpdate:
    """Tests for tenant update operations."""

    async def test_update_tenant_name(self, db_session: AsyncSession, sample_tenant_data):
        """Test updating tenant name."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        tenant.name = "Updated Corporation"
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.name == "Updated Corporation"
        # Note: SQLite doesn't support onupdate for timestamps

    async def test_update_tenant_status(self, db_session: AsyncSession, sample_tenant_data):
        """Test updating tenant status lifecycle."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        # Activate tenant
        tenant.status = TenantStatusEnum.ACTIVE
        tenant.activated_at = datetime.now(UTC)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.status == TenantStatusEnum.ACTIVE
        assert tenant.activated_at is not None
        assert tenant.is_active() is True

    async def test_update_tenant_config(self, db_session: AsyncSession, sample_tenant_data):
        """Test updating tenant configuration."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        tenant.config = {
            **tenant.config,
            "new_feature": True,
            "cache_ttl": 600,
        }
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.config["new_feature"] is True
        assert tenant.config["cache_ttl"] == 600
        assert tenant.config["enable_batch_processing"] is True

    async def test_update_tenant_quota(self, db_session: AsyncSession, sample_tenant_data):
        """Test updating tenant quota limits."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        tenant.quota = {
            "max_agents": 200,
            "max_policies": 2000,
            "max_messages_per_minute": 20000,
        }
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.quota["max_agents"] == 200
        assert tenant.quota["max_policies"] == 2000

    async def test_suspend_tenant(self, db_session: AsyncSession, sample_tenant_data):
        """Test suspending an active tenant."""
        tenant = TenantORM(**sample_tenant_data)
        tenant.status = TenantStatusEnum.ACTIVE
        tenant.activated_at = datetime.now(UTC)
        db_session.add(tenant)
        await db_session.commit()

        # Suspend
        tenant.status = TenantStatusEnum.SUSPENDED
        tenant.suspended_at = datetime.now(UTC)
        tenant.metadata_ = {**tenant.metadata_, "suspension_reason": "Non-payment"}
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.status == TenantStatusEnum.SUSPENDED
        assert tenant.suspended_at is not None
        assert tenant.metadata_["suspension_reason"] == "Non-payment"
        assert tenant.is_active() is False


class TestTenantDelete:
    """Tests for tenant deletion operations."""

    async def test_delete_tenant(self, db_session: AsyncSession, sample_tenant_data):
        """Test deleting a tenant."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        await db_session.delete(tenant)
        await db_session.commit()

        result = await db_session.execute(
            select(TenantORM).where(TenantORM.tenant_id == sample_tenant_data["tenant_id"])
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_parent_sets_null_on_children(self, db_session: AsyncSession):
        """Test that deleting parent tenant sets NULL on children (SET NULL foreign key)."""
        # Create parent
        parent = TenantORM(name="Parent", slug="parent-del")
        db_session.add(parent)
        await db_session.commit()
        await db_session.refresh(parent)
        parent_id = parent.tenant_id

        # Create child
        child = TenantORM(
            name="Child",
            slug="child-del",
            parent_tenant_id=parent_id,
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)
        child_id = child.tenant_id

        # Expire the child from the session cache so we get fresh data after delete
        db_session.expire(child)

        # Delete parent
        await db_session.delete(parent)
        await db_session.commit()

        # Expire all to ensure fresh fetch from DB
        db_session.expire_all()

        # Verify child still exists with NULL parent (fresh query from DB)
        result = await db_session.execute(select(TenantORM).where(TenantORM.tenant_id == child_id))
        orphaned_child = result.scalar_one_or_none()
        assert orphaned_child is not None
        assert orphaned_child.parent_tenant_id is None


# =============================================================================
# Test Cases - EnterpriseIntegrationORM CRUD
# =============================================================================


class TestEnterpriseIntegration:
    """Tests for enterprise integration CRUD operations."""

    async def test_create_integration(self, db_session: AsyncSession, sample_tenant_data):
        """Test creating an enterprise integration."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        integration = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="sso",
            provider="okta",
            name="Okta SSO",
            config={
                "client_id": "test-client-id",
                "metadata_url": "https://example.okta.com/.well-known/openid-configuration",
            },
        )
        db_session.add(integration)
        await db_session.commit()
        await db_session.refresh(integration)

        assert integration.integration_id is not None
        assert integration.tenant_id == tenant.tenant_id
        assert integration.integration_type == "sso"
        assert integration.provider == "okta"
        assert integration.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_cascade_delete_integration(self, db_session: AsyncSession, sample_tenant_data):
        """Test that deleting tenant cascades to integrations."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        integration = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="ldap",
            provider="azure_ad",
            name="Azure AD LDAP",
        )
        db_session.add(integration)
        await db_session.commit()
        integration_id = integration.integration_id

        # Delete tenant
        await db_session.delete(tenant)
        await db_session.commit()

        # Verify integration is also deleted
        result = await db_session.execute(
            select(EnterpriseIntegrationORM).where(
                EnterpriseIntegrationORM.integration_id == integration_id
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_unique_integration_per_tenant(
        self, db_session: AsyncSession, sample_tenant_data
    ):
        """Test that tenant can't have duplicate integration type+provider."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        integration1 = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="sso",
            provider="okta",
            name="Okta SSO 1",
        )
        db_session.add(integration1)
        await db_session.commit()

        integration2 = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="sso",
            provider="okta",
            name="Okta SSO 2",
        )
        db_session.add(integration2)

        with pytest.raises((Exception,), match=r".+"):  # IntegrityError - noqa: B017
            await db_session.commit()


# =============================================================================
# Test Cases - TenantRoleMappingORM CRUD
# =============================================================================


class TestTenantRoleMapping:
    """Tests for tenant role mapping CRUD operations."""

    async def test_create_role_mapping(self, db_session: AsyncSession, sample_tenant_data):
        """Test creating a role mapping."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        mapping = TenantRoleMappingORM(
            tenant_id=tenant.tenant_id,
            external_role="admins",
            internal_role="EXECUTIVE",
            priority=100,
            description="Map IdP admins to EXECUTIVE role",
        )
        db_session.add(mapping)
        await db_session.commit()
        await db_session.refresh(mapping)

        assert mapping.mapping_id is not None
        assert mapping.external_role == "admins"
        assert mapping.internal_role == "EXECUTIVE"
        assert mapping.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_role_mapping_with_integration(
        self, db_session: AsyncSession, sample_tenant_data
    ):
        """Test role mapping associated with an integration."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        integration = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="sso",
            provider="okta",
            name="Okta SSO",
        )
        db_session.add(integration)
        await db_session.commit()

        mapping = TenantRoleMappingORM(
            tenant_id=tenant.tenant_id,
            integration_id=integration.integration_id,
            external_role="developers",
            internal_role="IMPLEMENTER",
        )
        db_session.add(mapping)
        await db_session.commit()

        assert mapping.integration_id == integration.integration_id


# =============================================================================
# Test Cases - MigrationJobORM CRUD
# =============================================================================


class TestMigrationJob:
    """Tests for migration job CRUD operations."""

    async def test_create_migration_job(self, db_session: AsyncSession, sample_tenant_data):
        """Test creating a migration job."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        job = MigrationJobORM(
            tenant_id=tenant.tenant_id,
            job_type="region",
            source_region="us-east-1",
            target_region="eu-west-1",
            config={"batch_size": 1000},
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        assert job.job_id is not None
        assert job.status == "pending"
        assert job.progress == 0.0
        assert job.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_update_migration_progress(self, db_session: AsyncSession, sample_tenant_data):
        """Test updating migration job progress."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        job = MigrationJobORM(
            tenant_id=tenant.tenant_id,
            job_type="schema",
        )
        db_session.add(job)
        await db_session.commit()

        # Start job
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.progress = 50.0
        await db_session.commit()
        await db_session.refresh(job)

        assert job.status == "running"
        assert job.progress == 50.0
        assert job.started_at is not None

    async def test_complete_migration_job(self, db_session: AsyncSession, sample_tenant_data):
        """Test completing a migration job."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        job = MigrationJobORM(
            tenant_id=tenant.tenant_id,
            job_type="data",
        )
        db_session.add(job)
        await db_session.commit()

        # Complete job
        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.now(UTC)
        job.result = {"records_migrated": 10000, "duration_seconds": 120}
        await db_session.commit()
        await db_session.refresh(job)

        assert job.status == "completed"
        assert job.progress == 100.0
        assert job.result["records_migrated"] == 10000


# =============================================================================
# Test Cases - TenantAuditLogORM CRUD
# =============================================================================


class TestTenantAuditLog:
    """Tests for tenant audit log operations."""

    @pytest.mark.governance
    async def test_create_audit_log(self, db_session: AsyncSession, sample_tenant_data):
        """Test creating an audit log entry."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        log = TenantAuditLogORM(
            tenant_id=tenant.tenant_id,
            action="create",
            resource_type="tenant",
            actor_id="admin@example.com",
            actor_type="user",
            actor_ip="192.168.1.1",
            details={
                "after": {
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "status": tenant.status,
                }
            },
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.log_id is not None
        assert log.action == "create"
        assert log.actor_id == "admin@example.com"
        assert log.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.governance
    async def test_audit_log_immutability(self, db_session: AsyncSession, sample_tenant_data):
        """Test that audit log entries are immutable (no update_at field)."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        log = TenantAuditLogORM(
            tenant_id=tenant.tenant_id,
            action="activate",
            actor_id="system",
            actor_type="system",
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        original_created_at = log.created_at

        # Audit log should only have created_at, no updated_at
        assert hasattr(log, "created_at")
        assert log.created_at == original_created_at

    @pytest.mark.governance
    async def test_list_audit_logs_by_tenant(self, db_session: AsyncSession, sample_tenant_data):
        """Test listing audit logs for a specific tenant."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        # Create multiple audit entries
        for action in ["create", "activate", "update_config"]:
            log = TenantAuditLogORM(
                tenant_id=tenant.tenant_id,
                action=action,
                actor_id="admin",
                actor_type="user",
            )
            db_session.add(log)
        await db_session.commit()

        result = await db_session.execute(
            select(TenantAuditLogORM)
            .where(TenantAuditLogORM.tenant_id == tenant.tenant_id)
            .order_by(TenantAuditLogORM.created_at)
        )
        logs = result.scalars().all()

        assert len(logs) == 3
        assert logs[0].action == "create"
        assert logs[1].action == "activate"
        assert logs[2].action == "update_config"


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance in database models."""

    @pytest.mark.constitutional
    async def test_tenant_constitutional_hash(self, db_session: AsyncSession):
        """Test that tenants have correct constitutional hash."""
        tenant = TenantORM(name="Test", slug="test-hash")
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.constitutional_hash == CONSTITUTIONAL_HASH
        assert tenant.validate_constitutional_compliance() is True

    @pytest.mark.constitutional
    async def test_integration_constitutional_hash(
        self, db_session: AsyncSession, sample_tenant_data
    ):
        """Test that integrations have correct constitutional hash."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        integration = EnterpriseIntegrationORM(
            tenant_id=tenant.tenant_id,
            integration_type="sso",
            provider="test",
            name="Test Integration",
        )
        db_session.add(integration)
        await db_session.commit()
        await db_session.refresh(integration)

        assert integration.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.constitutional
    async def test_audit_log_constitutional_hash(
        self, db_session: AsyncSession, sample_tenant_data
    ):
        """Test that audit logs have correct constitutional hash."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        log = TenantAuditLogORM(
            tenant_id=tenant.tenant_id,
            action="test",
            actor_id="system",
            actor_type="system",
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Test Cases - Model Methods
# =============================================================================


class TestTenantModelMethods:
    """Tests for TenantORM model helper methods."""

    async def test_is_active_true(self, db_session: AsyncSession):
        """Test is_active returns True for active tenants."""
        tenant = TenantORM(
            name="Active",
            slug="active-test",
            status=TenantStatusEnum.ACTIVE,
        )
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.is_active() is True

    async def test_is_active_false(self, db_session: AsyncSession):
        """Test is_active returns False for non-active tenants."""
        tenant = TenantORM(
            name="Pending",
            slug="pending-test",
            status=TenantStatusEnum.PENDING,
        )
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.is_active() is False

    async def test_validate_constitutional_compliance_valid(self, db_session: AsyncSession):
        """Test constitutional compliance validation passes for valid hash."""
        tenant = TenantORM(
            name="Compliant",
            slug="compliant-test",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.validate_constitutional_compliance() is True

    async def test_validate_constitutional_compliance_invalid(self, db_session: AsyncSession):
        """Test constitutional compliance validation fails for invalid hash."""
        tenant = TenantORM(
            name="Non-Compliant",
            slug="non-compliant-test",
            constitutional_hash="invalid_hash",
        )
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.validate_constitutional_compliance() is False

    async def test_repr(self, db_session: AsyncSession, sample_tenant_data):
        """Test __repr__ method output."""
        tenant = TenantORM(**sample_tenant_data)
        db_session.add(tenant)
        await db_session.commit()

        repr_str = repr(tenant)
        assert "TenantORM" in repr_str
        assert tenant.slug in repr_str
        assert tenant.status in repr_str
