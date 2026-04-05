"""
Tests for ACGS-2 Row-Level Security Integration
Constitutional Hash: 608508a9bd224290

Integration tests for RLS policy generation and management.
Tests that require PostgreSQL are marked with @pytest.mark.postgres.
"""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from enhanced_agent_bus._compat.database.session import Base
from enhanced_agent_bus.multi_tenancy.rls import (
    ACGS2_RLS_TABLES,
    ALLOWED_RLS_TABLES,
    CONSTITUTIONAL_HASH,
    ENTERPRISE_RLS_TABLES,
    RLSPolicy,
    RLSPolicyManager,
    RLSPolicyType,
    SQLIdentifierError,
    create_acgs2_rls_policies,
    create_admin_bypass_policy,
    create_tenant_isolation_policy,
    create_tenant_rls_policies,
    disable_rls_for_table,
    enable_rls_for_table,
    quote_sql_identifier,
    validate_role_name,
    validate_sql_identifier,
    validate_table_name,
)

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
# Test Cases - SQL Identifier Validation
# =============================================================================


class TestSQLIdentifierValidation:
    """Tests for SQL identifier validation functions."""

    def test_valid_identifier(self):
        """Test valid SQL identifiers pass validation."""
        assert validate_sql_identifier("users") == "users"
        assert validate_sql_identifier("my_table") == "my_table"
        assert validate_sql_identifier("Table123") == "Table123"
        assert validate_sql_identifier("_private") == "_private"

    def test_empty_identifier_fails(self):
        """Test empty identifier raises error."""
        with pytest.raises(SQLIdentifierError, match="Empty"):
            validate_sql_identifier("")

    def test_reserved_keyword_fails(self):
        """Test reserved keywords are rejected."""
        with pytest.raises(SQLIdentifierError, match="reserved keyword"):
            validate_sql_identifier("select")
        with pytest.raises(SQLIdentifierError, match="reserved keyword"):
            validate_sql_identifier("FROM")

    def test_invalid_characters_fail(self):
        """Test invalid characters are rejected."""
        with pytest.raises(SQLIdentifierError):
            validate_sql_identifier("my-table")  # hyphens not allowed
        with pytest.raises(SQLIdentifierError):
            validate_sql_identifier("table.name")  # dots not allowed without schema
        with pytest.raises(SQLIdentifierError):
            validate_sql_identifier("123table")  # can't start with number

    def test_max_length_check(self):
        """Test max length validation."""
        long_name = "a" * 64  # PostgreSQL max is 63
        with pytest.raises(SQLIdentifierError, match="exceeds maximum length"):
            validate_sql_identifier(long_name)

    def test_schema_qualified_names(self):
        """Test schema-qualified names are validated correctly."""
        result = validate_sql_identifier(
            "public.users",
            allow_schema_qualified=True,
        )
        assert result == "public.users"

    def test_quote_sql_identifier(self):
        """Test SQL identifier quoting."""
        assert quote_sql_identifier("users") == '"users"'
        assert quote_sql_identifier('my"table') == '"my""table"'


# =============================================================================
# Test Cases - Table Name Validation
# =============================================================================


class TestTableNameValidation:
    """Tests for table name validation."""

    def test_allowed_table_strict(self):
        """Test allowed tables pass strict validation."""
        result = validate_table_name("users", strict=True)
        assert result == "users"

    def test_disallowed_table_strict_fails(self):
        """Test disallowed tables fail strict validation."""
        with pytest.raises(SQLIdentifierError, match="not in the allowed"):
            validate_table_name("unknown_table", strict=True)

    def test_any_table_non_strict(self):
        """Test any valid table passes non-strict validation."""
        result = validate_table_name("custom_table", strict=False)
        assert result == "custom_table"

    def test_schema_qualified_allowed_table(self):
        """Test schema-qualified allowed tables."""
        result = validate_table_name("public.users", strict=True)
        assert result == "public.users"


# =============================================================================
# Test Cases - Role Name Validation
# =============================================================================


class TestRoleNameValidation:
    """Tests for PostgreSQL role name validation."""

    def test_public_role_special_case(self):
        """Test PUBLIC role is handled specially."""
        assert validate_role_name("PUBLIC") == "PUBLIC"
        assert validate_role_name("public") == "PUBLIC"

    def test_valid_role_name(self):
        """Test valid role names pass validation."""
        assert validate_role_name("app_user") == "app_user"
        assert validate_role_name("admin") == "admin"


# =============================================================================
# Test Cases - RLS Policy Creation
# =============================================================================


class TestRLSPolicyCreation:
    """Tests for RLS policy object creation."""

    def test_create_tenant_isolation_policy(self):
        """Test creating a tenant isolation policy."""
        policy = create_tenant_isolation_policy(
            table_name="users",
            strict_table_validation=True,
        )

        assert policy.name == "users_tenant_isolation"
        assert policy.table_name == "users"
        assert policy.policy_type == RLSPolicyType.ALL
        assert "current_setting" in policy.using_expression
        assert "app.current_tenant_id" in policy.using_expression

    def test_create_admin_bypass_policy(self):
        """Test creating an admin bypass policy."""
        policy = create_admin_bypass_policy(
            table_name="users",
            strict_table_validation=True,
        )

        assert policy.name == "users_admin_bypass"
        assert "is_admin" in policy.using_expression

    def test_create_policies_for_multiple_tables(self):
        """Test creating policies for multiple tables."""
        policies = create_tenant_rls_policies(
            tables=["users", "sso_providers"],
            include_admin_bypass=True,
            strict_table_validation=True,
        )

        # 2 tables x 2 policies each = 4 policies
        assert len(policies) == 4

        # Check policy names
        policy_names = [p.name for p in policies]
        assert "users_tenant_isolation" in policy_names
        assert "users_admin_bypass" in policy_names
        assert "sso_providers_tenant_isolation" in policy_names
        assert "sso_providers_admin_bypass" in policy_names


# =============================================================================
# Test Cases - RLS Policy SQL Generation
# =============================================================================


class TestRLSPolicySQLGeneration:
    """Tests for RLS policy SQL statement generation."""

    def test_policy_to_sql_create(self):
        """Test SQL CREATE POLICY generation."""
        policy = RLSPolicy(
            name="users_tenant_isolation",
            table_name="users",
            policy_type=RLSPolicyType.ALL,
            using_expression="tenant_id = 'test'",
            strict_table_validation=True,
        )

        sql = policy.to_sql_create()

        assert 'CREATE POLICY "users_tenant_isolation"' in sql
        assert 'ON "users"' in sql
        assert "FOR ALL" in sql
        assert "USING (tenant_id = 'test')" in sql

    def test_policy_to_sql_drop(self):
        """Test SQL DROP POLICY generation."""
        policy = RLSPolicy(
            name="users_tenant_isolation",
            table_name="users",
            policy_type=RLSPolicyType.ALL,
            using_expression="true",
            strict_table_validation=True,
        )

        sql = policy.to_sql_drop()

        assert 'DROP POLICY IF EXISTS "users_tenant_isolation"' in sql
        assert 'ON "users"' in sql

    def test_enable_rls_for_table(self):
        """Test enable RLS SQL generation."""
        sql = enable_rls_for_table("users", force=True, strict=True)

        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "FORCE ROW LEVEL SECURITY" in sql
        assert '"users"' in sql

    def test_disable_rls_for_table(self):
        """Test disable RLS SQL generation."""
        sql = disable_rls_for_table("users", strict=True)

        assert "DISABLE ROW LEVEL SECURITY" in sql
        assert '"users"' in sql


# =============================================================================
# Test Cases - RLS Policy Manager
# =============================================================================


class TestRLSPolicyManager:
    """Tests for RLS policy manager."""

    def test_manager_init_with_valid_hash(self):
        """Test manager initialization with correct hash."""
        manager = RLSPolicyManager(constitutional_hash=CONSTITUTIONAL_HASH)
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH

    def test_manager_init_invalid_hash_fails(self):
        """Test manager initialization with wrong hash fails."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            RLSPolicyManager(constitutional_hash="wrong-hash")

    def test_register_and_get_policy(self):
        """Test registering and retrieving policies."""
        manager = RLSPolicyManager()
        policy = RLSPolicy(
            name="test_policy",
            table_name="users",
            policy_type=RLSPolicyType.SELECT,
            using_expression="true",
            strict_table_validation=True,
        )

        manager.register_policy(policy)
        retrieved = manager.get_policy("users", "test_policy")

        assert retrieved is not None
        assert retrieved.name == "test_policy"

    def test_list_policies_by_table(self):
        """Test listing policies by table."""
        manager = RLSPolicyManager()

        policy1 = RLSPolicy(
            name="policy1",
            table_name="users",
            policy_type=RLSPolicyType.ALL,
            using_expression="true",
            strict_table_validation=True,
        )
        policy2 = RLSPolicy(
            name="policy2",
            table_name="sso_providers",
            policy_type=RLSPolicyType.ALL,
            using_expression="true",
            strict_table_validation=True,
        )

        manager.register_policy(policy1)
        manager.register_policy(policy2)

        users_policies = manager.list_policies(table_name="users")
        assert len(users_policies) == 1
        assert users_policies[0].name == "policy1"

    def test_generate_migration_up(self):
        """Test migration script generation."""
        manager = RLSPolicyManager()
        policy = RLSPolicy(
            name="users_tenant",
            table_name="users",
            policy_type=RLSPolicyType.ALL,
            using_expression="tenant_id = 'test'",
            strict_table_validation=True,
        )
        manager.register_policy(policy)

        migration = manager.generate_migration_up()

        assert "ENABLE ROW LEVEL SECURITY" in migration
        assert "CREATE POLICY" in migration
        assert "Constitutional Hash" in migration


# =============================================================================
# Test Cases - ACGS-2 Standard Policies
# =============================================================================


class TestACGS2StandardPolicies:
    """Tests for ACGS-2 standard RLS configuration."""

    def test_acgs2_rls_tables_defined(self):
        """Test that ACGS-2 RLS tables are defined."""
        assert len(ACGS2_RLS_TABLES) > 0
        assert "users" in ACGS2_RLS_TABLES
        assert "sso_providers" in ACGS2_RLS_TABLES

    def test_enterprise_rls_tables_defined(self):
        """Test that enterprise RLS tables are defined."""
        assert len(ENTERPRISE_RLS_TABLES) > 0
        assert "enterprise_integrations" in ENTERPRISE_RLS_TABLES

    def test_allowed_rls_tables_includes_sso(self):
        """Test allowed tables includes SSO tables."""
        assert "users" in ALLOWED_RLS_TABLES
        assert "sso_providers" in ALLOWED_RLS_TABLES
        assert "sso_role_mappings" in ALLOWED_RLS_TABLES

    def test_create_acgs2_rls_policies(self):
        """Test creating standard ACGS-2 RLS policies."""
        manager = create_acgs2_rls_policies()

        # Should have policies registered
        policies = manager.list_policies()
        assert len(policies) > 0

        # Should have tenant isolation and admin bypass for each table
        users_policies = manager.list_policies(table_name="users")
        policy_names = [p.name for p in users_policies]
        assert "users_tenant_isolation" in policy_names
        assert "users_admin_bypass" in policy_names


# =============================================================================
# Test Cases - Constitutional Compliance
# =============================================================================


class TestRLSConstitutionalCompliance:
    """Tests for constitutional compliance of RLS module."""

    def test_constitutional_hash_constant(self):
        """Test constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_migration_includes_hash(self):
        """Test generated migrations include constitutional hash."""
        manager = create_acgs2_rls_policies()
        migration = manager.generate_migration_up()

        assert CONSTITUTIONAL_HASH in migration

    def test_policy_manager_validates_hash(self):
        """Test policy manager enforces constitutional hash."""
        # Should work with correct hash
        manager = RLSPolicyManager(constitutional_hash=CONSTITUTIONAL_HASH)
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH

        # Should fail with wrong hash
        with pytest.raises(ValueError):
            RLSPolicyManager(constitutional_hash="wrong")
