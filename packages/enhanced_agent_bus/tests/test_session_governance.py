"""
Unit tests for Session Governance (Spec 003)
Constitutional Hash: 608508a9bd224290

Tests for:
- RiskLevel enum
- SessionGovernanceConfig model
- SessionContext model
- SessionGovernanceService
"""

import os

# Import models directly to avoid full package initialization
import sys
from datetime import UTC, datetime, timedelta, timezone

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    RiskLevel,
    SessionContext,
    SessionGovernanceConfig,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self):
        """Test all risk level values exist."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_risk_level_from_string(self):
        """Test creating risk level from string."""
        assert RiskLevel("low") == RiskLevel.LOW
        assert RiskLevel("critical") == RiskLevel.CRITICAL


class TestSessionGovernanceConfig:
    """Tests for SessionGovernanceConfig model."""

    def test_basic_creation(self):
        """Test basic config creation with required fields."""
        config = SessionGovernanceConfig(
            session_id="test-session",
            tenant_id="tenant-1",
        )
        assert config.session_id == "test-session"
        assert config.tenant_id == "tenant-1"
        assert config.risk_level == RiskLevel.MEDIUM  # default
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_full_creation(self):
        """Test config with all fields."""
        config = SessionGovernanceConfig(
            session_id="test-session",
            tenant_id="tenant-1",
            user_id="user-123",
            risk_level=RiskLevel.HIGH,
            policy_id="custom-policy",
            policy_overrides={"max_tokens": 1000},
            enabled_policies=["policy-a", "policy-b"],
            disabled_policies=["policy-c"],
            require_human_approval=True,
            max_automation_level="partial",
            constitutional_strictness=1.5,
            context_tags=["finance", "pii"],
        )
        assert config.user_id == "user-123"
        assert config.risk_level == RiskLevel.HIGH
        assert config.require_human_approval is True
        assert config.constitutional_strictness == 1.5
        assert "finance" in config.context_tags

    def test_invalid_constitutional_hash(self):
        """Test that invalid constitutional hash raises error."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            SessionGovernanceConfig(
                session_id="test-invalid",
                tenant_id="tenant",
                constitutional_hash="invalid-hash",
            )

    def test_expiration(self):
        """Test session expiration checking."""
        # Not expired
        config = SessionGovernanceConfig(
            session_id="test",
            tenant_id="tenant",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert config.is_expired() is False

        # Expired
        config_expired = SessionGovernanceConfig(
            session_id="test2",
            tenant_id="tenant",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert config_expired.is_expired() is True

        # Never expires
        config_no_expiry = SessionGovernanceConfig(
            session_id="test3",
            tenant_id="tenant",
        )
        assert config_no_expiry.is_expired() is False

    def test_human_approval_thresholds(self):
        """Test risk-based human approval thresholds."""
        # Low risk - threshold 0.9
        low_config = SessionGovernanceConfig(
            session_id="low",
            tenant_id="tenant",
            risk_level=RiskLevel.LOW,
        )
        assert low_config.should_require_human_approval(0.85) is False
        assert low_config.should_require_human_approval(0.95) is True

        # Critical risk - threshold 0.3
        critical_config = SessionGovernanceConfig(
            session_id="critical",
            tenant_id="tenant",
            risk_level=RiskLevel.CRITICAL,
        )
        assert critical_config.should_require_human_approval(0.25) is False
        assert critical_config.should_require_human_approval(0.35) is True

    def test_human_approval_override(self):
        """Test require_human_approval override."""
        config = SessionGovernanceConfig(
            session_id="test-approval",
            tenant_id="tenant",
            risk_level=RiskLevel.LOW,
            require_human_approval=True,
        )
        # Even low impact should require approval when override is set
        assert config.should_require_human_approval(0.1) is True

    def test_effective_risk_level_override(self):
        """Test effective risk level with policy override."""
        config = SessionGovernanceConfig(
            session_id="test-effective",
            tenant_id="tenant",
            risk_level=RiskLevel.LOW,
            policy_overrides={"risk_level": "critical"},
        )
        assert config.get_effective_risk_level() == RiskLevel.CRITICAL


class TestSessionContext:
    """Tests for SessionContext model."""

    def test_basic_creation(self):
        """Test basic context creation."""
        config = SessionGovernanceConfig(
            session_id="test-session",
            tenant_id="tenant-1",
        )
        context = SessionContext(
            session_id="test-session",
            config=config,
        )
        assert context.session_id == "test-session"
        assert context.is_active is True
        assert context.request_count == 0
        assert context.violation_count == 0

    def test_record_request(self):
        """Test request recording."""
        config = SessionGovernanceConfig(
            session_id="test",
            tenant_id="tenant",
        )
        context = SessionContext(session_id="test", config=config)

        original_time = context.last_activity_at
        context.record_request()

        assert context.request_count == 1
        assert context.last_activity_at >= original_time

    def test_record_violation(self):
        """Test violation recording."""
        config = SessionGovernanceConfig(
            session_id="test",
            tenant_id="tenant",
        )
        context = SessionContext(session_id="test", config=config)

        context.record_violation()
        assert context.violation_count == 1

        context.record_violation()
        assert context.violation_count == 2

    def test_record_policy_change(self):
        """Test policy change recording."""
        config = SessionGovernanceConfig(
            session_id="test",
            tenant_id="tenant",
        )
        context = SessionContext(session_id="test", config=config)

        context.record_policy_change("old-policy", "new-policy", "Testing")

        assert len(context.policy_changes) == 1
        assert context.policy_changes[0]["old_policy"] == "old-policy"
        assert context.policy_changes[0]["new_policy"] == "new-policy"
        assert context.current_policy_version == "new-policy"

    def test_audit_dict(self):
        """Test audit dictionary generation."""
        config = SessionGovernanceConfig(
            session_id="test-audit",
            tenant_id="tenant-1",
            user_id="user-123",
            risk_level=RiskLevel.HIGH,
        )
        context = SessionContext(session_id="test", config=config)
        context.record_request()
        context.record_violation()

        audit = context.to_audit_dict()

        assert audit["session_id"] == "test"
        assert audit["tenant_id"] == "tenant-1"
        assert audit["user_id"] == "user-123"
        assert audit["risk_level"] == "high"
        assert audit["request_count"] == 1
        assert audit["violation_count"] == 1
        assert audit["constitutional_hash"] == CONSTITUTIONAL_HASH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
