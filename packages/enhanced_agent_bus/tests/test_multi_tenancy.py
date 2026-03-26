"""
ACGS-2 Multi-Tenancy Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the multi-tenant isolation system.
Tests TenantContext, RLS policies, repository operations, and middleware.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.multi_tenancy import (
    CONSTITUTIONAL_HASH,
    RLSPolicy,
    RLSPolicyManager,
    Tenant,
    TenantConfig,
    TenantContext,
    TenantMiddleware,
    TenantQuota,
    TenantRepository,
    TenantStatus,
    TenantUsage,
    clear_tenant_context,
    create_tenant_rls_policies,
    get_current_tenant,
    set_current_tenant,
    tenant_context,
)
from enhanced_agent_bus.multi_tenancy.rls import (
    ACGS2_RLS_TABLES,
    RLSPolicyType,
    create_acgs2_rls_policies,
    create_admin_bypass_policy,
    create_tenant_isolation_policy,
)

# =============================================================================
# TenantContext Tests
# =============================================================================


class TestTenantContext:
    """Tests for TenantContext class."""

    def test_context_creation(self):
        """Test basic tenant context creation."""
        ctx = TenantContext(tenant_id="test-tenant")

        assert ctx.tenant_id == "test-tenant"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.is_admin is False
        assert ctx.user_id is None

    def test_context_requires_tenant_id(self):
        """Test that tenant_id is required."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            TenantContext(tenant_id="")

    def test_context_validates_constitutional_hash(self):
        """Test constitutional hash validation."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            TenantContext(tenant_id="test", constitutional_hash="invalid-hash")

    def test_context_with_all_fields(self):
        """Test context with all fields populated."""
        expires = datetime.now(UTC) + timedelta(hours=1)

        ctx = TenantContext(
            tenant_id="test-tenant",
            user_id="user-123",
            session_id="session-456",
            request_id="request-789",
            source_ip="192.168.1.1",
            is_admin=True,
            roles=["admin", "operator"],
            permissions=["read", "write"],
            expires_at=expires,
        )

        assert ctx.tenant_id == "test-tenant"
        assert ctx.user_id == "user-123"
        assert ctx.session_id == "session-456"
        assert ctx.request_id == "request-789"
        assert ctx.is_admin is True
        assert "admin" in ctx.roles
        assert "read" in ctx.permissions
        assert not ctx.is_expired()

    def test_context_expiration(self):
        """Test context expiration checking."""
        # Not expired
        future = datetime.now(UTC) + timedelta(hours=1)
        ctx = TenantContext(tenant_id="test", expires_at=future)
        assert not ctx.is_expired()

        # Expired
        past = datetime.now(UTC) - timedelta(hours=1)
        ctx = TenantContext(tenant_id="test", expires_at=past)
        assert ctx.is_expired()

        # No expiration
        ctx = TenantContext(tenant_id="test")
        assert not ctx.is_expired()

    def test_context_validation(self):
        """Test context validation."""
        # Valid context
        ctx = TenantContext(tenant_id="test")
        assert ctx.validate() is True

        # Expired context
        past = datetime.now(UTC) - timedelta(hours=1)
        ctx = TenantContext(tenant_id="test", expires_at=past)
        assert ctx.validate() is False

    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = TenantContext(
            tenant_id="test-tenant",
            user_id="user-123",
            is_admin=True,
        )

        data = ctx.to_dict()
        assert data["tenant_id"] == "test-tenant"
        assert data["user_id"] == "user-123"
        assert data["is_admin"] is True
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_context_to_sql_params(self):
        """Test SQL parameter generation for RLS."""
        ctx = TenantContext(
            tenant_id="test-tenant",
            user_id="user-123",
            is_admin=True,
        )

        params = ctx.to_sql_params()
        assert params["app.current_tenant_id"] == "test-tenant"
        assert params["app.user_id"] == "user-123"
        assert params["app.is_admin"] == "true"
        assert params["app.constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_context_manager_sync(self):
        """Test synchronous context manager."""
        assert get_current_tenant() is None

        with TenantContext(tenant_id="test-tenant") as ctx:
            current = get_current_tenant()
            assert current is not None
            assert current.tenant_id == "test-tenant"

        assert get_current_tenant() is None

    async def test_context_manager_async(self):
        """Test asynchronous context manager."""
        assert get_current_tenant() is None

        async with TenantContext(tenant_id="test-tenant") as ctx:
            current = get_current_tenant()
            assert current is not None
            assert current.tenant_id == "test-tenant"

        assert get_current_tenant() is None


class TestTenantContextFunctions:
    """Tests for context management functions."""

    def test_set_and_get_tenant(self):
        """Test setting and getting tenant context."""
        clear_tenant_context()
        assert get_current_tenant() is None

        ctx = TenantContext(tenant_id="test-tenant")
        token = set_current_tenant(ctx)

        current = get_current_tenant()
        assert current is not None
        assert current.tenant_id == "test-tenant"

        clear_tenant_context()
        assert get_current_tenant() is None

    def test_tenant_context_helper(self):
        """Test tenant_context helper."""
        clear_tenant_context()

        with tenant_context(
            tenant_id="my-tenant",
            user_id="user-1",
            is_admin=False,
        ) as ctx:
            assert ctx.tenant_id == "my-tenant"
            assert ctx.user_id == "user-1"
            assert ctx.is_admin is False

            current = get_current_tenant()
            assert current.tenant_id == "my-tenant"

        assert get_current_tenant() is None

    def test_nested_contexts(self):
        """Test nested tenant contexts."""
        with tenant_context(tenant_id="outer-tenant"):
            assert get_current_tenant().tenant_id == "outer-tenant"

            with tenant_context(tenant_id="inner-tenant"):
                assert get_current_tenant().tenant_id == "inner-tenant"

            # After inner context, should restore outer
            # Token-based reset correctly restores outer context
            assert get_current_tenant().tenant_id == "outer-tenant"


# =============================================================================
# TenantModel Tests
# =============================================================================


class TestTenantModels:
    """Tests for tenant models."""

    def test_tenant_creation(self):
        """Test Tenant model creation."""
        tenant = Tenant(
            name="Acme Corporation",
            slug="acme-corp",
        )

        assert tenant.name == "Acme Corporation"
        assert tenant.slug == "acme-corp"
        assert tenant.status == TenantStatus.PENDING
        assert tenant.tenant_id is not None
        assert tenant.constitutional_hash == CONSTITUTIONAL_HASH

    def test_tenant_is_active(self):
        """Test tenant active status check."""
        tenant = Tenant(name="Test", slug="test-slug")
        assert tenant.is_active() is False

        tenant.status = TenantStatus.ACTIVE
        assert tenant.is_active() is True

        tenant.status = TenantStatus.SUSPENDED
        assert tenant.is_active() is False

    def test_tenant_quota(self):
        """Test TenantQuota model."""
        quota = TenantQuota()

        assert quota.max_agents == 100
        assert quota.max_policies == 1000
        assert quota.max_messages_per_minute == 10000

        # Custom quota
        quota = TenantQuota(max_agents=500, max_policies=5000)
        assert quota.max_agents == 500
        assert quota.max_policies == 5000

    def test_tenant_usage_within_quota(self):
        """Test usage quota checking."""
        quota = TenantQuota(max_agents=10, max_policies=100)
        usage = TenantUsage(agent_count=5, policy_count=50)

        assert usage.is_within_quota(quota) is True

        usage.agent_count = 15
        assert usage.is_within_quota(quota) is False

    def test_tenant_config(self):
        """Test TenantConfig model."""
        config = TenantConfig()

        assert config.constitutional_hash == CONSTITUTIONAL_HASH
        assert config.enable_batch_processing is True
        assert config.require_jwt_auth is True

    def test_tenant_validate_constitutional_compliance(self):
        """Test constitutional compliance validation."""
        tenant = Tenant(name="Test", slug="test-slug")
        assert tenant.validate_constitutional_compliance() is True

        # Invalid tenant would fail validation
        tenant.constitutional_hash = "invalid"
        assert tenant.validate_constitutional_compliance() is False

    def test_tenant_to_rls_context(self):
        """Test RLS context generation."""
        tenant = Tenant(name="Test", slug="test-slug")
        rls = tenant.to_rls_context()

        assert "tenant_id" in rls
        assert rls["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# RLS Policy Tests
# =============================================================================


class TestRLSPolicy:
    """Tests for RLS policy management."""

    def test_rls_policy_creation(self):
        """Test RLSPolicy creation."""
        policy = RLSPolicy(
            name="test_isolation",
            table_name="test_table",
            policy_type=RLSPolicyType.ALL,
            using_expression="tenant_id = current_setting('app.current_tenant_id')",
            strict_table_validation=False,  # Allow test table names
        )

        assert policy.name == "test_isolation"
        assert policy.table_name == "test_table"
        assert policy.policy_type == RLSPolicyType.ALL
        assert policy.enabled is True

    def test_rls_policy_to_sql_create(self):
        """Test SQL CREATE POLICY generation."""
        policy = RLSPolicy(
            name="test_policy",
            table_name="test_table",
            policy_type=RLSPolicyType.SELECT,
            using_expression="tenant_id = 'test'",
            strict_table_validation=False,  # Allow test table names
        )

        sql = policy.to_sql_create()
        # Identifiers are now quoted for SQL injection safety
        assert 'CREATE POLICY "test_policy" ON "test_table"' in sql
        assert "FOR SELECT" in sql
        assert "USING (tenant_id = 'test')" in sql

    def test_rls_policy_with_check(self):
        """Test policy with WITH CHECK clause."""
        policy = RLSPolicy(
            name="insert_policy",
            table_name="test_table",
            policy_type=RLSPolicyType.INSERT,
            using_expression="true",
            with_check_expression="tenant_id = current_setting('app.current_tenant_id')",
            strict_table_validation=False,  # Allow test table names
        )

        sql = policy.to_sql_create()
        assert "WITH CHECK" in sql

    def test_rls_policy_to_sql_drop(self):
        """Test SQL DROP POLICY generation."""
        policy = RLSPolicy(
            name="test_policy",
            table_name="test_table",
            policy_type=RLSPolicyType.ALL,
            using_expression="true",
            strict_table_validation=False,  # Allow test table names
        )

        sql = policy.to_sql_drop()
        # Identifiers are now quoted for SQL injection safety
        assert 'DROP POLICY IF EXISTS "test_policy" ON "test_table"' in sql

    def test_create_tenant_isolation_policy(self):
        """Test tenant isolation policy creation."""
        policy = create_tenant_isolation_policy("my_table", strict_table_validation=False)

        assert "tenant_isolation" in policy.name
        assert policy.table_name == "my_table"
        assert "current_setting('app.current_tenant_id'" in policy.using_expression

    def test_create_admin_bypass_policy(self):
        """Test admin bypass policy creation."""
        policy = create_admin_bypass_policy("my_table", strict_table_validation=False)

        assert "admin_bypass" in policy.name
        assert "app.is_admin" in policy.using_expression


class TestRLSPolicyManager:
    """Tests for RLSPolicyManager."""

    def test_policy_manager_creation(self):
        """Test policy manager initialization."""
        manager = RLSPolicyManager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(manager.list_policies()) == 0

    def test_policy_manager_invalid_hash(self):
        """Test policy manager rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            RLSPolicyManager(constitutional_hash="invalid")

    def test_register_and_get_policy(self):
        """Test policy registration and retrieval."""
        manager = RLSPolicyManager()
        policy = create_tenant_isolation_policy("test_table", strict_table_validation=False)

        manager.register_policy(policy)

        retrieved = manager.get_policy("test_table", policy.name)
        assert retrieved is not None
        assert retrieved.table_name == "test_table"

    def test_list_policies_by_table(self):
        """Test listing policies by table."""
        manager = RLSPolicyManager()

        manager.register_policy(
            create_tenant_isolation_policy("table_a", strict_table_validation=False)
        )
        manager.register_policy(
            create_admin_bypass_policy("table_a", strict_table_validation=False)
        )
        manager.register_policy(
            create_tenant_isolation_policy("table_b", strict_table_validation=False)
        )

        table_a_policies = manager.list_policies("table_a")
        assert len(table_a_policies) == 2

        table_b_policies = manager.list_policies("table_b")
        assert len(table_b_policies) == 1

    def test_generate_migration_up(self):
        """Test migration script generation."""
        manager = RLSPolicyManager()
        manager.register_policy(
            create_tenant_isolation_policy("test_table", strict_table_validation=False)
        )

        sql = manager.generate_migration_up()
        assert "ACGS-2 Multi-Tenant RLS Migration" in sql
        assert CONSTITUTIONAL_HASH in sql
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "CREATE POLICY" in sql

    def test_generate_migration_down(self):
        """Test rollback script generation."""
        manager = RLSPolicyManager()
        manager.register_policy(
            create_tenant_isolation_policy("test_table", strict_table_validation=False)
        )

        sql = manager.generate_migration_down()
        assert "RLS Rollback" in sql
        assert "DROP POLICY" in sql
        assert "DISABLE ROW LEVEL SECURITY" in sql

    def test_create_acgs2_rls_policies(self):
        """Test ACGS-2 standard policies creation."""
        manager = create_acgs2_rls_policies()

        # Should have 2 policies per table (isolation + admin bypass)
        expected_count = len(ACGS2_RLS_TABLES) * 2
        assert len(manager.list_policies()) == expected_count


class TestCreateTenantRLSPolicies:
    """Tests for create_tenant_rls_policies function."""

    def test_create_policies_for_tables(self):
        """Test creating policies for multiple tables."""
        tables = ["table1", "table2", "table3"]
        policies = create_tenant_rls_policies(tables, strict_table_validation=False)

        # 2 policies per table (isolation + admin bypass)
        assert len(policies) == 6

    def test_create_policies_without_admin_bypass(self):
        """Test creating policies without admin bypass."""
        tables = ["table1", "table2"]
        policies = create_tenant_rls_policies(
            tables, include_admin_bypass=False, strict_table_validation=False
        )

        # Only isolation policies
        assert len(policies) == 2

    def test_custom_tenant_column(self):
        """Test using custom tenant column name."""
        policies = create_tenant_rls_policies(
            ["test_table"],
            tenant_column="organization_id",
            include_admin_bypass=False,
            strict_table_validation=False,
        )

        assert len(policies) == 1
        assert "organization_id" in policies[0].using_expression


# =============================================================================
# TenantRepository Tests
# =============================================================================


class TestTenantRepository:
    """Tests for TenantRepository."""

    @pytest.fixture
    def repo(self):
        """Create a fresh repository for each test."""
        return TenantRepository()

    async def test_create_tenant(self, repo):
        """Test tenant creation."""
        tenant = await repo.create_tenant(
            name="Test Company",
            slug="test-company",
        )

        assert tenant.name == "Test Company"
        assert tenant.slug == "test-company"
        assert tenant.status == TenantStatus.PENDING
        assert repo.get_tenant_count() == 1

    async def test_create_tenant_duplicate_slug(self, repo):
        """Test duplicate slug rejection."""
        await repo.create_tenant(name="First", slug="my-slug")

        with pytest.raises(ValueError, match="already exists"):
            await repo.create_tenant(name="Second", slug="my-slug")

    async def test_get_tenant(self, repo):
        """Test getting tenant by ID."""
        created = await repo.create_tenant(name="Test", slug="test-get")

        retrieved = await repo.get_tenant(created.tenant_id)
        assert retrieved is not None
        assert retrieved.name == "Test"

        not_found = await repo.get_tenant("nonexistent-id")
        assert not_found is None

    async def test_get_tenant_by_slug(self, repo):
        """Test getting tenant by slug."""
        await repo.create_tenant(name="Test", slug="test-slug")

        tenant = await repo.get_tenant_by_slug("test-slug")
        assert tenant is not None
        assert tenant.name == "Test"

        not_found = await repo.get_tenant_by_slug("nonexistent")
        assert not_found is None

    async def test_list_tenants(self, repo):
        """Test listing tenants."""
        await repo.create_tenant(name="A", slug="tenant-a")
        await repo.create_tenant(name="B", slug="tenant-b")
        await repo.create_tenant(name="C", slug="tenant-c")

        tenants = await repo.list_tenants()
        assert len(tenants) == 3

        # Test pagination
        tenants = await repo.list_tenants(skip=1, limit=1)
        assert len(tenants) == 1

    async def test_list_tenants_by_status(self, repo):
        """Test filtering tenants by status."""
        t1 = await repo.create_tenant(name="A", slug="tenant-a")
        t2 = await repo.create_tenant(name="B", slug="tenant-b")
        await repo.activate_tenant(t1.tenant_id)

        active = await repo.list_tenants(status=TenantStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].tenant_id == t1.tenant_id

        pending = await repo.list_tenants(status=TenantStatus.PENDING)
        assert len(pending) == 1

    async def test_activate_tenant(self, repo):
        """Test tenant activation."""
        tenant = await repo.create_tenant(name="Test", slug="test-activate")
        assert tenant.status == TenantStatus.PENDING

        activated = await repo.activate_tenant(tenant.tenant_id)
        assert activated.status == TenantStatus.ACTIVE
        assert activated.activated_at is not None

        assert repo.get_active_tenant_count() == 1

    async def test_suspend_tenant(self, repo):
        """Test tenant suspension."""
        tenant = await repo.create_tenant(name="Test", slug="test-suspend")
        await repo.activate_tenant(tenant.tenant_id)

        suspended = await repo.suspend_tenant(tenant.tenant_id, reason="Policy violation")
        assert suspended.status == TenantStatus.SUSPENDED
        assert suspended.suspended_at is not None
        assert "suspension_reason" in suspended.metadata

    async def test_update_tenant_config(self, repo):
        """Test updating tenant configuration."""
        tenant = await repo.create_tenant(name="Test", slug="test-config")

        new_config = TenantConfig(
            enable_blockchain_anchoring=True,
            default_timeout_ms=10000,
        )
        updated = await repo.update_tenant_config(tenant.tenant_id, new_config)

        assert updated.config.enable_blockchain_anchoring is True
        assert updated.config.default_timeout_ms == 10000

    async def test_update_tenant_quota(self, repo):
        """Test updating tenant quota."""
        tenant = await repo.create_tenant(name="Test", slug="test-quota")

        new_quota = TenantQuota(max_agents=500, max_policies=5000)
        updated = await repo.update_tenant_quota(tenant.tenant_id, new_quota)

        assert updated.quota["max_agents"] == 500
        assert updated.quota["max_policies"] == 5000

    async def test_delete_tenant(self, repo):
        """Test tenant deletion."""
        tenant = await repo.create_tenant(name="Test", slug="test-delete")
        assert repo.get_tenant_count() == 1

        result = await repo.delete_tenant(tenant.tenant_id)
        assert result is True
        assert repo.get_tenant_count() == 0

        # Deleting non-existent tenant
        result = await repo.delete_tenant("nonexistent")
        assert result is False


# =============================================================================
# Middleware Tests
# =============================================================================


class TestTenantMiddleware:
    """Tests for TenantMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create mock ASGI app."""

        async def app(scope, receive, send):
            pass

        return app

    def test_middleware_creation(self, mock_app):
        """Test middleware initialization."""
        middleware = TenantMiddleware(
            mock_app,
            require_tenant=True,
            public_paths=["/health", "/metrics"],
        )

        assert middleware.require_tenant is True

    def test_is_public_path(self, mock_app):
        """Test public path detection."""
        middleware = TenantMiddleware(
            mock_app,
            public_paths=["/health", "/docs"],
        )

        assert middleware._is_public_path("/health") is True
        assert middleware._is_public_path("/health/live") is True
        assert middleware._is_public_path("/api/items") is False


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
class TestMultiTenancyIntegration:
    """Integration tests for multi-tenancy system."""

    async def test_full_tenant_lifecycle(self):
        """Test complete tenant lifecycle."""
        repo = TenantRepository()

        # Create tenant
        tenant = await repo.create_tenant(
            name="Integration Test Corp",
            slug="integration-test",
            config=TenantConfig(enable_deliberation=True),
            quota=TenantQuota(max_agents=200),
        )
        assert tenant.status == TenantStatus.PENDING

        # Activate tenant
        await repo.activate_tenant(tenant.tenant_id)
        tenant = await repo.get_tenant(tenant.tenant_id)
        assert tenant.status == TenantStatus.ACTIVE

        # Use tenant context
        with tenant_context(tenant_id=tenant.tenant_id) as ctx:
            assert get_current_tenant().tenant_id == tenant.tenant_id
            assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

        # Suspend tenant
        await repo.suspend_tenant(tenant.tenant_id, "Test suspension")
        tenant = await repo.get_tenant(tenant.tenant_id)
        assert tenant.status == TenantStatus.SUSPENDED

        # Delete tenant
        await repo.delete_tenant(tenant.tenant_id)
        tenant = await repo.get_tenant(tenant.tenant_id)
        assert tenant is None

    async def test_rls_policy_generation_and_application(self):
        """Test RLS policy generation produces valid SQL."""
        manager = create_acgs2_rls_policies()

        up_sql = manager.generate_migration_up()
        down_sql = manager.generate_migration_down()

        # Verify SQL structure
        assert "CREATE POLICY" in up_sql
        assert "DROP POLICY" in down_sql
        assert CONSTITUTIONAL_HASH in up_sql

        # Check all standard tables are covered
        for table in ACGS2_RLS_TABLES:
            assert table in up_sql

    async def test_concurrent_tenant_contexts(self):
        """Test multiple concurrent tenant contexts."""
        results = []

        async def worker(tenant_id: str):
            with tenant_context(tenant_id=tenant_id):
                await asyncio.sleep(0.01)  # Simulate work
                current = get_current_tenant()
                results.append(current.tenant_id if current else None)

        await asyncio.gather(
            worker("tenant-a"),
            worker("tenant-b"),
            worker("tenant-c"),
        )

        # Each worker should have captured its own tenant
        assert len(results) == 3
        # Note: Due to context isolation, each async task has its own context


class TestTenantManager:
    """Test TenantManager high-level operations."""

    @pytest.fixture
    def manager(self):
        """Create a TenantManager for testing."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantManager

        return TenantManager(cache_ttl_seconds=60, quota_warning_threshold=0.8)

    async def test_create_tenant_with_validation(self, manager):
        """Test tenant creation with validation."""
        tenant = await manager.create_tenant(
            name="Test Corp",
            slug="test-corp",
        )

        assert tenant is not None
        assert tenant.name == "Test Corp"
        assert tenant.slug == "test-corp"
        assert tenant.status == TenantStatus.PENDING
        assert tenant.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_create_tenant_auto_activate(self, manager):
        """Test tenant creation with auto-activation."""
        tenant = await manager.create_tenant(
            name="Auto Corp",
            slug="auto-corp",
            auto_activate=True,
        )

        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.activated_at is not None

    async def test_create_tenant_invalid_slug(self, manager):
        """Test tenant creation with invalid slug fails."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantValidationError

        with pytest.raises(TenantValidationError, match="Invalid slug format"):
            await manager.create_tenant(
                name="Bad Slug Corp",
                slug="Bad-Slug!",
            )

    async def test_create_tenant_short_slug(self, manager):
        """Test minimum 2 character slug validation."""
        # Minimum 2 chars required by model pattern
        tenant = await manager.create_tenant(
            name="X Corp",
            slug="xc",
        )
        assert tenant.slug == "xc"

    async def test_create_tenant_with_parent(self, manager):
        """Test creating child tenant."""
        parent = await manager.create_tenant(
            name="Parent Corp",
            slug="parent-corp",
            auto_activate=True,
        )

        child = await manager.create_tenant(
            name="Child Division",
            slug="child-div",
            parent_tenant_id=parent.tenant_id,
        )

        assert child.parent_tenant_id == parent.tenant_id

    async def test_create_tenant_with_inactive_parent_fails(self, manager):
        """Test creating child with inactive parent fails."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantValidationError

        parent = await manager.create_tenant(
            name="Inactive Parent",
            slug="inactive-parent",
        )
        # Parent is PENDING, not ACTIVE

        with pytest.raises(TenantValidationError, match="not active"):
            await manager.create_tenant(
                name="Child",
                slug="child-tenant",
                parent_tenant_id=parent.tenant_id,
            )

    async def test_get_tenant_with_caching(self, manager):
        """Test tenant caching."""
        tenant = await manager.create_tenant(
            name="Cache Test",
            slug="cache-test",
        )

        # First fetch
        fetched1 = await manager.get_tenant(tenant.tenant_id)
        # Second fetch should hit cache
        fetched2 = await manager.get_tenant(tenant.tenant_id)

        assert fetched1 == fetched2
        assert len(manager._cache) > 0

    async def test_get_tenant_by_slug(self, manager):
        """Test tenant lookup by slug."""
        tenant = await manager.create_tenant(
            name="Slug Test",
            slug="slug-test",
        )

        fetched = await manager.get_tenant_by_slug("slug-test")
        assert fetched is not None
        assert fetched.tenant_id == tenant.tenant_id

    async def test_list_tenants_with_status_filter(self, manager):
        """Test listing tenants with status filter."""
        # Create multiple tenants
        t1 = await manager.create_tenant(name="T1", slug="t1", auto_activate=True)
        t2 = await manager.create_tenant(name="T2", slug="t2")  # PENDING
        t3 = await manager.create_tenant(name="T3", slug="t3", auto_activate=True)

        active = await manager.list_tenants(status=TenantStatus.ACTIVE)
        pending = await manager.list_tenants(status=TenantStatus.PENDING)

        assert len([t for t in active if t.status == TenantStatus.ACTIVE]) >= 2
        assert any(t.status == TenantStatus.PENDING for t in pending)

    async def test_suspend_and_reactivate_tenant(self, manager):
        """Test tenant suspension and reactivation."""
        tenant = await manager.create_tenant(
            name="Suspend Test",
            slug="suspend-test",
            auto_activate=True,
        )

        # Suspend
        suspended = await manager.suspend_tenant(tenant.tenant_id, reason="Testing")
        assert suspended.status == TenantStatus.SUSPENDED
        assert "suspension_reason" in suspended.metadata

        # Reactivate
        reactivated = await manager.reactivate_tenant(tenant.tenant_id)
        assert reactivated.status == TenantStatus.ACTIVE

    async def test_delete_tenant_with_children_fails(self, manager):
        """Test deleting tenant with children fails without force."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantValidationError

        parent = await manager.create_tenant(
            name="Parent",
            slug="parent-delete",
            auto_activate=True,
        )
        await manager.create_tenant(
            name="Child",
            slug="child-delete",
            parent_tenant_id=parent.tenant_id,
        )

        with pytest.raises(TenantValidationError, match="child tenants"):
            await manager.delete_tenant(parent.tenant_id)

    async def test_delete_tenant_with_force(self, manager):
        """Test force deleting tenant with children."""
        parent = await manager.create_tenant(
            name="Parent Force",
            slug="parent-force",
            auto_activate=True,
        )
        child = await manager.create_tenant(
            name="Child Force",
            slug="child-force",
            parent_tenant_id=parent.tenant_id,
        )

        result = await manager.delete_tenant(parent.tenant_id, force=True)
        assert result is True

        # Both should be gone
        assert await manager.get_tenant(parent.tenant_id) is None
        assert await manager.get_tenant(child.tenant_id) is None

    async def test_quota_check_within_limits(self, manager):
        """Test quota check when within limits."""
        tenant = await manager.create_tenant(
            name="Quota Test",
            slug="quota-test",
        )

        result = await manager.check_quota(tenant.tenant_id, "agents", 10)
        assert result is True

    async def test_quota_check_exceeds_limits(self, manager):
        """Test quota check when exceeding limits."""
        tenant = await manager.create_tenant(
            name="Quota Exceed",
            slug="quota-exceed",
            quota=TenantQuota(max_agents=5),
        )

        # Within limit
        assert await manager.check_quota(tenant.tenant_id, "agents", 3) is True

        # Increment to near limit
        await manager.increment_usage(tenant.tenant_id, "agents", 3)

        # Now exceeds
        result = await manager.check_quota(tenant.tenant_id, "agents", 5)
        assert result is False

    async def test_increment_usage(self, manager):
        """Test incrementing resource usage."""
        tenant = await manager.create_tenant(
            name="Usage Test",
            slug="usage-test",
        )

        usage = await manager.increment_usage(tenant.tenant_id, "agents", 5)
        assert usage.agent_count == 5

        usage = await manager.increment_usage(tenant.tenant_id, "agents", 3)
        assert usage.agent_count == 8

    async def test_decrement_usage(self, manager):
        """Test decrementing resource usage."""
        tenant = await manager.create_tenant(
            name="Decrement Test",
            slug="decrement-test",
        )

        await manager.increment_usage(tenant.tenant_id, "policies", 10)
        usage = await manager.decrement_usage(tenant.tenant_id, "policies", 3)
        assert usage.policy_count == 7

        # Should not go below 0
        usage = await manager.decrement_usage(tenant.tenant_id, "policies", 100)
        assert usage.policy_count == 0

    async def test_quota_exceeded_error(self, manager):
        """Test quota exceeded error on increment."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantQuotaExceededError

        tenant = await manager.create_tenant(
            name="Quota Error",
            slug="quota-error",
            quota=TenantQuota(max_agents=5),
        )

        await manager.increment_usage(tenant.tenant_id, "agents", 5)

        with pytest.raises(TenantQuotaExceededError) as exc:
            await manager.increment_usage(tenant.tenant_id, "agents", 1)

        assert exc.value.resource == "agents"
        assert exc.value.limit == 5

    async def test_get_child_tenants(self, manager):
        """Test getting child tenants."""
        parent = await manager.create_tenant(
            name="Parent Hierarchy",
            slug="parent-hier",
            auto_activate=True,
        )

        await manager.create_tenant(
            name="Child 1",
            slug="child-hier-1",
            parent_tenant_id=parent.tenant_id,
        )
        await manager.create_tenant(
            name="Child 2",
            slug="child-hier-2",
            parent_tenant_id=parent.tenant_id,
        )

        children = await manager.get_child_tenants(parent.tenant_id)
        assert len(children) == 2

    async def test_get_tenant_hierarchy(self, manager):
        """Test getting full tenant hierarchy."""
        root = await manager.create_tenant(
            name="Root",
            slug="root-hier",
            auto_activate=True,
        )
        mid = await manager.create_tenant(
            name="Middle",
            slug="middle-hier",
            parent_tenant_id=root.tenant_id,
            auto_activate=True,
        )
        leaf = await manager.create_tenant(
            name="Leaf",
            slug="leaf-hier",
            parent_tenant_id=mid.tenant_id,
        )

        hierarchy = await manager.get_tenant_hierarchy(leaf.tenant_id)
        assert len(hierarchy) == 3
        assert hierarchy[0].tenant_id == root.tenant_id
        assert hierarchy[1].tenant_id == mid.tenant_id
        assert hierarchy[2].tenant_id == leaf.tenant_id

    async def test_get_all_descendants(self, manager):
        """Test getting all descendant tenants."""
        root = await manager.create_tenant(
            name="Root Desc",
            slug="root-desc",
            auto_activate=True,
        )
        child1 = await manager.create_tenant(
            name="Child 1",
            slug="child-desc-1",
            parent_tenant_id=root.tenant_id,
            auto_activate=True,
        )
        await manager.create_tenant(
            name="Grandchild",
            slug="grandchild-desc",
            parent_tenant_id=child1.tenant_id,
        )
        await manager.create_tenant(
            name="Child 2",
            slug="child-desc-2",
            parent_tenant_id=root.tenant_id,
        )

        descendants = await manager.get_all_descendants(root.tenant_id)
        assert len(descendants) == 3

    async def test_event_subscription(self, manager):
        """Test event subscription and publishing."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantEvent

        events_received = []

        def handler(tenant, extra):
            events_received.append((tenant, extra))

        manager.subscribe(TenantEvent.CREATED, handler)
        manager.subscribe(TenantEvent.ACTIVATED, handler)

        tenant = await manager.create_tenant(
            name="Event Test",
            slug="event-test",
            auto_activate=True,
        )

        assert len(events_received) == 2
        assert events_received[0][0].tenant_id == tenant.tenant_id
        assert "constitutional_hash" in events_received[0][1]

    async def test_event_unsubscribe(self, manager):
        """Test event unsubscription."""
        from enhanced_agent_bus.multi_tenancy.manager import TenantEvent

        events_received = []

        def handler(tenant, extra):
            events_received.append(tenant.tenant_id)

        manager.subscribe(TenantEvent.CREATED, handler)
        await manager.create_tenant(name="Sub1", slug="sub1")

        manager.unsubscribe(TenantEvent.CREATED, handler)
        await manager.create_tenant(name="Sub2", slug="sub2")

        assert len(events_received) == 1

    async def test_update_config(self, manager):
        """Test updating tenant configuration."""
        tenant = await manager.create_tenant(
            name="Config Test",
            slug="config-test",
        )

        new_config = TenantConfig(
            enable_batch_processing=False,
            cache_ttl_seconds=600,
        )

        updated = await manager.update_config(tenant.tenant_id, new_config)
        assert updated.config.enable_batch_processing is False
        assert updated.config.cache_ttl_seconds == 600

    async def test_update_quota(self, manager):
        """Test updating tenant quota."""
        tenant = await manager.create_tenant(
            name="Quota Update",
            slug="quota-update",
        )

        new_quota = TenantQuota(
            max_agents=500,
            max_policies=5000,
        )

        updated = await manager.update_quota(tenant.tenant_id, new_quota)
        quota = updated.get_quota()
        assert quota.max_agents == 500
        assert quota.max_policies == 5000

    async def test_context_manager_helper(self, manager):
        """Test manager context helper."""
        tenant = await manager.create_tenant(
            name="Context Helper",
            slug="context-helper",
        )

        with manager.context(tenant.tenant_id, user_id="user-123") as ctx:
            assert ctx.tenant_id == tenant.tenant_id
            assert ctx.user_id == "user-123"
            assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_clear_cache(self, manager):
        """Test clearing cache."""
        tenant = await manager.create_tenant(
            name="Clear Cache",
            slug="clear-cache",
        )

        # Verify cached
        assert len(manager._cache) > 0

        manager.clear_cache()
        assert len(manager._cache) == 0
        assert len(manager._slug_to_id) == 0

    async def test_get_stats(self, manager):
        """Test getting manager statistics."""
        await manager.create_tenant(name="Stats 1", slug="stats-1", auto_activate=True)
        await manager.create_tenant(name="Stats 2", slug="stats-2")

        stats = manager.get_stats()
        assert "total_tenants" in stats
        assert "active_tenants" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_reset_message_usage(self, manager):
        """Test resetting message rate limit counters."""
        tenant = await manager.create_tenant(
            name="Message Reset",
            slug="message-reset",
        )

        await manager.increment_usage(tenant.tenant_id, "messages", 100)
        usage = await manager.get_usage(tenant.tenant_id)
        assert usage.message_count_minute == 100

        await manager.reset_message_usage()
        usage = await manager.get_usage(tenant.tenant_id)
        assert usage.message_count_minute == 0

    async def test_suspend_children_cascade(self, manager):
        """Test suspending parent cascades to children."""
        parent = await manager.create_tenant(
            name="Cascade Parent",
            slug="cascade-parent",
            auto_activate=True,
        )
        child = await manager.create_tenant(
            name="Cascade Child",
            slug="cascade-child",
            parent_tenant_id=parent.tenant_id,
            auto_activate=True,
        )

        await manager.suspend_tenant(
            parent.tenant_id,
            reason="Cascade test",
            suspend_children=True,
        )

        # Both should be suspended
        parent_after = await manager.get_tenant(parent.tenant_id)
        child_after = await manager.get_tenant(child.tenant_id)

        assert parent_after.status == TenantStatus.SUSPENDED
        assert child_after.status == TenantStatus.SUSPENDED


class TestTenantManagerSingleton:
    """Test TenantManager singleton pattern."""

    def test_get_tenant_manager_returns_instance(self):
        """Test get_tenant_manager returns a TenantManager."""
        from enhanced_agent_bus.multi_tenancy.manager import (
            get_tenant_manager,
            set_tenant_manager,
        )

        # Reset singleton
        set_tenant_manager(None)

        manager = get_tenant_manager()
        assert manager is not None
        assert isinstance(manager, TenantManager)

    def test_get_tenant_manager_returns_same_instance(self):
        """Test get_tenant_manager returns same instance."""
        from enhanced_agent_bus.multi_tenancy.manager import get_tenant_manager

        m1 = get_tenant_manager()
        m2 = get_tenant_manager()
        assert m1 is m2

    def test_set_tenant_manager(self):
        """Test set_tenant_manager replaces instance."""
        from enhanced_agent_bus.multi_tenancy.manager import (
            TenantManager,
            get_tenant_manager,
            set_tenant_manager,
        )

        custom = TenantManager(cache_ttl_seconds=120)
        set_tenant_manager(custom)

        assert get_tenant_manager() is custom
        assert get_tenant_manager()._cache_ttl == 120


# Import TenantManager for fixture
from enhanced_agent_bus.multi_tenancy.manager import TenantManager

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
