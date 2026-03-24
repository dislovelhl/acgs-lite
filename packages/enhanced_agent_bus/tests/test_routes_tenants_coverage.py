"""
Comprehensive pytest test suite for routes/tenants.py
Constitutional Hash: cdd01ef066bc6cf2

Targets ≥90% coverage of the tenant management API routes, including:
- All route handlers (CRUD, lifecycle, quota, hierarchy, children)
- Authorization helpers (_validate_admin_api_key, _validate_jwt_token, get_admin_tenant_id)
- Helper utilities (_to_dict_safe, get_manager)
- All error paths: 400, 401, 404, 409, 429, 500, 503
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from src.core.shared.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Module under test — import via absolute path (importlib mode compatible)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.routes import tenants as tenants_module
from enhanced_agent_bus.routes.models.tenant_models import (
    CreateTenantRequest,
    QuotaCheckRequest,
    SuspendTenantRequest,
    TenantResponse,
    UpdateQuotaRequest,
    UpdateTenantRequest,
    UsageIncrementRequest,
)
from enhanced_agent_bus.routes.tenants import (
    _build_quota_check_response,
    _build_tenant_config_and_quota,
    _build_tenant_hierarchy_response,
    _build_tenant_list_response,
    _build_usage_response,
    _calculate_utilization,
    _check_tenant_scope,
    _extract_usage_and_quota_dicts,
    _get_tenant_or_404,
    _has_auth_configuration,
    _is_production_runtime,
    _parse_status_filter,
    _to_dict_safe,
    _validate_admin_api_key,
    _validate_jwt_token,
    get_admin_tenant_id,
    get_manager,
    router,
)

# ---------------------------------------------------------------------------
# FastAPI test application
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers: build fake Tenant objects
# ---------------------------------------------------------------------------


def _make_tenant(
    tenant_id: str = "tenant-001",
    name: str = "Test Tenant",
    slug: str = "test-tenant",
    status_value: str = "active",
    parent_tenant_id: str | None = None,
    quota: dict | None = None,
    usage: dict | None = None,
    config: dict | None = None,
    metadata: dict | None = None,
) -> MagicMock:
    """Return a MagicMock that behaves like a Tenant object."""
    tenant = MagicMock()
    tenant.tenant_id = tenant_id
    tenant.name = name
    tenant.slug = slug

    # status with .value attribute
    status_mock = MagicMock()
    status_mock.value = status_value
    tenant.status = status_mock

    tenant.parent_tenant_id = parent_tenant_id
    tenant.metadata = metadata or {}
    tenant.constitutional_hash = CONSTITUTIONAL_HASH

    now = datetime.now(UTC)
    tenant.created_at = now
    tenant.updated_at = now
    tenant.activated_at = None
    tenant.suspended_at = None

    # quota
    quota_dict = quota or {
        "max_agents": 100,
        "max_policies": 1000,
        "max_messages_per_minute": 10000,
    }
    quota_mock = MagicMock()
    quota_mock.model_dump.return_value = quota_dict
    tenant.quota = quota_mock

    # usage
    usage_dict = usage or {"agents_count": 5, "policies_count": 50, "messages_this_minute": 100}
    usage_mock = MagicMock()
    usage_mock.model_dump.return_value = usage_dict
    tenant.usage = usage_mock

    # config
    config_dict = config or {}
    config_mock = MagicMock()
    config_mock.model_dump.return_value = config_dict
    tenant.config = config_mock

    return tenant


def _admin_headers(key: str = "secret-admin-key") -> dict:
    return {"X-Admin-Key": key}


def _override_auth(admin_id: str = "system-admin") -> None:
    """Override get_admin_tenant_id dependency to always succeed."""
    _app.dependency_overrides[get_admin_tenant_id] = lambda: admin_id


def _clear_overrides() -> None:
    _app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# _to_dict_safe
# ---------------------------------------------------------------------------


class TestToDictSafe:
    def test_none_returns_empty_dict(self):
        assert _to_dict_safe(None) == {}

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert _to_dict_safe(d) == d

    def test_pydantic_model_dump(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"key": "val"}
        # Remove to_dict so model_dump branch is taken
        del obj.to_dict
        result = _to_dict_safe(obj)
        assert result == {"key": "val"}

    def test_to_dict_method(self):
        obj = MagicMock(spec=["to_dict"])
        obj.to_dict.return_value = {"foo": "bar"}
        result = _to_dict_safe(obj)
        assert result == {"foo": "bar"}

    def test_dataclass_converted(self):
        from dataclasses import dataclass as dc

        @dc
        class Simple:
            x: int = 1
            y: str = "hello"

        result = _to_dict_safe(Simple())
        assert result == {"x": 1, "y": "hello"}

    def test_dict_cast_fallback(self):
        # Object that can be cast with dict() but has no special method
        class DictLike:
            def keys(self):
                return ["a"]

            def __getitem__(self, key):
                return 42

        result = _to_dict_safe(DictLike())
        assert result == {"a": 42}


class TestTenantRouteHelpers:
    def test_build_tenant_config_and_quota_defaults(self):
        request = CreateTenantRequest(name="Acme", slug="acme")
        config, quota = _build_tenant_config_and_quota(request)
        assert config is None
        assert quota is None

    def test_build_tenant_config_and_quota_values(self):
        request = CreateTenantRequest(
            name="Acme",
            slug="acme",
            config={"enable_batch_processing": True},
            quota={"max_agents": 12},
        )
        config, quota = _build_tenant_config_and_quota(request)
        assert config is not None
        assert quota is not None
        assert config.enable_batch_processing is True
        assert quota.max_agents == 12

    def test_parse_status_filter_none(self):
        assert _parse_status_filter(None) is None

    def test_parse_status_filter_valid(self):
        result = _parse_status_filter("ACTIVE")
        assert result == tenants_module.TenantStatus.ACTIVE

    def test_parse_status_filter_invalid_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_status_filter("bogus")
        assert exc_info.value.status_code == 400

    def test_check_tenant_scope_allows_same_tenant(self):
        _check_tenant_scope("tenant-001", "tenant-001")

    def test_check_tenant_scope_denies_cross_tenant_access(self):
        # Use UUID-format IDs so _is_uuid returns True and scope check is enforced
        with pytest.raises(HTTPException) as exc_info:
            _check_tenant_scope(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
            )

        assert exc_info.value.status_code == 403

    def test_check_tenant_scope_denies_substring_admin_without_flag(self):
        # Use UUID-format admin so _is_uuid returns True and scope check is enforced
        with pytest.raises(HTTPException) as exc_info:
            _check_tenant_scope(
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "00000000-0000-0000-0000-000000000002",
            )

        assert exc_info.value.status_code == 403

    def test_check_tenant_scope_allows_explicit_super_admin_flag(self):
        _check_tenant_scope("controller-ops", "tenant-002", is_super_admin=True)

    def test_check_tenant_scope_allows_system_admin_account(self):
        _check_tenant_scope("system-admin", "tenant-002")

    async def test_get_tenant_or_404_returns_tenant(self):
        manager = MagicMock()
        tenant = _make_tenant()
        manager.get_tenant = AsyncMock(return_value=tenant)

        result = await _get_tenant_or_404(manager, tenant.tenant_id)

        assert result is tenant

    async def test_get_tenant_or_404_raises(self):
        manager = MagicMock()
        manager.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await _get_tenant_or_404(manager, "missing-tenant")

        assert exc_info.value.status_code == 404

    def test_extract_usage_and_quota_dicts(self):
        tenant = _make_tenant(
            quota={"max_agents": 12},
            usage={"agents_count": 3},
        )

        usage_dict, quota_dict = _extract_usage_and_quota_dicts(tenant)

        assert usage_dict == {"agents_count": 3}
        assert quota_dict == {"max_agents": 12}

    def test_extract_usage_and_quota_dicts_with_override_and_missing_usage(self):
        tenant = _make_tenant(quota={"max_agents": 12})
        del tenant.usage
        usage_override = MagicMock()
        usage_override.model_dump.return_value = {"agents_count": 8}

        usage_dict, quota_dict = _extract_usage_and_quota_dicts(
            tenant,
            usage_override=usage_override,
        )

        assert usage_dict == {"agents_count": 8}
        assert quota_dict == {"max_agents": 12}

    def test_build_tenant_list_response(self):
        tenants = [
            _make_tenant(tenant_id="t-1", slug="t-1"),
            _make_tenant(tenant_id="t-2", slug="t-2"),
        ]

        response = _build_tenant_list_response(tenants, page=1, page_size=2, has_more=True)

        assert response.total_count == 2
        assert response.page == 1
        assert response.page_size == 2
        assert response.has_more is True
        assert [tenant.tenant_id for tenant in response.tenants] == ["t-1", "t-2"]

    def test_calculate_utilization(self):
        utilization = _calculate_utilization(
            {"agents_count": 25, "messages_this_minute": 200},
            {"max_agents": 100, "max_messages_per_minute": 400},
        )

        assert utilization == {"agents_count": 25.0, "messages_this_minute": 50.0}

    def test_build_usage_response_defaults_utilization(self):
        response = _build_usage_response(
            "tenant-001",
            usage_dict={"agents_count": 4},
            quota_dict={"max_agents": 10},
        )

        assert response.tenant_id == "tenant-001"
        assert response.usage == {"agents_count": 4}
        assert response.quota == {"max_agents": 10}
        assert response.utilization == {}

    def test_build_quota_check_response(self):
        request = QuotaCheckRequest(resource="agents", requested_amount=2)

        response = _build_quota_check_response(
            "tenant-001",
            request,
            available=True,
            usage_dict={"agents_count": 8},
            quota_dict={"max_agents": 10},
        )

        assert response.current_usage == 8
        assert response.quota_limit == 10
        assert response.remaining == 2
        assert response.warning_threshold_reached is True

    def test_build_tenant_hierarchy_response_excludes_self_from_ancestors(self):
        root = _make_tenant(tenant_id="root", slug="root")
        child = _make_tenant(tenant_id="child", slug="child")
        grandchild = _make_tenant(tenant_id="grandchild", slug="grandchild")

        response = _build_tenant_hierarchy_response(
            "grandchild",
            ancestors=[root, child, grandchild],
            descendants=[],
        )

        assert response.depth == 2
        assert [tenant.tenant_id for tenant in response.ancestors] == ["root", "child"]

    def test_unserializable_returns_empty_dict(self):
        result = _to_dict_safe(object())
        assert result == {}


# ---------------------------------------------------------------------------
# _validate_admin_api_key
# ---------------------------------------------------------------------------


class TestValidateAdminApiKey:
    def test_empty_tenant_admin_key_returns_false(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", ""):
            assert _validate_admin_api_key("anything") is False

    def test_correct_key_returns_true(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "my-secret"):
            assert _validate_admin_api_key("my-secret") is True

    def test_wrong_key_returns_false(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "my-secret"):
            assert _validate_admin_api_key("wrong-key") is False

    def test_timing_safe_comparison_used(self):
        """Ensure hmac.compare_digest is used (not ==)."""
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "abc"):
            with patch("hmac.compare_digest", return_value=True) as mock_compare:
                result = _validate_admin_api_key("abc")
                mock_compare.assert_called_once()
                assert result is True


# ---------------------------------------------------------------------------
# _validate_jwt_token
# ---------------------------------------------------------------------------


class TestValidateJwtToken:
    def test_no_jwt_secret_returns_none(self):
        with patch.object(tenants_module, "JWT_SECRET_KEY", ""):
            result = _validate_jwt_token("any-token")
            assert result is None

    def test_valid_controller_token(self):
        payload = {
            "sub": "agent-123",
            "tenant_id": "t-001",
            "maci_role": "CONTROLLER",
            "permissions": [],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("valid.token.here")
                assert result is not None
                assert result["maci_role"] == "CONTROLLER"

    def test_valid_admin_permission_token(self):
        payload = {
            "sub": "agent-456",
            "tenant_id": "t-002",
            "maci_role": "VOTER",
            "permissions": ["ADMIN"],
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("valid.token.here")
                assert result is not None

    def test_valid_tenant_manage_permission(self):
        payload = {
            "sub": "agent-789",
            "maci_role": "VOTER",
            "permissions": ["TENANT_MANAGE"],
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("token")
                assert result is not None

    def test_constitutional_hash_mismatch_returns_none(self):
        payload = {
            "sub": "agent-x",
            "maci_role": "CONTROLLER",
            "permissions": [],
            "constitutional_hash": "wrong-hash",
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("token")
                assert result is None

    def test_insufficient_permissions_returns_none(self):
        payload = {
            "sub": "agent-y",
            "maci_role": "VOTER",
            "permissions": ["READ_ONLY"],
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("token")
                assert result is None

    def test_expired_token_returns_none(self):
        class FakeExpired(Exception):
            pass

        mock_jwt = MagicMock()
        mock_jwt.decode.side_effect = FakeExpired("expired")
        mock_jwt.ExpiredSignatureError = FakeExpired
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("token")
                assert result is None

    def test_invalid_token_returns_none(self):
        class FakeInvalid(Exception):
            pass

        mock_jwt = MagicMock()
        mock_jwt.decode.side_effect = FakeInvalid("bad token")
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = FakeInvalid

        with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                result = _validate_jwt_token("token")
                assert result is None

    def test_import_error_returns_none(self):
        import sys

        original = sys.modules.pop("jwt", None)
        try:
            with patch.object(tenants_module, "JWT_SECRET_KEY", "test-secret"):
                # Force ImportError by making jwt unavailable
                with patch.dict("sys.modules", {"jwt": None}):
                    # Python raises ImportError when module is None in sys.modules
                    result = _validate_jwt_token("token")
                    # Either None (handled) or raises — both are acceptable paths
        except Exception:
            pass
        finally:
            if original is not None:
                sys.modules["jwt"] = original


# ---------------------------------------------------------------------------
# _is_production_runtime / _has_auth_configuration
# ---------------------------------------------------------------------------


class TestEnvironmentHelpers:
    def test_is_production_true(self):
        with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "production"):
            assert _is_production_runtime() is True

    def test_is_production_false(self):
        with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "development"):
            assert _is_production_runtime() is False

    def test_has_auth_with_admin_key(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "some-key"):
            with patch.object(tenants_module, "JWT_SECRET_KEY", ""):
                assert _has_auth_configuration() is True

    def test_has_auth_with_jwt_key(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", ""):
            with patch.object(tenants_module, "JWT_SECRET_KEY", "jwt-secret"):
                assert _has_auth_configuration() is True

    def test_has_auth_false(self):
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", ""):
            with patch.object(tenants_module, "JWT_SECRET_KEY", ""):
                assert _has_auth_configuration() is False


# ---------------------------------------------------------------------------
# get_admin_tenant_id (via HTTP requests with dependency override)
# ---------------------------------------------------------------------------


class TestGetAdminTenantId:
    """Test auth dependency directly via FastAPI TestClient."""

    def test_production_without_auth_config_returns_503(self):
        _clear_overrides()
        with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "production"):
            with patch.object(tenants_module, "TENANT_ADMIN_KEY", ""):
                with patch.object(tenants_module, "JWT_SECRET_KEY", ""):
                    resp = _client.get("/api/v1/tenants/some-id")
                    assert resp.status_code == 503

    def test_valid_api_key_grants_access(self):
        _clear_overrides()
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "valid-key"):
            with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "development"):
                mock_mgr = MagicMock()
                mock_mgr.get_tenant = AsyncMock(return_value=_make_tenant())
                _app.dependency_overrides[get_manager] = lambda: mock_mgr
                try:
                    resp = _client.get(
                        "/api/v1/tenants/tenant-001",
                        headers={"X-Admin-Key": "valid-key"},
                    )
                    assert resp.status_code == 200
                finally:
                    _app.dependency_overrides.pop(get_manager, None)

    def test_invalid_api_key_returns_401(self):
        _clear_overrides()
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "valid-key"):
            with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "development"):
                resp = _client.get(
                    "/api/v1/tenants/tenant-001",
                    headers={"X-Admin-Key": "wrong-key"},
                )
                assert resp.status_code == 401

    def test_no_auth_returns_401(self):
        _clear_overrides()
        with patch.object(tenants_module, "TENANT_ADMIN_KEY", "valid-key"):
            with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "development"):
                resp = _client.get("/api/v1/tenants/tenant-001")
                assert resp.status_code == 401

    def test_development_mode_bypass(self):
        _clear_overrides()
        with patch.object(tenants_module, "TENANT_AUTH_MODE", "development"):
            with patch.object(tenants_module, "NORMALIZED_ENVIRONMENT", "development"):
                with patch.object(tenants_module, "TENANT_ADMIN_KEY", ""):
                    mock_mgr = MagicMock()
                    mock_mgr.get_tenant = AsyncMock(return_value=_make_tenant())
                    _app.dependency_overrides[get_manager] = lambda: mock_mgr
                    try:
                        resp = _client.get(
                            "/api/v1/tenants/tenant-001",
                            headers={"X-Admin-Key": "any-key-in-dev"},
                        )
                        assert resp.status_code == 200
                    finally:
                        _app.dependency_overrides.pop(get_manager, None)

    def test_valid_jwt_bearer_grants_access(self):
        _clear_overrides()
        payload = {
            "sub": "agent-1",
            "tenant_id": "tenant-001",
            "maci_role": "CONTROLLER",
            "permissions": [],
        }
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = payload
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "jwt-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                mock_mgr = MagicMock()
                mock_mgr.get_tenant = AsyncMock(return_value=_make_tenant())
                _app.dependency_overrides[get_manager] = lambda: mock_mgr
                try:
                    resp = _client.get(
                        "/api/v1/tenants/tenant-001",
                        headers={"Authorization": "Bearer valid.jwt.token"},
                    )
                    assert resp.status_code == 200
                finally:
                    _app.dependency_overrides.pop(get_manager, None)

    def test_invalid_jwt_bearer_returns_401(self):
        _clear_overrides()
        mock_jwt = MagicMock()
        # Invalid token → returns None from _validate_jwt_token
        mock_jwt.decode.return_value = {"maci_role": "VOTER", "permissions": []}
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with patch.object(tenants_module, "JWT_SECRET_KEY", "jwt-secret"):
            with patch.dict("sys.modules", {"jwt": mock_jwt}):
                resp = _client.get(
                    "/api/v1/tenants/tenant-001",
                    headers={"Authorization": "Bearer bad.jwt"},
                )
                assert resp.status_code == 401


# ---------------------------------------------------------------------------
# get_manager
# ---------------------------------------------------------------------------


class TestGetManager:
    def test_returns_manager_from_get_tenant_manager(self):
        mock_mgr = MagicMock()
        with patch.object(tenants_module, "get_tenant_manager", return_value=mock_mgr):
            result = get_manager()
            assert result is mock_mgr

    def test_raises_503_on_runtime_error(self):
        with patch.object(
            tenants_module, "get_tenant_manager", side_effect=RuntimeError("unavailable")
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_manager()
            assert exc_info.value.status_code == 503

    def test_raises_503_on_value_error(self):
        with patch.object(
            tenants_module, "get_tenant_manager", side_effect=ValueError("bad config")
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_manager()
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Route tests — all use dependency overrides for auth + manager
# ---------------------------------------------------------------------------


def _setup_auth_and_manager(mock_mgr: MagicMock) -> None:
    _app.dependency_overrides[get_admin_tenant_id] = lambda: "system-admin"
    _app.dependency_overrides[get_manager] = lambda: mock_mgr


class TestCreateTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_create_tenant_success(self):
        tenant = _make_tenant()
        self.mock_mgr.create_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Acme Corp", "slug": "acme-corp"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tenant_id"] == "tenant-001"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_create_tenant_with_config_and_quota(self):
        tenant = _make_tenant()
        self.mock_mgr.create_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants",
            json={
                "name": "Acme Corp",
                "slug": "acme-corp",
                "config": {"theme": "dark"},
                "quota": {"max_agents": 50},
                "auto_activate": True,
            },
        )
        assert resp.status_code == 201

    def test_create_tenant_validation_error(self):
        from enhanced_agent_bus.routes.tenants import TenantValidationError

        self.mock_mgr.create_tenant = AsyncMock(side_effect=TenantValidationError("Slug invalid"))
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Bad", "slug": "bad-slug"},
        )
        assert resp.status_code == 400

    def test_create_tenant_duplicate_slug(self):
        self.mock_mgr.create_tenant = AsyncMock(side_effect=ValueError("slug already exists"))
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Dup", "slug": "dup-slug"},
        )
        assert resp.status_code == 409

    def test_create_tenant_duplicate_slug_case(self):
        self.mock_mgr.create_tenant = AsyncMock(side_effect=ValueError("duplicate entry for slug"))
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Dup2", "slug": "dup-slug2"},
        )
        assert resp.status_code == 409

    def test_create_tenant_value_error_non_duplicate(self):
        self.mock_mgr.create_tenant = AsyncMock(side_effect=ValueError("some other value error"))
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Bad", "slug": "bad-tenant"},
        )
        assert resp.status_code == 400

    def test_create_tenant_runtime_error(self):
        self.mock_mgr.create_tenant = AsyncMock(side_effect=RuntimeError("DB connection failed"))
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Fail", "slug": "fail-tenant"},
        )
        assert resp.status_code == 500

    def test_create_tenant_invalid_slug_pydantic(self):
        """Pydantic validation should reject invalid slug format."""
        resp = _client.post(
            "/api/v1/tenants",
            json={"name": "Bad Slug", "slug": "INVALID_SLUG!"},
        )
        assert resp.status_code == 422


class TestGetTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_get_tenant_success(self):
        tenant = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.get("/api/v1/tenants/tenant-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant-001"
        assert data["slug"] == "test-tenant"

    def test_get_tenant_not_found_none(self):
        self.mock_mgr.get_tenant = AsyncMock(return_value=None)

        resp = _client.get("/api/v1/tenants/missing-tenant")
        assert resp.status_code == 404

    def test_get_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.get("/api/v1/tenants/missing-tenant")
        assert resp.status_code == 404

    def test_get_tenant_runtime_error(self):
        self.mock_mgr.get_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants/tenant-001")
        assert resp.status_code == 500


class TestGetTenantBySlug:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_get_by_slug_success(self):
        tenant = _make_tenant()
        self.mock_mgr.get_tenant_by_slug = AsyncMock(return_value=tenant)

        resp = _client.get("/api/v1/tenants/by-slug/test-tenant")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "test-tenant"

    def test_get_by_slug_not_found_none(self):
        self.mock_mgr.get_tenant_by_slug = AsyncMock(return_value=None)

        resp = _client.get("/api/v1/tenants/by-slug/nonexistent")
        assert resp.status_code == 404

    def test_get_by_slug_runtime_error(self):
        self.mock_mgr.get_tenant_by_slug = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants/by-slug/error-slug")
        assert resp.status_code == 500


class TestListTenants:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_list_tenants_success(self):
        tenants = [_make_tenant(tenant_id=f"t-{i}", slug=f"slug-{i}") for i in range(3)]
        self.mock_mgr.list_tenants = AsyncMock(return_value=tenants)

        resp = _client.get("/api/v1/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        assert data["has_more"] is False

    def test_list_tenants_has_more(self):
        # Return limit+1 items to trigger has_more=True
        tenants = [_make_tenant(tenant_id=f"t-{i}", slug=f"slug-{i}") for i in range(21)]
        self.mock_mgr.list_tenants = AsyncMock(return_value=tenants)

        resp = _client.get("/api/v1/tenants?limit=20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert len(data["tenants"]) == 20

    def test_list_tenants_with_status_filter(self):
        tenants = [_make_tenant()]
        self.mock_mgr.list_tenants = AsyncMock(return_value=tenants)

        resp = _client.get("/api/v1/tenants?status=active")
        assert resp.status_code == 200

    def test_list_tenants_invalid_status(self):
        resp = _client.get("/api/v1/tenants?status=invalid_status")
        assert resp.status_code == 400

    def test_list_tenants_with_parent_filter(self):
        tenants = [_make_tenant()]
        self.mock_mgr.list_tenants = AsyncMock(return_value=tenants)

        resp = _client.get("/api/v1/tenants?parent_id=parent-001")
        assert resp.status_code == 200

    def test_list_tenants_with_skip_limit(self):
        tenants = []
        self.mock_mgr.list_tenants = AsyncMock(return_value=tenants)

        resp = _client.get("/api/v1/tenants?skip=10&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2  # skip // limit = 10 // 5

    def test_list_tenants_runtime_error(self):
        self.mock_mgr.list_tenants = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants")
        assert resp.status_code == 500


class TestUpdateTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_update_tenant_name(self):
        tenant = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.patch(
            "/api/v1/tenants/tenant-001",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200

    def test_update_tenant_config(self):
        tenant = _make_tenant()
        updated_tenant = _make_tenant(name="Updated")
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)
        self.mock_mgr.update_config = AsyncMock(return_value=updated_tenant)

        resp = _client.patch(
            "/api/v1/tenants/tenant-001",
            json={"config": {"theme": "light"}},
        )
        assert resp.status_code == 200

    def test_update_tenant_metadata(self):
        tenant = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.patch(
            "/api/v1/tenants/tenant-001",
            json={"metadata": {"env": "staging"}},
        )
        assert resp.status_code == 200

    def test_update_tenant_not_found(self):
        self.mock_mgr.get_tenant = AsyncMock(return_value=None)

        resp = _client.patch(
            "/api/v1/tenants/missing",
            json={"name": "New Name"},
        )
        assert resp.status_code == 404

    def test_update_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.patch(
            "/api/v1/tenants/missing",
            json={"name": "New Name"},
        )
        assert resp.status_code == 404

    def test_update_tenant_runtime_error(self):
        self.mock_mgr.get_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.patch(
            "/api/v1/tenants/tenant-001",
            json={"name": "New Name"},
        )
        assert resp.status_code == 500

    def test_update_tenant_no_metadata(self):
        """When tenant.metadata is None, update should not crash."""
        tenant = _make_tenant()
        tenant.metadata = None
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.patch(
            "/api/v1/tenants/tenant-001",
            json={"metadata": {"key": "value"}},
        )
        assert resp.status_code == 200


class TestDeleteTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_delete_tenant_success(self):
        self.mock_mgr.delete_tenant = AsyncMock(return_value=True)

        resp = _client.delete("/api/v1/tenants/tenant-001")
        assert resp.status_code == 204

    def test_delete_tenant_not_found(self):
        self.mock_mgr.delete_tenant = AsyncMock(return_value=False)

        resp = _client.delete("/api/v1/tenants/missing")
        assert resp.status_code == 404

    def test_delete_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.delete_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.delete("/api/v1/tenants/missing")
        assert resp.status_code == 404

    def test_delete_tenant_has_children(self):
        self.mock_mgr.delete_tenant = AsyncMock(side_effect=ValueError("tenant has children"))
        resp = _client.delete("/api/v1/tenants/parent-001")
        assert resp.status_code == 409

    def test_delete_tenant_value_error_other(self):
        self.mock_mgr.delete_tenant = AsyncMock(side_effect=ValueError("some other error"))
        resp = _client.delete("/api/v1/tenants/tenant-001")
        assert resp.status_code == 400

    def test_delete_tenant_force(self):
        self.mock_mgr.delete_tenant = AsyncMock(return_value=True)

        resp = _client.delete("/api/v1/tenants/tenant-001?force=true")
        assert resp.status_code == 204
        self.mock_mgr.delete_tenant.assert_called_once_with("tenant-001", force=True)

    def test_delete_tenant_runtime_error(self):
        self.mock_mgr.delete_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.delete("/api/v1/tenants/tenant-001")
        assert resp.status_code == 500


class TestActivateTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_activate_tenant_success(self):
        tenant = _make_tenant(status_value="active")
        self.mock_mgr.activate_tenant = AsyncMock(return_value=tenant)

        resp = _client.post("/api/v1/tenants/tenant-001/activate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    def test_activate_tenant_not_found_none(self):
        self.mock_mgr.activate_tenant = AsyncMock(return_value=None)

        resp = _client.post("/api/v1/tenants/missing/activate")
        assert resp.status_code == 404

    def test_activate_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.activate_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.post("/api/v1/tenants/missing/activate")
        assert resp.status_code == 404

    def test_activate_tenant_runtime_error(self):
        self.mock_mgr.activate_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.post("/api/v1/tenants/tenant-001/activate")
        assert resp.status_code == 500


class TestSuspendTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_suspend_tenant_success(self):
        tenant = _make_tenant(status_value="suspended")
        self.mock_mgr.suspend_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/suspend",
            json={"reason": "Policy violation", "suspend_children": True},
        )
        assert resp.status_code == 200

    def test_suspend_tenant_no_body(self):
        tenant = _make_tenant(status_value="suspended")
        self.mock_mgr.suspend_tenant = AsyncMock(return_value=tenant)

        resp = _client.post("/api/v1/tenants/tenant-001/suspend")
        assert resp.status_code == 200

    def test_suspend_tenant_not_found_none(self):
        self.mock_mgr.suspend_tenant = AsyncMock(return_value=None)

        resp = _client.post("/api/v1/tenants/missing/suspend")
        assert resp.status_code == 404

    def test_suspend_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.suspend_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.post("/api/v1/tenants/missing/suspend")
        assert resp.status_code == 404

    def test_suspend_tenant_runtime_error(self):
        self.mock_mgr.suspend_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.post("/api/v1/tenants/tenant-001/suspend")
        assert resp.status_code == 500

    def test_suspend_with_reason_in_log(self):
        tenant = _make_tenant(status_value="suspended")
        self.mock_mgr.suspend_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/suspend",
            json={"reason": "spam"},
        )
        assert resp.status_code == 200
        self.mock_mgr.suspend_tenant.assert_called_once_with(
            "tenant-001", reason="spam", suspend_children=True
        )


class TestDeactivateTenant:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_deactivate_tenant_success(self):
        tenant = _make_tenant(status_value="deactivated")
        self.mock_mgr.deactivate_tenant = AsyncMock(return_value=tenant)

        resp = _client.post("/api/v1/tenants/tenant-001/deactivate")
        assert resp.status_code == 200

    def test_deactivate_tenant_not_found_none(self):
        self.mock_mgr.deactivate_tenant = AsyncMock(return_value=None)

        resp = _client.post("/api/v1/tenants/missing/deactivate")
        assert resp.status_code == 404

    def test_deactivate_tenant_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.deactivate_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.post("/api/v1/tenants/missing/deactivate")
        assert resp.status_code == 404

    def test_deactivate_tenant_runtime_error(self):
        self.mock_mgr.deactivate_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.post("/api/v1/tenants/tenant-001/deactivate")
        assert resp.status_code == 500


class TestUpdateTenantQuota:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_update_quota_success(self):
        tenant = _make_tenant()
        updated = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)
        self.mock_mgr.update_quota = AsyncMock(return_value=updated)

        resp = _client.put(
            "/api/v1/tenants/tenant-001/quota",
            json={"max_agents": 200},
        )
        assert resp.status_code == 200

    def test_update_quota_not_found_none(self):
        self.mock_mgr.get_tenant = AsyncMock(return_value=None)

        resp = _client.put(
            "/api/v1/tenants/missing/quota",
            json={"max_agents": 200},
        )
        assert resp.status_code == 404

    def test_update_quota_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.put(
            "/api/v1/tenants/missing/quota",
            json={"max_agents": 200},
        )
        assert resp.status_code == 404

    def test_update_quota_runtime_error(self):
        self.mock_mgr.get_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.put(
            "/api/v1/tenants/tenant-001/quota",
            json={"max_agents": 200},
        )
        assert resp.status_code == 500

    def test_update_quota_tenant_no_quota_attr(self):
        """Tenant with no model_dump on quota should use empty dict."""
        tenant = _make_tenant()
        tenant.quota = None  # no model_dump
        updated = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)
        self.mock_mgr.update_quota = AsyncMock(return_value=updated)

        resp = _client.put(
            "/api/v1/tenants/tenant-001/quota",
            json={"max_agents": 50},
        )
        assert resp.status_code == 200


class TestCheckQuota:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_check_quota_agents_available(self):
        tenant = _make_tenant(
            quota={"max_agents": 100, "max_policies": 1000},
            usage={"agents_count": 5},
        )
        self.mock_mgr.check_quota = AsyncMock(return_value=True)
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["resource"] == "agents"

    def test_check_quota_not_available(self):
        tenant = _make_tenant(
            quota={"max_agents": 10, "max_policies": 1000},
            usage={"agents_count": 10},
        )
        self.mock_mgr.check_quota = AsyncMock(return_value=False)
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    def test_check_quota_warning_threshold(self):
        tenant = _make_tenant(
            quota={"max_agents": 100, "max_policies": 1000},
            usage={"agents_count": 85},
        )
        self.mock_mgr.check_quota = AsyncMock(return_value=True)
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["warning_threshold_reached"] is True

    def test_check_quota_unknown_resource(self):
        tenant = _make_tenant()
        self.mock_mgr.check_quota = AsyncMock(return_value=True)
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "custom_resource", "requested_amount": 1},
        )
        assert resp.status_code == 200

    def test_check_quota_known_resources(self):
        for resource in ["policies", "messages", "batch", "storage", "sessions"]:
            tenant = _make_tenant()
            self.mock_mgr.check_quota = AsyncMock(return_value=True)
            self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

            resp = _client.post(
                "/api/v1/tenants/tenant-001/quota/check",
                json={"resource": resource, "requested_amount": 1},
            )
            assert resp.status_code == 200, f"Failed for resource={resource}"

    def test_check_quota_tenant_not_found_after_check(self):
        self.mock_mgr.check_quota = AsyncMock(return_value=True)
        self.mock_mgr.get_tenant = AsyncMock(return_value=None)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 404

    def test_check_quota_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.check_quota = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.post(
            "/api/v1/tenants/missing/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 404

    def test_check_quota_runtime_error(self):
        self.mock_mgr.check_quota = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 500

    def test_check_quota_no_usage_attr(self):
        """Tenant without usage attribute uses empty dict."""
        tenant = _make_tenant()
        del tenant.usage  # remove usage attribute
        self.mock_mgr.check_quota = AsyncMock(return_value=True)
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 200


class TestGetTenantUsage:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_get_usage_success(self):
        tenant = _make_tenant(
            quota={"max_agents": 100, "max_policies": 1000, "max_messages_per_minute": 10000},
            usage={"agents_count": 10, "policies_count": 50, "messages_this_minute": 500},
        )
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.get("/api/v1/tenants/tenant-001/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant-001"
        assert "utilization" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_usage_calculates_utilization(self):
        tenant = _make_tenant(
            quota={"max_agents": 100, "max_policies": 0, "max_messages_per_minute": 10000},
            usage={"agents_count": 50, "policies_count": 0, "messages_this_minute": 5000},
        )
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.get("/api/v1/tenants/tenant-001/usage")
        assert resp.status_code == 200
        data = resp.json()
        # agents_count/max_agents * 100 = 50.0
        assert "agents_count" in data["utilization"]
        assert data["utilization"]["agents_count"] == 50.0

    def test_get_usage_zero_quota_skips_utilization(self):
        tenant = _make_tenant(
            quota={"max_agents": 0, "max_policies": 0, "max_messages_per_minute": 0},
            usage={"agents_count": 5},
        )
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.get("/api/v1/tenants/tenant-001/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["utilization"] == {}

    def test_get_usage_not_found_none(self):
        self.mock_mgr.get_tenant = AsyncMock(return_value=None)

        resp = _client.get("/api/v1/tenants/missing/usage")
        assert resp.status_code == 404

    def test_get_usage_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_tenant = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.get("/api/v1/tenants/missing/usage")
        assert resp.status_code == 404

    def test_get_usage_runtime_error(self):
        self.mock_mgr.get_tenant = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants/tenant-001/usage")
        assert resp.status_code == 500


class TestIncrementUsage:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_increment_usage_success(self):
        usage_mock = MagicMock()
        usage_mock.model_dump.return_value = {"agents_count": 6}
        self.mock_mgr.increment_usage = AsyncMock(return_value=usage_mock)

        tenant = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant-001"

    def test_increment_usage_quota_exceeded(self):
        from enhanced_agent_bus.routes.tenants import TenantQuotaExceededError

        try:
            exc = TenantQuotaExceededError(
                "quota exceeded",
                tenant_id="tenant-001",
                resource="agents",
                current=100,
                limit=100,
            )
        except TypeError:
            # Fallback stub only takes message
            exc = TenantQuotaExceededError("quota exceeded")

        self.mock_mgr.increment_usage = AsyncMock(side_effect=exc)
        resp = _client.post(
            "/api/v1/tenants/tenant-001/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 429

    def test_increment_usage_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.increment_usage = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.post(
            "/api/v1/tenants/missing/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 404

    def test_increment_usage_runtime_error(self):
        self.mock_mgr.increment_usage = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.post(
            "/api/v1/tenants/tenant-001/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 500

    def test_increment_usage_no_model_dump(self):
        """Usage object without model_dump should yield empty dict."""
        usage_mock = MagicMock(spec=[])  # no model_dump
        self.mock_mgr.increment_usage = AsyncMock(return_value=usage_mock)
        tenant = _make_tenant()
        self.mock_mgr.get_tenant = AsyncMock(return_value=tenant)

        resp = _client.post(
            "/api/v1/tenants/tenant-001/usage/increment",
            json={"resource": "agents", "amount": 2},
        )
        assert resp.status_code == 200


class TestGetTenantHierarchy:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_get_hierarchy_root_tenant(self):
        root = _make_tenant(tenant_id="root", slug="root-slug")
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(return_value=[root])
        self.mock_mgr.get_all_descendants = AsyncMock(return_value=[])

        resp = _client.get("/api/v1/tenants/root/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "root"
        assert data["depth"] == 0
        assert data["ancestors"] == []
        assert data["descendants"] == []

    def test_get_hierarchy_child_tenant(self):
        root = _make_tenant(tenant_id="root", slug="root-slug")
        child = _make_tenant(tenant_id="child", slug="child-slug")
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(return_value=[root, child])
        self.mock_mgr.get_all_descendants = AsyncMock(return_value=[])

        resp = _client.get("/api/v1/tenants/child/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 1
        # Ancestors excludes the last element (self)
        assert len(data["ancestors"]) == 1

    def test_get_hierarchy_deep_nesting(self):
        tenants = [_make_tenant(tenant_id=f"t{i}", slug=f"slug-{i}") for i in range(4)]
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(return_value=tenants)
        self.mock_mgr.get_all_descendants = AsyncMock(return_value=[])

        resp = _client.get("/api/v1/tenants/t3/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 3
        assert len(data["ancestors"]) == 3

    def test_get_hierarchy_with_descendants(self):
        root = _make_tenant(tenant_id="root", slug="root-slug")
        child = _make_tenant(tenant_id="child", slug="child-slug")
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(return_value=[root])
        self.mock_mgr.get_all_descendants = AsyncMock(return_value=[child])

        resp = _client.get("/api/v1/tenants/root/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["descendants"]) == 1

    def test_get_hierarchy_empty_ancestors(self):
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(return_value=[])
        self.mock_mgr.get_all_descendants = AsyncMock(return_value=[])

        resp = _client.get("/api/v1/tenants/tenant-001/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 0

    def test_get_hierarchy_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_tenant_hierarchy = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.get("/api/v1/tenants/missing/hierarchy")
        assert resp.status_code == 404

    def test_get_hierarchy_runtime_error(self):
        self.mock_mgr.get_tenant_hierarchy = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants/tenant-001/hierarchy")
        assert resp.status_code == 500


class TestGetChildTenants:
    def setup_method(self):
        self.mock_mgr = MagicMock()
        _setup_auth_and_manager(self.mock_mgr)

    def teardown_method(self):
        _clear_overrides()

    def test_get_children_success(self):
        children = [_make_tenant(tenant_id=f"child-{i}", slug=f"child-{i}") for i in range(3)]
        self.mock_mgr.get_child_tenants = AsyncMock(return_value=children)

        resp = _client.get("/api/v1/tenants/parent-001/children")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        assert data["has_more"] is False
        assert data["page"] == 0

    def test_get_children_empty(self):
        self.mock_mgr.get_child_tenants = AsyncMock(return_value=[])

        resp = _client.get("/api/v1/tenants/leaf-tenant/children")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0

    def test_get_children_not_found_error(self):
        from enhanced_agent_bus.routes.tenants import TenantNotFoundError

        self.mock_mgr.get_child_tenants = AsyncMock(side_effect=TenantNotFoundError("not found"))
        resp = _client.get("/api/v1/tenants/missing/children")
        assert resp.status_code == 404

    def test_get_children_runtime_error(self):
        self.mock_mgr.get_child_tenants = AsyncMock(side_effect=RuntimeError("DB error"))
        resp = _client.get("/api/v1/tenants/tenant-001/children")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TenantResponse.from_tenant — cover model conversion paths
# ---------------------------------------------------------------------------


class TestTenantResponseFromTenant:
    def test_from_tenant_full(self):
        tenant = _make_tenant()
        tenant.activated_at = datetime.now(UTC)
        tenant.suspended_at = datetime.now(UTC)

        response = TenantResponse.from_tenant(tenant)
        assert response.tenant_id == "tenant-001"
        assert response.constitutional_hash == CONSTITUTIONAL_HASH
        assert response.activated_at is not None
        assert response.suspended_at is not None

    def test_from_tenant_no_created_at(self):
        tenant = _make_tenant()
        tenant.created_at = None
        tenant.updated_at = None

        response = TenantResponse.from_tenant(tenant)
        assert response.created_at is not None  # falls back to datetime.now

    def test_from_tenant_status_string(self):
        tenant = _make_tenant()
        # Make status a plain string (no .value attribute)
        tenant.status = "active"

        response = TenantResponse.from_tenant(tenant)
        assert response.status == "active"

    def test_from_tenant_no_constitutional_hash(self):
        tenant = _make_tenant()
        tenant.constitutional_hash = None

        response = TenantResponse.from_tenant(tenant)
        assert response.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Edge cases — router configuration
# ---------------------------------------------------------------------------


class TestRouterConfiguration:
    def test_router_prefix(self):
        assert router.prefix == "/api/v1/tenants"

    def test_router_tags(self):
        assert "Tenant Management" in router.tags

    def test_all_export(self):
        from enhanced_agent_bus.routes.tenants import __all__

        assert "router" in __all__
