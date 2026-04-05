"""
Security tests for workflow, visual studio, and policy copilot auth wiring.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.api.routes.workflows import (
    _resolve_tenant_id as resolve_workflow_tenant_id,
)
from enhanced_agent_bus.api.routes.workflows import router as workflow_router
from enhanced_agent_bus.policy_copilot.api import (
    _assert_tenant_scope as assert_copilot_tenant_scope,
)
from enhanced_agent_bus.policy_copilot.api import router as copilot_router
from enhanced_agent_bus.visual_studio.api import (
    _resolve_tenant_id as resolve_visual_tenant_id,
)
from enhanced_agent_bus.visual_studio.api import router as visual_router


def _mock_user(tenant_id: str = "tenant-jwt") -> UserClaims:
    return UserClaims(
        sub="user-123",
        tenant_id=tenant_id,
        roles=["agent"],
        permissions=["read", "write"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


def _iter_api_routes(router) -> list[APIRoute]:
    return [route for route in router.routes if isinstance(route, APIRoute)]


def test_workflow_routes_require_get_current_user_dependency() -> None:
    routes = _iter_api_routes(workflow_router)
    assert routes
    for route in routes:
        dependency_calls = [dependency.call for dependency in route.dependant.dependencies]
        assert get_current_user in dependency_calls, f"Missing auth dependency on {route.path}"


def test_visual_router_has_router_level_auth_dependency() -> None:
    dependency_calls = [dependency.dependency for dependency in visual_router.dependencies]
    assert get_current_user in dependency_calls


def test_copilot_router_has_router_level_auth_dependency() -> None:
    dependency_calls = [dependency.dependency for dependency in copilot_router.dependencies]
    assert get_current_user in dependency_calls


def test_workflow_tenant_resolution_denies_cross_tenant() -> None:
    user = _mock_user("tenant-a")
    with pytest.raises(HTTPException) as exc_info:
        resolve_workflow_tenant_id(user, "tenant-b")
    assert exc_info.value.status_code == 403


def test_workflow_tenant_resolution_uses_jwt_tenant() -> None:
    user = _mock_user("tenant-a")
    assert resolve_workflow_tenant_id(user, None) == "tenant-a"
    assert resolve_workflow_tenant_id(user, "tenant-a") == "tenant-a"


def test_visual_tenant_resolution_denies_cross_tenant() -> None:
    user = _mock_user("tenant-a")
    with pytest.raises(HTTPException) as exc_info:
        resolve_visual_tenant_id(user, "tenant-b")
    assert exc_info.value.status_code == 403


def test_copilot_tenant_scope_denies_cross_tenant() -> None:
    user = _mock_user("tenant-a")
    with pytest.raises(HTTPException) as exc_info:
        assert_copilot_tenant_scope(user, "tenant-b")
    assert exc_info.value.status_code == 403


def test_copilot_tenant_scope_allows_same_or_empty_tenant() -> None:
    user = _mock_user("tenant-a")
    assert_copilot_tenant_scope(user, None)
    assert_copilot_tenant_scope(user, "tenant-a")
