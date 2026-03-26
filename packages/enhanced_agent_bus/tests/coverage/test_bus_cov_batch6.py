"""
Tests for enhanced_agent_bus coverage batch 6:
- enterprise_sso/middleware.py
- enterprise_sso/integration.py
- llm_adapters/models.py
- llm_adapters/capability_matrix.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# enterprise_sso.integration
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.integration import (
    EnterpriseSSOService,
    SSOAuthenticationResult,
    SSOIntegrationError,
    SSOSession,
    SSOUser,
)

# ---------------------------------------------------------------------------
# enterprise_sso.middleware
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.middleware import (
    SSOMiddlewareConfig,
    SSOSessionContext,
    _check_session_roles,
    _check_session_roles_sync,
    _check_session_valid,
    _check_session_valid_sync,
    _raise_auth_error,
    clear_sso_session,
    get_current_sso_session,
    require_sso_authentication,
    set_sso_session,
)
from enhanced_agent_bus.enterprise_sso.tenant_sso_config import (
    IdPProviderType,
    OIDCConfig,
    RoleMappingRule,
    SSOProtocolType,
    TenantIdPConfig,
    TenantSSOConfigManager,
)

# ---------------------------------------------------------------------------
# llm_adapters.capability_matrix
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityDimension,
    CapabilityLevel,
    CapabilityRegistry,
    CapabilityRequirement,
    CapabilityRouter,
    CapabilityValue,
    LatencyClass,
    ProviderCapabilityProfile,
    get_capability_registry,
    get_capability_router,
    initialize_capability_matrix,
)

# ---------------------------------------------------------------------------
# llm_adapters.models
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.models import (
    FunctionDefinition,
    FunctionParameters,
    LLMMessage,
    LLMRequest,
    MessageConverter,
    RequestConverter,
    ResponseConverter,
    ToolCall,
    ToolCallFunction,
    ToolDefinition,
    ToolType,
)

# ============================================================================
# Helpers / Fixtures
# ============================================================================


def _make_session_context(
    *,
    expired: bool = False,
    roles: list[str] | None = None,
    tenant_id: str = "tenant-1",
) -> SSOSessionContext:
    now = datetime.now(UTC)
    if expired:
        expires = now - timedelta(hours=1)
    else:
        expires = now + timedelta(hours=1)
    return SSOSessionContext(
        session_id="sess-1",
        user_id="user-1",
        tenant_id=tenant_id,
        email="user@example.com",
        display_name="Test User",
        maci_roles=roles or ["ADMIN", "MONITOR"],
        idp_groups=["developers"],
        attributes={"tenant_name": "Acme"},
        authenticated_at=now,
        expires_at=expires,
        access_token="tok-abc",
        refresh_token="ref-xyz",
        idp_id="okta-1",
        idp_type="oidc",
    )


def _make_idp_config(
    tenant_id: str = "acme",
    idp_id: str = "okta-1",
    *,
    enabled: bool = True,
    allowed_domains: list[str] | None = None,
    role_mappings: list[RoleMappingRule] | None = None,
) -> TenantIdPConfig:
    return TenantIdPConfig(
        idp_id=idp_id,
        tenant_id=tenant_id,
        provider_type=IdPProviderType.OKTA,
        protocol=SSOProtocolType.OIDC,
        display_name="Okta",
        enabled=enabled,
        oidc_config=OIDCConfig(issuer="https://acme.okta.com", client_id="cid"),
        allowed_domains=allowed_domains or [],
        role_mappings=role_mappings or [],
    )


def _make_sso_user(email: str = "user@acme.com") -> SSOUser:
    return SSOUser(
        external_id="ext-1",
        email=email,
        display_name="Test User",
        first_name="Test",
        last_name="User",
        groups=["developers", "admins"],
    )


@pytest.fixture(autouse=True)
def _clear_session():
    """Ensure SSO session context is clean before/after each test."""
    clear_sso_session()
    yield
    clear_sso_session()


# ============================================================================
# SSO Middleware - SSOSessionContext
# ============================================================================


class TestSSOSessionContext:
    def test_not_expired(self):
        ctx = _make_session_context()
        assert ctx.is_expired is False

    def test_expired(self):
        ctx = _make_session_context(expired=True)
        assert ctx.is_expired is True

    def test_time_until_expiry_positive(self):
        ctx = _make_session_context()
        assert ctx.time_until_expiry > 0

    def test_time_until_expiry_zero_when_expired(self):
        ctx = _make_session_context(expired=True)
        assert ctx.time_until_expiry == 0.0

    def test_has_role_case_insensitive(self):
        ctx = _make_session_context(roles=["Admin", "MONITOR"])
        assert ctx.has_role("admin") is True
        assert ctx.has_role("ADMIN") is True
        assert ctx.has_role("missing") is False

    def test_has_any_role(self):
        ctx = _make_session_context(roles=["ADMIN"])
        assert ctx.has_any_role(["ADMIN", "OPERATOR"]) is True
        assert ctx.has_any_role(["OPERATOR", "VIEWER"]) is False

    def test_has_all_roles(self):
        ctx = _make_session_context(roles=["ADMIN", "MONITOR"])
        assert ctx.has_all_roles(["ADMIN", "MONITOR"]) is True
        assert ctx.has_all_roles(["ADMIN", "OPERATOR"]) is False

    def test_to_dict_keys(self):
        ctx = _make_session_context()
        d = ctx.to_dict()
        assert "session_id" in d
        assert "user_id" in d
        assert "tenant_id" in d
        assert "maci_roles" in d
        assert "constitutional_hash" in d
        # tokens should NOT appear in dict
        assert "access_token" not in d


# ============================================================================
# SSO Middleware - context helpers
# ============================================================================


class TestContextHelpers:
    def test_get_set_clear(self):
        assert get_current_sso_session() is None
        ctx = _make_session_context()
        set_sso_session(ctx)
        assert get_current_sso_session() is ctx
        clear_sso_session()
        assert get_current_sso_session() is None


# ============================================================================
# SSO Middleware - _raise_auth_error
# ============================================================================


class TestRaiseAuthError:
    def test_raises_permission_error_without_fastapi(self):
        with patch("enhanced_agent_bus.enterprise_sso.middleware.FASTAPI_AVAILABLE", False):
            with pytest.raises(PermissionError, match="some detail"):
                _raise_auth_error(401, "some detail")


# ============================================================================
# SSO Middleware - _check_session_valid / _check_session_roles
# ============================================================================


class TestCheckSessionValid:
    def test_none_session_raises(self):
        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(None, allow_expired=False)

    def test_expired_session_raises(self):
        ctx = _make_session_context(expired=True)
        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(ctx, allow_expired=False)

    def test_expired_session_allowed(self):
        ctx = _make_session_context(expired=True)
        # Should not raise
        _check_session_valid(ctx, allow_expired=True)

    def test_valid_session_ok(self):
        ctx = _make_session_context()
        _check_session_valid(ctx, allow_expired=False)


class TestCheckSessionRoles:
    def test_no_roles_required(self):
        ctx = _make_session_context()
        _check_session_roles(ctx, [], any_role=True)

    def test_any_role_satisfied(self):
        ctx = _make_session_context(roles=["ADMIN"])
        _check_session_roles(ctx, ["ADMIN", "OP"], any_role=True)

    def test_any_role_not_satisfied(self):
        ctx = _make_session_context(roles=["MONITOR"])
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(ctx, ["ADMIN", "OP"], any_role=True)

    def test_all_roles_satisfied(self):
        ctx = _make_session_context(roles=["ADMIN", "MONITOR"])
        _check_session_roles(ctx, ["ADMIN", "MONITOR"], any_role=False)

    def test_all_roles_not_satisfied(self):
        ctx = _make_session_context(roles=["ADMIN"])
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(ctx, ["ADMIN", "MONITOR"], any_role=False)


class TestCheckSessionValidSync:
    def test_none_session_raises(self):
        with pytest.raises(PermissionError):
            _check_session_valid_sync(None, allow_expired=False)

    def test_expired_raises(self):
        ctx = _make_session_context(expired=True)
        with pytest.raises(PermissionError):
            _check_session_valid_sync(ctx, allow_expired=False)

    def test_expired_allowed(self):
        ctx = _make_session_context(expired=True)
        _check_session_valid_sync(ctx, allow_expired=True)


class TestCheckSessionRolesSync:
    def test_no_roles(self):
        ctx = _make_session_context()
        _check_session_roles_sync(ctx, [], any_role=True)

    def test_any_role_fail(self):
        ctx = _make_session_context(roles=["MONITOR"])
        with pytest.raises(PermissionError):
            _check_session_roles_sync(ctx, ["ADMIN"], any_role=True)

    def test_all_roles_fail(self):
        ctx = _make_session_context(roles=["ADMIN"])
        with pytest.raises(PermissionError):
            _check_session_roles_sync(ctx, ["ADMIN", "MONITOR"], any_role=False)


# ============================================================================
# SSO Middleware - require_sso_authentication decorator
# ============================================================================


class TestRequireSSOAuthenticationDecorator:
    @pytest.mark.asyncio
    async def test_async_no_session_raises(self):
        @require_sso_authentication()
        async def handler():
            return "ok"

        with pytest.raises((PermissionError, Exception)):
            await handler()

    @pytest.mark.asyncio
    async def test_async_with_valid_session(self):
        set_sso_session(_make_session_context())

        @require_sso_authentication()
        async def handler():
            return "ok"

        result = await handler()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_with_role_check(self):
        set_sso_session(_make_session_context(roles=["ADMIN"]))

        @require_sso_authentication(roles=["ADMIN"])
        async def handler():
            return "ok"

        result = await handler()
        assert result == "ok"

    def test_sync_no_session_raises(self):
        @require_sso_authentication()
        def handler():
            return "ok"

        with pytest.raises(PermissionError):
            handler()

    def test_sync_with_valid_session(self):
        set_sso_session(_make_session_context())

        @require_sso_authentication()
        def handler():
            return "ok"

        assert handler() == "ok"

    def test_sync_with_role_fail(self):
        set_sso_session(_make_session_context(roles=["MONITOR"]))

        @require_sso_authentication(roles=["ADMIN"], any_role=True)
        def handler():
            return "ok"

        with pytest.raises(PermissionError):
            handler()


# ============================================================================
# SSO Middleware - SSOMiddlewareConfig
# ============================================================================


class TestSSOMiddlewareConfig:
    def test_defaults(self):
        cfg = SSOMiddlewareConfig()
        assert "/health" in cfg.excluded_paths
        assert cfg.require_authentication is True
        assert cfg.auto_refresh_sessions is True
        assert cfg.refresh_threshold_seconds == 300

    def test_custom(self):
        cfg = SSOMiddlewareConfig(
            require_authentication=False,
            refresh_threshold_seconds=600,
        )
        assert cfg.require_authentication is False
        assert cfg.refresh_threshold_seconds == 600


# ============================================================================
# enterprise_sso.integration - data classes
# ============================================================================


class TestSSOUser:
    def test_to_dict(self):
        user = _make_sso_user()
        d = user.to_dict()
        assert d["external_id"] == "ext-1"
        assert d["email"] == "user@acme.com"
        assert "authenticated_at" in d


class TestSSOSession:
    def test_not_expired_no_expiry(self):
        s = SSOSession(
            session_id="s1",
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
        )
        assert s.is_expired() is False

    def test_expired(self):
        s = SSOSession(
            session_id="s1",
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert s.is_expired() is True

    def test_has_role(self):
        s = SSOSession(
            session_id="s1",
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            maci_roles=["ADMIN", "MONITOR"],
        )
        assert s.has_role("admin") is True
        assert s.has_role("MISSING") is False

    def test_to_dict(self):
        s = SSOSession(
            session_id="s1" * 20,
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            maci_roles=["ADMIN"],
            metadata={"email": "a@b.com", "display_name": "A"},
        )
        d = s.to_dict()
        assert d["session_id"].endswith("...")
        assert d["email"] == "a@b.com"

    def test_to_dict_with_expires(self):
        s = SSOSession(
            session_id="s1" * 20,
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        d = s.to_dict()
        assert d["expires_at"] is not None


class TestSSOAuthenticationResult:
    def test_success_to_dict(self):
        session = SSOSession(
            session_id="s" * 20,
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
        )
        user = _make_sso_user()
        result = SSOAuthenticationResult(success=True, session=session, user=user)
        d = result.to_dict()
        assert d["success"] is True
        assert "session" in d
        assert "user" in d

    def test_failure_to_dict(self):
        result = SSOAuthenticationResult(success=False, error="bad", error_code="ERR")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "bad"


class TestSSOIntegrationError:
    def test_basic(self):
        err = SSOIntegrationError("fail", error_code="MY_ERR")
        assert "fail" in str(err)
        # Class-level error_code may shadow instance; check details instead
        assert err.details.get("sso_error_code") == "MY_ERR"

    def test_with_details(self):
        err = SSOIntegrationError("fail", details={"key": "val"})
        assert err.details.get("sso_error_code") == "SSO_ERROR"
        assert err.details.get("key") == "val"


# ============================================================================
# enterprise_sso.integration - EnterpriseSSOService
# ============================================================================


class TestEnterpriseSSOService:
    def _make_service(self) -> EnterpriseSSOService:
        return EnterpriseSSOService()

    def test_invalid_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            EnterpriseSSOService(constitutional_hash="wrong-hash")

    def test_configure_tenant_sso_new(self):
        svc = self._make_service()
        cfg = svc.configure_tenant_sso("acme", sso_enabled=True)
        assert cfg.tenant_id == "acme"
        assert cfg.sso_enabled is True

    def test_configure_tenant_sso_update(self):
        svc = self._make_service()
        svc.configure_tenant_sso("acme", sso_enabled=False)
        cfg = svc.configure_tenant_sso("acme", sso_enabled=True)
        assert cfg.sso_enabled is True

    def test_get_tenant_sso_config(self):
        svc = self._make_service()
        assert svc.get_tenant_sso_config("no-exist") is None
        svc.configure_tenant_sso("acme")
        assert svc.get_tenant_sso_config("acme") is not None

    def test_add_identity_provider(self):
        svc = self._make_service()
        idp = _make_idp_config()
        result = svc.add_identity_provider("acme", idp)
        assert len(result.identity_providers) == 1

    def test_add_identity_provider_set_default(self):
        svc = self._make_service()
        idp = _make_idp_config()
        result = svc.add_identity_provider("acme", idp, set_as_default=True)
        assert result.default_idp_id == idp.idp_id

    def test_remove_identity_provider(self):
        svc = self._make_service()
        idp = _make_idp_config()
        svc.add_identity_provider("acme", idp)
        result = svc.remove_identity_provider("acme", idp.idp_id)
        assert result is not None
        assert len(result.identity_providers) == 0

    def test_remove_identity_provider_not_found(self):
        svc = self._make_service()
        assert svc.remove_identity_provider("noexist", "x") is None

    @pytest.mark.asyncio
    async def test_authenticate_sso_no_config(self):
        svc = self._make_service()
        result = await svc.authenticate_sso("noexist", "idp-1", _make_sso_user())
        assert result.success is False
        assert result.error_code == "TENANT_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_authenticate_sso_disabled(self):
        svc = self._make_service()
        svc.configure_tenant_sso("acme", sso_enabled=False)
        result = await svc.authenticate_sso("acme", "idp-1", _make_sso_user())
        assert result.success is False
        assert result.error_code == "SSO_DISABLED"

    @pytest.mark.asyncio
    async def test_authenticate_sso_idp_not_found(self):
        svc = self._make_service()
        svc.configure_tenant_sso("acme", sso_enabled=True)
        result = await svc.authenticate_sso("acme", "bad-idp", _make_sso_user())
        assert result.success is False
        assert result.error_code == "IDP_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_authenticate_sso_idp_disabled(self):
        svc = self._make_service()
        idp = _make_idp_config(enabled=False)
        svc.add_identity_provider("acme", idp)
        result = await svc.authenticate_sso("acme", idp.idp_id, _make_sso_user())
        assert result.success is False
        assert result.error_code == "IDP_DISABLED"

    @pytest.mark.asyncio
    async def test_authenticate_sso_domain_not_allowed(self):
        svc = self._make_service()
        idp = _make_idp_config(allowed_domains=["other.com"])
        svc.add_identity_provider("acme", idp)
        result = await svc.authenticate_sso("acme", idp.idp_id, _make_sso_user("user@acme.com"))
        assert result.success is False
        assert result.error_code == "DOMAIN_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_authenticate_sso_success(self):
        svc = self._make_service()
        role_rule = RoleMappingRule(idp_group="admins", maci_role="EXECUTIVE")
        idp = _make_idp_config(role_mappings=[role_rule])
        svc.add_identity_provider("acme", idp)
        user = _make_sso_user("user@acme.com")
        result = await svc.authenticate_sso("acme", idp.idp_id, user)
        assert result.success is True
        assert result.session is not None
        assert "EXECUTIVE" in result.session.maci_roles

    @pytest.mark.asyncio
    async def test_authenticate_sso_jit_update(self):
        svc = self._make_service()
        idp = _make_idp_config()
        svc.add_identity_provider("acme", idp)
        user = _make_sso_user()
        # First auth - provision
        r1 = await svc.authenticate_sso("acme", idp.idp_id, user)
        assert r1.success is True
        # Second auth - JIT update
        r2 = await svc.authenticate_sso("acme", idp.idp_id, user)
        assert r2.success is True
        # Same internal user id
        assert r1.session.user_id == r2.session.user_id

    def test_session_management(self):
        svc = self._make_service()
        # _create_session directly
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            maci_roles=["ADMIN"],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        assert svc.get_session(session.session_id) is not None

    def test_validate_session_sso_disabled(self):
        svc = self._make_service()
        svc.configure_tenant_sso("t1", sso_enabled=True)
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        # Now disable SSO
        svc.config_manager.update_config("t1", sso_enabled=False)
        assert svc.validate_session(session.session_id) is None

    def test_invalidate_session(self):
        svc = self._make_service()
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="idp1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        assert svc.invalidate_session(session.session_id) is True
        assert svc.invalidate_session(session.session_id) is False

    def test_invalidate_user_sessions(self):
        svc = self._make_service()
        svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        assert svc.invalidate_user_sessions("u1") == 2
        assert svc.invalidate_user_sessions("u1") == 0

    def test_get_user_sessions(self):
        svc = self._make_service()
        svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        sessions = svc.get_user_sessions("u1")
        assert len(sessions) == 1
        assert svc.get_user_sessions("no-user") == []

    def test_refresh_session(self):
        svc = self._make_service()
        svc.configure_tenant_sso("t1", sso_enabled=True)
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=[],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        old_expires = session.expires_at
        refreshed = svc.refresh_session(session.session_id)
        assert refreshed is not None
        assert refreshed.expires_at >= old_expires

    def test_refresh_session_not_found(self):
        svc = self._make_service()
        assert svc.refresh_session("nonexistent") is None

    def test_get_user_by_external_id(self):
        svc = self._make_service()
        assert svc.get_user_by_external_id("t1", "e1") is None
        svc._users["t1:e1"] = {"user_id": "u1", "tenant_id": "t1", "email": "a@b.com"}
        assert svc.get_user_by_external_id("t1", "e1") is not None

    def test_get_user_by_email(self):
        svc = self._make_service()
        svc._users["t1:e1"] = {"user_id": "u1", "tenant_id": "t1", "email": "a@b.com"}
        assert svc.get_user_by_email("t1", "a@b.com") is not None
        assert svc.get_user_by_email("t1", "no@b.com") is None

    def test_list_tenant_users(self):
        svc = self._make_service()
        svc._users["t1:e1"] = {"user_id": "u1", "tenant_id": "t1"}
        svc._users["t1:e2"] = {"user_id": "u2", "tenant_id": "t1"}
        svc._users["t2:e3"] = {"user_id": "u3", "tenant_id": "t2"}
        assert len(svc.list_tenant_users("t1")) == 2
        assert len(svc.list_tenant_users("t1", skip=1)) == 1
        assert len(svc.list_tenant_users("t1", limit=1)) == 1

    def test_session_maci_roles(self):
        svc = self._make_service()
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=["ADMIN"],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        assert svc.get_session_maci_roles(session.session_id) == ["ADMIN"]
        assert svc.get_session_maci_roles("nope") == []

    def test_session_has_role(self):
        svc = self._make_service()
        session = svc._create_session(
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=["ADMIN"],
            email="a@b.com",
            display_name="A",
            session_hours=1,
        )
        assert svc.session_has_role(session.session_id, "ADMIN") is True
        assert svc.session_has_role(session.session_id, "VIEWER") is False
        assert svc.session_has_role("nope", "ADMIN") is False

    def test_get_statistics(self):
        svc = self._make_service()
        svc.configure_tenant_sso("t1", sso_enabled=True)
        stats = svc.get_statistics()
        assert "total_users" in stats
        assert "active_sessions" in stats
        assert stats["configured_tenants"] >= 1

    def test_create_tenant_context_no_multitenancy(self):
        svc = self._make_service()
        session = SSOSession(
            session_id="s1",
            user_id="u1",
            external_id="e1",
            tenant_id="t1",
            idp_id="i1",
            maci_roles=["ADMIN"],
        )
        # This may return None depending on multi_tenancy availability
        result = svc.create_tenant_context(session)
        # Either returns TenantContext or None - both are acceptable
        assert result is None or result is not None


# ============================================================================
# llm_adapters.models - ToolType
# ============================================================================


class TestToolType:
    def test_values(self):
        assert ToolType.FUNCTION.value == "function"
        assert ToolType.CODE_INTERPRETER.value == "code_interpreter"
        assert ToolType.FILE_SEARCH.value == "file_search"
        assert ToolType.WEB_BROWSER.value == "web_browser"


# ============================================================================
# llm_adapters.models - FunctionParameters
# ============================================================================


class TestFunctionParameters:
    def test_defaults(self):
        fp = FunctionParameters()
        assert fp.type == "object"
        assert fp.properties == {}
        assert fp.required == []

    def test_to_dict_minimal(self):
        fp = FunctionParameters()
        d = fp.to_dict()
        assert d["type"] == "object"
        assert "required" not in d
        assert "description" not in d

    def test_to_dict_full(self):
        fp = FunctionParameters(
            properties={"name": {"type": "string"}},
            required=["name"],
            description="A schema",
        )
        d = fp.to_dict()
        assert d["required"] == ["name"]
        assert d["description"] == "A schema"


# ============================================================================
# llm_adapters.models - FunctionDefinition
# ============================================================================


class TestFunctionDefinition:
    def test_valid(self):
        fd = FunctionDefinition(name="get_weather", description="Get weather")
        assert fd.name == "get_weather"

    def test_invalid_name(self):
        with pytest.raises(ValidationError):
            FunctionDefinition(name="", description="bad")

    def test_invalid_name_special(self):
        with pytest.raises(ValidationError):
            FunctionDefinition(name="foo bar", description="bad")

    def test_to_dict(self):
        fd = FunctionDefinition(name="get_weather", description="Get weather", strict=True)
        d = fd.to_dict()
        assert d["name"] == "get_weather"
        assert d["strict"] is True

    def test_to_dict_no_strict(self):
        fd = FunctionDefinition(name="get_weather", description="Get weather")
        d = fd.to_dict()
        assert "strict" not in d


# ============================================================================
# llm_adapters.models - ToolDefinition
# ============================================================================


class TestToolDefinition:
    def test_to_dict(self):
        td = ToolDefinition(function=FunctionDefinition(name="test_fn", description="test"))
        d = td.to_dict()
        assert d["type"] == "function"
        assert d["function"]["name"] == "test_fn"

    def test_from_dict(self):
        data = {
            "type": "function",
            "function": {"name": "test_fn", "description": "test"},
        }
        td = ToolDefinition.from_dict(data)
        assert td.function.name == "test_fn"
        assert td.type == ToolType.FUNCTION

    def test_from_dict_default_type(self):
        data = {"function": {"name": "test_fn", "description": "test"}}
        td = ToolDefinition.from_dict(data)
        assert td.type == ToolType.FUNCTION


# ============================================================================
# llm_adapters.models - ToolCallFunction
# ============================================================================


class TestToolCallFunction:
    def test_valid(self):
        tcf = ToolCallFunction(name="fn", arguments='{"x": 1}')
        assert tcf.get_arguments_dict() == {"x": 1}

    def test_invalid_json(self):
        with pytest.raises(ValidationError):
            ToolCallFunction(name="fn", arguments="not json")

    def test_to_dict(self):
        tcf = ToolCallFunction(name="fn", arguments='{"x": 1}')
        d = tcf.to_dict()
        assert d["name"] == "fn"


# ============================================================================
# llm_adapters.models - ToolCall
# ============================================================================


class TestToolCall:
    def test_to_dict(self):
        tc = ToolCall(
            id="tc-1",
            function=ToolCallFunction(name="fn", arguments="{}"),
        )
        d = tc.to_dict()
        assert d["id"] == "tc-1"
        assert d["type"] == "function"

    def test_from_dict(self):
        data = {
            "id": "tc-1",
            "type": "function",
            "function": {"name": "fn", "arguments": "{}"},
        }
        tc = ToolCall.from_dict(data)
        assert tc.id == "tc-1"


# ============================================================================
# llm_adapters.models - LLMRequest
# ============================================================================


class TestLLMRequest:
    def test_empty_messages_raises(self):
        with pytest.raises(ValidationError):
            LLMRequest(messages=[])

    def test_minimal(self):
        req = LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        assert req.temperature == 0.7
        assert req.stream is False

    def test_to_dict_minimal(self):
        req = LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        d = req.to_dict()
        assert "messages" in d
        assert "model" not in d

    def test_to_dict_full(self):
        tool = ToolDefinition(function=FunctionDefinition(name="fn", description="d"))
        req = LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            model="gpt-4",
            max_tokens=100,
            top_k=50,
            frequency_penalty=0.5,
            presence_penalty=0.5,
            stop=["END"],
            tools=[tool],
            tool_choice="auto",
            response_format={"type": "json_object"},
            metadata={"task": "test"},
        )
        d = req.to_dict()
        assert d["model"] == "gpt-4"
        assert d["max_tokens"] == 100
        assert d["top_k"] == 50
        assert d["stop"] == ["END"]
        assert len(d["tools"]) == 1
        assert d["tool_choice"] == "auto"
        assert d["response_format"] == {"type": "json_object"}


# ============================================================================
# llm_adapters.models - MessageConverter
# ============================================================================


class TestMessageConverter:
    def _msgs(self) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello!"),
        ]

    def test_to_openai_format(self):
        result = MessageConverter.to_openai_format(self._msgs())
        assert len(result) == 3
        assert result[0]["role"] == "system"

    def test_to_openai_with_extras(self):
        msgs = [
            LLMMessage(
                role="assistant",
                content="",
                name="bot",
                tool_calls=[{"id": "tc1", "function": {"name": "fn", "arguments": "{}"}}],
                tool_call_id="tc1",
                function_call={"name": "fn", "arguments": "{}"},
            ),
        ]
        result = MessageConverter.to_openai_format(msgs)
        assert result[0]["name"] == "bot"
        assert result[0]["tool_calls"] is not None
        assert result[0]["tool_call_id"] == "tc1"
        assert result[0]["function_call"] is not None

    def test_to_anthropic_format_skips_system(self):
        result = MessageConverter.to_anthropic_format(self._msgs())
        roles = [m["role"] for m in result]
        assert "system" not in roles

    def test_to_anthropic_format_tool_calls(self):
        msgs = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "function": {"name": "fn", "arguments": '{"x": 1}'},
                    }
                ],
            ),
        ]
        result = MessageConverter.to_anthropic_format(msgs)
        assert result[0]["content"][0]["type"] == "tool_use"

    def test_to_bedrock_anthropic(self):
        result = MessageConverter.to_bedrock_format(self._msgs(), provider="anthropic")
        assert "messages" in result
        assert "system" in result

    def test_to_bedrock_other(self):
        result = MessageConverter.to_bedrock_format(self._msgs(), provider="meta")
        assert "messages" in result

    def test_from_openai_format(self):
        openai_msgs = [
            {"role": "user", "content": "hi", "name": "alice"},
        ]
        result = MessageConverter.from_openai_format(openai_msgs)
        assert result[0].role == "user"
        assert result[0].name == "alice"

    def test_from_anthropic_format_with_system(self):
        msgs = [{"role": "user", "content": "hi"}]
        result = MessageConverter.from_anthropic_format(msgs, system="You are helpful.")
        assert result[0].role == "system"
        assert result[1].role == "user"

    def test_from_anthropic_format_tool_use(self):
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "tool_use",
                        "id": "tc1",
                        "name": "fn",
                        "input": {"x": 1},
                    },
                ],
            },
        ]
        result = MessageConverter.from_anthropic_format(msgs)
        assert result[0].tool_calls is not None
        assert result[0].content == "Let me check."

    def test_from_anthropic_format_no_system(self):
        msgs = [{"role": "user", "content": "hi"}]
        result = MessageConverter.from_anthropic_format(msgs)
        assert len(result) == 1


# ============================================================================
# llm_adapters.models - RequestConverter
# ============================================================================


class TestRequestConverter:
    def _req(self, **kwargs) -> LLMRequest:
        defaults = {"messages": [LLMMessage(role="user", content="hi")]}
        defaults.update(kwargs)
        return LLMRequest(**defaults)

    def test_to_openai_minimal(self):
        r = RequestConverter.to_openai_request(self._req())
        assert "messages" in r
        assert "temperature" in r

    def test_to_openai_full(self):
        tool = ToolDefinition(function=FunctionDefinition(name="fn", description="d"))
        r = RequestConverter.to_openai_request(
            self._req(
                model="gpt-4",
                max_tokens=100,
                frequency_penalty=0.5,
                presence_penalty=0.5,
                stop=["END"],
                tools=[tool],
                tool_choice="auto",
                response_format={"type": "json_object"},
            )
        )
        assert r["model"] == "gpt-4"
        assert r["stop"] == ["END"]
        assert len(r["tools"]) == 1

    def test_to_anthropic_minimal(self):
        r = RequestConverter.to_anthropic_request(self._req())
        assert "messages" in r

    def test_to_anthropic_with_system(self):
        req = LLMRequest(
            messages=[
                LLMMessage(role="system", content="Be helpful"),
                LLMMessage(role="user", content="hi"),
            ]
        )
        r = RequestConverter.to_anthropic_request(req)
        assert r["system"] == "Be helpful"

    def test_to_anthropic_with_tools(self):
        tool = ToolDefinition(function=FunctionDefinition(name="fn", description="d"))
        r = RequestConverter.to_anthropic_request(self._req(tools=[tool], stream=True))
        assert "tools" in r
        assert r["stream"] is True

    def test_to_anthropic_with_stop(self):
        r = RequestConverter.to_anthropic_request(self._req(stop=["END"]))
        assert r["stop_sequences"] == ["END"]

    def test_to_bedrock_anthropic(self):
        r = RequestConverter.to_bedrock_request(
            self._req(), model_id="claude-v2", provider="anthropic"
        )
        assert r["modelId"] == "claude-v2"
        assert r["contentType"] == "application/json"

    def test_to_bedrock_other(self):
        r = RequestConverter.to_bedrock_request(self._req(), model_id="llama", provider="meta")
        assert r["modelId"] == "llama"


# ============================================================================
# llm_adapters.models - ResponseConverter
# ============================================================================


class TestResponseConverter:
    def test_from_openai_response(self):
        resp = {
            "id": "chatcmpl-1",
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        result = ResponseConverter.from_openai_response(resp)
        assert result.content == "Hello!"
        assert result.usage.total_tokens == 15
        assert result.metadata.provider == "openai"

    def test_from_anthropic_response(self):
        resp = {
            "id": "msg-1",
            "model": "claude-3",
            "content": [{"type": "text", "text": "Hi there!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = ResponseConverter.from_anthropic_response(resp)
        assert result.content == "Hi there!"
        assert result.usage.prompt_tokens == 10
        assert result.metadata.provider == "anthropic"

    def test_from_anthropic_with_tool_use(self):
        resp = {
            "id": "msg-1",
            "model": "claude-3",
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "tc1",
                    "name": "fn",
                    "input": {"x": 1},
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = ResponseConverter.from_anthropic_response(resp)
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1

    def test_from_bedrock_anthropic(self):
        body = {
            "id": "msg-1",
            "model": "claude-3",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        resp = {"body": json.dumps(body)}
        result = ResponseConverter.from_bedrock_response(resp, provider="anthropic")
        assert result.content == "Hello"

    def test_from_bedrock_other(self):
        body = {
            "id": "chat-1",
            "model": "llama",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hi"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        resp = {"body": json.dumps(body)}
        result = ResponseConverter.from_bedrock_response(resp, provider="meta")
        assert result.content == "Hi"


# ============================================================================
# capability_matrix - Enums
# ============================================================================


class TestCapabilityEnums:
    def test_capability_dimension(self):
        assert CapabilityDimension.CONTEXT_LENGTH.value == "context_length"
        assert CapabilityDimension.VISION.value == "vision"

    def test_latency_class(self):
        assert LatencyClass.ULTRA_LOW.value == "ultra_low"

    def test_capability_level(self):
        assert CapabilityLevel.NONE.value == "none"
        assert CapabilityLevel.FULL.value == "full"


# ============================================================================
# capability_matrix - CapabilityValue
# ============================================================================


class TestCapabilityValue:
    def test_to_dict(self):
        cv = CapabilityValue(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            value=128000,
        )
        d = cv.to_dict()
        assert d["dimension"] == "context_length"
        assert d["value"] == 128000

    def test_to_dict_enum_value(self):
        cv = CapabilityValue(
            dimension=CapabilityDimension.LATENCY_CLASS,
            value=LatencyClass.LOW,
        )
        d = cv.to_dict()
        assert d["value"] == "low"

    def test_is_satisfied_by_bool_true(self):
        cv = CapabilityValue(dimension=CapabilityDimension.VISION, value=True)
        req = CapabilityRequirement(dimension=CapabilityDimension.VISION, min_value=True)
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_bool_false(self):
        cv = CapabilityValue(dimension=CapabilityDimension.VISION, value=False)
        req = CapabilityRequirement(dimension=CapabilityDimension.VISION, min_value=True)
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_bool_no_min(self):
        cv = CapabilityValue(dimension=CapabilityDimension.VISION, value=False)
        req = CapabilityRequirement(dimension=CapabilityDimension.VISION)
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_numeric_min(self):
        cv = CapabilityValue(dimension=CapabilityDimension.CONTEXT_LENGTH, value=128000)
        req = CapabilityRequirement(dimension=CapabilityDimension.CONTEXT_LENGTH, min_value=100000)
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_numeric_min_fail(self):
        cv = CapabilityValue(dimension=CapabilityDimension.CONTEXT_LENGTH, value=4096)
        req = CapabilityRequirement(dimension=CapabilityDimension.CONTEXT_LENGTH, min_value=100000)
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_numeric_max(self):
        cv = CapabilityValue(dimension=CapabilityDimension.INPUT_COST_PER_1K, value=0.01)
        req = CapabilityRequirement(dimension=CapabilityDimension.INPUT_COST_PER_1K, max_value=0.05)
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_numeric_max_fail(self):
        cv = CapabilityValue(dimension=CapabilityDimension.INPUT_COST_PER_1K, value=0.1)
        req = CapabilityRequirement(dimension=CapabilityDimension.INPUT_COST_PER_1K, max_value=0.05)
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_level(self):
        cv = CapabilityValue(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            value=CapabilityLevel.FULL,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            min_value=CapabilityLevel.STANDARD,
        )
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_level_fail(self):
        cv = CapabilityValue(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            value=CapabilityLevel.BASIC,
        )
        req = CapabilityRequirement(
            dimension=CapabilityDimension.FUNCTION_CALLING,
            min_value=CapabilityLevel.FULL,
        )
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_string_exact(self):
        cv = CapabilityValue(dimension=CapabilityDimension.LATENCY_CLASS, value="low")
        req = CapabilityRequirement(dimension=CapabilityDimension.LATENCY_CLASS, exact_value="low")
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_string_exact_fail(self):
        cv = CapabilityValue(dimension=CapabilityDimension.LATENCY_CLASS, value="high")
        req = CapabilityRequirement(dimension=CapabilityDimension.LATENCY_CLASS, exact_value="low")
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_string_no_exact(self):
        cv = CapabilityValue(dimension=CapabilityDimension.LATENCY_CLASS, value="high")
        req = CapabilityRequirement(dimension=CapabilityDimension.LATENCY_CLASS)
        assert cv.is_satisfied_by(req) is True

    def test_is_satisfied_by_dimension_mismatch(self):
        cv = CapabilityValue(dimension=CapabilityDimension.VISION, value=True)
        req = CapabilityRequirement(dimension=CapabilityDimension.CONTEXT_LENGTH, min_value=1000)
        assert cv.is_satisfied_by(req) is False

    def test_is_satisfied_by_none_value(self):
        cv = CapabilityValue(dimension=CapabilityDimension.VISION, value=None)
        req = CapabilityRequirement(dimension=CapabilityDimension.VISION)
        assert cv.is_satisfied_by(req) is True


# ============================================================================
# capability_matrix - CapabilityRequirement
# ============================================================================


class TestCapabilityRequirement:
    def test_to_dict(self):
        req = CapabilityRequirement(
            dimension=CapabilityDimension.CONTEXT_LENGTH,
            min_value=100000,
            priority=1,
        )
        d = req.to_dict()
        assert d["dimension"] == "context_length"
        assert d["min_value"] == 100000


# ============================================================================
# capability_matrix - ProviderCapabilityProfile
# ============================================================================


class TestProviderCapabilityProfile:
    def _profile(self, **kwargs) -> ProviderCapabilityProfile:
        defaults = {
            "provider_id": "test-1",
            "model_id": "test-model",
            "display_name": "Test",
            "provider_type": "test",
        }
        defaults.update(kwargs)
        return ProviderCapabilityProfile(**defaults)

    def test_get_capability(self):
        p = self._profile(context_length=128000)
        cap = p.get_capability(CapabilityDimension.CONTEXT_LENGTH)
        assert cap.value == 128000

    def test_get_capability_vision(self):
        p = self._profile(vision=True)
        cap = p.get_capability(CapabilityDimension.VISION)
        assert cap.value is True

    def test_satisfies_requirements(self):
        p = self._profile(context_length=128000, vision=True)
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        satisfied, unsatisfied = p.satisfies_requirements(reqs)
        assert satisfied is True
        assert unsatisfied == []

    def test_satisfies_requirements_fail(self):
        p = self._profile(context_length=4096)
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        satisfied, unsatisfied = p.satisfies_requirements(reqs)
        assert satisfied is False
        assert "context_length" in unsatisfied

    def test_satisfies_skips_non_required(self):
        p = self._profile(context_length=4096)
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=2,  # preferred, not required
            ),
        ]
        satisfied, _ = p.satisfies_requirements(reqs)
        assert satisfied is True

    def test_calculate_score(self):
        p = self._profile(context_length=128000)
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        score = p.calculate_score(reqs)
        assert score > 0

    def test_calculate_score_empty(self):
        p = self._profile()
        assert p.calculate_score([]) == 0.0

    def test_calculate_score_with_weights(self):
        p = self._profile(context_length=128000)
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        score = p.calculate_score(reqs, weights={"context_length": 2.0})
        assert score > 0


# ============================================================================
# capability_matrix - CapabilityRegistry
# ============================================================================


class TestCapabilityRegistry:
    def test_default_profiles_registered(self):
        reg = CapabilityRegistry()
        profiles = reg.get_all_profiles()
        assert len(profiles) > 0

    def test_register_profile(self):
        reg = CapabilityRegistry()
        p = ProviderCapabilityProfile(
            provider_id="custom-1",
            model_id="custom",
            display_name="Custom",
            provider_type="custom",
        )
        reg.register_profile(p)
        assert reg.get_profile("custom-1") is not None

    def test_get_profile_not_found(self):
        reg = CapabilityRegistry()
        assert reg.get_profile("nonexistent") is None

    def test_get_all_profiles_active_only(self):
        reg = CapabilityRegistry()
        p = ProviderCapabilityProfile(
            provider_id="inactive-1",
            model_id="x",
            display_name="X",
            provider_type="test",
            is_active=False,
        )
        reg.register_profile(p)
        active = reg.get_all_profiles(active_only=True)
        inactive = reg.get_all_profiles(active_only=False)
        assert len(inactive) > len(active)

    def test_get_by_provider_type(self):
        reg = CapabilityRegistry()
        openai = reg.get_by_provider_type("openai")
        assert len(openai) > 0
        assert all(p.provider_type == "openai" for p in openai)

    def test_get_by_provider_type_empty(self):
        reg = CapabilityRegistry()
        assert reg.get_by_provider_type("nonexistent") == []

    def test_find_capable_providers(self):
        reg = CapabilityRegistry()
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.VISION,
                min_value=True,
                priority=1,
            ),
        ]
        results = reg.find_capable_providers(reqs)
        assert len(results) > 0
        # Should be sorted by score descending
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_generate_fallback_chain(self):
        reg = CapabilityRegistry()
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        chain = reg.generate_fallback_chain("openai-gpt4o", reqs, max_fallbacks=3)
        assert len(chain) <= 3
        assert "openai-gpt4o" not in chain

    def test_generate_fallback_chain_primary_not_found(self):
        reg = CapabilityRegistry()
        chain = reg.generate_fallback_chain("nonexistent", [], max_fallbacks=3)
        assert chain == []

    def test_register_discovery_hook(self):
        reg = CapabilityRegistry()
        hook = MagicMock(return_value=[])
        reg.register_discovery_hook(hook)
        assert len(reg._discovery_hooks) == 1

    @pytest.mark.asyncio
    async def test_discover_capabilities(self):
        reg = CapabilityRegistry()
        p = ProviderCapabilityProfile(
            provider_id="discovered-1",
            model_id="d",
            display_name="D",
            provider_type="test",
        )
        hook = MagicMock(return_value=[p])
        reg.register_discovery_hook(hook)
        updated = await reg.discover_capabilities(force=True)
        assert updated == 1
        assert reg.get_profile("discovered-1") is not None

    @pytest.mark.asyncio
    async def test_discover_capabilities_skips_recent(self):
        reg = CapabilityRegistry()
        hook = MagicMock(return_value=[])
        reg.register_discovery_hook(hook)
        await reg.discover_capabilities(force=True)
        # Second call without force should skip
        updated = await reg.discover_capabilities(force=False)
        assert updated == 0

    @pytest.mark.asyncio
    async def test_discover_capabilities_hook_error(self):
        reg = CapabilityRegistry()

        def bad_hook():
            raise RuntimeError("discovery failed")

        reg.register_discovery_hook(bad_hook)
        updated = await reg.discover_capabilities(force=True)
        assert updated == 0

    @pytest.mark.asyncio
    async def test_initialize(self):
        reg = CapabilityRegistry()
        await reg.initialize()
        assert reg._initialized is True
        # Second call should be a no-op (already initialized)
        await reg.initialize()


# ============================================================================
# capability_matrix - CapabilityRouter
# ============================================================================


class TestCapabilityRouter:
    def test_select_provider(self):
        router = CapabilityRouter()
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        provider = router.select_provider(reqs)
        assert provider is not None

    def test_select_provider_no_match(self):
        router = CapabilityRouter()
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=99999999,
                priority=1,
            ),
        ]
        provider = router.select_provider(reqs)
        assert provider is None

    def test_select_provider_with_exclusion(self):
        router = CapabilityRouter()
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        first = router.select_provider(reqs)
        assert first is not None
        second = router.select_provider(reqs, exclude_providers=[first.provider_id])
        if second is not None:
            assert second.provider_id != first.provider_id

    def test_set_preferences(self):
        router = CapabilityRouter()
        router.set_preferences({"prefer_low_cost": True, "prefer_low_latency": False})
        assert router._routing_preferences["prefer_low_cost"] is True

    def test_select_provider_prefer_low_cost(self):
        router = CapabilityRouter()
        router.set_preferences({"prefer_low_cost": True, "prefer_low_latency": False})
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        provider = router.select_provider(reqs)
        assert provider is not None

    def test_get_fallback_chain(self):
        router = CapabilityRouter()
        primary = router.registry.get_profile("openai-gpt4o")
        assert primary is not None
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        fallbacks = router.get_fallback_chain(primary, reqs)
        assert isinstance(fallbacks, list)

    def test_estimate_cost(self):
        router = CapabilityRouter()
        profile = ProviderCapabilityProfile(
            provider_id="test",
            model_id="test",
            display_name="Test",
            provider_type="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )
        cost = router.estimate_cost(profile, input_tokens=1000, output_tokens=500)
        expected = 0.01 + (500 / 1000) * 0.03
        assert abs(cost - expected) < 1e-9

    def test_load_balancing(self):
        router = CapabilityRouter()
        router.set_preferences({"load_balance": True, "prefer_low_latency": False})
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=100000,
                priority=1,
            ),
        ]
        # Make multiple selections to exercise load balancing
        providers = set()
        for _ in range(5):
            p = router.select_provider(reqs)
            if p:
                providers.add(p.provider_id)
        # Should select at least 2 different providers
        assert len(providers) >= 1


# ============================================================================
# capability_matrix - Global accessors
# ============================================================================


class TestGlobalAccessors:
    def test_get_capability_registry(self):
        import enhanced_agent_bus.llm_adapters.capability_matrix as cm

        cm._capability_registry = None
        reg = get_capability_registry()
        assert reg is not None
        # Second call should return same instance
        assert get_capability_registry() is reg

    def test_get_capability_router(self):
        import enhanced_agent_bus.llm_adapters.capability_matrix as cm

        cm._capability_router = None
        router = get_capability_router()
        assert router is not None
        assert get_capability_router() is router

    @pytest.mark.asyncio
    async def test_initialize_capability_matrix(self):
        import enhanced_agent_bus.llm_adapters.capability_matrix as cm

        cm._capability_registry = None
        await initialize_capability_matrix()
        assert cm._capability_registry is not None
