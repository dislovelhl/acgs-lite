"""
Coverage tests for src/core/enhanced_agent_bus/routes/tenants.py
Constitutional Hash: 608508a9bd224290

Targets missing lines to boost coverage from 70% to 92%+.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import the module under test once (after conftest has been loaded)
# ---------------------------------------------------------------------------
import enhanced_agent_bus.routes.tenants as _tenants_mod
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ACGSBaseError

# The admin key that we will patch into the module for each test.
_TEST_ADMIN_KEY = "test-coverage-admin-key-xyz"

# ---------------------------------------------------------------------------
# Shared mock objects
# ---------------------------------------------------------------------------


class _FakeStatus:
    """Enum-like status with a .value attribute."""

    def __init__(self, val: str) -> None:
        self.value = val

    def __str__(self) -> str:
        return self.value


class _FakeConfig:
    def model_dump(self) -> dict:
        return {}


class _FakeQuota:
    def __init__(self, **kw: Any) -> None:
        self.max_agents = kw.get("max_agents", 100)
        self.max_policies = kw.get("max_policies", 1000)
        self.max_messages_per_minute = kw.get("max_messages_per_minute", 10000)
        self.max_batch_size = kw.get("max_batch_size", 1000)
        self.max_storage_mb = kw.get("max_storage_mb", 10240)
        self.max_concurrent_sessions = kw.get("max_concurrent_sessions", 100)

    def model_dump(self) -> dict:
        return {
            "max_agents": self.max_agents,
            "max_policies": self.max_policies,
            "max_messages_per_minute": self.max_messages_per_minute,
            "max_batch_size": self.max_batch_size,
            "max_storage_mb": self.max_storage_mb,
            "max_concurrent_sessions": self.max_concurrent_sessions,
        }


class _FakeUsage:
    def __init__(self, **kw: Any) -> None:
        self.agents_count = kw.get("agents_count", 0)
        self.policies_count = kw.get("policies_count", 0)
        self.messages_this_minute = kw.get("messages_this_minute", 0)

    def model_dump(self) -> dict:
        return {
            "agents_count": self.agents_count,
            "policies_count": self.policies_count,
            "messages_this_minute": self.messages_this_minute,
        }


def make_tenant(
    tenant_id: str | None = None,
    name: str = "Test Tenant",
    slug: str = "test-tenant",
    status: str | _FakeStatus = "active",
    parent_tenant_id: str | None = None,
    quota: _FakeQuota | None = None,
    usage: _FakeUsage | None = None,
    activated_at: datetime | None = None,
    suspended_at: datetime | None = None,
) -> MagicMock:
    t = MagicMock()
    t.tenant_id = tenant_id or str(uuid.uuid4())
    t.name = name
    t.slug = slug
    t.status = _FakeStatus(status) if isinstance(status, str) else status
    t.parent_tenant_id = parent_tenant_id
    t.config = _FakeConfig()
    t.quota = quota or _FakeQuota()
    t.usage = usage or _FakeUsage()
    t.metadata = {}
    t.created_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    t.activated_at = activated_at
    t.suspended_at = suspended_at
    t.constitutional_hash = CONSTITUTIONAL_HASH
    return t


class _FakeNotFoundError(ACGSBaseError):
    http_status_code = 404
    error_code = "TENANT_NOT_FOUND"


class _FakeQuotaExceededError(ACGSBaseError):
    http_status_code = 429
    error_code = "TENANT_QUOTA_EXCEEDED"


class _FakeValidationError(ACGSBaseError):
    http_status_code = 400
    error_code = "TENANT_VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Client factory — patches module-level vars so auth works predictably
# ---------------------------------------------------------------------------


def _build_client(mock_manager: Any) -> TestClient:
    """Build a TestClient with the tenants router mounted.

    Patches the module-level TENANT_ADMIN_KEY so tests are not affected by
    whatever value was set at import time (which depends on conftest order).
    """
    _tenants_mod.get_tenant_manager = lambda: mock_manager  # type: ignore[assignment]
    _tenants_mod.TenantNotFoundError = _FakeNotFoundError  # type: ignore[assignment]
    _tenants_mod.TenantQuotaExceededError = _FakeQuotaExceededError  # type: ignore[assignment]
    _tenants_mod.TenantValidationError = _FakeValidationError  # type: ignore[assignment]

    app = FastAPI()
    app.include_router(_tenants_mod.router)
    return TestClient(app, raise_server_exceptions=False)


def _manager() -> MagicMock:
    mgr = MagicMock()
    for method in (
        "create_tenant",
        "get_tenant",
        "get_tenant_by_slug",
        "list_tenants",
        "update_config",
        "delete_tenant",
        "activate_tenant",
        "suspend_tenant",
        "deactivate_tenant",
        "update_quota",
        "check_quota",
        "increment_usage",
        "get_tenant_hierarchy",
        "get_all_descendants",
        "get_child_tenants",
    ):
        setattr(mgr, method, AsyncMock())
    return mgr


# Fixture that patches TENANT_ADMIN_KEY on the module for every test
@pytest.fixture(autouse=True)
def _patch_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", _TEST_ADMIN_KEY)
    monkeypatch.setattr(_tenants_mod, "TENANT_AUTH_MODE", "strict")
    monkeypatch.setattr(_tenants_mod, "NORMALIZED_ENVIRONMENT", "development")


# All tests use this header
ADMIN_HEADERS = {"X-Admin-Key": _TEST_ADMIN_KEY}


# ===========================================================================
# 1. Helper: _to_dict_safe
# ===========================================================================


def test_to_dict_safe_none():
    assert _tenants_mod._to_dict_safe(None) == {}


def test_to_dict_safe_dict():
    assert _tenants_mod._to_dict_safe({"k": "v"}) == {"k": "v"}


def test_to_dict_safe_model_dump():
    obj = MagicMock()
    obj.model_dump.return_value = {"a": 1}
    assert _tenants_mod._to_dict_safe(obj) == {"a": 1}


def test_to_dict_safe_to_dict():
    obj = MagicMock(spec=["to_dict"])
    obj.to_dict.return_value = {"b": 2}
    assert _tenants_mod._to_dict_safe(obj) == {"b": 2}


def test_to_dict_safe_dataclass():
    from dataclasses import dataclass

    @dataclass
    class Pt:
        x: int = 1

    assert _tenants_mod._to_dict_safe(Pt()) == {"x": 1}


def test_to_dict_safe_unserializable():
    class Bad:
        pass

    assert _tenants_mod._to_dict_safe(Bad()) == {}


# ===========================================================================
# 2. Auth helper functions
# ===========================================================================


def test_is_production_runtime_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "NORMALIZED_ENVIRONMENT", "development")
    assert _tenants_mod._is_production_runtime() is False


def test_is_production_runtime_true(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "NORMALIZED_ENVIRONMENT", "production")
    assert _tenants_mod._is_production_runtime() is True


def test_has_auth_configuration_with_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", "some-key")
    assert _tenants_mod._has_auth_configuration() is True


def test_has_auth_configuration_no_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", "")
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", "")
    assert _tenants_mod._has_auth_configuration() is False


def test_validate_admin_api_key_no_admin_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", "")
    assert _tenants_mod._validate_admin_api_key("anything") is False


def test_validate_admin_api_key_correct():
    assert _tenants_mod._validate_admin_api_key(_TEST_ADMIN_KEY) is True


def test_validate_admin_api_key_wrong():
    assert _tenants_mod._validate_admin_api_key("wrong-key") is False


def test_validate_jwt_token_no_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", "")
    assert _tenants_mod._validate_jwt_token("some.token.here") is None


# ===========================================================================
# 3. Authentication flows via HTTP
# ===========================================================================


def test_auth_no_key_returns_401():
    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants")
    assert resp.status_code == 401


def test_auth_wrong_key_returns_401():
    mgr = _manager()
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers={"X-Admin-Key": "wrong-key"})
    assert resp.status_code == 401


def test_auth_correct_key_passes():
    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


# ===========================================================================
# 4. POST /api/v1/tenants — create tenant
# ===========================================================================

CREATE_PAYLOAD = {
    "name": "Acme Corp",
    "slug": "acme-corp",
    "auto_activate": False,
}


def test_create_tenant_success():
    mgr = _manager()
    mgr.create_tenant.return_value = make_tenant(slug="acme-corp", name="Acme Corp")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants", json=CREATE_PAYLOAD, headers=ADMIN_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "acme-corp"
    assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


def test_create_tenant_with_quota_and_config():
    mgr = _manager()
    mgr.create_tenant.return_value = make_tenant(slug="acme-corp")
    client = _build_client(mgr)
    payload = {
        **CREATE_PAYLOAD,
        "quota": {"max_agents": 50},
        "config": {"theme": "dark"},
    }
    resp = client.post("/api/v1/tenants", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 201


def test_create_tenant_auto_activate():
    mgr = _manager()
    t = make_tenant(slug="auto-co", activated_at=datetime.now(UTC))
    mgr.create_tenant.return_value = t
    client = _build_client(mgr)
    payload = {"name": "Auto Co", "slug": "auto-co", "auto_activate": True}
    resp = client.post("/api/v1/tenants", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 201


def test_create_tenant_validation_error():
    mgr = _manager()
    mgr.create_tenant.side_effect = _FakeValidationError("bad slug")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants", json=CREATE_PAYLOAD, headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_create_tenant_duplicate_slug_409():
    mgr = _manager()
    mgr.create_tenant.side_effect = ValueError("slug already exists")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants", json=CREATE_PAYLOAD, headers=ADMIN_HEADERS)
    assert resp.status_code == 409


def test_create_tenant_value_error_non_duplicate():
    mgr = _manager()
    mgr.create_tenant.side_effect = ValueError("some other error")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants", json=CREATE_PAYLOAD, headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_create_tenant_runtime_error_500():
    mgr = _manager()
    mgr.create_tenant.side_effect = RuntimeError("boom")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants", json=CREATE_PAYLOAD, headers=ADMIN_HEADERS)
    assert resp.status_code == 500


def test_create_tenant_parent_id():
    mgr = _manager()
    mgr.create_tenant.return_value = make_tenant(slug="child-org", parent_tenant_id="parent-123")
    client = _build_client(mgr)
    payload = {**CREATE_PAYLOAD, "slug": "child-org", "parent_tenant_id": "parent-123"}
    resp = client.post("/api/v1/tenants", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 201


# ===========================================================================
# 5. GET /api/v1/tenants/{tenant_id} — get tenant
# ===========================================================================


def test_get_tenant_found():
    mgr = _manager()
    t = make_tenant(tenant_id="tid-001")
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/tid-001", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "tid-001"


def test_get_tenant_not_found_none():
    mgr = _manager()
    mgr.get_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/missing", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_tenant_not_found_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = _FakeNotFoundError("not found")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/missing", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_tenant_runtime_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = RuntimeError("db error")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t1", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 6. GET /api/v1/tenants/by-slug/{slug}
# ===========================================================================


def test_get_by_slug_found():
    mgr = _manager()
    mgr.get_tenant_by_slug.return_value = make_tenant(slug="acme-co")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/by-slug/acme-co", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_get_by_slug_not_found():
    mgr = _manager()
    mgr.get_tenant_by_slug.return_value = None
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/by-slug/ghost", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_by_slug_runtime_error():
    mgr = _manager()
    mgr.get_tenant_by_slug.side_effect = RuntimeError("db down")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/by-slug/ghost", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 7. GET /api/v1/tenants — list tenants
# ===========================================================================


def test_list_tenants_empty():
    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 0
    assert body["has_more"] is False


def test_list_tenants_with_results():
    mgr = _manager()
    tenants = [make_tenant(slug=f"t{i}") for i in range(3)]
    mgr.list_tenants.return_value = tenants
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()["tenants"]) == 3


def test_list_tenants_has_more():
    mgr = _manager()
    tenants = [make_tenant(slug=f"t{i}") for i in range(21)]
    mgr.list_tenants.return_value = tenants
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants?limit=20", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_more"] is True
    assert len(body["tenants"]) == 20


def test_list_tenants_status_filter_valid():
    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants?status=active", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_list_tenants_status_filter_invalid():
    mgr = _manager()
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants?status=BOGUS", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_list_tenants_runtime_error():
    mgr = _manager()
    mgr.list_tenants.side_effect = RuntimeError("db fail")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 8. PATCH /api/v1/tenants/{tenant_id} — update tenant
# ===========================================================================


def test_update_tenant_name_only():
    mgr = _manager()
    t = make_tenant(tenant_id="tid-002", name="Old Name")
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/tid-002",
        json={"name": "New Name"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_update_tenant_config():
    mgr = _manager()
    t = make_tenant(tenant_id="tid-003")
    mgr.get_tenant.return_value = t
    mgr.update_config.return_value = t
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/tid-003",
        json={"config": {"theme": "light"}},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_update_tenant_metadata():
    mgr = _manager()
    t = make_tenant(tenant_id="tid-004")
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/tid-004",
        json={"metadata": {"owner": "alice"}},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_update_tenant_not_found():
    mgr = _manager()
    mgr.get_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/ghost",
        json={"name": "x"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_update_tenant_not_found_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/ghost",
        json={"name": "x"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_update_tenant_runtime_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.patch(
        "/api/v1/tenants/t1",
        json={"name": "x"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 500


# ===========================================================================
# 9. DELETE /api/v1/tenants/{tenant_id}
# ===========================================================================


def test_delete_tenant_success():
    mgr = _manager()
    mgr.delete_tenant.return_value = True
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/tid-del", headers=ADMIN_HEADERS)
    assert resp.status_code == 204


def test_delete_tenant_not_found():
    mgr = _manager()
    mgr.delete_tenant.return_value = False
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/ghost", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_delete_tenant_not_found_error():
    mgr = _manager()
    mgr.delete_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/ghost", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_delete_tenant_children_conflict():
    mgr = _manager()
    mgr.delete_tenant.side_effect = ValueError("has children")
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/parent", headers=ADMIN_HEADERS)
    assert resp.status_code == 409


def test_delete_tenant_value_error_other():
    mgr = _manager()
    mgr.delete_tenant.side_effect = ValueError("other error")
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/t1", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_delete_tenant_force():
    mgr = _manager()
    mgr.delete_tenant.return_value = True
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/tid-del?force=true", headers=ADMIN_HEADERS)
    assert resp.status_code == 204
    mgr.delete_tenant.assert_awaited_once_with("tid-del", force=True)


def test_delete_tenant_runtime_error():
    mgr = _manager()
    mgr.delete_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.delete("/api/v1/tenants/t1", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 10. POST /api/v1/tenants/{tenant_id}/activate
# ===========================================================================


def test_activate_tenant_success():
    mgr = _manager()
    t = make_tenant(tenant_id="t-act", activated_at=datetime.now(UTC))
    mgr.activate_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t-act/activate", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_activate_tenant_not_found_none():
    mgr = _manager()
    mgr.activate_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/activate", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_activate_tenant_not_found_error():
    mgr = _manager()
    mgr.activate_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/activate", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_activate_tenant_runtime_error():
    mgr = _manager()
    mgr.activate_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t1/activate", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 11. POST /api/v1/tenants/{tenant_id}/suspend
# ===========================================================================


def test_suspend_tenant_success_with_reason():
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-sus",
        status="suspended",
        suspended_at=datetime.now(UTC),
    )
    mgr.suspend_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-sus/suspend",
        json={"reason": "Billing overdue", "suspend_children": True},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_suspend_tenant_no_body():
    mgr = _manager()
    t = make_tenant(tenant_id="t-sus2", status="suspended")
    mgr.suspend_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t-sus2/suspend", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_suspend_tenant_not_found_none():
    mgr = _manager()
    mgr.suspend_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/suspend", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_suspend_tenant_not_found_error():
    mgr = _manager()
    mgr.suspend_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/suspend", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_suspend_tenant_runtime_error():
    mgr = _manager()
    mgr.suspend_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t1/suspend", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 12. POST /api/v1/tenants/{tenant_id}/deactivate
# ===========================================================================


def test_deactivate_tenant_success():
    mgr = _manager()
    t = make_tenant(tenant_id="t-deac", status="deactivated")
    mgr.deactivate_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t-deac/deactivate", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_deactivate_tenant_not_found_none():
    mgr = _manager()
    mgr.deactivate_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/deactivate", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_deactivate_tenant_not_found_error():
    mgr = _manager()
    mgr.deactivate_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/ghost/deactivate", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_deactivate_tenant_runtime_error():
    mgr = _manager()
    mgr.deactivate_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.post("/api/v1/tenants/t1/deactivate", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 13. PUT /api/v1/tenants/{tenant_id}/quota
# ===========================================================================


def test_update_quota_success():
    mgr = _manager()
    t = make_tenant(tenant_id="t-quota")
    mgr.get_tenant.return_value = t
    mgr.update_quota.return_value = t
    client = _build_client(mgr)
    resp = client.put(
        "/api/v1/tenants/t-quota/quota",
        json={"max_agents": 200},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_update_quota_tenant_not_found():
    mgr = _manager()
    mgr.get_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.put(
        "/api/v1/tenants/ghost/quota",
        json={"max_agents": 200},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_update_quota_not_found_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.put(
        "/api/v1/tenants/ghost/quota",
        json={"max_agents": 200},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_update_quota_runtime_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.put(
        "/api/v1/tenants/t1/quota",
        json={"max_agents": 200},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 500


# ===========================================================================
# 14. POST /api/v1/tenants/{tenant_id}/quota/check
# ===========================================================================


def test_check_quota_available():
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-chk",
        quota=_FakeQuota(max_agents=100),
        usage=_FakeUsage(agents_count=10),
    )
    mgr.check_quota.return_value = True
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-chk/quota/check",
        json={"resource": "agents", "requested_amount": 5},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["resource"] == "agents"


def test_check_quota_unavailable():
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-chk2",
        quota=_FakeQuota(max_agents=10),
        usage=_FakeUsage(agents_count=10),
    )
    mgr.check_quota.return_value = False
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-chk2/quota/check",
        json={"resource": "agents", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_check_quota_tenant_not_found_after_check():
    mgr = _manager()
    mgr.check_quota.return_value = True
    mgr.get_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/ghost/quota/check",
        json={"resource": "agents", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_check_quota_unknown_resource():
    mgr = _manager()
    t = make_tenant(tenant_id="t-chk3")
    mgr.check_quota.return_value = True
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-chk3/quota/check",
        json={"resource": "custom_res", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200


def test_check_quota_not_found_error():
    mgr = _manager()
    mgr.check_quota.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/ghost/quota/check",
        json={"resource": "agents", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_check_quota_runtime_error():
    mgr = _manager()
    mgr.check_quota.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t1/quota/check",
        json={"resource": "agents", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 500


# ===========================================================================
# 15. GET /api/v1/tenants/{tenant_id}/usage
# ===========================================================================


def test_get_usage_success():
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-usg",
        quota=_FakeQuota(max_agents=100, max_policies=1000, max_messages_per_minute=5000),
        usage=_FakeUsage(agents_count=20, policies_count=100, messages_this_minute=500),
    )
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t-usg/usage", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "utilization" in body
    assert body["tenant_id"] == "t-usg"


def test_get_usage_tenant_not_found():
    mgr = _manager()
    mgr.get_tenant.return_value = None
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/ghost/usage", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_usage_not_found_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/ghost/usage", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_usage_runtime_error():
    mgr = _manager()
    mgr.get_tenant.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t1/usage", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 16. POST /api/v1/tenants/{tenant_id}/usage/increment
# ===========================================================================


def test_increment_usage_success():
    mgr = _manager()
    t = make_tenant(tenant_id="t-inc")
    usage = _FakeUsage(agents_count=1)
    mgr.increment_usage.return_value = usage
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-inc/usage/increment",
        json={"resource": "agents", "amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "t-inc"


def test_increment_usage_quota_exceeded():
    mgr = _manager()
    mgr.increment_usage.side_effect = _FakeQuotaExceededError("quota exceeded")
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t1/usage/increment",
        json={"resource": "agents", "amount": 100},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 429


def test_increment_usage_not_found():
    mgr = _manager()
    mgr.increment_usage.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/ghost/usage/increment",
        json={"resource": "agents", "amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_increment_usage_runtime_error():
    mgr = _manager()
    mgr.increment_usage.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t1/usage/increment",
        json={"resource": "agents", "amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 500


# ===========================================================================
# 17. GET /api/v1/tenants/{tenant_id}/hierarchy
# ===========================================================================


def test_get_hierarchy_success_no_ancestors():
    mgr = _manager()
    root = make_tenant(tenant_id="t-root")
    child = make_tenant(tenant_id="t-child")
    mgr.get_tenant_hierarchy.return_value = [root]
    mgr.get_all_descendants.return_value = [child]
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t-root/hierarchy", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "t-root"
    assert body["depth"] == 0
    assert len(body["descendants"]) == 1


def test_get_hierarchy_with_ancestors():
    mgr = _manager()
    grandparent = make_tenant(tenant_id="gp")
    parent = make_tenant(tenant_id="par")
    current = make_tenant(tenant_id="cur")
    mgr.get_tenant_hierarchy.return_value = [grandparent, parent, current]
    mgr.get_all_descendants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/cur/hierarchy", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["depth"] == 2
    assert len(body["ancestors"]) == 2


def test_get_hierarchy_not_found():
    mgr = _manager()
    mgr.get_tenant_hierarchy.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/ghost/hierarchy", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_hierarchy_runtime_error():
    mgr = _manager()
    mgr.get_tenant_hierarchy.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t1/hierarchy", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 18. GET /api/v1/tenants/{tenant_id}/children
# ===========================================================================


def test_get_children_success():
    mgr = _manager()
    children = [make_tenant(slug=f"child-{i}") for i in range(2)]
    mgr.get_child_tenants.return_value = children
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t-parent/children", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tenants"]) == 2
    assert body["has_more"] is False


def test_get_children_empty():
    mgr = _manager()
    mgr.get_child_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t-leaf/children", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 0


def test_get_children_not_found():
    mgr = _manager()
    mgr.get_child_tenants.side_effect = _FakeNotFoundError("nf")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/ghost/children", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


def test_get_children_runtime_error():
    mgr = _manager()
    mgr.get_child_tenants.side_effect = RuntimeError("crash")
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t1/children", headers=ADMIN_HEADERS)
    assert resp.status_code == 500


# ===========================================================================
# 19. get_manager dependency 503 path
# ===========================================================================


def test_get_manager_503_when_factory_raises(monkeypatch: pytest.MonkeyPatch):
    original = _tenants_mod.get_tenant_manager

    def _bad():
        raise RuntimeError("no manager")

    monkeypatch.setattr(_tenants_mod, "get_tenant_manager", _bad)

    app = FastAPI()
    app.include_router(_tenants_mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/tenants", headers=ADMIN_HEADERS)
    assert resp.status_code == 503


# ===========================================================================
# 20. Development-mode auth bypass
# ===========================================================================


def test_dev_mode_auth_bypass(monkeypatch: pytest.MonkeyPatch):
    mgr = _manager()
    mgr.list_tenants.return_value = []
    monkeypatch.setattr(_tenants_mod, "TENANT_AUTH_MODE", "development")
    monkeypatch.setattr(_tenants_mod, "NORMALIZED_ENVIRONMENT", "development")
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", "")

    client = _build_client(mgr)
    resp = client.get(
        "/api/v1/tenants",
        headers={"X-Admin-Key": "any-key-works-in-dev"},
    )
    # Dev bypass should return 200 (not 401)
    assert resp.status_code == 200


# ===========================================================================
# 21. Quota check — warning threshold reached
# ===========================================================================


def test_check_quota_warning_threshold():
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-warn",
        quota=_FakeQuota(max_agents=100),
        usage=_FakeUsage(agents_count=85),  # 85% >= 80% threshold
    )
    mgr.check_quota.return_value = True
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.post(
        "/api/v1/tenants/t-warn/quota/check",
        json={"resource": "agents", "requested_amount": 1},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["warning_threshold_reached"] is True


# ===========================================================================
# 22. Production mode security guard
# ===========================================================================


def test_production_no_auth_config_returns_503(monkeypatch: pytest.MonkeyPatch):
    mgr = _manager()
    monkeypatch.setattr(_tenants_mod, "NORMALIZED_ENVIRONMENT", "production")
    monkeypatch.setattr(_tenants_mod, "TENANT_ADMIN_KEY", "")
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", "")

    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants", headers={"X-Admin-Key": "any"})
    assert resp.status_code == 503


# ===========================================================================
# 23. X-Admin-Tenant-ID header is forwarded
# ===========================================================================


def test_admin_tenant_id_header_forwarded():
    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)
    resp = client.get(
        "/api/v1/tenants",
        headers={**ADMIN_HEADERS, "X-Admin-Tenant-ID": "my-admin-tenant"},
    )
    assert resp.status_code == 200


# ===========================================================================
# 24. JWT token validation paths (lines 230-268, 313-330)
# ===========================================================================


def test_validate_jwt_token_valid_controller_role(monkeypatch: pytest.MonkeyPatch):
    """Valid JWT with CONTROLLER role returns payload (lines 230-251)."""
    import jwt as _jwt

    secret = "test-jwt-secret-for-coverage-32-bytes"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-001",
        "tenant_id": "tenant-abc",
        "maci_role": "CONTROLLER",
        "permissions": [],
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is not None
    assert result["tenant_id"] == "tenant-abc"


def test_validate_jwt_token_valid_admin_permission(monkeypatch: pytest.MonkeyPatch):
    """Valid JWT with ADMIN permission returns payload."""
    import jwt as _jwt

    secret = "test-jwt-secret-admin-32-bytes-long"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-002",
        "tenant_id": "tenant-abc",
        "maci_role": "",
        "permissions": ["ADMIN"],
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is not None


def test_validate_jwt_token_lacks_permission(monkeypatch: pytest.MonkeyPatch):
    """JWT without admin role/permission returns None (line 253-258)."""
    import jwt as _jwt

    secret = "test-jwt-secret-noperm-32-bytes-long"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-003",
        "tenant_id": "tenant-abc",
        "maci_role": "OBSERVER",
        "permissions": ["READ"],
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is None


def test_validate_jwt_token_hash_mismatch(monkeypatch: pytest.MonkeyPatch):
    """JWT with wrong constitutional hash returns None (lines 237-243)."""
    import jwt as _jwt

    secret = "test-jwt-secret-hash-32-bytes-longxx"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-004",
        "tenant_id": "tenant-abc",
        "maci_role": "CONTROLLER",
        "permissions": [],
        "constitutional_hash": "wrong-hash-value-here",
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is None


def test_validate_jwt_token_expired(monkeypatch: pytest.MonkeyPatch):
    """Expired JWT returns None (line 263-264)."""
    from datetime import timedelta

    import jwt as _jwt

    secret = "test-jwt-secret-exp-32-bytes-longxxx"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-005",
        "tenant_id": "tenant-abc",
        "maci_role": "CONTROLLER",
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is None


def test_validate_jwt_token_invalid_signature(monkeypatch: pytest.MonkeyPatch):
    """JWT with wrong secret returns None (line 266-267)."""
    import jwt as _jwt

    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", "correct-secret-32-bytes-long-key")
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-006",
        "tenant_id": "tenant-abc",
        "maci_role": "CONTROLLER",
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, "wrong-secret-32-bytes-long-secret", algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is None


def test_auth_via_jwt_bearer_token(monkeypatch: pytest.MonkeyPatch):
    """Authenticated request using Bearer JWT token succeeds (lines 312-323)."""
    import jwt as _jwt

    secret = "bearer-test-secret-32-bytes-longxx"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    mgr = _manager()
    mgr.list_tenants.return_value = []
    client = _build_client(mgr)

    payload = {
        "sub": "agent-bearer",
        "tenant_id": "bearer-tenant",
        "maci_role": "CONTROLLER",
        "permissions": [],
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    resp = client.get(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_auth_via_jwt_bearer_token_invalid(monkeypatch: pytest.MonkeyPatch):
    """Invalid Bearer JWT returns 401 (lines 324-338)."""
    import jwt as _jwt

    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", "real-secret-32-bytes-long-keyyyy")
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    mgr = _manager()
    client = _build_client(mgr)

    payload = {
        "sub": "agent-bad",
        "tenant_id": "tenant-abc",
        "maci_role": "CONTROLLER",
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, "wrong-secret-32-bytes-long-secret", algorithm="HS256")

    resp = client.get(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ===========================================================================
# 25. Usage with quota_val = 0 (branch line 1110->1107)
# ===========================================================================


def test_get_usage_zero_quota_no_utilization():
    """When quota values are 0, utilization dict should not include them."""
    mgr = _manager()
    t = make_tenant(
        tenant_id="t-zero",
        quota=_FakeQuota(max_agents=0, max_policies=0, max_messages_per_minute=0),
        usage=_FakeUsage(agents_count=0, policies_count=0, messages_this_minute=0),
    )
    mgr.get_tenant.return_value = t
    client = _build_client(mgr)
    resp = client.get("/api/v1/tenants/t-zero/usage", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    # Utilization should be empty since all quota values are 0
    assert body["utilization"] == {}


# ===========================================================================
# 26. _to_dict_safe dataclass TypeError path (lines 150-151)
# ===========================================================================


def test_to_dict_safe_dataclass_type_error():
    """When asdict raises TypeError, fall through to dict() attempt (line 150)."""
    from dataclasses import dataclass

    @dataclass
    class Dummy:
        x: int = 1

    # Patch dataclasses.asdict to raise TypeError, simulating a failure during
    # dataclass serialization (e.g. non-serializable field).
    import dataclasses

    original_asdict = dataclasses.asdict

    def _bad_asdict(obj, **kw):
        raise TypeError("cannot serialize")

    dataclasses.asdict = _bad_asdict  # type: ignore[assignment]
    try:
        result = _tenants_mod._to_dict_safe(Dummy())
        # Falls through to dict() which also fails -> returns {}
        assert isinstance(result, dict)
    finally:
        dataclasses.asdict = original_asdict  # type: ignore[assignment]


# ===========================================================================
# 27. TENANT_MANAGE permission in JWT
# ===========================================================================


def test_validate_jwt_token_tenant_manage_permission(monkeypatch: pytest.MonkeyPatch):
    """TENANT_MANAGE permission grants access (line 250)."""
    import jwt as _jwt

    secret = "tenant-manage-secret-32-bytes-long"
    monkeypatch.setattr(_tenants_mod, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(_tenants_mod, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(_tenants_mod, "JWT_ISSUER", "acgs2-agent-runtime")
    monkeypatch.setattr(_tenants_mod, "JWT_AUDIENCE", "acgs2-services")

    payload = {
        "sub": "agent-tm",
        "tenant_id": "tenant-abc",
        "maci_role": "",
        "permissions": ["TENANT_MANAGE"],
        "iss": "acgs2-agent-runtime",
        "aud": "acgs2-services",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, secret, algorithm="HS256")

    result = _tenants_mod._validate_jwt_token(token)
    assert result is not None
