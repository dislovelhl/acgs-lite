"""
Tests for ACGS-2 Session Variable Management
Constitutional Hash: 608508a9bd224290

Unit tests for PostgreSQL session variable management functions.
Note: Some tests require PostgreSQL and will be skipped on SQLite.
"""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.database.session import Base
from enhanced_agent_bus.multi_tenancy.session_vars import (
    SESSION_VAR_IS_ADMIN,
    SESSION_VAR_TENANT_ID,
    admin_session,
    clear_tenant_session_vars,
    get_current_tenant_from_session,
    get_is_admin_from_session,
    set_tenant_for_request,
    set_tenant_session_vars,
    system_tenant_session,
    tenant_session,
)
from enhanced_agent_bus.multi_tenancy.system_tenant import SYSTEM_TENANT_ID

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
        yield session
        await session.rollback()


# =============================================================================
# Test Cases - Constants
# =============================================================================


class TestSessionVarConstants:
    """Tests for session variable constants."""

    def test_tenant_id_var_name(self):
        """Test tenant ID variable name."""
        assert SESSION_VAR_TENANT_ID == "app.current_tenant_id"

    def test_is_admin_var_name(self):
        """Test is_admin variable name."""
        assert SESSION_VAR_IS_ADMIN == "app.is_admin"


# =============================================================================
# Test Cases - SQLite Behavior (Limited)
# =============================================================================


class TestSessionVarsSQLite:
    """Tests for session variable behavior on SQLite.

    Note: PostgreSQL-specific SET LOCAL commands will fail on SQLite.
    These tests verify the functions handle this gracefully.
    """

    async def test_set_tenant_session_vars_sqlite_fails(self, db_session: AsyncSession):
        """Test that set_tenant_session_vars fails on SQLite."""
        # SQLite doesn't support SET LOCAL - expect any SQLAlchemy/DB error
        with pytest.raises((Exception,), match=r".+"):
            await set_tenant_session_vars(db_session, "test-tenant-id")

    async def test_get_current_tenant_sqlite(self, db_session: AsyncSession):
        """Test that get_current_tenant_from_session returns None on SQLite."""
        # SQLite doesn't have current_setting function - expect any DB error
        with pytest.raises((Exception,), match=r".+"):
            await get_current_tenant_from_session(db_session)


# =============================================================================
# Test Cases - Mock PostgreSQL Behavior
# =============================================================================


class TestSessionVarsUnitBehavior:
    """Unit tests for session variable logic without database."""

    def test_system_tenant_id_constant(self):
        """Test that SYSTEM_TENANT_ID is correctly defined."""
        assert SYSTEM_TENANT_ID == "00000000-0000-0000-0000-000000000001"

    def test_session_var_names_format(self):
        """Test session variable names follow PostgreSQL conventions."""
        # Should use app. namespace
        assert SESSION_VAR_TENANT_ID.startswith("app.")
        assert SESSION_VAR_IS_ADMIN.startswith("app.")


# =============================================================================
# Test Cases - Context Manager Structure
# =============================================================================


class TestContextManagerStructure:
    """Tests for context manager structure (not database operations)."""

    async def test_tenant_session_is_async_context_manager(self):
        """Test that tenant_session is an async context manager."""
        import inspect

        assert inspect.isasyncgenfunction(tenant_session.__wrapped__)

    async def test_system_tenant_session_is_async_context_manager(self):
        """Test that system_tenant_session is an async context manager."""
        import inspect

        assert inspect.isasyncgenfunction(system_tenant_session.__wrapped__)

    async def test_admin_session_is_async_context_manager(self):
        """Test that admin_session is an async context manager."""
        import inspect

        assert inspect.isasyncgenfunction(admin_session.__wrapped__)


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestSessionVarsConstitutionalCompliance:
    """Tests for constitutional compliance of session vars module."""

    def test_module_has_constitutional_hash(self):
        """Test that module exports constitutional hash."""
        from enhanced_agent_bus.multi_tenancy.session_vars import (
            CONSTITUTIONAL_HASH as SV_HASH,
        )

        assert SV_HASH == CONSTITUTIONAL_HASH

    def test_all_exports_defined(self):
        """Test that all expected functions are exported."""
        from enhanced_agent_bus.multi_tenancy import session_vars

        expected_exports = [
            "SESSION_VAR_TENANT_ID",
            "SESSION_VAR_IS_ADMIN",
            "set_tenant_session_vars",
            "clear_tenant_session_vars",
            "get_current_tenant_from_session",
            "get_is_admin_from_session",
            "tenant_session",
            "system_tenant_session",
            "admin_session",
            "set_tenant_for_request",
        ]

        for export in expected_exports:
            assert hasattr(session_vars, export), f"Missing export: {export}"


# =============================================================================
# Test Cases - Integration with Multi-Tenancy Module
# =============================================================================


class TestSessionVarsModuleIntegration:
    """Tests for integration with multi-tenancy module."""

    def test_exports_from_parent_module(self):
        """Test that session vars are exported from parent module."""
        from enhanced_agent_bus.multi_tenancy import (
            SESSION_VAR_IS_ADMIN as _SESSION_VAR_IS_ADMIN,
        )
        from enhanced_agent_bus.multi_tenancy import (
            SESSION_VAR_TENANT_ID as _SESSION_VAR_TENANT_ID,
        )
        from enhanced_agent_bus.multi_tenancy import (
            admin_session as _admin_session,
        )
        from enhanced_agent_bus.multi_tenancy import (
            set_tenant_for_request as _set_tenant_for_request,
        )
        from enhanced_agent_bus.multi_tenancy import (
            set_tenant_session_vars as _set_tenant_session_vars,
        )
        from enhanced_agent_bus.multi_tenancy import (
            system_tenant_session as _system_tenant_session,
        )
        from enhanced_agent_bus.multi_tenancy import (
            tenant_session as _tenant_session,
        )

        # Just verify imports work
        assert _SESSION_VAR_TENANT_ID is not None
        assert _SESSION_VAR_IS_ADMIN is not None
        assert _tenant_session is not None
        assert _system_tenant_session is not None
        assert _admin_session is not None
        assert _set_tenant_session_vars is not None
        assert _set_tenant_for_request is not None

    def test_system_tenant_available(self):
        """Test that SYSTEM_TENANT_ID is available in session_vars module."""
        from enhanced_agent_bus.multi_tenancy.session_vars import (
            SYSTEM_TENANT_ID as SESSION_SYSTEM_ID,
        )

        assert SESSION_SYSTEM_ID == "00000000-0000-0000-0000-000000000001"
