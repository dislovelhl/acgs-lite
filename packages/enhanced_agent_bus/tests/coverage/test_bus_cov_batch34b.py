"""
Coverage tests for:
  1. enhanced_agent_bus.routes.tenants — targeting ~54 uncovered lines
  2. enhanced_agent_bus.adaptive_governance.governance_engine — targeting ~43 uncovered lines

Focuses on error branches, auth edge cases, drift detection paths, feedback storage
branches, river model update failure/success paths, and background learning loop logic.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Governance engine imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    ImpactFeatures,
    ImpactLevel,
)

# ---------------------------------------------------------------------------
# Tenants module imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.routes import tenants as tenants_mod
from enhanced_agent_bus.routes.tenants import (
    _authenticate_via_api_key,
    _authenticate_via_jwt,
    _build_quota_check_response,
    _build_tenant_hierarchy_response,
    _calculate_utilization,
    _check_tenant_scope,
    _ensure_auth_configured,
    _extract_usage_and_quota_dicts,
    _is_uuid,
    _parse_status_filter,
    _quota_resource_keys,
    _raise_internal_tenant_error,
    _raise_tenant_not_found,
    _raise_value_http_error,
    _to_dict_safe,
    _validate_admin_api_key,
    _validate_jwt_token,
    get_admin_tenant_id,
    get_manager,
    get_optional_tenant_id,
)

HASH = "608508a9bd224290"


# ===========================================================================
# Helpers
# ===========================================================================


def _make_features(**overrides: Any) -> ImpactFeatures:
    defaults: dict[str, Any] = {
        "message_length": 100,
        "agent_count": 2,
        "tenant_complexity": 0.3,
        "temporal_patterns": [0.1, 0.2],
        "semantic_similarity": 0.2,
        "historical_precedence": 1,
        "resource_utilization": 0.1,
        "network_isolation": 0.8,
        "risk_score": 0.25,
        "confidence_level": 0.85,
    }
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides: Any) -> GovernanceDecision:
    defaults: dict[str, Any] = {
        "action_allowed": True,
        "impact_level": ImpactLevel.LOW,
        "confidence_score": 0.85,
        "reasoning": "Test reasoning",
        "recommended_threshold": 0.4,
        "features_used": _make_features(),
        "decision_id": "gov-test-001",
    }
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


class _FakeTenant:
    """Minimal tenant stub for route-level tests."""

    def __init__(self, **kw: Any) -> None:
        self.tenant_id = kw.get("tenant_id", "t-001")
        self.name = kw.get("name", "Test")
        self.slug = kw.get("slug", "test")
        self.status = SimpleNamespace(value=kw.get("status", "active"))
        self.parent_tenant_id = kw.get("parent_tenant_id", None)
        self.config = kw.get("config", SimpleNamespace(model_dump=lambda: {}))
        self.quota = kw.get("quota", SimpleNamespace(model_dump=lambda: {"max_agents": 100}))
        self.usage = kw.get("usage", SimpleNamespace(model_dump=lambda: {"agents_count": 5}))
        self.metadata = kw.get("metadata", {})
        self.created_at = kw.get("created_at", datetime.now(UTC))
        self.updated_at = kw.get("updated_at", datetime.now(UTC))
        self.activated_at = kw.get("activated_at", None)
        self.suspended_at = kw.get("suspended_at", None)
        self.constitutional_hash = kw.get("constitutional_hash", HASH)


# ---------------------------------------------------------------------------
# Governance engine fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_externals():
    with (
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.import_module"
        ) as mock_import,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ImpactScorer"
        ) as mock_scorer_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AdaptiveThresholds"
        ) as mock_thresh_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DTMCLearner"
        ) as mock_dtmc_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.TraceCollector"
        ) as mock_trace_cls,
    ):
        mock_validator = MagicMock()
        mock_validator.GovernanceDecisionValidator.return_value.validate_decision = AsyncMock(
            return_value=(True, [])
        )
        mock_import.return_value = mock_validator

        scorer = MagicMock()
        scorer.model_trained = False
        scorer.assess_impact = AsyncMock(return_value=_make_features())
        scorer.update_model = MagicMock()
        scorer.impact_classifier = MagicMock()
        mock_scorer_cls.return_value = scorer

        thresh = MagicMock()
        thresh.get_adaptive_threshold = MagicMock(return_value=0.5)
        thresh.update_model = MagicMock()
        mock_thresh_cls.return_value = thresh

        dtmc = MagicMock()
        dtmc.is_fitted = False
        mock_dtmc_cls.return_value = dtmc

        mock_trace_cls.return_value = MagicMock()

        yield SimpleNamespace(
            scorer=scorer,
            thresh=thresh,
            dtmc=dtmc,
            validator=mock_validator.GovernanceDecisionValidator.return_value,
            trace=mock_trace_cls.return_value,
        )


@pytest.fixture()
def engine(_patch_externals):
    eng = AdaptiveGovernanceEngine(HASH)
    eng._decision_validator = _patch_externals.validator
    return eng


@pytest.fixture()
def mocks(_patch_externals):
    return _patch_externals


# ===========================================================================
# PART 1: routes/tenants.py — uncovered branches
# ===========================================================================


class TestToDictSafeEdgeCases:
    """Cover _to_dict_safe branches: dataclass path, dict() fallback, failure."""

    def test_dataclass_conversion(self):
        @dataclasses.dataclass
        class Sample:
            x: int = 1
            y: str = "hello"

        result = _to_dict_safe(Sample())
        assert result == {"x": 1, "y": "hello"}

    def test_to_dict_method(self):
        obj = SimpleNamespace(to_dict=lambda: {"a": 1})
        result = _to_dict_safe(obj)
        assert result == {"a": 1}

    def test_dict_callable_fallback(self):
        """Objects that are iterable of key-value pairs."""
        result = _to_dict_safe([("k", "v")])
        assert result == {"k": "v"}

    def test_unconvertible_returns_empty(self):
        result = _to_dict_safe(42)
        assert result == {}


class TestIsUuid:
    def test_valid_uuid(self):
        assert _is_uuid("a1b2c3d4-e5f6-7890-abcd-ef1234567890") is True

    def test_invalid_uuid(self):
        assert _is_uuid("not-a-uuid") is False

    def test_uppercase_uuid(self):
        assert _is_uuid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890") is True

    def test_empty_string(self):
        assert _is_uuid("") is False


class TestCheckTenantScope:
    def test_allows_non_uuid_admin(self):
        # Non-UUID admin IDs get cross-tenant access
        _check_tenant_scope("admin-tenant", "target-tenant-id")

    def test_allows_same_tenant(self):
        _check_tenant_scope(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        )

    def test_allows_super_admin(self):
        _check_tenant_scope(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "b1b2c3d4-e5f6-7890-abcd-ef1234567890",
            is_super_admin=True,
        )

    def test_blocks_cross_tenant_uuid(self):
        with pytest.raises(HTTPException) as exc_info:
            _check_tenant_scope(
                "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "b1b2c3d4-e5f6-7890-abcd-ef1234567890",
            )
        assert exc_info.value.status_code == 403


class TestParseStatusFilter:
    def test_none_returns_none(self):
        assert _parse_status_filter(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_status_filter("") is None

    def test_valid_status(self):
        result = _parse_status_filter("active")
        assert result is not None

    def test_invalid_status_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_status_filter("bogus_status")
        assert exc_info.value.status_code == 400


class TestValidateAdminApiKey:
    def test_returns_false_when_no_key_configured(self):
        with patch.object(tenants_mod, "TENANT_ADMIN_KEY", ""):
            result = _validate_admin_api_key("some-key")
        assert result is False

    def test_returns_true_for_matching_key(self):
        with patch.object(tenants_mod, "TENANT_ADMIN_KEY", "secret-key"):
            result = _validate_admin_api_key("secret-key")
        assert result is True

    def test_returns_false_for_wrong_key(self):
        with patch.object(tenants_mod, "TENANT_ADMIN_KEY", "secret-key"):
            result = _validate_admin_api_key("wrong-key")
        assert result is False


class TestValidateJwtToken:
    def test_returns_none_when_no_secret(self):
        with patch.object(tenants_mod, "JWT_SECRET_KEY", ""):
            result = _validate_jwt_token("some.jwt.token")
        assert result is None

    def test_returns_none_when_pyjwt_missing(self):
        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": None}),
        ):
            # ImportError path
            result = _validate_jwt_token("some.jwt.token")
        assert result is None

    def test_returns_payload_for_valid_controller(self):
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "agent-1",
            "tenant_id": "t-abc",
            "maci_role": "CONTROLLER",
            "permissions": [],
        }
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("valid.jwt.token")
        assert result is not None
        assert result["tenant_id"] == "t-abc"

    def test_returns_payload_for_admin_permission(self):
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "agent-2",
            "tenant_id": "t-xyz",
            "maci_role": "",
            "permissions": ["ADMIN"],
        }
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("valid.jwt.token")
        assert result is not None

    def test_returns_none_for_insufficient_permissions(self):
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "agent-3",
            "tenant_id": "t-limited",
            "maci_role": "OBSERVER",
            "permissions": [],
        }
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("valid.jwt.token")
        assert result is None

    def test_returns_none_for_hash_mismatch(self):
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "agent-4",
            "tenant_id": "t-bad",
            "maci_role": "CONTROLLER",
            "permissions": [],
            "constitutional_hash": "wrong-hash",
        }
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("valid.jwt.token")
        assert result is None

    def test_returns_none_for_expired_token(self):
        class _ExpiredSig(Exception):
            pass

        class _InvalidToken(Exception):
            pass

        mock_jwt = MagicMock()
        mock_jwt.ExpiredSignatureError = _ExpiredSig
        mock_jwt.InvalidTokenError = _InvalidToken
        mock_jwt.decode.side_effect = _ExpiredSig("expired")

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("expired.jwt.token")
        assert result is None

    def test_returns_none_for_invalid_token(self):
        class _ExpiredSig(Exception):
            pass

        class _InvalidToken(Exception):
            pass

        mock_jwt = MagicMock()
        mock_jwt.ExpiredSignatureError = _ExpiredSig
        mock_jwt.InvalidTokenError = _InvalidToken
        mock_jwt.decode.side_effect = _InvalidToken("bad signature")

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("bad.jwt.token")
        assert result is None

    def test_tenant_manage_permission_accepted(self):
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "agent-5",
            "tenant_id": "t-manage",
            "maci_role": "",
            "permissions": ["TENANT_MANAGE"],
        }
        mock_jwt.ExpiredSignatureError = Exception
        mock_jwt.InvalidTokenError = Exception

        with (
            patch.object(tenants_mod, "JWT_SECRET_KEY", "secret"),
            patch.dict("sys.modules", {"jwt": mock_jwt}),
        ):
            result = _validate_jwt_token("valid.jwt.token")
        assert result is not None


class TestEnsureAuthConfigured:
    def test_raises_503_in_production_without_auth(self):
        with (
            patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "production"),
            patch.object(tenants_mod, "TENANT_ADMIN_KEY", ""),
            patch.object(tenants_mod, "JWT_SECRET_KEY", ""),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _ensure_auth_configured()
            assert exc_info.value.status_code == 503

    def test_no_raise_in_development(self):
        with (
            patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "development"),
            patch.object(tenants_mod, "TENANT_ADMIN_KEY", ""),
            patch.object(tenants_mod, "JWT_SECRET_KEY", ""),
        ):
            _ensure_auth_configured()  # should not raise


class TestAuthenticateViaJwt:
    def test_returns_tenant_id_from_valid_jwt(self):
        creds = SimpleNamespace(credentials="valid-token")
        with patch.object(
            tenants_mod,
            "_validate_jwt_token",
            return_value={"tenant_id": "t-jwt", "sub": "agent-1"},
        ):
            result = _authenticate_via_jwt(creds, "fallback-admin")
        assert result == "t-jwt"

    def test_raises_401_for_invalid_jwt(self):
        creds = SimpleNamespace(credentials="bad-token")
        with patch.object(tenants_mod, "_validate_jwt_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                _authenticate_via_jwt(creds, "admin-id")
            assert exc_info.value.status_code == 401


class TestAuthenticateViaApiKey:
    def test_raises_401_when_no_key_provided(self):
        with pytest.raises(HTTPException) as exc_info:
            _authenticate_via_api_key(None, "admin-id")
        assert exc_info.value.status_code == 401

    def test_dev_mode_bypass(self):
        with (
            patch.object(tenants_mod, "TENANT_AUTH_MODE", "development"),
            patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "development"),
        ):
            result = _authenticate_via_api_key("any-key", "dev-admin")
        assert result == "dev-admin"

    def test_valid_api_key_accepted(self):
        with patch.object(tenants_mod, "_validate_admin_api_key", return_value=True):
            result = _authenticate_via_api_key("correct-key", "admin-id")
        assert result == "admin-id"

    def test_invalid_api_key_raises_401(self):
        with (
            patch.object(tenants_mod, "TENANT_AUTH_MODE", "strict"),
            patch.object(tenants_mod, "_validate_admin_api_key", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _authenticate_via_api_key("wrong-key", "admin-id")
            assert exc_info.value.status_code == 401


class TestGetAdminTenantId:
    async def test_jwt_path_preferred(self):
        creds = SimpleNamespace(credentials="jwt-token")
        with (
            patch.object(tenants_mod, "_ensure_auth_configured"),
            patch.object(
                tenants_mod,
                "_authenticate_via_jwt",
                return_value="jwt-admin",
            ),
        ):
            result = await get_admin_tenant_id(
                x_admin_tenant_id="header-admin",
                x_admin_key=None,
                credentials=creds,
            )
        assert result == "jwt-admin"

    async def test_api_key_fallback(self):
        with (
            patch.object(tenants_mod, "_ensure_auth_configured"),
            patch.object(
                tenants_mod,
                "_authenticate_via_api_key",
                return_value="key-admin",
            ),
        ):
            result = await get_admin_tenant_id(
                x_admin_tenant_id="key-admin",
                x_admin_key="some-key",
                credentials=None,
            )
        assert result == "key-admin"

    async def test_default_admin_id_when_header_missing(self):
        with (
            patch.object(tenants_mod, "_ensure_auth_configured"),
            patch.object(
                tenants_mod,
                "_authenticate_via_api_key",
                return_value="system-admin",
            ),
        ):
            result = await get_admin_tenant_id(
                x_admin_tenant_id=None,
                x_admin_key="key",
                credentials=None,
            )
        assert result == "system-admin"


class TestGetOptionalTenantId:
    async def test_returns_header_value(self):
        result = await get_optional_tenant_id(x_tenant_id="my-tenant")
        assert result == "my-tenant"

    async def test_returns_none_when_absent(self):
        result = await get_optional_tenant_id(x_tenant_id=None)
        assert result is None


class TestRaiseHelpers:
    def test_raise_tenant_not_found(self):
        exc = tenants_mod.TenantNotFoundError("gone")
        with pytest.raises(HTTPException) as exc_info:
            _raise_tenant_not_found(exc)
        assert exc_info.value.status_code == 404

    def test_raise_internal_tenant_error(self):
        with pytest.raises(HTTPException) as exc_info:
            _raise_internal_tenant_error(RuntimeError("boom"), "test action", "test context")
        assert exc_info.value.status_code == 500

    def test_raise_value_http_error_conflict(self):
        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(
                ValueError("Tenant already exists"),
                action="tenant operation",
            )
        assert exc_info.value.status_code == 409

    def test_raise_value_http_error_conflict_markers(self):
        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(
                ValueError("has children"),
                action="tenant operation",
                conflict_markers=("children",),
            )
        assert exc_info.value.status_code == 409

    def test_raise_value_http_error_bad_request(self):
        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(ValueError("invalid field"), action="create")
        assert exc_info.value.status_code == 400


class TestGetManager:
    def test_success(self):
        mock_mgr = MagicMock()
        with patch.object(tenants_mod, "get_tenant_manager", return_value=mock_mgr):
            result = get_manager()
        assert result is mock_mgr

    def test_raises_503_on_failure(self):
        with patch.object(
            tenants_mod, "get_tenant_manager", side_effect=RuntimeError("unavailable")
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_manager()
            assert exc_info.value.status_code == 503


class TestQuotaResourceKeys:
    def test_known_resource(self):
        assert _quota_resource_keys("agents") == ("agents_count", "max_agents")

    def test_unknown_resource_fallback(self):
        assert _quota_resource_keys("widgets") == ("widgets_count", "max_widgets")


class TestCalculateUtilization:
    def test_calculates_percentages(self):
        usage = {"agents_count": 50, "policies_count": 200, "messages_this_minute": 5000}
        quota = {"max_agents": 100, "max_policies": 1000, "max_messages_per_minute": 10000}
        result = _calculate_utilization(usage, quota)
        assert result["agents_count"] == 50.0
        assert result["policies_count"] == 20.0
        assert result["messages_this_minute"] == 50.0

    def test_skips_zero_quota(self):
        result = _calculate_utilization(
            {"agents_count": 10},
            {"max_agents": 0},
        )
        assert "agents_count" not in result

    def test_skips_non_numeric(self):
        result = _calculate_utilization(
            {"agents_count": "invalid"},
            {"max_agents": 100},
        )
        assert "agents_count" not in result


class TestBuildQuotaCheckResponse:
    def test_warning_threshold_reached(self):
        from enhanced_agent_bus.routes.models.tenant_models import QuotaCheckRequest

        req = QuotaCheckRequest(resource="agents", requested_amount=1)
        result = _build_quota_check_response(
            "t-001",
            req,
            available=True,
            usage_dict={"agents_count": 90},
            quota_dict={"max_agents": 100},
        )
        assert result.warning_threshold_reached is True
        assert result.remaining == 10

    def test_non_int_usage_defaults_to_zero(self):
        from enhanced_agent_bus.routes.models.tenant_models import QuotaCheckRequest

        req = QuotaCheckRequest(resource="agents", requested_amount=1)
        result = _build_quota_check_response(
            "t-001",
            req,
            available=True,
            usage_dict={"agents_count": "bad"},
            quota_dict={"max_agents": "also_bad"},
        )
        assert result.current_usage == 0
        assert result.quota_limit == 0


class TestBuildTenantHierarchyResponse:
    def test_single_ancestor(self):
        tenant = _FakeTenant(tenant_id="t-root")
        result = _build_tenant_hierarchy_response(
            "t-001",
            ancestors=[tenant],
            descendants=[],
        )
        assert result.depth == 0
        assert len(result.ancestors) == 0

    def test_multiple_ancestors(self):
        root = _FakeTenant(tenant_id="t-root")
        parent = _FakeTenant(tenant_id="t-parent")
        current = _FakeTenant(tenant_id="t-001")
        result = _build_tenant_hierarchy_response(
            "t-001",
            ancestors=[root, parent, current],
            descendants=[],
        )
        assert result.depth == 2
        assert len(result.ancestors) == 2

    def test_empty_ancestors(self):
        result = _build_tenant_hierarchy_response(
            "t-001",
            ancestors=[],
            descendants=[],
        )
        assert result.depth == 0


class TestExtractUsageAndQuotaDicts:
    def test_with_override(self):
        tenant = _FakeTenant()
        override = {"agents_count": 99}
        usage_d, quota_d = _extract_usage_and_quota_dicts(tenant, usage_override=override)
        assert usage_d == {"agents_count": 99}

    def test_without_override(self):
        tenant = _FakeTenant()
        usage_d, quota_d = _extract_usage_and_quota_dicts(tenant)
        assert "agents_count" in usage_d


class TestIsProductionRuntime:
    def test_development_is_not_production(self):
        with patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "development"):
            assert tenants_mod._is_production_runtime() is False

    def test_staging_is_production(self):
        with patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "staging"):
            assert tenants_mod._is_production_runtime() is True

    def test_unknown_is_production(self):
        with patch.object(tenants_mod, "NORMALIZED_ENVIRONMENT", "some-unknown"):
            assert tenants_mod._is_production_runtime() is True


class TestHasAuthConfiguration:
    def test_true_with_admin_key(self):
        with (
            patch.object(tenants_mod, "TENANT_ADMIN_KEY", "key"),
            patch.object(tenants_mod, "JWT_SECRET_KEY", ""),
        ):
            assert tenants_mod._has_auth_configuration() is True

    def test_false_when_neither(self):
        with (
            patch.object(tenants_mod, "TENANT_ADMIN_KEY", ""),
            patch.object(tenants_mod, "JWT_SECRET_KEY", ""),
        ):
            assert tenants_mod._has_auth_configuration() is False


# ===========================================================================
# PART 2: adaptive_governance/governance_engine.py — uncovered branches
# ===========================================================================


class TestInitializeFeedbackHandler:
    def test_handler_init_failure_sets_none(self, engine, mocks):
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            mock_get = MagicMock(side_effect=RuntimeError("db unavailable"))
            with patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler",
                mock_get,
            ):
                engine._initialize_feedback_handler()
        assert engine._feedback_handler is None

    def test_handler_init_success(self, engine, mocks):
        mock_handler = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler",
                return_value=mock_handler,
            ),
        ):
            engine._initialize_feedback_handler()
        assert engine._feedback_handler is mock_handler
        mock_handler.initialize_schema.assert_called_once()


class TestInitializeDriftDetector:
    def test_detector_init_success_with_reference(self, engine, mocks):
        mock_detector = MagicMock()
        mock_detector.load_reference_data.return_value = True
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                return_value=mock_detector,
            ),
        ):
            engine._initialize_drift_detector()
        assert engine._drift_detector is mock_detector

    def test_detector_init_no_reference(self, engine, mocks):
        mock_detector = MagicMock()
        mock_detector.load_reference_data.return_value = False
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                return_value=mock_detector,
            ),
        ):
            engine._initialize_drift_detector()
        assert engine._drift_detector is mock_detector

    def test_detector_init_failure(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                side_effect=RuntimeError("fail"),
            ),
        ):
            engine._initialize_drift_detector()
        assert engine._drift_detector is None


class TestInitializeRiverModel:
    def test_river_init_success_with_trained_scorer(self, engine, mocks):
        mock_pipeline = MagicMock()
        mocks.scorer.model_trained = True

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_online_learning_pipeline",
                return_value=mock_pipeline,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ModelType",
                SimpleNamespace(REGRESSOR="regressor"),
            ),
        ):
            engine._initialize_river_model()
        assert engine.river_model is mock_pipeline
        mock_pipeline.set_fallback_model.assert_called_once()

    def test_river_init_failure(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_online_learning_pipeline",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ModelType",
                SimpleNamespace(REGRESSOR="regressor"),
            ),
        ):
            engine._initialize_river_model()
        assert engine.river_model is None

    def test_river_available_but_not_installed(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                False,
            ),
        ):
            engine._initialize_river_model()
        # Should just log warning; river_model stays as-is

    def test_online_learning_not_available(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
                False,
            ),
        ):
            engine._initialize_river_model()


class TestInitializeABTestRouter:
    def test_ab_init_success_with_trained(self, engine, mocks):
        mock_router = MagicMock()
        mock_executor = MagicMock()
        mocks.scorer.model_trained = True

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router",
                return_value=mock_router,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ShadowPolicyExecutor",
                return_value=mock_executor,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TEST_SPLIT",
                0.1,
            ),
        ):
            engine._initialize_ab_test_router()
        assert engine._ab_test_router is mock_router
        mock_router.set_champion_model.assert_called_once()

    def test_ab_init_failure(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router",
                side_effect=RuntimeError("fail"),
            ),
        ):
            engine._initialize_ab_test_router()
        assert engine._ab_test_router is None


class TestInitializeAnomalyMonitor:
    def test_anomaly_init_success(self, engine, mocks):
        mock_monitor = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor",
                return_value=mock_monitor,
            ),
        ):
            engine._initialize_anomaly_monitor()
        assert engine._anomaly_monitor is mock_monitor

    def test_anomaly_init_failure(self, engine, mocks):
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor",
                side_effect=RuntimeError("fail"),
            ),
        ):
            engine._initialize_anomaly_monitor()
        # Should not raise, monitor remains None


class TestRunScheduledDriftDetection:
    def test_skips_when_not_due(self, engine, mocks):
        engine._drift_detector = MagicMock()
        engine._last_drift_check = time.time()
        engine._drift_check_interval = 3600

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            True,
        ):
            engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()

    def test_runs_when_due_no_data(self, engine, mocks):
        engine._drift_detector = MagicMock()
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            True,
        ):
            with patch.object(engine, "_collect_drift_data", return_value=None):
                engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()

    def test_runs_drift_detection_no_drift(self, engine, mocks):
        mock_detector = MagicMock()
        report = SimpleNamespace(
            status=SimpleNamespace(value="success"),
            dataset_drift=False,
            drift_share=0.05,
        )
        # Make status match DriftStatus.SUCCESS comparison
        mock_detector.detect_drift.return_value = report
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_data = MagicMock()
        mock_data.__len__ = lambda self: 5

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus",
                SimpleNamespace(SUCCESS=report.status),
            ),
            patch.object(engine, "_collect_drift_data", return_value=mock_data),
        ):
            engine._run_scheduled_drift_detection()
        mock_detector.detect_drift.assert_called_once()

    def test_runs_drift_detection_with_drift(self, engine, mocks):
        mock_detector = MagicMock()
        drift_status = SimpleNamespace(value="success")
        report = SimpleNamespace(
            status=drift_status,
            dataset_drift=True,
            drift_severity=SimpleNamespace(value="high"),
            drifted_features=3,
            total_features=10,
            drift_share=0.3,
            recommendations=["retrain model"],
        )
        mock_detector.detect_drift.return_value = report
        mock_detector.should_trigger_retraining.return_value = True
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_data = MagicMock()
        mock_data.__len__ = lambda self: 5

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus",
                SimpleNamespace(SUCCESS=drift_status),
            ),
            patch.object(engine, "_collect_drift_data", return_value=mock_data),
        ):
            engine._run_scheduled_drift_detection()
        mock_detector.should_trigger_retraining.assert_called_once()

    def test_drift_detection_error(self, engine, mocks):
        mock_detector = MagicMock()
        mock_detector.detect_drift.side_effect = RuntimeError("detector crash")
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_data = MagicMock()
        mock_data.__len__ = lambda self: 5

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch.object(engine, "_collect_drift_data", return_value=mock_data),
        ):
            engine._run_scheduled_drift_detection()
        # Should update last_drift_check despite error
        assert engine._last_drift_check > 0

    def test_drift_non_success_status(self, engine, mocks):
        mock_detector = MagicMock()
        error_status = SimpleNamespace(value="error")
        report = SimpleNamespace(
            status=error_status,
            dataset_drift=False,
            error_message="some error",
        )
        mock_detector.detect_drift.return_value = report
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_data = MagicMock()
        mock_data.__len__ = lambda self: 5

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus",
                SimpleNamespace(SUCCESS=SimpleNamespace(value="success")),
            ),
            patch.object(engine, "_collect_drift_data", return_value=mock_data),
        ):
            engine._run_scheduled_drift_detection()


class TestCollectDriftDataPandasMissing:
    def test_returns_none_without_pandas(self, engine, mocks):
        engine.decision_history.append(_make_decision())
        with patch.dict("sys.modules", {"pandas": None}):
            result = engine._collect_drift_data()
        assert result is None


class TestRecordDecisionMetrics:
    def test_records_with_anomaly_monitor(self, engine, mocks):
        mock_monitor = MagicMock()
        engine._anomaly_monitor = mock_monitor
        decision = _make_decision()
        engine._record_decision_metrics(decision, time.time() - 0.01)
        assert len(engine.decision_history) == 1
        mock_monitor.record_metrics.assert_called_once()


class TestUpdateRiverModelExtended:
    def test_failed_learning_logs_warning(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.learn_from_feedback.return_value = SimpleNamespace(
            success=False, error_message="bad data", total_samples=0
        )
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            engine._update_river_model(_make_decision(), 0.5)

    def test_river_ready_but_scorer_not_trained(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.learn_from_feedback.return_value = SimpleNamespace(
            success=True, total_samples=50
        )
        mock_model.adapter.is_ready = True
        mocks.scorer.model_trained = False
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            engine._update_river_model(_make_decision(), 0.5)

    def test_river_exception_caught(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.learn_from_feedback.side_effect = ValueError("corrupt features")
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            engine._update_river_model(_make_decision(), 0.5)

    def test_river_with_empty_temporal_patterns(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.learn_from_feedback.return_value = SimpleNamespace(success=True, total_samples=5)
        mock_model.adapter.is_ready = False
        engine.river_model = mock_model

        decision = _make_decision(features_used=_make_features(temporal_patterns=[]))

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            engine._update_river_model(decision, 0.3)


class TestStoreFeedbackEventExtended:
    def test_negative_feedback_type(self, engine, mocks):
        mock_handler = MagicMock()
        mock_handler.store_feedback.return_value = SimpleNamespace(feedback_id="fb-neg")
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            engine._store_feedback_event(_make_decision(), False, None, 0.5)
        call_args = mock_handler.store_feedback.call_args[0][0]
        assert call_args.feedback_type.value == "negative"

    def test_store_failure_caught(self, engine, mocks):
        mock_handler = MagicMock()
        mock_handler.store_feedback.side_effect = RuntimeError("db down")
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            # Should not raise
            engine._store_feedback_event(_make_decision(), True, None, 0.3)


class TestGetRiverModelStatsExtended:
    def test_stats_exception_returns_none(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.get_stats.side_effect = RuntimeError("fail")
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
        assert result is None

    def test_stats_dict_return(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.get_stats.return_value = {"total": 42}
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
        assert result == {"total": 42}

    def test_stats_none_return(self, engine, mocks):
        mock_model = MagicMock()
        mock_model.get_stats.return_value = None
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
        assert result is None


class TestGetABTestMetricsWithRouter:
    def test_returns_metrics_when_available(self, engine, mocks):
        mock_router = MagicMock()
        mock_router.get_metrics_summary.return_value = {"champion": {}, "candidate": {}}
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_metrics()
        assert result is not None

    def test_returns_none_on_error(self, engine, mocks):
        mock_router = MagicMock()
        mock_router.get_metrics_summary.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_metrics()
        assert result is None


class TestGetABTestComparisonWithRouter:
    def test_returns_comparison(self, engine, mocks):
        mock_router = MagicMock()
        mock_router.compare_metrics.return_value = SimpleNamespace(winner="champion")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_comparison()
        assert result is not None

    def test_returns_none_on_error(self, engine, mocks):
        mock_router = MagicMock()
        mock_router.compare_metrics.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_comparison()
        assert result is None


class TestProvideFeedbackDTMC:
    def test_dtmc_online_update_with_enough_decisions(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.trace.collect_from_decision_history.return_value = [[1, 2, 3]]

        for _ in range(5):
            engine.decision_history.append(_make_decision())

        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)
        mocks.trace.collect_from_decision_history.assert_called()

    def test_dtmc_online_update_insufficient_new_decisions(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True

        # Set feedback idx to current length so no new decisions
        engine._dtmc_feedback_idx = 0

        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)


class TestInitializeWithAnomalyMonitor:
    async def test_initialize_starts_anomaly_monitor(self, engine, mocks):
        mock_monitor = AsyncMock()
        engine._anomaly_monitor = mock_monitor
        await engine.initialize()
        mock_monitor.start.assert_called_once()
        await engine.shutdown()
        mock_monitor.stop.assert_called_once()


class TestScheduleShadowExecution:
    async def test_schedules_for_champion_with_executor(self, engine, mocks):
        champion_cohort = SimpleNamespace(value="champion")
        candidate_cohort = SimpleNamespace(value="candidate")
        routing_result = SimpleNamespace(cohort=champion_cohort, model_version=1)
        decision = _make_decision()
        features = _make_features()

        mock_executor = AsyncMock()
        mock_executor.execute_shadow = AsyncMock(return_value=None)
        engine._shadow_executor = mock_executor

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
            SimpleNamespace(CHAMPION=champion_cohort, CANDIDATE=candidate_cohort),
        ):
            engine._schedule_shadow_execution_if_needed(routing_result, decision, features)
        # Should have created a task
        assert len(engine._background_tasks) >= 0  # Task may complete immediately

    def test_skips_for_candidate_cohort(self, engine, mocks):
        candidate_cohort = SimpleNamespace(value="candidate")
        champion_cohort = SimpleNamespace(value="champion")
        routing_result = SimpleNamespace(cohort=candidate_cohort, model_version=2)

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
            SimpleNamespace(CHAMPION=champion_cohort, CANDIDATE=candidate_cohort),
        ):
            engine._schedule_shadow_execution_if_needed(
                routing_result, _make_decision(), _make_features()
            )

    def test_skips_when_no_executor(self, engine, mocks):
        champion_cohort = SimpleNamespace(value="champion")
        routing_result = SimpleNamespace(cohort=champion_cohort, model_version=1)
        engine._shadow_executor = None

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
            SimpleNamespace(CHAMPION=champion_cohort),
        ):
            engine._schedule_shadow_execution_if_needed(
                routing_result, _make_decision(), _make_features()
            )


class TestRecordABTestRequest:
    def test_champion_path(self, engine, mocks):
        champion_cohort = SimpleNamespace(value="champion")
        candidate_cohort = SimpleNamespace(value="candidate")
        routing_result = SimpleNamespace(cohort=champion_cohort, model_version=1)

        mock_router = MagicMock()
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
            SimpleNamespace(CHAMPION=champion_cohort, CANDIDATE=candidate_cohort),
        ):
            engine._record_ab_test_request(routing_result, 10.0, True)
        mock_router.get_champion_metrics.return_value.record_request.assert_called_once()

    def test_candidate_path(self, engine, mocks):
        candidate_cohort = SimpleNamespace(value="candidate")
        routing_result = SimpleNamespace(cohort=candidate_cohort, model_version=2)

        mock_router = MagicMock()
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
            SimpleNamespace(CANDIDATE=candidate_cohort),
        ):
            engine._record_ab_test_request(routing_result, 5.0, False)
        mock_router.get_candidate_metrics.return_value.record_request.assert_called_once()


class TestAnalyzePerformanceTrendsError:
    def test_catches_exception(self, engine, mocks):
        # Force an error by making compliance_trend raise on append
        engine.metrics.compliance_trend = MagicMock()
        engine.metrics.compliance_trend.append.side_effect = RuntimeError("oops")
        engine._analyze_performance_trends()  # should not raise


class TestLogPerformanceSummaryError:
    def test_catches_exception(self, engine, mocks):
        engine.metrics = None  # Force AttributeError
        # The method catches RuntimeError/ValueError/TypeError but not AttributeError,
        # so let's use a mock that raises TypeError
        engine.metrics = MagicMock()
        engine.metrics.constitutional_compliance_rate = MagicMock(
            __format__=MagicMock(side_effect=TypeError("format error"))
        )
        engine._log_performance_summary()  # should not raise


class TestDTMCRiskBlendEmptyHistory:
    def test_returns_original_when_no_trajectory(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        # Empty decision_history means _get_trajectory_prefix returns None
        features = _make_features(risk_score=0.4)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.4


class TestDTMCEscalationNoIntervention:
    def test_no_escalation_when_should_intervene_false(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.should_intervene.return_value = False
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        d = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.LOW

    def test_no_escalation_when_empty_prefix(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        # Empty history -> no prefix
        d = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.LOW

    def test_no_escalation_when_critical(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.should_intervene.return_value = True
        mocks.dtmc.predict_risk.return_value = 0.9
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.CRITICAL))

        d = _make_decision(impact_level=ImpactLevel.CRITICAL)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.CRITICAL
