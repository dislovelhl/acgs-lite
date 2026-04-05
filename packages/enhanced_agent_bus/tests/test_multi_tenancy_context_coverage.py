# Constitutional Hash: 608508a9bd224290
"""
Focused coverage tests for multi_tenancy/context.py.

Exercises every branch in TenantContext, tenant_context, and the
module-level helper functions to push line coverage to ≥90%.
"""

from contextvars import ContextVar, Token
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.multi_tenancy.context import (
    TenantContext,
    clear_tenant_context,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant_context,
    set_current_tenant,
    tenant_context,
)

# ---------------------------------------------------------------------------
# TenantContext - construction and validation
# ---------------------------------------------------------------------------


class TestTenantContextConstruction:
    """TenantContext dataclass initialisation paths."""

    def test_minimal_creation(self):
        ctx = TenantContext(tenant_id="acme")
        assert ctx.tenant_id == "acme"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.is_admin is False
        assert ctx.user_id is None
        assert ctx.session_id is None
        assert ctx.request_id is None
        assert ctx.source_ip is None
        assert ctx.user_agent is None
        assert ctx.roles == []
        assert ctx.permissions == []
        assert ctx.expires_at is None
        assert isinstance(ctx.created_at, datetime)

    def test_full_creation(self):
        expires = datetime.now(UTC) + timedelta(hours=1)
        ctx = TenantContext(
            tenant_id="beta-corp",
            user_id="u-1",
            session_id="s-1",
            request_id="r-1",
            source_ip="10.0.0.1",
            user_agent="test-agent/1.0",
            is_admin=True,
            roles=["admin", "reviewer"],
            permissions=["read", "write"],
            expires_at=expires,
        )
        assert ctx.tenant_id == "beta-corp"
        assert ctx.is_admin is True
        assert "admin" in ctx.roles
        assert "read" in ctx.permissions
        assert ctx.expires_at == expires

    def test_empty_tenant_id_raises(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            TenantContext(tenant_id="")

    def test_wrong_constitutional_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            TenantContext(tenant_id="t1", constitutional_hash="badhash")


# ---------------------------------------------------------------------------
# TenantContext.is_expired
# ---------------------------------------------------------------------------


class TestIsExpired:
    def test_no_expiry_returns_false(self):
        ctx = TenantContext(tenant_id="t1")
        assert ctx.is_expired() is False

    def test_future_expiry_returns_false(self):
        ctx = TenantContext(
            tenant_id="t1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert ctx.is_expired() is False

    def test_past_expiry_returns_true(self):
        ctx = TenantContext(
            tenant_id="t1",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert ctx.is_expired() is True


# ---------------------------------------------------------------------------
# TenantContext.validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_context(self):
        ctx = TenantContext(tenant_id="t1")
        assert ctx.validate() is True

    def test_expired_context_invalid(self):
        ctx = TenantContext(
            tenant_id="t1",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert ctx.validate() is False

    def test_tampered_hash_invalid(self):
        ctx = TenantContext(tenant_id="t1")
        # Bypass __post_init__ by mutating after creation
        object.__setattr__(ctx, "constitutional_hash", "tampered")
        assert ctx.validate() is False

    def test_empty_tenant_id_after_mutation(self):
        ctx = TenantContext(tenant_id="t1")
        object.__setattr__(ctx, "tenant_id", "")
        assert ctx.validate() is False


# ---------------------------------------------------------------------------
# TenantContext.to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_no_expires(self):
        ctx = TenantContext(tenant_id="t1", user_id="u1", is_admin=True, roles=["r1"])
        d = ctx.to_dict()
        assert d["tenant_id"] == "t1"
        assert d["user_id"] == "u1"
        assert d["is_admin"] is True
        assert d["roles"] == ["r1"]
        assert d["expires_at"] is None
        assert "created_at" in d

    def test_to_dict_with_expires(self):
        expires = datetime.now(UTC) + timedelta(hours=2)
        ctx = TenantContext(tenant_id="t1", expires_at=expires)
        d = ctx.to_dict()
        assert d["expires_at"] == expires.isoformat()


# ---------------------------------------------------------------------------
# TenantContext.to_sql_params
# ---------------------------------------------------------------------------


class TestToSqlParams:
    def test_to_sql_params_no_user(self):
        ctx = TenantContext(tenant_id="t1")
        params = ctx.to_sql_params()
        assert params["app.current_tenant_id"] == "t1"
        assert params["app.constitutional_hash"] == CONSTITUTIONAL_HASH
        assert params["app.user_id"] == ""
        assert params["app.is_admin"] == "false"

    def test_to_sql_params_with_user_admin(self):
        ctx = TenantContext(tenant_id="t1", user_id="u1", is_admin=True)
        params = ctx.to_sql_params()
        assert params["app.user_id"] == "u1"
        assert params["app.is_admin"] == "true"


# ---------------------------------------------------------------------------
# TenantContext sync context manager
# ---------------------------------------------------------------------------


class TestTenantContextSyncCM:
    def test_enter_sets_context(self):
        ctx = TenantContext(tenant_id="t1")
        with ctx:
            assert get_current_tenant() is ctx
        assert get_current_tenant() is None

    def test_exit_restores_previous(self):
        outer = TenantContext(tenant_id="outer")
        inner = TenantContext(tenant_id="inner")
        with outer:
            assert get_current_tenant() is outer
            with inner:
                assert get_current_tenant() is inner
            assert get_current_tenant() is outer
        assert get_current_tenant() is None

    def test_exit_without_token_is_safe(self):
        ctx = TenantContext(tenant_id="t1")
        ctx._token = None
        ctx.__exit__(None, None, None)  # must not raise

    def test_enter_returns_self(self):
        ctx = TenantContext(tenant_id="t1")
        result = ctx.__enter__()
        ctx.__exit__(None, None, None)
        assert result is ctx


# ---------------------------------------------------------------------------
# TenantContext async context manager
# ---------------------------------------------------------------------------


class TestTenantContextAsyncCM:
    async def test_aenter_sets_context(self):
        ctx = TenantContext(tenant_id="async-t1")
        async with ctx:
            assert get_current_tenant() is ctx
        assert get_current_tenant() is None

    async def test_aexit_restores_previous(self):
        outer = TenantContext(tenant_id="async-outer")
        inner = TenantContext(tenant_id="async-inner")
        async with outer:
            async with inner:
                assert get_current_tenant() is inner
            assert get_current_tenant() is outer
        assert get_current_tenant() is None

    async def test_aenter_returns_self(self):
        ctx = TenantContext(tenant_id="async-t2")
        result = await ctx.__aenter__()
        await ctx.__aexit__(None, None, None)
        assert result is ctx

    async def test_aexit_propagates_exception(self):
        ctx = TenantContext(tenant_id="async-t3")
        with pytest.raises(ValueError):
            async with ctx:
                raise ValueError("boom")
        # context must be cleared even after exception
        assert get_current_tenant() is None


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


class TestGetCurrentTenant:
    def setup_method(self):
        clear_tenant_context()

    def test_returns_none_when_unset(self):
        assert get_current_tenant() is None

    def test_returns_set_context(self):
        ctx = TenantContext(tenant_id="t1")
        token = set_current_tenant(ctx)
        try:
            assert get_current_tenant() is ctx
        finally:
            from enhanced_agent_bus.multi_tenancy.context import _tenant_context

            _tenant_context.reset(token)


class TestGetCurrentTenantId:
    def setup_method(self):
        clear_tenant_context()

    def test_returns_none_when_unset(self):
        assert get_current_tenant_id() is None

    def test_returns_tenant_id_when_set(self):
        ctx = TenantContext(tenant_id="gamma-inc")
        with ctx:
            assert get_current_tenant_id() == "gamma-inc"


class TestRequireTenantContext:
    def setup_method(self):
        clear_tenant_context()

    def test_raises_when_not_set(self):
        with pytest.raises(RuntimeError, match="No tenant context set"):
            require_tenant_context()

    def test_returns_valid_context(self):
        ctx = TenantContext(tenant_id="valid-tenant")
        with ctx:
            result = require_tenant_context()
            assert result is ctx

    def test_raises_on_expired_context(self):
        ctx = TenantContext(
            tenant_id="expired-tenant",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with ctx:
            with pytest.raises(RuntimeError, match="Invalid or expired"):
                require_tenant_context()


class TestSetCurrentTenant:
    def setup_method(self):
        clear_tenant_context()

    def test_set_and_returns_token(self):
        ctx = TenantContext(tenant_id="t1")
        token = set_current_tenant(ctx)
        assert isinstance(token, Token)
        assert get_current_tenant() is ctx
        from enhanced_agent_bus.multi_tenancy.context import _tenant_context

        _tenant_context.reset(token)


class TestClearTenantContext:
    def test_clears_set_context(self):
        ctx = TenantContext(tenant_id="t1")
        set_current_tenant(ctx)
        assert get_current_tenant() is not None
        clear_tenant_context()
        assert get_current_tenant() is None

    def test_clear_when_already_none(self):
        clear_tenant_context()
        clear_tenant_context()  # must not raise


# ---------------------------------------------------------------------------
# tenant_context class (context manager façade)
# ---------------------------------------------------------------------------


class TestTenantContextClass:
    def setup_method(self):
        clear_tenant_context()

    def test_basic_sync_usage(self):
        with tenant_context(tenant_id="tc-basic") as ctx:
            assert ctx.tenant_id == "tc-basic"
            assert get_current_tenant() is ctx
        assert get_current_tenant() is None

    def test_full_params(self):
        expires = datetime.now(UTC) + timedelta(hours=1)
        with tenant_context(
            tenant_id="tc-full",
            user_id="u2",
            session_id="s2",
            request_id="r2",
            is_admin=True,
            roles=["admin"],
            permissions=["write"],
            expires_at=expires,
        ) as ctx:
            assert ctx.user_id == "u2"
            assert ctx.is_admin is True
            assert ctx.expires_at == expires

    def test_nested_sync_usage(self):
        with tenant_context(tenant_id="outer") as outer:
            with tenant_context(tenant_id="inner") as inner:
                assert get_current_tenant() is inner
            assert get_current_tenant() is outer
        assert get_current_tenant() is None

    def test_exit_without_token(self):
        tc = tenant_context(tenant_id="tc-no-token")
        tc._token = None
        tc.__exit__(None, None, None)  # must not raise

    def test_exit_restores_on_exception(self):
        with pytest.raises(RuntimeError):
            with tenant_context(tenant_id="tc-exc"):
                raise RuntimeError("test error")
        assert get_current_tenant() is None

    async def test_async_usage(self):
        async with tenant_context(tenant_id="async-tc") as ctx:
            assert ctx.tenant_id == "async-tc"
            assert get_current_tenant() is ctx
        assert get_current_tenant() is None

    async def test_async_nested(self):
        async with tenant_context(tenant_id="async-outer") as outer:
            async with tenant_context(tenant_id="async-inner") as inner:
                assert get_current_tenant() is inner
            assert get_current_tenant() is outer
        assert get_current_tenant() is None

    async def test_async_exit_on_exception(self):
        with pytest.raises(ValueError):
            async with tenant_context(tenant_id="async-exc"):
                raise ValueError("async boom")
        assert get_current_tenant() is None

    def test_default_roles_permissions_empty(self):
        with tenant_context(tenant_id="defaults") as ctx:
            assert ctx.roles == []
            assert ctx.permissions == []

    def test_explicit_roles_permissions(self):
        with tenant_context(
            tenant_id="roles-test",
            roles=["viewer"],
            permissions=["read"],
        ) as ctx:
            assert ctx.roles == ["viewer"]
            assert ctx.permissions == ["read"]


# ---------------------------------------------------------------------------
# Isolation across different context vars tasks
# ---------------------------------------------------------------------------


class TestIsolation:
    def setup_method(self):
        clear_tenant_context()

    async def test_isolation_across_tasks(self):
        """Tenant context should be isolated per asyncio task."""
        import asyncio

        results: list = []

        async def task_a():
            async with tenant_context(tenant_id="tenant-a"):
                await asyncio.sleep(0)
                results.append(get_current_tenant_id())

        async def task_b():
            async with tenant_context(tenant_id="tenant-b"):
                await asyncio.sleep(0)
                results.append(get_current_tenant_id())

        await asyncio.gather(task_a(), task_b())
        assert set(results) == {"tenant-a", "tenant-b"}

    def test_sync_no_leakage(self):
        with tenant_context(tenant_id="inner-scope"):
            pass
        assert get_current_tenant() is None
