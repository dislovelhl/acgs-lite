# Constitutional Hash: 608508a9bd224290
# Sprint 58 — routes/sessions/endpoints.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/routes/sessions/endpoints.py
Target: ≥95% line coverage.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.routes.sessions._fallbacks import RiskLevel
from enhanced_agent_bus.routes.sessions.endpoints import (
    _apply_policy_candidate,
    _build_policy_selection,
    _build_policy_selection_response,
    _get_authorized_session_governance_config,
    _normalize_policy_selection_request,
    _resolve_effective_risk_level,
    create_session,
    delete_session,
    extend_session_ttl,
    get_session,
    get_session_metrics,
    select_session_policies,
    update_session_governance,
)
from enhanced_agent_bus.routes.sessions.models import (
    CreateSessionRequest,
    PolicySelectionRequest,
    SelectedPolicy,
    UpdateGovernanceRequest,
)

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

_RISK_LEVEL_MAP = {
    "low": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}


def _make_governance_config(
    tenant_id: str = "tenant-abc",
    risk_level_value: str = "medium",
    policy_id: str | None = None,
    policy_overrides: dict | None = None,
    enabled_policies: list | None = None,
    disabled_policies: list | None = None,
    user_id: str | None = None,
    require_human_approval: bool = False,
    max_automation_level: str | None = None,
):
    cfg = MagicMock()
    cfg.tenant_id = tenant_id
    cfg.user_id = user_id
    cfg.risk_level = _RISK_LEVEL_MAP.get(risk_level_value, RiskLevel.MEDIUM)
    cfg.policy_id = policy_id
    cfg.policy_overrides = policy_overrides if policy_overrides is not None else {}
    cfg.enabled_policies = enabled_policies if enabled_policies is not None else []
    cfg.disabled_policies = disabled_policies if disabled_policies is not None else []
    cfg.require_human_approval = require_human_approval
    cfg.max_automation_level = max_automation_level
    return cfg


def _make_session_context(
    session_id: str = "sess-001",
    tenant_id: str = "tenant-abc",
    risk_level_value: str = "medium",
    policy_id: str | None = None,
    policy_overrides: dict | None = None,
    enabled_policies: list | None = None,
    disabled_policies: list | None = None,
):
    ctx = MagicMock()
    ctx.session_id = session_id
    ctx.governance_config = _make_governance_config(
        tenant_id=tenant_id,
        risk_level_value=risk_level_value,
        policy_id=policy_id,
        policy_overrides=policy_overrides,
        enabled_policies=enabled_policies if enabled_policies is not None else [],
        disabled_policies=disabled_policies if disabled_policies is not None else [],
    )
    ctx.metadata = {}
    ctx.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    ctx.updated_at = datetime(2026, 1, 2, tzinfo=UTC)
    ctx.expires_at = None
    ctx.constitutional_hash = CONSTITUTIONAL_HASH
    return ctx


def _make_manager(
    session_context=None,
    create_result=None,
    update_result=None,
    delete_result: bool = True,
    extend_result: bool = True,
    ttl_remaining: int = 3600,
    metrics: dict | None = None,
):
    """Build a mock SessionContextManager."""
    manager = MagicMock()
    manager.store = MagicMock()
    manager.store.get_ttl = AsyncMock(return_value=ttl_remaining)

    ctx = session_context or _make_session_context()
    manager.create = AsyncMock(return_value=create_result if create_result is not None else ctx)
    manager.get = AsyncMock(return_value=ctx)
    manager.update = AsyncMock(return_value=update_result if update_result is not None else ctx)
    manager.delete = AsyncMock(return_value=delete_result)
    manager.extend_ttl = AsyncMock(return_value=extend_result)
    manager.get_metrics = MagicMock(
        return_value=metrics
        if metrics is not None
        else {
            "cache_hits": 5,
            "cache_misses": 2,
            "cache_hit_rate": 0.71,
            "cache_size": 3,
            "cache_capacity": 100,
            "creates": 10,
            "reads": 20,
            "updates": 8,
            "deletes": 2,
            "errors": 1,
        }
    )
    return manager


# ===========================================================================
# create_session
# ===========================================================================


class TestCreateSession:
    async def test_happy_path_minimal(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, ttl_remaining=3600)
        req = CreateSessionRequest()
        result = await create_session(req, "tenant-abc", "user-99", manager)
        assert result.session_id == "sess-001"

    async def test_user_id_falls_back_to_header(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(user_id=None)
        await create_session(req, "tenant-abc", "header-user", manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.user_id == "header-user"

    async def test_user_id_from_body_takes_precedence(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(user_id="body-user")
        await create_session(req, "tenant-abc", "header-user", manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.user_id == "body-user"

    async def test_tenant_id_mismatch_raises_400(self):
        manager = _make_manager()
        req = CreateSessionRequest(tenant_id="other-tenant")
        with pytest.raises(HTTPException) as exc_info:
            await create_session(req, "tenant-abc", None, manager)
        assert exc_info.value.status_code == 400

    async def test_risk_level_low(self):
        ctx = _make_session_context(risk_level_value="low")
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(risk_level="low")
        result = await create_session(req, "tenant-abc", None, manager)
        assert result is not None

    async def test_risk_level_high(self):
        ctx = _make_session_context(risk_level_value="high")
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(risk_level="high")
        await create_session(req, "tenant-abc", None, manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.risk_level == RiskLevel.HIGH

    async def test_risk_level_critical(self):
        ctx = _make_session_context(risk_level_value="critical")
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(risk_level="critical")
        await create_session(req, "tenant-abc", None, manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.risk_level == RiskLevel.CRITICAL

    async def test_risk_level_unknown_defaults_to_medium(self):
        # We bypass pydantic validation by patching request.risk_level after creation
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest()
        # Simulate unknown risk_level by monkey-patching after model creation
        object.__setattr__(req, "risk_level", "unknown")
        await create_session(req, "tenant-abc", None, manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.risk_level == RiskLevel.MEDIUM

    async def test_value_error_raises_409(self):
        manager = _make_manager()
        manager.create = AsyncMock(side_effect=ValueError("duplicate"))
        req = CreateSessionRequest()
        with pytest.raises(HTTPException) as exc_info:
            await create_session(req, "tenant-abc", None, manager)
        assert exc_info.value.status_code == 409

    async def test_runtime_error_raises_500(self):
        manager = _make_manager()
        manager.create = AsyncMock(side_effect=RuntimeError("store failure"))
        req = CreateSessionRequest()
        with pytest.raises(HTTPException) as exc_info:
            await create_session(req, "tenant-abc", None, manager)
        assert exc_info.value.status_code == 500

    async def test_os_error_raises_500(self):
        manager = _make_manager()
        manager.create = AsyncMock(side_effect=OSError("io"))
        req = CreateSessionRequest()
        with pytest.raises(HTTPException) as exc_info:
            await create_session(req, "tenant-abc", None, manager)
        assert exc_info.value.status_code == 500

    async def test_session_id_in_request_forwarded(self):
        ctx = _make_session_context(session_id="custom-id")
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(session_id="custom-id")
        result = await create_session(req, "tenant-abc", None, manager)
        assert result.session_id == "custom-id"

    async def test_tenant_id_in_body_matches_header(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(tenant_id="tenant-abc")
        result = await create_session(req, "tenant-abc", None, manager)
        assert result is not None

    async def test_no_user_id_anywhere(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = CreateSessionRequest(user_id=None)
        await create_session(req, "tenant-abc", None, manager)
        call_kwargs = manager.create.call_args.kwargs
        gov = call_kwargs["governance_config"]
        assert gov.user_id is None

    async def test_key_error_raises_500(self):
        manager = _make_manager()
        manager.create = AsyncMock(side_effect=KeyError("missing"))
        req = CreateSessionRequest()
        with pytest.raises(HTTPException) as exc_info:
            await create_session(req, "tenant-abc", None, manager)
        assert exc_info.value.status_code == 500


# ===========================================================================
# get_session
# ===========================================================================


class TestGetSession:
    async def test_happy_path(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        result = await get_session("sess-001", "tenant-abc", manager)
        assert result.session_id == "sess-001"

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await get_session("no-session", "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other-tenant")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await get_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 403

    async def test_http_exception_re_raised(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=HTTPException(status_code=404, detail="gone"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_runtime_error_raises_500(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_attribute_error_raises_500(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=AttributeError("attr"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_ttl_remaining_included(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, ttl_remaining=1800)
        result = await get_session("sess-001", "tenant-abc", manager)
        assert result.ttl_remaining_seconds == 1800


# ===========================================================================
# update_session_governance
# ===========================================================================


class TestUpdateSessionGovernance:
    async def test_happy_path_no_changes(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest()
        result = await update_session_governance("sess-001", req, "tenant-abc", manager)
        assert result.session_id == "sess-001"

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await update_session_governance("bad", UpdateGovernanceRequest(), "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await update_session_governance(
                "sess-001", UpdateGovernanceRequest(), "tenant-abc", manager
            )
        assert exc_info.value.status_code == 403

    async def test_update_returns_none_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, update_result=None)
        manager.update = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await update_session_governance(
                "sess-001", UpdateGovernanceRequest(), "tenant-abc", manager
            )
        assert exc_info.value.status_code == 500

    async def test_risk_level_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(risk_level="high")
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].risk_level == RiskLevel.HIGH

    async def test_risk_level_none_keeps_existing(self):
        ctx = _make_session_context(risk_level_value="low")
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(risk_level=None)
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        # risk_level should come from the mock governance config
        assert call_kwargs["governance_config"].risk_level == ctx.governance_config.risk_level

    async def test_policy_id_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(policy_id="policy-new")
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].policy_id == "policy-new"

    async def test_policy_overrides_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(policy_overrides={"key": "val"})
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].policy_overrides == {"key": "val"}

    async def test_enabled_policies_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(enabled_policies=["p1", "p2"])
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].enabled_policies == ["p1", "p2"]

    async def test_disabled_policies_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(disabled_policies=["p3"])
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].disabled_policies == ["p3"]

    async def test_require_human_approval_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(require_human_approval=True)
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].require_human_approval is True

    async def test_max_automation_level_updated(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest(max_automation_level="partial")
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        assert call_kwargs["governance_config"].max_automation_level == "partial"

    async def test_http_exception_re_raised(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=HTTPException(status_code=403, detail="denied"))
        with pytest.raises(HTTPException) as exc_info:
            await update_session_governance(
                "sess-001", UpdateGovernanceRequest(), "tenant-abc", manager
            )
        assert exc_info.value.status_code == 403

    async def test_runtime_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        manager.update = AsyncMock(side_effect=RuntimeError("crash"))
        with pytest.raises(HTTPException) as exc_info:
            await update_session_governance(
                "sess-001", UpdateGovernanceRequest(), "tenant-abc", manager
            )
        assert exc_info.value.status_code == 500

    async def test_unknown_risk_level_keeps_existing(self):
        ctx = _make_session_context(risk_level_value="low")
        manager = _make_manager(session_context=ctx)
        req = UpdateGovernanceRequest()
        object.__setattr__(req, "risk_level", "unknown-level")
        await update_session_governance("sess-001", req, "tenant-abc", manager)
        call_kwargs = manager.update.call_args.kwargs
        # should fall back to current_config.risk_level
        assert call_kwargs["governance_config"].risk_level == ctx.governance_config.risk_level


# ===========================================================================
# delete_session
# ===========================================================================


class TestDeleteSession:
    async def test_happy_path(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, delete_result=True)
        # Should return None without raising
        result = await delete_session("sess-001", "tenant-abc", manager)
        assert result is None

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("no-sess", "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 403

    async def test_delete_failure_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, delete_result=False)
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_http_exception_re_raised(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=HTTPException(status_code=403, detail="denied"))
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 403

    async def test_runtime_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        manager.delete = AsyncMock(side_effect=RuntimeError("crash"))
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_type_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        manager.delete = AsyncMock(side_effect=TypeError("type"))
        with pytest.raises(HTTPException) as exc_info:
            await delete_session("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 500


# ===========================================================================
# extend_session_ttl
# ===========================================================================


class TestExtendSessionTtl:
    async def test_happy_path(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, extend_result=True, ttl_remaining=7200)
        result = await extend_session_ttl("sess-001", 7200, "tenant-abc", manager)
        assert result.session_id == "sess-001"
        assert result.ttl_remaining_seconds == 7200

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("no-sess", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("sess-001", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 403

    async def test_extend_failure_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx, extend_result=False)
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("sess-001", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_http_exception_re_raised(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=HTTPException(status_code=404, detail="nope"))
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("sess-001", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_runtime_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        manager.extend_ttl = AsyncMock(side_effect=RuntimeError("timeout"))
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("sess-001", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_value_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        manager.extend_ttl = AsyncMock(side_effect=ValueError("bad value"))
        with pytest.raises(HTTPException) as exc_info:
            await extend_session_ttl("sess-001", 3600, "tenant-abc", manager)
        assert exc_info.value.status_code == 500


# ===========================================================================
# _normalize_policy_selection_request
# ===========================================================================


class TestNormalizePolicySelectionRequest:
    def test_returns_provided_request(self):
        req = PolicySelectionRequest(include_disabled=True)
        result = _normalize_policy_selection_request(req)
        assert result is req

    def test_returns_default_when_none(self):
        result = _normalize_policy_selection_request(None)
        assert isinstance(result, PolicySelectionRequest)
        assert result.include_disabled is False


# ===========================================================================
# _get_authorized_session_governance_config
# ===========================================================================


class TestGetAuthorizedSessionGovernanceConfig:
    async def test_returns_config(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        cfg = await _get_authorized_session_governance_config("sess-001", "tenant-abc", manager)
        assert cfg.tenant_id == "tenant-abc"

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await _get_authorized_session_governance_config("no-sess", "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await _get_authorized_session_governance_config("sess-001", "tenant-abc", manager)
        assert exc_info.value.status_code == 403


# ===========================================================================
# _resolve_effective_risk_level
# ===========================================================================


class TestResolveEffectiveRiskLevel:
    def test_override_takes_precedence(self):
        cfg = _make_governance_config(risk_level_value="low")
        req = PolicySelectionRequest(risk_level_override="critical")
        result = _resolve_effective_risk_level(cfg, req)
        assert result == "critical"

    def test_uses_config_risk_level_enum_value(self):
        cfg = _make_governance_config(risk_level_value="high")
        req = PolicySelectionRequest()
        result = _resolve_effective_risk_level(cfg, req)
        assert result == "high"

    def test_uses_str_risk_level_when_no_value_attr(self):
        cfg = MagicMock()
        cfg.risk_level = "medium"  # plain string, no .value
        req = PolicySelectionRequest()
        result = _resolve_effective_risk_level(cfg, req)
        assert result == "medium"


# ===========================================================================
# _apply_policy_candidate
# ===========================================================================


class TestApplyPolicyCandidate:
    def _make_policy(self, policy_id: str = "pol-1") -> SelectedPolicy:
        return SelectedPolicy(
            policy_id=policy_id,
            name=policy_id,
            source="session",
            priority=50,
            reasoning="test",
        )

    def test_sets_selected_policy_when_none(self):
        policy = self._make_policy()
        result = _apply_policy_candidate(policy, False, None, [])
        assert result is policy

    def test_keeps_existing_selected_policy(self):
        existing = self._make_policy("existing")
        new_policy = self._make_policy("new")
        result = _apply_policy_candidate(new_policy, False, existing, [])
        assert result is existing

    def test_appends_to_candidates_when_include_all(self):
        policy = self._make_policy()
        candidates: list = []
        _apply_policy_candidate(policy, True, None, candidates)
        assert policy in candidates

    def test_does_not_append_when_not_include_all(self):
        policy = self._make_policy()
        candidates: list = []
        _apply_policy_candidate(policy, False, None, candidates)
        assert candidates == []


# ===========================================================================
# _build_policy_selection
# ===========================================================================


class TestBuildPolicySelection:
    def test_policy_id_selected(self):
        cfg = _make_governance_config(policy_id="pol-override")
        req = PolicySelectionRequest()
        selected, _candidates = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        assert selected.policy_id == "pol-override"
        assert selected.source == "session"

    def test_policy_overrides_with_policy_id(self):
        cfg = _make_governance_config(policy_overrides={"policy_id": "pol-from-override"})
        req = PolicySelectionRequest()
        selected, _ = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        assert selected.policy_id == "pol-from-override"

    def test_enabled_policies_list(self):
        cfg = _make_governance_config(
            enabled_policies=["pol-a", "pol-b"],
        )
        req = PolicySelectionRequest()
        selected, _ = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        assert selected.policy_id == "pol-a"

    def test_disabled_policy_skipped(self):
        cfg = _make_governance_config(
            enabled_policies=["pol-a", "pol-b"],
            disabled_policies=["pol-a"],
        )
        req = PolicySelectionRequest(include_disabled=False)
        selected, _ = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        assert selected.policy_id == "pol-b"

    def test_disabled_policy_included_when_flag_set(self):
        cfg = _make_governance_config(
            enabled_policies=["pol-a"],
            disabled_policies=["pol-a"],
        )
        req = PolicySelectionRequest(include_disabled=True)
        selected, _ = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        assert selected.policy_id == "pol-a"

    def test_fallback_to_tenant_default_when_no_policies(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest()
        selected, _ = _build_policy_selection(cfg, req, "tenant-abc", "low")
        assert "tenant-abc" in selected.policy_id
        assert selected.source == "tenant"

    def test_global_fallback_when_no_selection_and_include_all(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest(include_all_candidates=True)
        _selected, candidates = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        policy_ids = [c.policy_id for c in candidates]
        assert "policy-global-default" in policy_ids

    def test_include_all_candidates_includes_everything(self):
        cfg = _make_governance_config(
            policy_id="pol-explicit",
            policy_overrides={"policy_id": "pol-override"},
            enabled_policies=["pol-a"],
        )
        req = PolicySelectionRequest(include_all_candidates=True)
        _, candidates = _build_policy_selection(cfg, req, "tenant-abc", "medium")
        candidate_ids = [c.policy_id for c in candidates]
        assert "pol-explicit" in candidate_ids
        assert "pol-override" in candidate_ids
        assert "pol-a" in candidate_ids

    def test_global_fallback_when_selected_is_none(self):
        # When all enabled_policies are disabled and no overrides, selected becomes None
        # then the fallback code adds tenant + global
        cfg = _make_governance_config(
            enabled_policies=["pol-x"],
            disabled_policies=["pol-x"],
        )
        req = PolicySelectionRequest(include_disabled=False)
        selected, _ = _build_policy_selection(cfg, req, "t1", "medium")
        # tenant default kicks in because selected_policy was None
        assert selected is not None

    def test_policy_overrides_metadata_excludes_policy_id_key(self):
        cfg = _make_governance_config(
            policy_overrides={"policy_id": "pol-from-override", "extra": "value"}
        )
        req = PolicySelectionRequest()
        selected, _ = _build_policy_selection(cfg, req, "t1", "medium")
        # The selected policy's metadata should not contain 'policy_id'
        assert "policy_id" not in selected.metadata


# ===========================================================================
# _build_policy_selection_response
# ===========================================================================


class TestBuildPolicySelectionResponse:
    def _make_selected_policy(self) -> SelectedPolicy:
        return SelectedPolicy(
            policy_id="pol-1",
            name="Policy One",
            source="session",
            priority=100,
            reasoning="test",
        )

    def test_basic_response_shape(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest()
        selected = self._make_selected_policy()
        resp = _build_policy_selection_response(
            session_id="sess-1",
            tenant_id="t1",
            risk_level="high",
            selected_policy=selected,
            candidate_policies=[selected],
            config=cfg,
            request=req,
            elapsed_ms=1.23,
        )
        assert resp.session_id == "sess-1"
        assert resp.tenant_id == "t1"
        assert resp.risk_level == "high"
        assert resp.selected_policy == selected
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_candidate_policies_empty_when_not_include_all(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest(include_all_candidates=False)
        selected = self._make_selected_policy()
        resp = _build_policy_selection_response(
            session_id="s",
            tenant_id="t",
            risk_level="low",
            selected_policy=selected,
            candidate_policies=[selected],
            config=cfg,
            request=req,
            elapsed_ms=0.5,
        )
        assert resp.candidate_policies == []

    def test_candidate_policies_included_when_include_all(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest(include_all_candidates=True)
        selected = self._make_selected_policy()
        resp = _build_policy_selection_response(
            session_id="s",
            tenant_id="t",
            risk_level="low",
            selected_policy=selected,
            candidate_policies=[selected],
            config=cfg,
            request=req,
            elapsed_ms=0.5,
        )
        assert len(resp.candidate_policies) == 1

    def test_selection_metadata_contains_risk_level_source_override(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest(risk_level_override="high")
        resp = _build_policy_selection_response(
            session_id="s",
            tenant_id="t",
            risk_level="high",
            selected_policy=None,
            candidate_policies=[],
            config=cfg,
            request=req,
            elapsed_ms=0.1,
        )
        assert resp.selection_metadata["risk_level_source"] == "override"

    def test_selection_metadata_contains_risk_level_source_session(self):
        cfg = _make_governance_config()
        req = PolicySelectionRequest()
        resp = _build_policy_selection_response(
            session_id="s",
            tenant_id="t",
            risk_level="medium",
            selected_policy=None,
            candidate_policies=[],
            config=cfg,
            request=req,
            elapsed_ms=0.2,
        )
        assert resp.selection_metadata["risk_level_source"] == "session"


# ===========================================================================
# select_session_policies
# ===========================================================================


class TestSelectSessionPolicies:
    async def test_happy_path_no_request(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        result = await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert result.session_id == "sess-001"

    async def test_happy_path_with_request(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        req = PolicySelectionRequest(include_all_candidates=True)
        result = await select_session_policies("sess-001", req, "tenant-abc", manager)
        assert "policy-global-default" in [c.policy_id for c in result.candidate_policies]

    async def test_not_found_raises_404(self):
        manager = _make_manager()
        manager.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await select_session_policies("bad", None, "tenant-abc", manager)
        assert exc_info.value.status_code == 404

    async def test_wrong_tenant_raises_403(self):
        ctx = _make_session_context(tenant_id="other")
        manager = _make_manager(session_context=ctx)
        with pytest.raises(HTTPException) as exc_info:
            await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert exc_info.value.status_code == 403

    async def test_http_exception_re_raised(self):
        manager = _make_manager()
        manager.get = AsyncMock(side_effect=HTTPException(status_code=422, detail="bad input"))
        with pytest.raises(HTTPException) as exc_info:
            await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert exc_info.value.status_code == 422

    async def test_runtime_error_raises_500(self):
        ctx = _make_session_context()
        manager = _make_manager(session_context=ctx)
        # Patch manager.get to raise after first call
        manager.get = AsyncMock(side_effect=RuntimeError("explode"))
        with pytest.raises(HTTPException) as exc_info:
            await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert exc_info.value.status_code == 500

    async def test_selected_policy_logged(self):
        ctx = _make_session_context(policy_id="pol-abc")
        ctx.governance_config.policy_id = "pol-abc"
        manager = _make_manager(session_context=ctx)
        result = await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert result.selected_policy.policy_id == "pol-abc"

    async def test_selected_policy_none_logged(self):
        ctx = _make_session_context()
        ctx.governance_config.policy_id = None
        ctx.governance_config.policy_overrides = {}
        ctx.governance_config.enabled_policies = []
        manager = _make_manager(session_context=ctx)
        result = await select_session_policies("sess-001", None, "tenant-abc", manager)
        # Should get tenant default
        assert result.selected_policy is not None

    async def test_with_policy_id_in_session(self):
        ctx = _make_session_context(policy_id="specific-pol")
        ctx.governance_config.policy_id = "specific-pol"
        ctx.governance_config.policy_overrides = {}
        ctx.governance_config.enabled_policies = []
        manager = _make_manager(session_context=ctx)
        result = await select_session_policies("sess-001", None, "tenant-abc", manager)
        assert result.selected_policy.policy_id == "specific-pol"


# ===========================================================================
# get_session_metrics
# ===========================================================================


class TestGetSessionMetrics:
    async def test_happy_path_full_metrics(self):
        manager = _make_manager(
            metrics={
                "cache_hits": 100,
                "cache_misses": 10,
                "cache_hit_rate": 0.909,
                "cache_size": 50,
                "cache_capacity": 200,
                "creates": 30,
                "reads": 120,
                "updates": 25,
                "deletes": 5,
                "errors": 2,
            }
        )
        result = await get_session_metrics(manager)
        assert result.cache_hits == 100
        assert result.cache_misses == 10
        assert result.cache_hit_rate == 0.909
        assert result.cache_size == 50
        assert result.cache_capacity == 200
        assert result.creates == 30
        assert result.reads == 120
        assert result.updates == 25
        assert result.deletes == 5
        assert result.errors == 2
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_missing_keys_default_to_zero(self):
        manager = _make_manager(metrics={})
        result = await get_session_metrics(manager)
        assert result.cache_hits == 0
        assert result.cache_hit_rate == 0.0

    async def test_runtime_error_raises_500(self):
        manager = _make_manager()
        manager.get_metrics = MagicMock(side_effect=RuntimeError("metrics fail"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session_metrics(manager)
        assert exc_info.value.status_code == 500

    async def test_attribute_error_raises_500(self):
        manager = _make_manager()
        manager.get_metrics = MagicMock(side_effect=AttributeError("no attr"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session_metrics(manager)
        assert exc_info.value.status_code == 500

    async def test_key_error_raises_500(self):
        manager = _make_manager()
        manager.get_metrics = MagicMock(side_effect=KeyError("missing"))
        with pytest.raises(HTTPException) as exc_info:
            await get_session_metrics(manager)
        assert exc_info.value.status_code == 500
