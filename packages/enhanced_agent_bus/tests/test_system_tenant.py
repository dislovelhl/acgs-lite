"""
Tests for ACGS-2 System Tenant Utilities
Constitutional Hash: 608508a9bd224290

Unit tests for system tenant constants, checks, and helper functions.
"""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.database.session import Base
from enhanced_agent_bus.multi_tenancy.db_repository import DatabaseTenantRepository
from enhanced_agent_bus.multi_tenancy.system_tenant import (
    SYSTEM_TENANT_ID,
    SYSTEM_TENANT_NAME,
    SYSTEM_TENANT_SLUG,
    ensure_system_tenant,
    get_system_tenant,
    get_system_tenant_defaults,
    get_tenant_id_or_system,
    is_system_tenant,
    is_system_tenant_slug,
)

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

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a fresh SQLite database for each test."""
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
async def db_session(test_engine) -> AsyncSession:
    """Provide a database session for tests."""
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
# Test Cases - Constants
# =============================================================================


class TestSystemTenantConstants:
    """Tests for system tenant constants."""

    def test_system_tenant_id_format(self):
        """Test that system tenant ID is a valid UUID format."""
        assert SYSTEM_TENANT_ID == "00000000-0000-0000-0000-000000000001"
        # Should be exactly 36 characters (8-4-4-4-12 + 4 hyphens)
        assert len(SYSTEM_TENANT_ID) == 36

    def test_system_tenant_slug(self):
        """Test that system tenant slug is 'system'."""
        assert SYSTEM_TENANT_SLUG == "system"

    def test_system_tenant_name(self):
        """Test that system tenant name is 'System'."""
        assert SYSTEM_TENANT_NAME == "System"


# =============================================================================
# Test Cases - Identity Checks
# =============================================================================


class TestSystemTenantIdentityChecks:
    """Tests for system tenant identity check functions."""

    def test_is_system_tenant_true(self):
        """Test is_system_tenant returns True for system tenant ID."""
        assert is_system_tenant(SYSTEM_TENANT_ID) is True

    def test_is_system_tenant_false(self):
        """Test is_system_tenant returns False for other tenant IDs."""
        assert is_system_tenant("other-tenant-id") is False

    def test_is_system_tenant_none(self):
        """Test is_system_tenant returns False for None."""
        assert is_system_tenant(None) is False

    def test_is_system_tenant_slug_true(self):
        """Test is_system_tenant_slug returns True for system slug."""
        assert is_system_tenant_slug(SYSTEM_TENANT_SLUG) is True

    def test_is_system_tenant_slug_false(self):
        """Test is_system_tenant_slug returns False for other slugs."""
        assert is_system_tenant_slug("other-slug") is False

    def test_is_system_tenant_slug_none(self):
        """Test is_system_tenant_slug returns False for None."""
        assert is_system_tenant_slug(None) is False


# =============================================================================
# Test Cases - Tenant ID Fallback
# =============================================================================


class TestTenantIdFallback:
    """Tests for tenant ID fallback function."""

    def test_get_tenant_id_or_system_with_id(self):
        """Test that provided tenant_id is returned when given."""
        tenant_id = "custom-tenant-id"
        result = get_tenant_id_or_system(tenant_id)
        assert result == tenant_id

    def test_get_tenant_id_or_system_with_none(self):
        """Test that system tenant ID is returned when None given."""
        result = get_tenant_id_or_system(None)
        assert result == SYSTEM_TENANT_ID

    def test_get_tenant_id_or_system_with_empty_string(self):
        """Test that system tenant ID is returned for empty string."""
        result = get_tenant_id_or_system("")
        assert result == SYSTEM_TENANT_ID


# =============================================================================
# Test Cases - System Tenant Defaults
# =============================================================================


class TestSystemTenantDefaults:
    """Tests for system tenant default configuration."""

    def test_get_system_tenant_defaults(self):
        """Test that defaults return valid Tenant model."""
        tenant = get_system_tenant_defaults()

        assert tenant.tenant_id == SYSTEM_TENANT_ID
        assert tenant.name == SYSTEM_TENANT_NAME
        assert tenant.slug == SYSTEM_TENANT_SLUG
        assert tenant.status.value == "active"
        assert tenant.metadata.get("is_system") is True

    def test_get_system_tenant_defaults_has_config(self):
        """Test that defaults include TenantConfig."""
        tenant = get_system_tenant_defaults()
        assert tenant.config is not None

    def test_get_system_tenant_defaults_has_description(self):
        """Test that defaults include description metadata."""
        tenant = get_system_tenant_defaults()
        assert "description" in tenant.metadata


# =============================================================================
# Test Cases - Database Operations
# =============================================================================


class TestSystemTenantDatabaseOperations:
    """Tests for system tenant database operations."""

    async def test_get_system_tenant_not_exists(self, repository: DatabaseTenantRepository):
        """Test get_system_tenant returns None when not created."""
        tenant = await get_system_tenant(repository)
        assert tenant is None

    async def test_ensure_system_tenant_creates(self, repository: DatabaseTenantRepository):
        """Test ensure_system_tenant creates the system tenant."""
        tenant = await ensure_system_tenant(repository)

        assert tenant is not None
        assert tenant.slug == SYSTEM_TENANT_SLUG
        assert tenant.name == SYSTEM_TENANT_NAME

    async def test_ensure_system_tenant_idempotent(self, repository: DatabaseTenantRepository):
        """Test ensure_system_tenant is idempotent."""
        tenant1 = await ensure_system_tenant(repository)
        tenant2 = await ensure_system_tenant(repository)

        # Should return the same tenant
        assert tenant1.tenant_id == tenant2.tenant_id

    async def test_get_system_tenant_after_ensure(self, repository: DatabaseTenantRepository):
        """Test get_system_tenant works after ensure."""
        await ensure_system_tenant(repository)
        tenant = await get_system_tenant(repository)

        assert tenant is not None
        assert is_system_tenant(tenant.tenant_id)


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestSystemTenantConstitutionalCompliance:
    """Tests for constitutional compliance of system tenant."""

    def test_system_tenant_defaults_no_constitutional_violation(self):
        """Test that system tenant defaults don't violate constitutional rules."""
        tenant = get_system_tenant_defaults()

        # Ensure the tenant can be serialized/deserialized
        data = tenant.model_dump()
        assert "tenant_id" in data
        assert "slug" in data
        assert "status" in data

    async def test_ensure_system_tenant_constitutional_hash(
        self, repository: DatabaseTenantRepository
    ):
        """Test that repository uses constitutional hash."""
        assert repository.constitutional_hash == CONSTITUTIONAL_HASH
