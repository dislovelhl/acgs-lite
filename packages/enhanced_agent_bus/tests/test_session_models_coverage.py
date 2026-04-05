# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/session_models.py

Targets ≥95% line coverage of session_models.py (72 stmts).
Covers: SessionGovernanceConfig, SessionContext, all methods, validators,
        edge cases, branches, and error paths.
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.enums import RiskLevel
from enhanced_agent_bus.session_models import (
    SessionContext,
    SessionGovernanceConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(**kwargs) -> SessionGovernanceConfig:
    """Create a minimal valid SessionGovernanceConfig."""
    defaults = {
        "session_id": "sess-001",
        "tenant_id": "tenant-a",
    }
    defaults.update(kwargs)
    return SessionGovernanceConfig(**defaults)


def make_context(config: SessionGovernanceConfig | None = None, **kwargs) -> SessionContext:
    """Create a minimal valid SessionContext."""
    if config is None:
        config = make_config()
    defaults = {
        "session_id": "sess-001",
        "config": config,
    }
    defaults.update(kwargs)
    return SessionContext(**defaults)


# ===========================================================================
# SessionGovernanceConfig — construction & defaults
# ===========================================================================


class TestSessionGovernanceConfigDefaults:
    def test_minimal_construction(self):
        cfg = make_config()
        assert cfg.session_id == "sess-001"
        assert cfg.tenant_id == "tenant-a"

    def test_default_user_id_is_none(self):
        cfg = make_config()
        assert cfg.user_id is None

    def test_default_risk_level_medium(self):
        cfg = make_config()
        assert cfg.risk_level == RiskLevel.MEDIUM

    def test_default_policy_id_none(self):
        cfg = make_config()
        assert cfg.policy_id is None

    def test_default_policy_overrides_empty(self):
        cfg = make_config()
        assert cfg.policy_overrides == {}

    def test_default_enabled_policies_empty(self):
        cfg = make_config()
        assert cfg.enabled_policies == []

    def test_default_disabled_policies_empty(self):
        cfg = make_config()
        assert cfg.disabled_policies == []

    def test_default_require_human_approval_false(self):
        cfg = make_config()
        assert cfg.require_human_approval is False

    def test_default_max_automation_level_none(self):
        cfg = make_config()
        assert cfg.max_automation_level is None

    def test_default_constitutional_strictness(self):
        cfg = make_config()
        assert cfg.constitutional_strictness == 1.0

    def test_default_context_tags_empty(self):
        cfg = make_config()
        assert cfg.context_tags == []

    def test_default_metadata_empty(self):
        cfg = make_config()
        assert cfg.metadata == {}

    def test_constitutional_hash_default(self):
        cfg = make_config()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_is_utc(self):
        cfg = make_config()
        assert cfg.created_at.tzinfo is not None

    def test_expires_at_default_none(self):
        cfg = make_config()
        assert cfg.expires_at is None


class TestSessionGovernanceConfigExplicitFields:
    def test_explicit_user_id(self):
        cfg = make_config(user_id="user-42")
        assert cfg.user_id == "user-42"

    def test_explicit_risk_level_low(self):
        cfg = make_config(risk_level=RiskLevel.LOW)
        assert cfg.risk_level == RiskLevel.LOW

    def test_explicit_risk_level_high(self):
        cfg = make_config(risk_level=RiskLevel.HIGH)
        assert cfg.risk_level == RiskLevel.HIGH

    def test_explicit_risk_level_critical(self):
        cfg = make_config(risk_level=RiskLevel.CRITICAL)
        assert cfg.risk_level == RiskLevel.CRITICAL

    def test_explicit_policy_id(self):
        cfg = make_config(policy_id="policy-xyz")
        assert cfg.policy_id == "policy-xyz"

    def test_explicit_policy_overrides(self):
        cfg = make_config(policy_overrides={"key": "value"})
        assert cfg.policy_overrides == {"key": "value"}

    def test_explicit_enabled_policies(self):
        cfg = make_config(enabled_policies=["p1", "p2"])
        assert cfg.enabled_policies == ["p1", "p2"]

    def test_explicit_disabled_policies(self):
        cfg = make_config(disabled_policies=["p3"])
        assert cfg.disabled_policies == ["p3"]

    def test_explicit_require_human_approval_true(self):
        cfg = make_config(require_human_approval=True)
        assert cfg.require_human_approval is True

    def test_explicit_max_automation_level(self):
        cfg = make_config(max_automation_level="partial")
        assert cfg.max_automation_level == "partial"

    def test_constitutional_strictness_min(self):
        cfg = make_config(constitutional_strictness=0.0)
        assert cfg.constitutional_strictness == 0.0

    def test_constitutional_strictness_max(self):
        cfg = make_config(constitutional_strictness=2.0)
        assert cfg.constitutional_strictness == 2.0

    def test_constitutional_strictness_mid(self):
        cfg = make_config(constitutional_strictness=1.5)
        assert cfg.constitutional_strictness == 1.5

    def test_context_tags(self):
        cfg = make_config(context_tags=["finance", "critical"])
        assert cfg.context_tags == ["finance", "critical"]

    def test_metadata(self):
        cfg = make_config(metadata={"env": "prod"})
        assert cfg.metadata == {"env": "prod"}

    def test_expires_at_explicit(self):
        exp = datetime.now(UTC) + timedelta(hours=1)
        cfg = make_config(expires_at=exp)
        assert cfg.expires_at == exp

    def test_created_at_explicit(self):
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        cfg = make_config(created_at=ts)
        assert cfg.created_at == ts


# ===========================================================================
# SessionGovernanceConfig — validation
# ===========================================================================


class TestSessionGovernanceConfigValidation:
    def test_constitutional_strictness_below_zero_raises(self):
        with pytest.raises(ValidationError):
            make_config(constitutional_strictness=-0.1)

    def test_constitutional_strictness_above_two_raises(self):
        with pytest.raises(ValidationError):
            make_config(constitutional_strictness=2.1)

    def test_missing_session_id_raises(self):
        with pytest.raises(ValidationError):
            SessionGovernanceConfig(tenant_id="t")

    def test_missing_tenant_id_raises(self):
        with pytest.raises(ValidationError):
            SessionGovernanceConfig(session_id="s")

    def test_invalid_constitutional_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            make_config(constitutional_hash="bad-hash")

    def test_valid_constitutional_hash_passes(self):
        cfg = make_config(constitutional_hash=CONSTITUTIONAL_HASH)
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_model_config_from_attributes(self):
        assert SessionGovernanceConfig.model_config.get("from_attributes") is True


# ===========================================================================
# SessionGovernanceConfig — is_expired
# ===========================================================================


class TestSessionGovernanceConfigIsExpired:
    def test_no_expiry_never_expired(self):
        cfg = make_config()
        assert cfg.is_expired() is False

    def test_future_expiry_not_expired(self):
        cfg = make_config(expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert cfg.is_expired() is False

    def test_past_expiry_is_expired(self):
        cfg = make_config(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        assert cfg.is_expired() is True

    def test_expiry_exactly_now_boundary(self):
        # Just after "now" → expired
        past = datetime.now(UTC) - timedelta(microseconds=1)
        cfg = make_config(expires_at=past)
        assert cfg.is_expired() is True


# ===========================================================================
# SessionGovernanceConfig — get_effective_risk_level
# ===========================================================================


class TestGetEffectiveRiskLevel:
    def test_no_override_returns_session_risk_level(self):
        cfg = make_config(risk_level=RiskLevel.HIGH)
        assert cfg.get_effective_risk_level() == RiskLevel.HIGH

    def test_valid_override_in_policy_overrides(self):
        cfg = make_config(
            risk_level=RiskLevel.LOW,
            policy_overrides={"risk_level": "critical"},
        )
        assert cfg.get_effective_risk_level() == RiskLevel.CRITICAL

    def test_valid_override_medium(self):
        cfg = make_config(
            risk_level=RiskLevel.HIGH,
            policy_overrides={"risk_level": "medium"},
        )
        assert cfg.get_effective_risk_level() == RiskLevel.MEDIUM

    def test_invalid_override_falls_back_to_session_risk_level(self):
        cfg = make_config(
            risk_level=RiskLevel.HIGH,
            policy_overrides={"risk_level": "not-a-valid-level"},
        )
        assert cfg.get_effective_risk_level() == RiskLevel.HIGH

    def test_override_key_absent_returns_session_risk_level(self):
        cfg = make_config(
            risk_level=RiskLevel.CRITICAL,
            policy_overrides={"other_key": "value"},
        )
        assert cfg.get_effective_risk_level() == RiskLevel.CRITICAL

    def test_empty_overrides_returns_session_risk_level(self):
        cfg = make_config(risk_level=RiskLevel.LOW)
        assert cfg.get_effective_risk_level() == RiskLevel.LOW


# ===========================================================================
# SessionGovernanceConfig — should_require_human_approval
# ===========================================================================


class TestShouldRequireHumanApproval:
    def test_require_human_approval_flag_always_true(self):
        cfg = make_config(require_human_approval=True, risk_level=RiskLevel.LOW)
        assert cfg.should_require_human_approval(0.0) is True

    def test_require_human_approval_flag_overrides_low_impact(self):
        cfg = make_config(require_human_approval=True)
        assert cfg.should_require_human_approval(0.0) is True

    # LOW risk threshold 0.9
    def test_low_risk_below_threshold(self):
        cfg = make_config(risk_level=RiskLevel.LOW, require_human_approval=False)
        assert cfg.should_require_human_approval(0.89) is False

    def test_low_risk_at_threshold(self):
        cfg = make_config(risk_level=RiskLevel.LOW, require_human_approval=False)
        assert cfg.should_require_human_approval(0.9) is True

    def test_low_risk_above_threshold(self):
        cfg = make_config(risk_level=RiskLevel.LOW, require_human_approval=False)
        assert cfg.should_require_human_approval(0.95) is True

    # MEDIUM risk threshold 0.7
    def test_medium_risk_below_threshold(self):
        cfg = make_config(risk_level=RiskLevel.MEDIUM, require_human_approval=False)
        assert cfg.should_require_human_approval(0.69) is False

    def test_medium_risk_at_threshold(self):
        cfg = make_config(risk_level=RiskLevel.MEDIUM, require_human_approval=False)
        assert cfg.should_require_human_approval(0.7) is True

    def test_medium_risk_above_threshold(self):
        cfg = make_config(risk_level=RiskLevel.MEDIUM, require_human_approval=False)
        assert cfg.should_require_human_approval(0.8) is True

    # HIGH risk threshold 0.5
    def test_high_risk_below_threshold(self):
        cfg = make_config(risk_level=RiskLevel.HIGH, require_human_approval=False)
        assert cfg.should_require_human_approval(0.49) is False

    def test_high_risk_at_threshold(self):
        cfg = make_config(risk_level=RiskLevel.HIGH, require_human_approval=False)
        assert cfg.should_require_human_approval(0.5) is True

    def test_high_risk_above_threshold(self):
        cfg = make_config(risk_level=RiskLevel.HIGH, require_human_approval=False)
        assert cfg.should_require_human_approval(0.6) is True

    # CRITICAL risk threshold 0.3
    def test_critical_risk_below_threshold(self):
        cfg = make_config(risk_level=RiskLevel.CRITICAL, require_human_approval=False)
        assert cfg.should_require_human_approval(0.29) is False

    def test_critical_risk_at_threshold(self):
        cfg = make_config(risk_level=RiskLevel.CRITICAL, require_human_approval=False)
        assert cfg.should_require_human_approval(0.3) is True

    def test_critical_risk_above_threshold(self):
        cfg = make_config(risk_level=RiskLevel.CRITICAL, require_human_approval=False)
        assert cfg.should_require_human_approval(0.8) is True

    def test_unknown_risk_level_uses_default_07(self):
        """Covers the thresholds.get(…, 0.7) fallback."""
        cfg = make_config(risk_level=RiskLevel.MEDIUM, require_human_approval=False)
        # Patch risk_level to something not in thresholds dict
        cfg.risk_level = "UNKNOWN_LEVEL"  # type: ignore[assignment]
        assert cfg.should_require_human_approval(0.7) is True
        assert cfg.should_require_human_approval(0.69) is False


# ===========================================================================
# SessionContext — construction & defaults
# ===========================================================================


class TestSessionContextDefaults:
    def test_minimal_construction(self):
        ctx = make_context()
        assert ctx.session_id == "sess-001"

    def test_is_active_default_true(self):
        ctx = make_context()
        assert ctx.is_active is True

    def test_current_policy_version_default_none(self):
        ctx = make_context()
        assert ctx.current_policy_version is None

    def test_request_count_default_zero(self):
        ctx = make_context()
        assert ctx.request_count == 0

    def test_violation_count_default_zero(self):
        ctx = make_context()
        assert ctx.violation_count == 0

    def test_escalation_count_default_zero(self):
        ctx = make_context()
        assert ctx.escalation_count == 0

    def test_policy_changes_default_empty(self):
        ctx = make_context()
        assert ctx.policy_changes == []

    def test_constitutional_hash_default(self):
        ctx = make_context()
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_started_at_utc(self):
        ctx = make_context()
        assert ctx.started_at.tzinfo is not None

    def test_last_activity_at_utc(self):
        ctx = make_context()
        assert ctx.last_activity_at.tzinfo is not None

    def test_model_config_from_attributes(self):
        assert SessionContext.model_config.get("from_attributes") is True


# ===========================================================================
# SessionContext — record_request
# ===========================================================================


class TestSessionContextRecordRequest:
    def test_increments_request_count(self):
        ctx = make_context()
        ctx.record_request()
        assert ctx.request_count == 1

    def test_increments_multiple_times(self):
        ctx = make_context()
        for _ in range(5):
            ctx.record_request()
        assert ctx.request_count == 5

    def test_updates_last_activity_at(self):
        ctx = make_context()
        before = ctx.last_activity_at
        ctx.record_request()
        assert ctx.last_activity_at >= before


# ===========================================================================
# SessionContext — record_violation
# ===========================================================================


class TestSessionContextRecordViolation:
    def test_increments_violation_count(self):
        ctx = make_context()
        ctx.record_violation()
        assert ctx.violation_count == 1

    def test_increments_multiple_times(self):
        ctx = make_context()
        ctx.record_violation()
        ctx.record_violation()
        assert ctx.violation_count == 2

    def test_updates_last_activity_at(self):
        ctx = make_context()
        before = ctx.last_activity_at
        ctx.record_violation()
        assert ctx.last_activity_at >= before


# ===========================================================================
# SessionContext — record_escalation
# ===========================================================================


class TestSessionContextRecordEscalation:
    def test_increments_escalation_count(self):
        ctx = make_context()
        ctx.record_escalation()
        assert ctx.escalation_count == 1

    def test_increments_multiple_times(self):
        ctx = make_context()
        ctx.record_escalation()
        ctx.record_escalation()
        ctx.record_escalation()
        assert ctx.escalation_count == 3

    def test_updates_last_activity_at(self):
        ctx = make_context()
        before = ctx.last_activity_at
        ctx.record_escalation()
        assert ctx.last_activity_at >= before


# ===========================================================================
# SessionContext — record_policy_change
# ===========================================================================


class TestSessionContextRecordPolicyChange:
    def test_appends_to_policy_changes(self):
        ctx = make_context()
        ctx.record_policy_change(None, "policy-v2", "initial")
        assert len(ctx.policy_changes) == 1

    def test_policy_change_contains_required_keys(self):
        ctx = make_context()
        ctx.record_policy_change("policy-v1", "policy-v2", "upgrade")
        entry = ctx.policy_changes[0]
        assert "timestamp" in entry
        assert "old_policy" in entry
        assert "new_policy" in entry
        assert "reason" in entry

    def test_policy_change_old_policy_none(self):
        ctx = make_context()
        ctx.record_policy_change(None, "policy-v1", "initial")
        assert ctx.policy_changes[0]["old_policy"] is None

    def test_policy_change_new_policy_value(self):
        ctx = make_context()
        ctx.record_policy_change(None, "policy-v2", "reason")
        assert ctx.policy_changes[0]["new_policy"] == "policy-v2"

    def test_policy_change_reason_value(self):
        ctx = make_context()
        ctx.record_policy_change("old", "new", "test reason")
        assert ctx.policy_changes[0]["reason"] == "test reason"

    def test_policy_change_updates_current_policy_version(self):
        ctx = make_context()
        ctx.record_policy_change(None, "policy-v3", "update")
        assert ctx.current_policy_version == "policy-v3"

    def test_multiple_policy_changes_accumulate(self):
        ctx = make_context()
        ctx.record_policy_change(None, "v1", "init")
        ctx.record_policy_change("v1", "v2", "upgrade")
        assert len(ctx.policy_changes) == 2
        assert ctx.current_policy_version == "v2"

    def test_timestamp_is_iso_format_string(self):
        ctx = make_context()
        ctx.record_policy_change(None, "v1", "init")
        ts = ctx.policy_changes[0]["timestamp"]
        # Should be parseable as isoformat
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None

    def test_updates_last_activity_at(self):
        ctx = make_context()
        before = ctx.last_activity_at
        ctx.record_policy_change(None, "v1", "init")
        assert ctx.last_activity_at >= before


# ===========================================================================
# SessionContext — to_audit_dict
# ===========================================================================


class TestSessionContextToAuditDict:
    def test_returns_dict(self):
        ctx = make_context()
        result = ctx.to_audit_dict()
        assert isinstance(result, dict)

    def test_contains_session_id(self):
        ctx = make_context()
        assert ctx.to_audit_dict()["session_id"] == "sess-001"

    def test_contains_tenant_id(self):
        cfg = make_config(tenant_id="tenant-xyz")
        ctx = make_context(config=cfg)
        assert ctx.to_audit_dict()["tenant_id"] == "tenant-xyz"

    def test_contains_user_id(self):
        cfg = make_config(user_id="user-99")
        ctx = make_context(config=cfg)
        assert ctx.to_audit_dict()["user_id"] == "user-99"

    def test_user_id_none_when_not_set(self):
        ctx = make_context()
        assert ctx.to_audit_dict()["user_id"] is None

    def test_contains_risk_level_value(self):
        cfg = make_config(risk_level=RiskLevel.HIGH)
        ctx = make_context(config=cfg)
        assert ctx.to_audit_dict()["risk_level"] == "high"

    def test_contains_request_count(self):
        ctx = make_context()
        ctx.record_request()
        ctx.record_request()
        assert ctx.to_audit_dict()["request_count"] == 2

    def test_contains_violation_count(self):
        ctx = make_context()
        ctx.record_violation()
        assert ctx.to_audit_dict()["violation_count"] == 1

    def test_contains_escalation_count(self):
        ctx = make_context()
        ctx.record_escalation()
        ctx.record_escalation()
        assert ctx.to_audit_dict()["escalation_count"] == 2

    def test_policy_changes_is_count(self):
        ctx = make_context()
        ctx.record_policy_change(None, "v1", "init")
        ctx.record_policy_change("v1", "v2", "upgrade")
        assert ctx.to_audit_dict()["policy_changes"] == 2

    def test_started_at_is_string(self):
        ctx = make_context()
        started = ctx.to_audit_dict()["started_at"]
        assert isinstance(started, str)
        datetime.fromisoformat(started)

    def test_last_activity_at_is_string(self):
        ctx = make_context()
        last = ctx.to_audit_dict()["last_activity_at"]
        assert isinstance(last, str)
        datetime.fromisoformat(last)

    def test_constitutional_hash_present(self):
        ctx = make_context()
        assert ctx.to_audit_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_all_expected_keys_present(self):
        ctx = make_context()
        expected = {
            "session_id",
            "tenant_id",
            "user_id",
            "risk_level",
            "request_count",
            "violation_count",
            "escalation_count",
            "policy_changes",
            "started_at",
            "last_activity_at",
            "constitutional_hash",
        }
        assert set(ctx.to_audit_dict().keys()) == expected


# ===========================================================================
# __all__ export check
# ===========================================================================


class TestModuleExports:
    def test_session_governance_config_exported(self):
        from enhanced_agent_bus.session_models import __all__

        assert "SessionGovernanceConfig" in __all__

    def test_session_context_exported(self):
        from enhanced_agent_bus.session_models import __all__

        assert "SessionContext" in __all__


# ===========================================================================
# Integration — SessionContext with various config scenarios
# ===========================================================================


class TestSessionContextIntegration:
    def test_full_session_workflow(self):
        cfg = make_config(
            tenant_id="enterprise",
            user_id="admin",
            risk_level=RiskLevel.HIGH,
            require_human_approval=False,
            enabled_policies=["pol-1", "pol-2"],
        )
        ctx = make_context(config=cfg, session_id="sess-full")
        assert ctx.session_id == "sess-full"
        assert ctx.config.tenant_id == "enterprise"

        ctx.record_request()
        ctx.record_request()
        ctx.record_policy_change(None, "pol-v1", "init")
        ctx.record_violation()
        ctx.record_escalation()

        audit = ctx.to_audit_dict()
        assert audit["request_count"] == 2
        assert audit["violation_count"] == 1
        assert audit["escalation_count"] == 1
        assert audit["policy_changes"] == 1
        assert audit["risk_level"] == "high"

    def test_expired_session_config_in_context(self):
        cfg = make_config(expires_at=datetime.now(UTC) - timedelta(hours=1))
        ctx = make_context(config=cfg)
        assert ctx.config.is_expired() is True

    def test_active_session_config_in_context(self):
        cfg = make_config(expires_at=datetime.now(UTC) + timedelta(hours=1))
        ctx = make_context(config=cfg)
        assert ctx.config.is_expired() is False

    def test_human_approval_required_via_context(self):
        cfg = make_config(require_human_approval=True)
        ctx = make_context(config=cfg)
        assert ctx.config.should_require_human_approval(0.0) is True

    def test_policy_change_reflected_in_audit(self):
        ctx = make_context()
        ctx.record_policy_change(None, "pol-abc", "initial deployment")
        ctx.record_policy_change("pol-abc", "pol-xyz", "policy update")
        audit = ctx.to_audit_dict()
        assert audit["policy_changes"] == 2
        assert ctx.current_policy_version == "pol-xyz"
