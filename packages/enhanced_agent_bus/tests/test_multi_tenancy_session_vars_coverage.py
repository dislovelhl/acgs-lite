# Constitutional Hash: 608508a9bd224290
# Sprint 61 — multi_tenancy/session_vars.py coverage
"""
Comprehensive coverage tests for multi_tenancy/session_vars.py.

Exercises every function, branch, and module-level constant to achieve ≥95%
line/branch coverage. All SQLAlchemy async I/O is mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> MagicMock:
    """Return a mock AsyncSession whose execute() is an AsyncMock."""
    session = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_session_with_scalar(value) -> MagicMock:
    """Return a mock AsyncSession where execute returns a result with scalar()."""
    session = MagicMock()
    result = MagicMock()
    result.scalar.return_value = value
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Verify constants are the expected PostgreSQL variable names."""

    def test_session_var_tenant_id(self):
        assert SESSION_VAR_TENANT_ID == "app.current_tenant_id"

    def test_session_var_is_admin(self):
        assert SESSION_VAR_IS_ADMIN == "app.is_admin"


# ---------------------------------------------------------------------------
# set_tenant_session_vars
# ---------------------------------------------------------------------------


class TestSetTenantSessionVars:
    """Tests for set_tenant_session_vars()."""

    async def test_sets_tenant_id(self):
        session = _make_session()
        await set_tenant_session_vars(session, tenant_id="tenant-abc")
        # First call should be for tenant_id
        first_call = session.execute.call_args_list[0]
        assert "tenant_id" in str(first_call)

    async def test_sets_is_admin_false_by_default(self):
        session = _make_session()
        await set_tenant_session_vars(session, tenant_id="t1")
        # Two execute calls expected
        assert session.execute.call_count == 2
        second_call_kwargs = session.execute.call_args_list[1]
        # The second positional arg dict should contain "false"
        assert "false" in str(second_call_kwargs)

    async def test_sets_is_admin_true_when_passed(self):
        session = _make_session()
        await set_tenant_session_vars(session, tenant_id="t1", is_admin=True)
        assert session.execute.call_count == 2
        second_call_kwargs = session.execute.call_args_list[1]
        assert "true" in str(second_call_kwargs)

    async def test_is_admin_false_branch(self):
        """Explicitly test the is_admin=False branch (admin_value = 'false')."""
        session = _make_session()
        await set_tenant_session_vars(session, tenant_id="any", is_admin=False)
        second_call = session.execute.call_args_list[1]
        assert "false" in str(second_call)

    async def test_execute_called_twice(self):
        session = _make_session()
        await set_tenant_session_vars(session, tenant_id="x", is_admin=True)
        assert session.execute.call_count == 2

    async def test_logs_debug(self):
        session = _make_session()
        with patch("enhanced_agent_bus.multi_tenancy.session_vars.logger") as mock_logger:
            await set_tenant_session_vars(session, tenant_id="log-test", is_admin=False)
            mock_logger.debug.assert_called_once()
            call_str = str(mock_logger.debug.call_args)
            assert "log-test" in call_str

    async def test_admin_logged(self):
        session = _make_session()
        with patch("enhanced_agent_bus.multi_tenancy.session_vars.logger") as mock_logger:
            await set_tenant_session_vars(session, tenant_id="t", is_admin=True)
            call_str = str(mock_logger.debug.call_args)
            assert "True" in call_str or "true" in call_str.lower()


# ---------------------------------------------------------------------------
# clear_tenant_session_vars
# ---------------------------------------------------------------------------


class TestClearTenantSessionVars:
    """Tests for clear_tenant_session_vars()."""

    async def test_executes_twice(self):
        session = _make_session()
        await clear_tenant_session_vars(session)
        assert session.execute.call_count == 2

    async def test_resets_tenant_id_var(self):
        session = _make_session()
        await clear_tenant_session_vars(session)
        first_arg = session.execute.call_args_list[0].args[0]
        assert SESSION_VAR_TENANT_ID in str(first_arg)

    async def test_resets_is_admin_var(self):
        session = _make_session()
        await clear_tenant_session_vars(session)
        second_arg = session.execute.call_args_list[1].args[0]
        assert SESSION_VAR_IS_ADMIN in str(second_arg)

    async def test_logs_debug(self):
        session = _make_session()
        with patch("enhanced_agent_bus.multi_tenancy.session_vars.logger") as mock_logger:
            await clear_tenant_session_vars(session)
            mock_logger.debug.assert_called_once()


# ---------------------------------------------------------------------------
# get_current_tenant_from_session
# ---------------------------------------------------------------------------


class TestGetCurrentTenantFromSession:
    """Tests for get_current_tenant_from_session()."""

    async def test_returns_tenant_id_when_set(self):
        session = _make_session_with_scalar("tenant-xyz")
        result = await get_current_tenant_from_session(session)
        assert result == "tenant-xyz"

    async def test_returns_none_when_empty_string(self):
        session = _make_session_with_scalar("")
        result = await get_current_tenant_from_session(session)
        assert result is None

    async def test_returns_none_when_scalar_is_none(self):
        session = _make_session_with_scalar(None)
        result = await get_current_tenant_from_session(session)
        assert result is None

    async def test_executes_select_statement(self):
        session = _make_session_with_scalar("t")
        await get_current_tenant_from_session(session)
        assert session.execute.call_count == 1
        first_arg = session.execute.call_args.args[0]
        assert SESSION_VAR_TENANT_ID in str(first_arg)


# ---------------------------------------------------------------------------
# get_is_admin_from_session
# ---------------------------------------------------------------------------


class TestGetIsAdminFromSession:
    """Tests for get_is_admin_from_session()."""

    async def test_returns_true_when_value_is_true_string(self):
        session = _make_session_with_scalar("true")
        result = await get_is_admin_from_session(session)
        assert result is True

    async def test_returns_false_when_value_is_false_string(self):
        session = _make_session_with_scalar("false")
        result = await get_is_admin_from_session(session)
        assert result is False

    async def test_returns_false_when_value_is_none(self):
        session = _make_session_with_scalar(None)
        result = await get_is_admin_from_session(session)
        assert result is False

    async def test_returns_false_when_value_is_empty_string(self):
        session = _make_session_with_scalar("")
        result = await get_is_admin_from_session(session)
        assert result is False

    async def test_executes_select_statement(self):
        session = _make_session_with_scalar("false")
        await get_is_admin_from_session(session)
        assert session.execute.call_count == 1
        first_arg = session.execute.call_args.args[0]
        assert SESSION_VAR_IS_ADMIN in str(first_arg)


# ---------------------------------------------------------------------------
# tenant_session context manager
# ---------------------------------------------------------------------------


class TestTenantSession:
    """Tests for the tenant_session() async context manager."""

    async def test_yields_same_session(self):
        session = _make_session()
        async with tenant_session(session, tenant_id="t1") as s:
            assert s is session

    async def test_sets_vars_before_yield(self):
        session = _make_session()
        call_counts_inside = {}
        async with tenant_session(session, tenant_id="t1"):
            call_counts_inside["execute"] = session.execute.call_count
        # Inside the context, set_tenant_session_vars was already called (2 executes)
        assert call_counts_inside["execute"] == 2

    async def test_clears_vars_after_yield(self):
        session = _make_session()
        async with tenant_session(session, tenant_id="t1"):
            pass
        # set (2) + clear (2) = 4
        assert session.execute.call_count == 4

    async def test_clears_vars_on_exception(self):
        """clear_tenant_session_vars must be called even when body raises."""
        session = _make_session()
        with pytest.raises(ValueError):
            async with tenant_session(session, tenant_id="t1"):
                raise ValueError("test error")
        # set (2) + clear (2) = 4
        assert session.execute.call_count == 4

    async def test_passes_is_admin(self):
        session = _make_session()
        async with tenant_session(session, tenant_id="t1", is_admin=True):
            pass
        # second call should carry "true"
        second_call = str(session.execute.call_args_list[1])
        assert "true" in second_call

    async def test_default_is_admin_false(self):
        session = _make_session()
        async with tenant_session(session, tenant_id="t1"):
            pass
        second_call = str(session.execute.call_args_list[1])
        assert "false" in second_call


# ---------------------------------------------------------------------------
# system_tenant_session context manager
# ---------------------------------------------------------------------------


class TestSystemTenantSession:
    """Tests for system_tenant_session()."""

    async def test_yields_session(self):
        session = _make_session()
        async with system_tenant_session(session) as s:
            assert s is session

    async def test_uses_system_tenant_id(self):
        session = _make_session()
        async with system_tenant_session(session):
            pass
        first_call = str(session.execute.call_args_list[0])
        assert SYSTEM_TENANT_ID in first_call

    async def test_default_is_admin_false(self):
        session = _make_session()
        async with system_tenant_session(session):
            pass
        second_call = str(session.execute.call_args_list[1])
        assert "false" in second_call

    async def test_is_admin_true_propagated(self):
        session = _make_session()
        async with system_tenant_session(session, is_admin=True):
            pass
        second_call = str(session.execute.call_args_list[1])
        assert "true" in second_call

    async def test_clears_vars_on_exit(self):
        session = _make_session()
        async with system_tenant_session(session):
            pass
        assert session.execute.call_count == 4  # set + clear

    async def test_clears_vars_on_exception(self):
        session = _make_session()
        with pytest.raises(RuntimeError):
            async with system_tenant_session(session):
                raise RuntimeError("boom")
        assert session.execute.call_count == 4


# ---------------------------------------------------------------------------
# admin_session context manager
# ---------------------------------------------------------------------------


class TestAdminSession:
    """Tests for admin_session()."""

    async def test_yields_session(self):
        session = _make_session()
        async with admin_session(session) as s:
            assert s is session

    async def test_uses_system_tenant_when_no_tenant_id(self):
        session = _make_session()
        async with admin_session(session):
            pass
        first_call = str(session.execute.call_args_list[0])
        assert SYSTEM_TENANT_ID in first_call

    async def test_uses_provided_tenant_id(self):
        session = _make_session()
        async with admin_session(session, tenant_id="custom-tenant"):
            pass
        first_call = str(session.execute.call_args_list[0])
        assert "custom-tenant" in first_call

    async def test_always_sets_is_admin_true(self):
        session = _make_session()
        async with admin_session(session):
            pass
        second_call = str(session.execute.call_args_list[1])
        assert "true" in second_call

    async def test_admin_true_with_explicit_tenant(self):
        session = _make_session()
        async with admin_session(session, tenant_id="t-explicit"):
            pass
        second_call = str(session.execute.call_args_list[1])
        assert "true" in second_call

    async def test_clears_vars_on_exit(self):
        session = _make_session()
        async with admin_session(session):
            pass
        assert session.execute.call_count == 4

    async def test_clears_vars_on_exception(self):
        session = _make_session()
        with pytest.raises(KeyError):
            async with admin_session(session):
                raise KeyError("oops")
        assert session.execute.call_count == 4

    async def test_none_tenant_id_falls_back_to_system_tenant(self):
        """Explicit None should behave the same as omitting tenant_id."""
        session = _make_session()
        async with admin_session(session, tenant_id=None):
            pass
        first_call = str(session.execute.call_args_list[0])
        assert SYSTEM_TENANT_ID in first_call


# ---------------------------------------------------------------------------
# set_tenant_for_request
# ---------------------------------------------------------------------------


class TestSetTenantForRequest:
    """Tests for set_tenant_for_request()."""

    async def test_sets_explicit_tenant_id(self):
        session = _make_session()
        await set_tenant_for_request(session, tenant_id="req-tenant")
        first_call = str(session.execute.call_args_list[0])
        assert "req-tenant" in first_call

    async def test_falls_back_to_system_tenant_when_none(self):
        session = _make_session()
        await set_tenant_for_request(session, tenant_id=None)
        first_call = str(session.execute.call_args_list[0])
        assert SYSTEM_TENANT_ID in first_call

    async def test_default_is_admin_false(self):
        session = _make_session()
        await set_tenant_for_request(session, tenant_id="t")
        second_call = str(session.execute.call_args_list[1])
        assert "false" in second_call

    async def test_is_admin_true_propagated(self):
        session = _make_session()
        await set_tenant_for_request(session, tenant_id="t", is_admin=True)
        second_call = str(session.execute.call_args_list[1])
        assert "true" in second_call

    async def test_execute_called_twice(self):
        session = _make_session()
        await set_tenant_for_request(session, tenant_id="t")
        assert session.execute.call_count == 2

    async def test_none_tenant_with_is_admin_true(self):
        """None tenant_id + is_admin=True should use system tenant with admin."""
        session = _make_session()
        await set_tenant_for_request(session, tenant_id=None, is_admin=True)
        first_call = str(session.execute.call_args_list[0])
        second_call = str(session.execute.call_args_list[1])
        assert SYSTEM_TENANT_ID in first_call
        assert "true" in second_call


# ---------------------------------------------------------------------------
# __all__ export check
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify __all__ declares the expected public names."""

    def test_all_contains_expected_exports(self):
        from enhanced_agent_bus.multi_tenancy import session_vars

        expected = {
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
            "CONSTITUTIONAL_HASH",
        }
        assert expected.issubset(set(session_vars.__all__))
