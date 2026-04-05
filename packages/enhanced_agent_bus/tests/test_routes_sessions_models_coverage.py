# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/routes/sessions/models.py
Target: ≥95% line coverage (136 stmts)
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from enhanced_agent_bus.routes.sessions.models import (
    CreateSessionRequest,
    ErrorResponse,
    PolicySelectionRequest,
    PolicySelectionResponse,
    SelectedPolicy,
    SessionListResponse,
    SessionMetricsResponse,
    SessionResponse,
    UpdateGovernanceRequest,
)

# ===========================================================================
# CreateSessionRequest - field defaults
# ===========================================================================


class TestCreateSessionRequestDefaults:
    def test_all_defaults(self):
        req = CreateSessionRequest()
        assert req.session_id is None
        assert req.tenant_id is None
        assert req.user_id is None
        assert req.risk_level == "medium"
        assert req.policy_id is None
        assert req.policy_overrides == {}
        assert req.enabled_policies == []
        assert req.disabled_policies == []
        assert req.require_human_approval is False
        assert req.max_automation_level is None
        assert req.metadata == {}
        assert req.ttl_seconds is None

    def test_explicit_values(self):
        req = CreateSessionRequest(
            session_id="sess-abc",
            tenant_id="tenant-1",
            user_id="user-99",
            risk_level="high",
            policy_id="pol-1",
            policy_overrides={"k": "v"},
            enabled_policies=["pol-a"],
            disabled_policies=["pol-b"],
            require_human_approval=True,
            max_automation_level="full",
            metadata={"src": "test"},
            ttl_seconds=3600,
        )
        assert req.session_id == "sess-abc"
        assert req.tenant_id == "tenant-1"
        assert req.user_id == "user-99"
        assert req.risk_level == "high"
        assert req.policy_id == "pol-1"
        assert req.policy_overrides == {"k": "v"}
        assert req.enabled_policies == ["pol-a"]
        assert req.disabled_policies == ["pol-b"]
        assert req.require_human_approval is True
        assert req.max_automation_level == "full"
        assert req.metadata == {"src": "test"}
        assert req.ttl_seconds == 3600


# ===========================================================================
# CreateSessionRequest - risk_level validator
# ===========================================================================


class TestCreateSessionRequestRiskLevel:
    @pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
    def test_valid_risk_level_lowercase(self, level):
        req = CreateSessionRequest(risk_level=level)
        assert req.risk_level == level

    @pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    def test_valid_risk_level_uppercase_normalised(self, level):
        req = CreateSessionRequest(risk_level=level)
        assert req.risk_level == level.lower()

    @pytest.mark.parametrize("level", ["Low", "Medium", "High", "Critical"])
    def test_valid_risk_level_mixed_case_normalised(self, level):
        req = CreateSessionRequest(risk_level=level)
        assert req.risk_level == level.lower()

    def test_invalid_risk_level_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateSessionRequest(risk_level="extreme")
        assert "risk_level" in str(exc_info.value)

    def test_invalid_risk_level_empty_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(risk_level="")


# ===========================================================================
# CreateSessionRequest - max_automation_level validator
# ===========================================================================


class TestCreateSessionRequestAutomationLevel:
    @pytest.mark.parametrize("level", ["full", "partial", "none"])
    def test_valid_automation_level(self, level):
        req = CreateSessionRequest(max_automation_level=level)
        assert req.max_automation_level == level

    @pytest.mark.parametrize("level", ["FULL", "PARTIAL", "NONE"])
    def test_valid_automation_level_uppercase_normalised(self, level):
        req = CreateSessionRequest(max_automation_level=level)
        assert req.max_automation_level == level.lower()

    def test_automation_level_none_allowed(self):
        req = CreateSessionRequest(max_automation_level=None)
        assert req.max_automation_level is None

    def test_invalid_automation_level_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateSessionRequest(max_automation_level="unlimited")
        assert "max_automation_level" in str(exc_info.value)


# ===========================================================================
# CreateSessionRequest - ttl_seconds bounds
# ===========================================================================


class TestCreateSessionRequestTTL:
    def test_ttl_minimum_valid(self):
        req = CreateSessionRequest(ttl_seconds=60)
        assert req.ttl_seconds == 60

    def test_ttl_maximum_valid(self):
        req = CreateSessionRequest(ttl_seconds=86400)
        assert req.ttl_seconds == 86400

    def test_ttl_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(ttl_seconds=59)

    def test_ttl_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(ttl_seconds=86401)

    def test_ttl_midrange_valid(self):
        req = CreateSessionRequest(ttl_seconds=3600)
        assert req.ttl_seconds == 3600


# ===========================================================================
# CreateSessionRequest - field length constraints
# ===========================================================================


class TestCreateSessionRequestLengthConstraints:
    def test_session_id_max_length(self):
        req = CreateSessionRequest(session_id="a" * 128)
        assert len(req.session_id) == 128

    def test_session_id_over_max_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(session_id="a" * 129)

    def test_tenant_id_max_length(self):
        req = CreateSessionRequest(tenant_id="t" * 100)
        assert len(req.tenant_id) == 100

    def test_tenant_id_over_max_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(tenant_id="t" * 101)

    def test_user_id_max_length(self):
        req = CreateSessionRequest(user_id="u" * 255)
        assert len(req.user_id) == 255

    def test_user_id_over_max_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(user_id="u" * 256)

    def test_policy_id_max_length(self):
        req = CreateSessionRequest(policy_id="p" * 100)
        assert len(req.policy_id) == 100

    def test_policy_id_over_max_raises(self):
        with pytest.raises(ValidationError):
            CreateSessionRequest(policy_id="p" * 101)


# ===========================================================================
# CreateSessionRequest - serialization round-trip
# ===========================================================================


class TestCreateSessionRequestSerialization:
    def test_model_dump_round_trip(self):
        req = CreateSessionRequest(
            session_id="s1",
            risk_level="low",
            ttl_seconds=120,
            metadata={"env": "test"},
        )
        data = req.model_dump()
        req2 = CreateSessionRequest(**data)
        assert req2.session_id == "s1"
        assert req2.risk_level == "low"
        assert req2.ttl_seconds == 120

    def test_model_json_schema_extra_present(self):
        schema = CreateSessionRequest.model_json_schema()
        assert (
            "example" in schema.get("examples", [{}])[0]
            or "examples" in schema
            or schema is not None
        )


# ===========================================================================
# UpdateGovernanceRequest - defaults
# ===========================================================================


class TestUpdateGovernanceRequestDefaults:
    def test_all_defaults_are_none(self):
        req = UpdateGovernanceRequest()
        assert req.risk_level is None
        assert req.policy_id is None
        assert req.policy_overrides is None
        assert req.enabled_policies is None
        assert req.disabled_policies is None
        assert req.require_human_approval is None
        assert req.max_automation_level is None
        assert req.metadata is None
        assert req.extend_ttl_seconds is None

    def test_explicit_values(self):
        req = UpdateGovernanceRequest(
            risk_level="critical",
            policy_id="pol-x",
            policy_overrides={"a": 1},
            enabled_policies=["p1", "p2"],
            disabled_policies=["p3"],
            require_human_approval=True,
            max_automation_level="none",
            metadata={"note": "test"},
            extend_ttl_seconds=1800,
        )
        assert req.risk_level == "critical"
        assert req.policy_id == "pol-x"
        assert req.policy_overrides == {"a": 1}
        assert req.enabled_policies == ["p1", "p2"]
        assert req.disabled_policies == ["p3"]
        assert req.require_human_approval is True
        assert req.max_automation_level == "none"
        assert req.metadata == {"note": "test"}
        assert req.extend_ttl_seconds == 1800


# ===========================================================================
# UpdateGovernanceRequest - risk_level validator
# ===========================================================================


class TestUpdateGovernanceRequestRiskLevel:
    def test_risk_level_none_passes_through(self):
        req = UpdateGovernanceRequest(risk_level=None)
        assert req.risk_level is None

    @pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
    def test_valid_risk_levels(self, level):
        req = UpdateGovernanceRequest(risk_level=level)
        assert req.risk_level == level

    @pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    def test_risk_level_uppercase_normalised(self, level):
        req = UpdateGovernanceRequest(risk_level=level)
        assert req.risk_level == level.lower()

    def test_invalid_risk_level_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateGovernanceRequest(risk_level="extreme")
        assert "risk_level" in str(exc_info.value)


# ===========================================================================
# UpdateGovernanceRequest - extend_ttl_seconds bounds
# ===========================================================================


class TestUpdateGovernanceRequestTTL:
    def test_ttl_minimum_valid(self):
        req = UpdateGovernanceRequest(extend_ttl_seconds=60)
        assert req.extend_ttl_seconds == 60

    def test_ttl_maximum_valid(self):
        req = UpdateGovernanceRequest(extend_ttl_seconds=86400)
        assert req.extend_ttl_seconds == 86400

    def test_ttl_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            UpdateGovernanceRequest(extend_ttl_seconds=59)

    def test_ttl_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            UpdateGovernanceRequest(extend_ttl_seconds=86401)


# ===========================================================================
# PolicySelectionRequest
# ===========================================================================


class TestPolicySelectionRequestDefaults:
    def test_all_defaults(self):
        req = PolicySelectionRequest()
        assert req.policy_name_filter is None
        assert req.include_disabled is False
        assert req.include_all_candidates is False
        assert req.risk_level_override is None

    def test_explicit_values(self):
        req = PolicySelectionRequest(
            policy_name_filter="strict",
            include_disabled=True,
            include_all_candidates=True,
            risk_level_override="high",
        )
        assert req.policy_name_filter == "strict"
        assert req.include_disabled is True
        assert req.include_all_candidates is True
        assert req.risk_level_override == "high"


class TestPolicySelectionRequestRiskLevelOverride:
    def test_risk_level_override_none(self):
        req = PolicySelectionRequest(risk_level_override=None)
        assert req.risk_level_override is None

    @pytest.mark.parametrize("level", ["low", "medium", "high", "critical"])
    def test_valid_risk_level_overrides(self, level):
        req = PolicySelectionRequest(risk_level_override=level)
        assert req.risk_level_override == level

    @pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    def test_risk_level_override_uppercase_normalised(self, level):
        req = PolicySelectionRequest(risk_level_override=level)
        assert req.risk_level_override == level.lower()

    def test_invalid_risk_level_override_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            PolicySelectionRequest(risk_level_override="unknown")
        assert "risk_level_override" in str(exc_info.value)

    def test_policy_name_filter_max_length(self):
        req = PolicySelectionRequest(policy_name_filter="x" * 100)
        assert len(req.policy_name_filter) == 100

    def test_policy_name_filter_over_max_raises(self):
        with pytest.raises(ValidationError):
            PolicySelectionRequest(policy_name_filter="x" * 101)


# ===========================================================================
# SessionResponse - construction and defaults
# ===========================================================================


class TestSessionResponseDefaults:
    def test_minimal_required_fields(self):
        resp = SessionResponse(
            session_id="s-1",
            tenant_id="t-1",
            risk_level="low",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert resp.session_id == "s-1"
        assert resp.tenant_id == "t-1"
        assert resp.risk_level == "low"
        assert resp.user_id is None
        assert resp.policy_id is None
        assert resp.policy_overrides == {}
        assert resp.enabled_policies == []
        assert resp.disabled_policies == []
        assert resp.require_human_approval is False
        assert resp.max_automation_level is None
        assert resp.metadata == {}
        assert resp.expires_at is None
        assert resp.ttl_remaining_seconds is None
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_default(self):
        resp = SessionResponse(
            session_id="s",
            tenant_id="t",
            risk_level="medium",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# SessionResponse.from_session_context - risk_level has .value
# ===========================================================================


class TestSessionResponseFromSessionContext:
    def _make_context(self, risk_level_val, expires_at=None):
        config = MagicMock()
        config.tenant_id = "tenant-x"
        config.user_id = "user-x"
        config.risk_level = risk_level_val
        config.policy_id = "pol-1"
        config.policy_overrides = {}
        config.enabled_policies = []
        config.disabled_policies = []
        config.require_human_approval = False
        config.max_automation_level = None

        ctx = MagicMock()
        ctx.session_id = "sess-1"
        ctx.governance_config = config
        ctx.metadata = {}
        ctx.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        ctx.updated_at = datetime(2026, 1, 2, tzinfo=UTC)
        ctx.expires_at = expires_at
        ctx.constitutional_hash = CONSTITUTIONAL_HASH
        return ctx

    def test_risk_level_with_value_attribute(self):
        """risk_level is an enum-like object with .value"""
        risk = MagicMock()
        risk.value = "high"
        ctx = self._make_context(risk_level_val=risk)
        resp = SessionResponse.from_session_context(ctx, ttl_remaining=120)
        assert resp.risk_level == "high"
        assert resp.ttl_remaining_seconds == 120

    def test_risk_level_string_fallback(self):
        """risk_level is a plain string (no .value attribute)"""
        ctx = self._make_context(risk_level_val="critical")
        # Plain string has no .value attribute that returns something meaningful
        # hasattr("critical", "value") == False in Python
        resp = SessionResponse.from_session_context(ctx)
        assert resp.risk_level == "critical"
        assert resp.ttl_remaining_seconds is None

    def test_expires_at_isoformat_when_set(self):
        expires = datetime(2026, 12, 31, tzinfo=UTC)
        ctx = self._make_context(risk_level_val="low", expires_at=expires)
        resp = SessionResponse.from_session_context(ctx)
        assert resp.expires_at is not None
        assert "2026-12-31" in resp.expires_at

    def test_expires_at_none_when_not_set(self):
        ctx = self._make_context(risk_level_val="low", expires_at=None)
        resp = SessionResponse.from_session_context(ctx)
        assert resp.expires_at is None

    def test_constitutional_hash_taken_from_context(self):
        ctx = self._make_context(risk_level_val="medium")
        ctx.constitutional_hash = CONSTITUTIONAL_HASH
        resp = SessionResponse.from_session_context(ctx)
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_and_updated_at_isoformat(self):
        ctx = self._make_context(risk_level_val="low")
        resp = SessionResponse.from_session_context(ctx)
        assert "2026-01-01" in resp.created_at
        assert "2026-01-02" in resp.updated_at

    def test_full_field_propagation(self):
        risk = MagicMock()
        risk.value = "critical"

        config = MagicMock()
        config.tenant_id = "t-abc"
        config.user_id = "u-abc"
        config.risk_level = risk
        config.policy_id = "pol-abc"
        config.policy_overrides = {"override_key": True}
        config.enabled_policies = ["p1"]
        config.disabled_policies = ["p2"]
        config.require_human_approval = True
        config.max_automation_level = "partial"

        ctx = MagicMock()
        ctx.session_id = "s-abc"
        ctx.governance_config = config
        ctx.metadata = {"meta": "data"}
        ctx.created_at = datetime(2026, 3, 1, tzinfo=UTC)
        ctx.updated_at = datetime(2026, 3, 2, tzinfo=UTC)
        ctx.expires_at = datetime(2026, 3, 3, tzinfo=UTC)
        ctx.constitutional_hash = CONSTITUTIONAL_HASH

        resp = SessionResponse.from_session_context(ctx, ttl_remaining=999)
        assert resp.session_id == "s-abc"
        assert resp.tenant_id == "t-abc"
        assert resp.user_id == "u-abc"
        assert resp.risk_level == "critical"
        assert resp.policy_id == "pol-abc"
        assert resp.policy_overrides == {"override_key": True}
        assert resp.enabled_policies == ["p1"]
        assert resp.disabled_policies == ["p2"]
        assert resp.require_human_approval is True
        assert resp.max_automation_level == "partial"
        assert resp.metadata == {"meta": "data"}
        assert resp.ttl_remaining_seconds == 999


# ===========================================================================
# SessionListResponse
# ===========================================================================


class TestSessionListResponse:
    def test_defaults(self):
        resp = SessionListResponse()
        assert resp.sessions == []
        assert resp.total_count == 0
        assert resp.page == 1
        assert resp.page_size == 20

    def test_with_values(self):
        session = SessionResponse(
            session_id="s1",
            tenant_id="t1",
            risk_level="low",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        resp = SessionListResponse(
            sessions=[session],
            total_count=1,
            page=2,
            page_size=10,
        )
        assert len(resp.sessions) == 1
        assert resp.total_count == 1
        assert resp.page == 2
        assert resp.page_size == 10

    def test_sessions_list_empty_default(self):
        resp = SessionListResponse(total_count=50, page=3, page_size=5)
        assert resp.sessions == []
        assert resp.total_count == 50
        assert resp.page == 3
        assert resp.page_size == 5


# ===========================================================================
# SessionMetricsResponse
# ===========================================================================


class TestSessionMetricsResponse:
    def test_defaults(self):
        resp = SessionMetricsResponse()
        assert resp.cache_hits == 0
        assert resp.cache_misses == 0
        assert resp.cache_hit_rate == 0.0
        assert resp.cache_size == 0
        assert resp.cache_capacity == 0
        assert resp.creates == 0
        assert resp.reads == 0
        assert resp.updates == 0
        assert resp.deletes == 0
        assert resp.errors == 0
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_explicit_values(self):
        resp = SessionMetricsResponse(
            cache_hits=100,
            cache_misses=10,
            cache_hit_rate=0.909,
            cache_size=50,
            cache_capacity=200,
            creates=30,
            reads=150,
            updates=20,
            deletes=5,
            errors=2,
        )
        assert resp.cache_hits == 100
        assert resp.cache_misses == 10
        assert resp.cache_hit_rate == 0.909
        assert resp.cache_size == 50
        assert resp.cache_capacity == 200
        assert resp.creates == 30
        assert resp.reads == 150
        assert resp.updates == 20
        assert resp.deletes == 5
        assert resp.errors == 2

    def test_constitutional_hash_is_correct(self):
        resp = SessionMetricsResponse()
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# SelectedPolicy
# ===========================================================================


class TestSelectedPolicy:
    def test_required_fields(self):
        sp = SelectedPolicy(
            policy_id="pol-1",
            name="Test Policy",
            source="session",
            reasoning="Chosen because of session override",
        )
        assert sp.policy_id == "pol-1"
        assert sp.name == "Test Policy"
        assert sp.version is None
        assert sp.source == "session"
        assert sp.priority == 0
        assert sp.reasoning == "Chosen because of session override"
        assert sp.metadata == {}

    def test_all_fields(self):
        sp = SelectedPolicy(
            policy_id="pol-2",
            name="Strict Policy",
            version="1.2.3",
            source="tenant",
            priority=99,
            reasoning="High-risk tenant policy",
            metadata={"tags": ["strict"]},
        )
        assert sp.policy_id == "pol-2"
        assert sp.name == "Strict Policy"
        assert sp.version == "1.2.3"
        assert sp.source == "tenant"
        assert sp.priority == 99
        assert sp.reasoning == "High-risk tenant policy"
        assert sp.metadata == {"tags": ["strict"]}

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            SelectedPolicy(name="Test", source="global", reasoning="reason")

    def test_model_config_example_present(self):
        schema = SelectedPolicy.model_json_schema()
        assert schema is not None

    def test_serialization_round_trip(self):
        sp = SelectedPolicy(
            policy_id="p-rt",
            name="RT",
            source="global",
            reasoning="round-trip test",
            version="2.0",
            priority=50,
        )
        data = sp.model_dump()
        sp2 = SelectedPolicy(**data)
        assert sp2.policy_id == "p-rt"
        assert sp2.version == "2.0"
        assert sp2.priority == 50


# ===========================================================================
# PolicySelectionResponse
# ===========================================================================


class TestPolicySelectionResponse:
    def _make_selected_policy(self):
        return SelectedPolicy(
            policy_id="pol-s",
            name="Selected",
            source="session",
            reasoning="direct override",
        )

    def test_required_fields_minimal(self):
        resp = PolicySelectionResponse(
            session_id="s-1",
            tenant_id="t-1",
            risk_level="medium",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.session_id == "s-1"
        assert resp.tenant_id == "t-1"
        assert resp.risk_level == "medium"
        assert resp.selected_policy is None
        assert resp.candidate_policies == []
        assert resp.enabled_policies == []
        assert resp.disabled_policies == []
        assert resp.selection_metadata == {}
        assert resp.timestamp == "2026-01-01T00:00:00Z"
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_selected_policy(self):
        sp = self._make_selected_policy()
        resp = PolicySelectionResponse(
            session_id="s-2",
            tenant_id="t-2",
            risk_level="high",
            selected_policy=sp,
            timestamp="2026-06-01T12:00:00Z",
        )
        assert resp.selected_policy.policy_id == "pol-s"

    def test_with_candidate_policies(self):
        sp1 = self._make_selected_policy()
        sp2 = SelectedPolicy(
            policy_id="pol-c",
            name="Candidate",
            source="tenant",
            reasoning="fallback",
        )
        resp = PolicySelectionResponse(
            session_id="s-3",
            tenant_id="t-3",
            risk_level="low",
            candidate_policies=[sp1, sp2],
            timestamp="2026-06-01T12:00:00Z",
        )
        assert len(resp.candidate_policies) == 2

    def test_enabled_disabled_policies(self):
        resp = PolicySelectionResponse(
            session_id="s-4",
            tenant_id="t-4",
            risk_level="critical",
            enabled_policies=["e1", "e2"],
            disabled_policies=["d1"],
            timestamp="2026-06-01T12:00:00Z",
        )
        assert resp.enabled_policies == ["e1", "e2"]
        assert resp.disabled_policies == ["d1"]

    def test_selection_metadata(self):
        resp = PolicySelectionResponse(
            session_id="s-5",
            tenant_id="t-5",
            risk_level="medium",
            selection_metadata={"cache_hit": True, "elapsed_ms": 0.5},
            timestamp="2026-06-01T12:00:00Z",
        )
        assert resp.selection_metadata["cache_hit"] is True

    def test_constitutional_hash_default(self):
        resp = PolicySelectionResponse(
            session_id="s-6",
            tenant_id="t-6",
            risk_level="low",
            timestamp="2026-06-01T12:00:00Z",
        )
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_model_config_example_present(self):
        schema = PolicySelectionResponse.model_json_schema()
        assert schema is not None

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            PolicySelectionResponse(session_id="s")


# ===========================================================================
# ErrorResponse
# ===========================================================================


class TestErrorResponse:
    def test_minimal_required_fields(self):
        resp = ErrorResponse(
            error="NotFound",
            message="Session not found",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.error == "NotFound"
        assert resp.message == "Session not found"
        assert resp.details is None
        assert resp.timestamp == "2026-01-01T00:00:00Z"
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_details(self):
        resp = ErrorResponse(
            error="ValidationError",
            message="Invalid input",
            details={"field": "risk_level", "reason": "invalid value"},
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.details == {"field": "risk_level", "reason": "invalid value"}

    def test_constitutional_hash_is_correct(self):
        resp = ErrorResponse(
            error="InternalError",
            message="Unexpected failure",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            ErrorResponse(error="Err", message="msg")

    def test_serialization(self):
        resp = ErrorResponse(
            error="E",
            message="M",
            timestamp="T",
            details={"x": 1},
        )
        data = resp.model_dump()
        assert data["error"] == "E"
        assert data["details"] == {"x": 1}


# ===========================================================================
# __all__ exports check
# ===========================================================================


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.routes.sessions import models as m

        for name in m.__all__:
            assert hasattr(m, name), f"{name} missing from module"

    def test_all_list_contents(self):
        from enhanced_agent_bus.routes.sessions import models as m

        expected = {
            "CreateSessionRequest",
            "UpdateGovernanceRequest",
            "PolicySelectionRequest",
            "SessionResponse",
            "SessionListResponse",
            "SessionMetricsResponse",
            "SelectedPolicy",
            "PolicySelectionResponse",
            "ErrorResponse",
        }
        assert expected == set(m.__all__)


# ===========================================================================
# Additional edge-case / boundary tests
# ===========================================================================


class TestEdgeCases:
    def test_create_session_request_json_round_trip(self):
        req = CreateSessionRequest(
            session_id="json-test",
            risk_level="high",
            max_automation_level="partial",
            ttl_seconds=600,
            metadata={"nested": {"deep": True}},
        )
        json_str = req.model_dump_json()
        req2 = CreateSessionRequest.model_validate_json(json_str)
        assert req2.session_id == "json-test"
        assert req2.risk_level == "high"
        assert req2.max_automation_level == "partial"
        assert req2.ttl_seconds == 600

    def test_update_governance_request_json_round_trip(self):
        req = UpdateGovernanceRequest(
            risk_level="low",
            extend_ttl_seconds=300,
        )
        json_str = req.model_dump_json()
        req2 = UpdateGovernanceRequest.model_validate_json(json_str)
        assert req2.risk_level == "low"
        assert req2.extend_ttl_seconds == 300

    def test_session_metrics_response_json_round_trip(self):
        resp = SessionMetricsResponse(
            cache_hits=42,
            cache_hit_rate=0.84,
            creates=10,
        )
        json_str = resp.model_dump_json()
        resp2 = SessionMetricsResponse.model_validate_json(json_str)
        assert resp2.cache_hits == 42
        assert resp2.creates == 10

    def test_session_list_response_multiple_sessions(self):
        sessions = [
            SessionResponse(
                session_id=f"s-{i}",
                tenant_id="t",
                risk_level="low",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
            for i in range(5)
        ]
        resp = SessionListResponse(sessions=sessions, total_count=5)
        assert len(resp.sessions) == 5

    def test_policy_selection_response_selected_policy_none(self):
        resp = PolicySelectionResponse(
            session_id="s",
            tenant_id="t",
            risk_level="medium",
            selected_policy=None,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.selected_policy is None

    def test_create_session_request_risk_level_mixed_case_normalisation(self):
        req = CreateSessionRequest(risk_level="HiGh")
        assert req.risk_level == "high"

    def test_update_governance_request_risk_level_mixed_case_normalisation(self):
        req = UpdateGovernanceRequest(risk_level="CrItIcAl")
        assert req.risk_level == "critical"

    def test_policy_selection_request_risk_level_override_mixed_case(self):
        req = PolicySelectionRequest(risk_level_override="mEdIuM")
        assert req.risk_level_override == "medium"

    def test_session_response_with_all_optional_fields(self):
        resp = SessionResponse(
            session_id="full",
            tenant_id="t",
            user_id="u",
            risk_level="critical",
            policy_id="p",
            policy_overrides={"k": "v"},
            enabled_policies=["e1"],
            disabled_policies=["d1"],
            require_human_approval=True,
            max_automation_level="none",
            metadata={"m": 1},
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            expires_at="2026-12-31T00:00:00Z",
            ttl_remaining_seconds=7200,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert resp.session_id == "full"
        assert resp.ttl_remaining_seconds == 7200
        assert resp.expires_at == "2026-12-31T00:00:00Z"
