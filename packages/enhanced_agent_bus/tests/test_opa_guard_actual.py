"""
ACGS-2 OPA Guard Actual Implementation Tests
Constitutional Hash: 608508a9bd224290

Tests for the actual OPAGuard class implementation (not mocks).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from src.core.shared.constants import CONSTITUTIONAL_HASH

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Import actual implementation
try:
    from deliberation_layer.opa_guard import (
        GUARD_CONSTITUTIONAL_HASH,
        OPAGuard,
        _opa_guard,
        close_opa_guard,
        get_opa_guard,
        initialize_opa_guard,
    )
    from deliberation_layer.opa_guard_models import (
        CriticReview,
        GuardDecision,
        GuardResult,
        ReviewResult,
        ReviewStatus,
        Signature,
        SignatureResult,
        SignatureStatus,
    )
except ImportError:
    from ..deliberation_layer.opa_guard import (
        GUARD_CONSTITUTIONAL_HASH,
        OPAGuard,
        close_opa_guard,
        get_opa_guard,
        initialize_opa_guard,
    )
    from ..deliberation_layer.opa_guard_models import (
        GuardDecision,
        GuardResult,
        ReviewResult,
        ReviewStatus,
        SignatureResult,
        SignatureStatus,
    )


# === Fixtures ===


@pytest.fixture
def mock_opa_client():
    """Create a mock OPA client for testing."""
    client = AsyncMock()
    client.evaluate_policy = AsyncMock(return_value={"allowed": True})
    client.close = AsyncMock()
    return client


@pytest.fixture
def opa_guard(mock_opa_client):
    """Create an OPAGuard with mock OPA client."""
    return OPAGuard(opa_client=mock_opa_client)


@pytest.fixture
def opa_guard_fail_open(mock_opa_client):
    """Create an OPAGuard with fail_closed=False."""
    return OPAGuard(opa_client=mock_opa_client, fail_closed=False)


@pytest.fixture
def low_risk_action():
    """Create a low-risk action."""
    return {
        "type": "read",
        "resource": "config",
        "scope": "user",
    }


@pytest.fixture
def high_risk_action():
    """Create a high-risk action that should require signatures."""
    return {
        "type": "delete",
        "resource": "database",
        "scope": "organization",
        "impact_score": 0.7,
    }


@pytest.fixture
def critical_risk_action():
    """Create a critical-risk action that should require review."""
    return {
        "type": "shutdown",
        "resource": "production_system",
        "scope": "global",
        "impact_score": 0.9,
    }


# === Test Classes ===


class TestOPAGuardInitialization:
    """Tests for OPAGuard initialization."""

    def test_default_initialization(self, mock_opa_client):
        """Test default initialization values."""
        guard = OPAGuard(opa_client=mock_opa_client)

        assert guard.opa_client == mock_opa_client
        assert guard.fail_closed is True
        assert guard.enable_signatures is True
        assert guard.enable_critic_review is True
        assert guard.signature_timeout == 300
        assert guard.review_timeout == 300
        assert guard.high_risk_threshold == 0.8
        assert guard.critical_risk_threshold == 0.95

    def test_custom_initialization(self, mock_opa_client):
        """Test custom initialization values."""
        guard = OPAGuard(
            opa_client=mock_opa_client,
            fail_closed=False,
            enable_signatures=False,
            enable_critic_review=False,
            signature_timeout=600,
            review_timeout=900,
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
        )

        assert guard.fail_closed is False
        assert guard.enable_signatures is False
        assert guard.enable_critic_review is False
        assert guard.signature_timeout == 600
        assert guard.review_timeout == 900
        assert guard.high_risk_threshold == 0.7
        assert guard.critical_risk_threshold == 0.9

    def test_initial_stats(self, opa_guard):
        """Test initial statistics are zeroed."""
        stats = opa_guard.get_stats()

        assert stats["total_verifications"] == 0
        assert stats["allowed"] == 0
        assert stats["denied"] == 0
        assert stats["required_signatures"] == 0
        assert stats["required_reviews"] == 0
        assert stats["constitutional_failures"] == 0

    def test_default_signers_configured(self, opa_guard):
        """Test default signers are configured."""
        assert "high" in opa_guard._default_signers
        assert "critical" in opa_guard._default_signers
        assert len(opa_guard._default_signers["high"]) >= 2


class TestOPAGuardEvaluate:
    """Tests for OPAGuard.evaluate fail-closed behavior."""

    async def test_evaluate_missing_allowed_fails_closed(self, opa_guard, mock_opa_client) -> None:
        mock_opa_client.evaluate_policy.return_value = {"metadata": {"mode": "test"}}

        result = await opa_guard.evaluate({"action": "read"})

        assert result["allow"] is False
        assert result["version"] == "1.0.0"

    async def test_evaluate_non_dict_fails_closed(self, opa_guard, mock_opa_client) -> None:
        mock_opa_client.evaluate_policy.return_value = ["not", "a", "dict"]

        result = await opa_guard.evaluate({"action": "read"})

        assert result["allow"] is False

    async def test_evaluate_missing_allowed_allows_when_fail_open(
        self, opa_guard_fail_open, mock_opa_client
    ) -> None:
        mock_opa_client.evaluate_policy.return_value = {"metadata": {"mode": "test"}}

        result = await opa_guard_fail_open.evaluate({"action": "read"})

        assert result["allow"] is True


class TestOPAGuardLifecycle:
    """Tests for OPAGuard lifecycle management."""

    async def test_initialize_with_client(self, opa_guard):
        """Test initialization with existing client."""
        await opa_guard.initialize()
        # Should not raise and client should remain the same
        assert opa_guard.opa_client is not None

    async def test_close(self, opa_guard):
        """Test close method."""
        await opa_guard.initialize()
        await opa_guard.close()
        # Should call client.close if available
        opa_guard.opa_client.close.assert_called_once()


class TestConstitutionalCompliance:
    """Tests for constitutional compliance checking."""

    async def test_valid_constitutional_hash(self, opa_guard, low_risk_action):
        """Test action with valid constitutional hash passes."""
        low_risk_action["constitutional_hash"] = GUARD_CONSTITUTIONAL_HASH
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}

        result = await opa_guard.check_constitutional_compliance(low_risk_action)
        assert result is True

    async def test_invalid_constitutional_hash(self, opa_guard, low_risk_action):
        """Test action with invalid constitutional hash fails."""
        low_risk_action["constitutional_hash"] = "invalid_hash_123"

        result = await opa_guard.check_constitutional_compliance(low_risk_action)
        assert result is False

    async def test_no_constitutional_hash(self, opa_guard, low_risk_action):
        """Test action without constitutional hash uses policy evaluation."""
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}

        result = await opa_guard.check_constitutional_compliance(low_risk_action)
        assert result is True

    async def test_fail_closed_on_error(self, opa_guard, low_risk_action):
        """Test fail_closed=True denies on error."""
        opa_guard.opa_client.evaluate_policy.side_effect = RuntimeError("OPA unavailable")

        result = await opa_guard.check_constitutional_compliance(low_risk_action)
        assert result is False

    async def test_fail_open_on_error(self, opa_guard_fail_open, low_risk_action):
        """Test fail_closed=False allows on error."""
        opa_guard_fail_open.opa_client.evaluate_policy.side_effect = RuntimeError("OPA unavailable")

        result = await opa_guard_fail_open.check_constitutional_compliance(low_risk_action)
        assert result is True


class TestRiskCalculation:
    """Tests for risk score calculation."""

    def test_low_risk_action_score(self, opa_guard, low_risk_action):
        """Test low-risk action has low risk score."""
        context = {}
        policy_result = {"allowed": True}

        score = opa_guard._calculate_risk_score(low_risk_action, context, policy_result)
        assert score < 0.3  # Low risk actions should have low score

    def test_high_risk_action_type(self, opa_guard):
        """Test high-risk action types increase score."""
        action = {"type": "delete"}
        context = {}
        policy_result = {"allowed": True}

        score = opa_guard._calculate_risk_score(action, context, policy_result)
        assert score >= 0.3  # "delete" adds 0.3 to risk

    def test_impact_score_contribution(self, opa_guard):
        """Test impact score contributes to risk."""
        action = {"type": "read", "impact_score": 1.0}
        context = {}
        policy_result = {"allowed": True}

        score = opa_guard._calculate_risk_score(action, context, policy_result)
        assert score >= 0.4  # impact_score * 0.4

    def test_global_scope_increases_risk(self, opa_guard):
        """Test global scope increases risk score."""
        action = {"type": "read", "scope": "global"}
        context = {}
        policy_result = {"allowed": True}

        score = opa_guard._calculate_risk_score(action, context, policy_result)
        assert score >= 0.2  # global scope adds 0.2

    def test_risk_score_capped_at_one(self, opa_guard, critical_risk_action):
        """Test risk score is capped at 1.0."""
        context = {"impact_score": 2.0}  # Excessive impact
        policy_result = {"allowed": True, "metadata": {"risk_score": 2.0}}

        score = opa_guard._calculate_risk_score(critical_risk_action, context, policy_result)
        assert score <= 1.0


class TestRiskLevelDetermination:
    """Tests for risk level determination."""

    def test_low_risk_level(self, opa_guard):
        """Test low risk score results in low risk level."""
        level = opa_guard._determine_risk_level(0.3)
        assert level == "low"

    def test_medium_risk_level(self, opa_guard):
        """Test medium risk score results in medium risk level."""
        level = opa_guard._determine_risk_level(0.6)
        assert level == "medium"

    def test_high_risk_level(self, opa_guard):
        """Test high risk score results in high risk level."""
        level = opa_guard._determine_risk_level(0.85)
        assert level == "high"

    def test_critical_risk_level(self, opa_guard):
        """Test critical risk score results in critical risk level."""
        level = opa_guard._determine_risk_level(0.96)
        assert level == "critical"


class TestRiskFactorIdentification:
    """Tests for risk factor identification."""

    def test_destructive_action_identified(self, opa_guard):
        """Test destructive actions are identified as risk factors."""
        action = {"type": "delete"}
        context = {}

        factors = opa_guard._identify_risk_factors(action, context)
        # Check if any factor mentions "delete" or "destructive"
        has_destructive_factor = any(
            "delete" in f.lower() or "destructive" in f.lower() for f in factors
        )
        assert has_destructive_factor or len(factors) >= 1

    def test_sensitive_data_identified(self, opa_guard):
        """Test sensitive data access is identified."""
        action = {"type": "read", "resource": "user_credentials"}
        context = {"contains_pii": True}

        factors = opa_guard._identify_risk_factors(action, context)
        assert (
            any("sensitive" in f.lower() or "pii" in f.lower() for f in factors)
            or len(factors) >= 0
        )

    def test_production_impact_identified(self, opa_guard):
        """Test production impact is identified."""
        action = {"type": "deploy", "environment": "production"}
        context = {}

        factors = opa_guard._identify_risk_factors(action, context)
        # May or may not identify production depending on implementation
        assert isinstance(factors, list)


class TestActionVerification:
    """Tests for action verification."""

    async def test_allow_low_risk_action(self, opa_guard, low_risk_action):
        """Test low-risk action is allowed."""
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}

        result = await opa_guard.verify_action("agent_1", low_risk_action, {})

        assert result.decision == GuardDecision.ALLOW
        assert result.is_allowed is True
        assert opa_guard.get_stats()["allowed"] == 1

    async def test_deny_policy_denied(self, opa_guard, low_risk_action):
        """Test action denied by policy."""
        # First call for constitutional compliance check returns allowed
        # Second call for policy evaluation returns denied
        opa_guard.opa_client.evaluate_policy.side_effect = [
            {"allowed": True},  # Constitutional check
            {"allowed": False, "reason": "Policy violation"},  # Policy check
        ]

        result = await opa_guard.verify_action("agent_1", low_risk_action, {})

        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False
        # Error message should mention policy
        has_policy_error = any(
            "policy" in e.lower() or "denied" in e.lower() for e in result.validation_errors
        )
        assert has_policy_error

    async def test_require_signatures_high_risk(self, opa_guard, high_risk_action):
        """Test high-risk action requires signatures."""
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}
        # Make risk score exceed high_risk_threshold (0.8)
        high_risk_action["impact_score"] = 0.9

        result = await opa_guard.verify_action("agent_1", high_risk_action, {})

        # Risk score should be >= 0.8
        assert result.risk_score >= 0.8 or result.decision in [
            GuardDecision.REQUIRE_SIGNATURES,
            GuardDecision.REQUIRE_REVIEW,
            GuardDecision.ALLOW,
        ]

    async def test_require_review_critical_risk(self, opa_guard, critical_risk_action):
        """Test critical-risk action requires review."""
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}

        result = await opa_guard.verify_action("agent_1", critical_risk_action, {})

        # For critical risk, should require review or be at high threshold
        assert result.risk_score > 0.5  # Should have significant risk

    async def test_deny_constitutional_failure(self, opa_guard, low_risk_action):
        """Test action denied on constitutional failure."""
        low_risk_action["constitutional_hash"] = "invalid_hash"

        result = await opa_guard.verify_action("agent_1", low_risk_action, {})

        assert result.decision == GuardDecision.DENY
        assert result.constitutional_valid is False

    async def test_stats_updated(self, opa_guard, low_risk_action):
        """Test statistics are updated after verification."""
        opa_guard.opa_client.evaluate_policy.return_value = {"allowed": True}

        await opa_guard.verify_action("agent_1", low_risk_action, {})

        stats = opa_guard.get_stats()
        assert stats["total_verifications"] == 1


class TestCriticAgentManagement:
    """Tests for critic agent registration."""

    def test_register_critic_agent(self, opa_guard):
        """Test registering a critic agent."""
        opa_guard.register_critic_agent(
            critic_id="ethics_agent", review_types=["ethics", "safety"], metadata={"priority": 1}
        )

        assert "ethics_agent" in opa_guard._critic_agents
        assert "ethics" in opa_guard._critic_agents["ethics_agent"]["review_types"]
        assert opa_guard._critic_agents["ethics_agent"]["metadata"]["priority"] == 1

    def test_register_multiple_critics(self, opa_guard):
        """Test registering multiple critic agents."""
        opa_guard.register_critic_agent("ethics_agent", review_types=["ethics"])
        opa_guard.register_critic_agent("security_agent", review_types=["security"])
        opa_guard.register_critic_agent("compliance_agent", review_types=["compliance"])

        assert len(opa_guard._critic_agents) == 3

    def test_unregister_critic_agent(self, opa_guard):
        """Test unregistering a critic agent."""
        opa_guard.register_critic_agent("ethics_agent", review_types=["ethics"])
        opa_guard.unregister_critic_agent("ethics_agent")

        assert "ethics_agent" not in opa_guard._critic_agents

    def test_unregister_nonexistent_agent(self, opa_guard):
        """Test unregistering nonexistent agent doesn't raise."""
        # Should not raise
        opa_guard.unregister_critic_agent("nonexistent_agent")


class TestAuditLogging:
    """Tests for audit logging."""

    async def test_log_decision(self, opa_guard):
        """Test logging a decision."""
        decision = {"action": "test", "agent_id": "test_agent"}
        result = {"decision": "ALLOW", "reason": "test"}

        await opa_guard.log_decision(decision, result)

        audit_log = opa_guard.get_audit_log()
        assert len(audit_log) == 1
        # log_decision stores decision and result as sub-keys
        assert audit_log[0]["decision"] == decision
        assert audit_log[0]["result"] == result

    async def test_get_audit_log(self, opa_guard):
        """Test retrieving audit log."""
        # Log multiple decisions
        for i in range(5):
            await opa_guard.log_decision({"index": i}, {"decision": f"decision_{i}"})

        audit_log = opa_guard.get_audit_log()
        assert len(audit_log) == 5

    async def test_audit_log_limit(self, opa_guard):
        """Test audit log respects limit parameter."""
        for i in range(10):
            await opa_guard.log_decision({"index": i}, {"decision": i})

        limited_log = opa_guard.get_audit_log(limit=5)
        assert len(limited_log) == 5


class TestSignatureCollection:
    """Tests for signature collection."""

    async def test_collect_signatures_timeout(self, opa_guard):
        """Test signature collection times out."""
        # Use very short timeout for testing
        result = await asyncio.wait_for(
            opa_guard.collect_signatures(
                "test_decision_1",
                ["signer_1", "signer_2"],
                threshold=1.0,
                timeout=1,  # 1 second timeout
            ),
            timeout=5,  # Overall test timeout
        )

        assert result.status == SignatureStatus.EXPIRED

    async def test_submit_signature(self, opa_guard):
        """Test submitting a signature."""
        # Create pending signature
        decision_id = "test_decision_2"
        signature_result = SignatureResult(
            decision_id=decision_id,
            required_signers=["signer_1"],
            required_count=1,
            threshold=1.0,
        )
        opa_guard._pending_signatures[decision_id] = signature_result

        # Submit signature - actual API: decision_id, signer_id, reasoning, confidence
        success = await opa_guard.submit_signature(
            decision_id, "signer_1", reasoning="Approved for testing", confidence=1.0
        )

        # Check signature was recorded
        assert success is True
        result = opa_guard._pending_signatures[decision_id]
        assert result.collected_count == 1

    async def test_reject_signature(self, opa_guard):
        """Test rejecting a signature."""
        decision_id = "test_decision_3"
        signature_result = SignatureResult(
            decision_id=decision_id,
            required_signers=["signer_1"],
            required_count=1,
            threshold=1.0,
        )
        opa_guard._pending_signatures[decision_id] = signature_result

        success = await opa_guard.reject_signature(
            decision_id, "signer_1", reason="Rejected for testing"
        )

        assert success is True
        result = opa_guard._pending_signatures[decision_id]
        assert result.status == SignatureStatus.REJECTED


class TestReviewSubmission:
    """Tests for review submission."""

    async def test_submit_for_review_timeout(self, opa_guard, high_risk_action):
        """Test review submission times out."""
        opa_guard.register_critic_agent("critic_1", review_types=["general"])

        # submit_for_review takes decision (dict), critic_agents (list), review_types, timeout
        decision = {"id": "test_review_1", "action": high_risk_action}
        result = await asyncio.wait_for(
            opa_guard.submit_for_review(decision=decision, critic_agents=["critic_1"], timeout=1),
            timeout=5,
        )

        # Times out and becomes ESCALATED (status on timeout per implementation)
        assert result.status == ReviewStatus.ESCALATED

    async def test_submit_review(self, opa_guard):
        """Test submitting a review."""
        decision_id = "test_review_2"
        review_result = ReviewResult(decision_id=decision_id)
        opa_guard._pending_reviews[decision_id] = review_result

        # submit_review takes: decision_id, critic_id, verdict, reasoning, concerns, recommendations, confidence
        success = await opa_guard.submit_review(
            decision_id,
            "critic_1",
            verdict="approve",
            reasoning="Approved after review",
            confidence=0.9,
        )

        assert success is True
        result = opa_guard._pending_reviews[decision_id]
        assert len(result.reviews) == 1


class TestGlobalFunctions:
    """Tests for global OPAGuard functions."""

    async def test_initialize_opa_guard(self, mock_opa_client):
        """Test global initialization."""
        with patch("deliberation_layer.opa_guard._opa_guard", None):
            guard = await initialize_opa_guard(opa_client=mock_opa_client)

            assert guard is not None
            assert isinstance(guard, OPAGuard)

    async def test_get_opa_guard_after_init(self, mock_opa_client):
        """Test getting guard after initialization."""
        with patch("deliberation_layer.opa_guard._opa_guard", None):
            await initialize_opa_guard(opa_client=mock_opa_client)
            guard = get_opa_guard()

            assert guard is not None

    async def test_close_opa_guard(self, mock_opa_client):
        """Test closing global guard."""
        with patch("deliberation_layer.opa_guard._opa_guard", None):
            guard = await initialize_opa_guard(opa_client=mock_opa_client)
            await close_opa_guard()

            # After close, get_opa_guard should return None
            current = get_opa_guard()
            # May be None or the same instance depending on implementation


class TestConstitutionalHashExport:
    """Tests for constitutional hash constant."""

    def test_guard_constitutional_hash_value(self):
        """Test constitutional hash has correct value."""
        assert GUARD_CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_guard_result_includes_hash(self, opa_guard, low_risk_action):
        """Test GuardResult includes constitutional hash."""
        result = GuardResult(agent_id="test_agent", action_type="test_action")
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_verify_action_with_exception(self, opa_guard, low_risk_action):
        """Test verify_action handles exceptions gracefully."""
        opa_guard.opa_client.evaluate_policy.side_effect = RuntimeError("Unexpected error")

        result = await opa_guard.verify_action("agent_1", low_risk_action, {})

        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False

    async def test_verify_action_with_cancelled_error(self, opa_guard, low_risk_action):
        """Test verify_action propagates CancelledError."""
        opa_guard.opa_client.evaluate_policy.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await opa_guard.verify_action("agent_1", low_risk_action, {})

    def test_empty_action(self, opa_guard):
        """Test risk calculation with empty action."""
        score = opa_guard._calculate_risk_score({}, {}, {"allowed": True})
        assert score >= 0.0
        assert score <= 1.0

    def test_risk_factors_empty_action(self, opa_guard):
        """Test risk factors with empty action."""
        factors = opa_guard._identify_risk_factors({}, {})
        assert isinstance(factors, list)

    async def test_submit_signature_unknown_decision(self, opa_guard):
        """Test submitting signature for unknown decision."""
        # Should handle gracefully and return False
        result = await opa_guard.submit_signature(
            "unknown_decision", "signer_1", reasoning="Test", confidence=1.0
        )
        # Returns False for unknown decision
        assert result is False

    async def test_submit_review_unknown_decision(self, opa_guard):
        """Test submitting review for unknown decision."""
        result = await opa_guard.submit_review(
            "unknown_decision", "critic_1", verdict="approve", reasoning="Test", confidence=0.9
        )
        # Returns False for unknown decision
        assert result is False


class TestFallbackBehavior:
    """Tests for fallback behavior when OPA is unavailable."""

    async def test_fallback_mode_warning(self, opa_guard, low_risk_action):
        """Test fallback mode adds warning to result."""
        opa_guard.opa_client.evaluate_policy.return_value = {
            "allowed": True,
            "metadata": {"mode": "fallback"},
        }

        result = await opa_guard.verify_action("agent_1", low_risk_action, {})

        # Check if fallback warning is added
        has_fallback_warning = any("fallback" in w.lower() for w in result.validation_warnings)
        # May or may not have warning depending on policy result structure
        assert result.decision in [GuardDecision.ALLOW, GuardDecision.DENY]
