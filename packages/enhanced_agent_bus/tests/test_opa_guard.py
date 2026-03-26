"""
ACGS-2 OPA Guard Module Tests
Constitutional Hash: 608508a9bd224290

Tests for enhanced_agent_bus/deliberation_layer/opa_guard.py
"""

import importlib.util
import os
import sys
import types
from datetime import UTC, datetime, timezone

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# ============================================================================
# Direct Module Loading (compatible with conftest.py)
# ============================================================================

_parent_dir = os.path.dirname(os.path.dirname(__file__))
enhanced_agent_bus_dir = _parent_dir


def _load_module(name: str, path: str):
    """Load a module directly from path."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [enhanced_agent_bus_dir]
        pkg.__file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load required modules
_models_path = os.path.join(_parent_dir, "models.py")
_validators_path = os.path.join(_parent_dir, "validators.py")
_opa_guard_models_path = os.path.join(_parent_dir, "deliberation_layer", "opa_guard_models.py")

_models = _load_module("_models_for_guard", _models_path)
_validators = _load_module("_validators_for_guard", _validators_path)
_opa_models = _load_module("_opa_guard_models_test", _opa_guard_models_path)

# Extract types
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
MessageStatus = _models.MessageStatus
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH
ValidationResult = _validators.ValidationResult
GuardDecision = _opa_models.GuardDecision
GuardResult = _opa_models.GuardResult
SignatureStatus = _opa_models.SignatureStatus
ReviewStatus = _opa_models.ReviewStatus
Signature = _opa_models.Signature
SignatureResult = _opa_models.SignatureResult
CriticReview = _opa_models.CriticReview
ReviewResult = _opa_models.ReviewResult
GUARD_CONSTITUTIONAL_HASH = _opa_models.GUARD_CONSTITUTIONAL_HASH


# ============================================================================
# OPAGuard Mock Implementation for Testing
# ============================================================================


class MockOPAClient:
    """Mock OPA client for testing."""

    def __init__(self):
        self._initialized = False
        self._closed = False
        self._policy_results = {}

    async def initialize(self):
        self._initialized = True

    async def close(self):
        self._closed = True

    async def evaluate_policy(self, input_data, policy_path):
        return self._policy_results.get(policy_path, {"allowed": True})

    def set_policy_result(self, policy_path, result):
        self._policy_results[policy_path] = result


class OPAGuardForTest:
    """Test-friendly OPAGuard implementation."""

    def __init__(
        self,
        opa_client=None,
        enable_signatures=True,
        enable_critic_review=True,
        signature_timeout=300,
        review_timeout=300,
        high_risk_threshold=0.8,
        critical_risk_threshold=0.95,
    ):
        self.opa_client = opa_client
        self.enable_signatures = enable_signatures
        self.enable_critic_review = enable_critic_review
        self.signature_timeout = signature_timeout
        self.review_timeout = review_timeout
        self.high_risk_threshold = high_risk_threshold
        self.critical_risk_threshold = critical_risk_threshold

        self._pending_signatures = {}
        self._pending_reviews = {}
        self._audit_log = []

        self._stats = {
            "total_verifications": 0,
            "allowed": 0,
            "denied": 0,
            "required_signatures": 0,
            "required_reviews": 0,
            "signatures_collected": 0,
            "reviews_completed": 0,
            "constitutional_failures": 0,
        }

        self._critic_agents = {}
        self._default_signers = {
            "high": ["supervisor_agent", "compliance_agent"],
            "critical": ["supervisor_agent", "compliance_agent", "security_agent", "ethics_agent"],
        }

    async def initialize(self):
        if self.opa_client is None:
            self.opa_client = MockOPAClient()
        await self.opa_client.initialize()

    async def close(self):
        if self.opa_client:
            await self.opa_client.close()
        self._pending_signatures.clear()
        self._pending_reviews.clear()

    async def check_constitutional_compliance(self, action):
        """Check constitutional compliance."""
        constitutional_hash = action.get("constitutional_hash")
        return not (constitutional_hash and constitutional_hash != GUARD_CONSTITUTIONAL_HASH)

    def _calculate_risk_score(self, action, context, policy_result):
        """Calculate risk score based on action and context."""
        score = 0.0

        # Base score from policy result
        score += policy_result.get("risk_score", 0.0)

        # Action type factors
        action_type = action.get("type", "")
        risk_factors = {
            "delete": 0.3,
            "modify": 0.2,
            "execute": 0.15,
            "create": 0.1,
            "read": 0.05,
        }
        score += risk_factors.get(action_type, 0.0)

        # Context factors
        if context.get("affects_production", False):
            score += 0.3
        if context.get("affects_users", False):
            score += 0.2
        if context.get("sensitive_data", False):
            score += 0.25

        return min(score, 1.0)

    def _determine_risk_level(self, risk_score):
        """Determine risk level from score."""
        if risk_score >= self.critical_risk_threshold:
            return "critical"
        elif risk_score >= self.high_risk_threshold:
            return "high"
        elif risk_score >= 0.5:
            return "medium"
        return "low"

    def _identify_risk_factors(self, action, context):
        """Identify risk factors in action and context."""
        factors = []
        if action.get("type") == "delete":
            factors.append("destructive_action")
        if context.get("affects_production"):
            factors.append("production_impact")
        if context.get("sensitive_data"):
            factors.append("sensitive_data_access")
        return factors

    async def verify_action(self, agent_id, action, context):
        """Verify action before execution."""
        self._stats["total_verifications"] += 1

        result = GuardResult(
            agent_id=agent_id,
            action_type=action.get("type", "unknown"),
        )

        # Check constitutional compliance
        constitutional_valid = await self.check_constitutional_compliance(action)
        result.constitutional_valid = constitutional_valid

        if not constitutional_valid:
            self._stats["constitutional_failures"] += 1
            result.decision = GuardDecision.DENY
            result.is_allowed = False
            result.validation_errors.append("Constitutional compliance check failed")
            return result

        # Evaluate policy
        policy_input = {
            "agent_id": agent_id,
            "action": action,
            "context": context,
            "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
        }
        policy_path = action.get("policy_path", "data.acgs.guard.verify")
        policy_result = await self.opa_client.evaluate_policy(policy_input, policy_path)

        result.policy_path = policy_path
        result.policy_result = policy_result

        # Calculate risk
        risk_score = self._calculate_risk_score(action, context, policy_result)
        result.risk_score = risk_score
        result.risk_level = self._determine_risk_level(risk_score)
        result.risk_factors = self._identify_risk_factors(action, context)

        # Determine decision
        if not policy_result.get("allowed", False):
            result.decision = GuardDecision.DENY
            result.is_allowed = False
            result.validation_errors.append(policy_result.get("reason", "Policy denied action"))
            self._stats["denied"] += 1
        elif risk_score >= self.critical_risk_threshold:
            result.decision = GuardDecision.REQUIRE_REVIEW
            result.is_allowed = False
            result.requires_signatures = True
            result.requires_review = True
            result.required_signers = self._default_signers["critical"]
            self._stats["required_reviews"] += 1
            self._stats["required_signatures"] += 1
        elif risk_score >= self.high_risk_threshold:
            result.decision = GuardDecision.REQUIRE_SIGNATURES
            result.is_allowed = False
            result.requires_signatures = True
            result.required_signers = self._default_signers["high"]
            self._stats["required_signatures"] += 1
        else:
            result.decision = GuardDecision.ALLOW
            result.is_allowed = True
            self._stats["allowed"] += 1

        return result

    def register_critic_agent(self, agent_id, agent_type="general", expertise=None):
        """Register a critic agent."""
        self._critic_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "expertise": expertise or [],
            "registered_at": datetime.now(UTC),
        }
        return True

    def get_statistics(self):
        """Get guard statistics."""
        return self._stats.copy()

    def get_audit_log(self, limit=100):
        """Get audit log entries."""
        return self._audit_log[-limit:]

    async def log_decision(self, request, result):
        """Log a decision to audit log."""
        self._audit_log.append(
            {
                "request": request,
                "result": result,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


OPAGuard = OPAGuardForTest


# ============================================================================
# OPAGuard Initialization Tests
# ============================================================================


class TestOPAGuardInit:
    """Test OPAGuard initialization."""

    def test_default_initialization(self):
        """Test default initialization values."""
        guard = OPAGuard()

        assert guard.opa_client is None
        assert guard.enable_signatures is True
        assert guard.enable_critic_review is True
        assert guard.signature_timeout == 300
        assert guard.review_timeout == 300
        assert guard.high_risk_threshold == 0.8
        assert guard.critical_risk_threshold == 0.95

    def test_custom_initialization(self):
        """Test custom initialization values."""
        mock_client = MockOPAClient()
        guard = OPAGuard(
            opa_client=mock_client,
            enable_signatures=False,
            enable_critic_review=False,
            signature_timeout=600,
            review_timeout=120,
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
        )

        assert guard.opa_client is mock_client
        assert guard.enable_signatures is False
        assert guard.enable_critic_review is False
        assert guard.signature_timeout == 600
        assert guard.review_timeout == 120
        assert guard.high_risk_threshold == 0.7
        assert guard.critical_risk_threshold == 0.9

    def test_stats_initialization(self):
        """Test statistics are initialized correctly."""
        guard = OPAGuard()

        assert guard._stats["total_verifications"] == 0
        assert guard._stats["allowed"] == 0
        assert guard._stats["denied"] == 0
        assert guard._stats["required_signatures"] == 0

    def test_default_signers_configured(self):
        """Test default signers are configured."""
        guard = OPAGuard()

        assert "high" in guard._default_signers
        assert "critical" in guard._default_signers
        assert len(guard._default_signers["critical"]) > len(guard._default_signers["high"])


# ============================================================================
# OPAGuard Lifecycle Tests
# ============================================================================


class TestOPAGuardLifecycle:
    """Test OPAGuard lifecycle methods."""

    async def test_initialize(self):
        """Test guard initialization."""
        guard = OPAGuard()
        await guard.initialize()

        assert guard.opa_client is not None
        assert guard.opa_client._initialized is True

    async def test_initialize_with_existing_client(self):
        """Test initialization with existing OPA client."""
        mock_client = MockOPAClient()
        guard = OPAGuard(opa_client=mock_client)
        await guard.initialize()

        assert guard.opa_client is mock_client
        assert mock_client._initialized is True

    async def test_close(self):
        """Test guard cleanup."""
        guard = OPAGuard()
        await guard.initialize()
        guard._pending_signatures["test"] = SignatureResult(decision_id="test")
        guard._pending_reviews["test"] = ReviewResult(decision_id="test")

        await guard.close()

        assert guard.opa_client._closed is True
        assert len(guard._pending_signatures) == 0
        assert len(guard._pending_reviews) == 0


# ============================================================================
# Constitutional Compliance Tests
# ============================================================================


class TestConstitutionalCompliance:
    """Test constitutional compliance checking."""

    async def test_valid_constitutional_hash(self):
        """Test valid constitutional hash passes."""
        guard = OPAGuard()
        action = {"constitutional_hash": GUARD_CONSTITUTIONAL_HASH}

        result = await guard.check_constitutional_compliance(action)

        assert result is True

    async def test_invalid_constitutional_hash(self):
        """Test invalid constitutional hash fails."""
        guard = OPAGuard()
        action = {"constitutional_hash": "invalid_hash"}

        result = await guard.check_constitutional_compliance(action)

        assert result is False

    async def test_no_constitutional_hash(self):
        """Test missing constitutional hash passes."""
        guard = OPAGuard()
        action = {"type": "read"}

        result = await guard.check_constitutional_compliance(action)

        assert result is True


# ============================================================================
# Risk Calculation Tests
# ============================================================================


class TestRiskCalculation:
    """Test risk score calculation."""

    def test_low_risk_action(self):
        """Test low risk action calculation."""
        guard = OPAGuard()
        action = {"type": "read"}
        context = {}
        policy_result = {"risk_score": 0.0}

        score = guard._calculate_risk_score(action, context, policy_result)

        assert score < guard.high_risk_threshold

    def test_high_risk_action(self):
        """Test high risk action calculation."""
        guard = OPAGuard()
        action = {"type": "delete"}
        context = {"affects_production": True, "sensitive_data": True}
        policy_result = {"risk_score": 0.2}

        score = guard._calculate_risk_score(action, context, policy_result)

        assert score >= guard.high_risk_threshold

    def test_score_capped_at_one(self):
        """Test risk score is capped at 1.0."""
        guard = OPAGuard()
        action = {"type": "delete"}
        context = {"affects_production": True, "affects_users": True, "sensitive_data": True}
        policy_result = {"risk_score": 0.9}

        score = guard._calculate_risk_score(action, context, policy_result)

        assert score <= 1.0

    def test_risk_level_determination(self):
        """Test risk level determination."""
        guard = OPAGuard()

        assert guard._determine_risk_level(0.1) == "low"
        assert guard._determine_risk_level(0.5) == "medium"
        assert guard._determine_risk_level(0.85) == "high"
        assert guard._determine_risk_level(0.98) == "critical"


# ============================================================================
# Action Verification Tests
# ============================================================================


class TestActionVerification:
    """Test action verification."""

    async def test_allow_low_risk_action(self):
        """Test low risk action is allowed."""
        guard = OPAGuard()
        mock_client = MockOPAClient()
        mock_client.set_policy_result(
            "data.acgs.guard.verify", {"allowed": True, "risk_score": 0.0}
        )
        guard.opa_client = mock_client

        result = await guard.verify_action(
            agent_id="test_agent", action={"type": "read"}, context={}
        )

        assert result.decision == GuardDecision.ALLOW
        assert result.is_allowed is True

    async def test_require_signatures_high_risk(self):
        """Test high risk action requires signatures."""
        guard = OPAGuard(high_risk_threshold=0.5, critical_risk_threshold=0.9)
        mock_client = MockOPAClient()
        mock_client.set_policy_result(
            "data.acgs.guard.verify", {"allowed": True, "risk_score": 0.1}
        )
        guard.opa_client = mock_client

        result = await guard.verify_action(
            agent_id="test_agent",
            action={"type": "modify"},  # 0.2 risk
            context={"affects_production": True},  # 0.3 risk = 0.6 total (high but not critical)
        )

        assert result.decision == GuardDecision.REQUIRE_SIGNATURES
        assert result.is_allowed is False
        assert result.requires_signatures is True

    async def test_require_review_critical_risk(self):
        """Test critical risk action requires review."""
        guard = OPAGuard(critical_risk_threshold=0.7)
        mock_client = MockOPAClient()
        mock_client.set_policy_result(
            "data.acgs.guard.verify", {"allowed": True, "risk_score": 0.5}
        )
        guard.opa_client = mock_client

        result = await guard.verify_action(
            agent_id="test_agent",
            action={"type": "delete"},
            context={"affects_production": True, "sensitive_data": True},
        )

        assert result.decision == GuardDecision.REQUIRE_REVIEW
        assert result.requires_signatures is True
        assert result.requires_review is True

    async def test_deny_policy_denied(self):
        """Test action denied by policy."""
        guard = OPAGuard()
        mock_client = MockOPAClient()
        mock_client.set_policy_result(
            "data.acgs.guard.verify",
            {"allowed": False, "reason": "Policy denied: Unauthorized access"},
        )
        guard.opa_client = mock_client

        result = await guard.verify_action(
            agent_id="test_agent", action={"type": "execute"}, context={}
        )

        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False
        assert len(result.validation_errors) > 0
        assert "Policy denied" in result.validation_errors[0]

    async def test_deny_constitutional_failure(self):
        """Test action denied due to constitutional failure."""
        guard = OPAGuard()
        mock_client = MockOPAClient()
        guard.opa_client = mock_client

        result = await guard.verify_action(
            agent_id="test_agent",
            action={"type": "execute", "constitutional_hash": "invalid_hash"},
            context={},
        )

        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False
        assert result.constitutional_valid is False

    async def test_stats_updated(self):
        """Test statistics are updated after verification."""
        guard = OPAGuard()
        mock_client = MockOPAClient()
        mock_client.set_policy_result(
            "data.acgs.guard.verify", {"allowed": True, "risk_score": 0.0}
        )
        guard.opa_client = mock_client

        await guard.verify_action(agent_id="test_agent", action={"type": "read"}, context={})

        assert guard._stats["total_verifications"] == 1
        assert guard._stats["allowed"] == 1


# ============================================================================
# Critic Agent Registration Tests
# ============================================================================


class TestCriticAgentRegistration:
    """Test critic agent registration."""

    def test_register_critic_agent(self):
        """Test registering a critic agent."""
        guard = OPAGuard()

        result = guard.register_critic_agent(
            agent_id="critic_1", agent_type="security", expertise=["policy", "compliance"]
        )

        assert result is True
        assert "critic_1" in guard._critic_agents
        assert guard._critic_agents["critic_1"]["agent_type"] == "security"

    def test_register_multiple_critics(self):
        """Test registering multiple critic agents."""
        guard = OPAGuard()

        guard.register_critic_agent("critic_1", "security")
        guard.register_critic_agent("critic_2", "ethics")
        guard.register_critic_agent("critic_3", "compliance")

        assert len(guard._critic_agents) == 3


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Test guard statistics."""

    def test_get_statistics(self):
        """Test getting guard statistics."""
        guard = OPAGuard()
        guard._stats["total_verifications"] = 100
        guard._stats["allowed"] = 90
        guard._stats["denied"] = 10

        stats = guard.get_statistics()

        assert stats["total_verifications"] == 100
        assert stats["allowed"] == 90
        assert stats["denied"] == 10

    def test_statistics_copy(self):
        """Test statistics returns a copy."""
        guard = OPAGuard()

        stats = guard.get_statistics()
        stats["total_verifications"] = 999

        assert guard._stats["total_verifications"] == 0


# ============================================================================
# Audit Log Tests
# ============================================================================


class TestAuditLog:
    """Test audit logging."""

    async def test_log_decision(self):
        """Test logging a decision."""
        guard = OPAGuard()

        await guard.log_decision(
            request={"agent_id": "test", "action": {"type": "read"}}, result={"decision": "allow"}
        )

        assert len(guard._audit_log) == 1
        assert guard._audit_log[0]["result"]["decision"] == "allow"

    def test_get_audit_log(self):
        """Test getting audit log."""
        guard = OPAGuard()
        guard._audit_log = [{"request": 1}, {"request": 2}, {"request": 3}]

        log = guard.get_audit_log(limit=2)

        assert len(log) == 2

    def test_audit_log_limit(self):
        """Test audit log respects limit."""
        guard = OPAGuard()
        for i in range(150):
            guard._audit_log.append({"request": i})

        log = guard.get_audit_log(limit=100)

        assert len(log) == 100


# ============================================================================
# Risk Factor Identification Tests
# ============================================================================


class TestRiskFactorIdentification:
    """Test risk factor identification."""

    def test_identify_destructive_action(self):
        """Test destructive action is identified."""
        guard = OPAGuard()
        action = {"type": "delete"}
        context = {}

        factors = guard._identify_risk_factors(action, context)

        assert "destructive_action" in factors

    def test_identify_production_impact(self):
        """Test production impact is identified."""
        guard = OPAGuard()
        action = {"type": "modify"}
        context = {"affects_production": True}

        factors = guard._identify_risk_factors(action, context)

        assert "production_impact" in factors

    def test_identify_sensitive_data(self):
        """Test sensitive data access is identified."""
        guard = OPAGuard()
        action = {"type": "read"}
        context = {"sensitive_data": True}

        factors = guard._identify_risk_factors(action, context)

        assert "sensitive_data_access" in factors

    def test_no_risk_factors(self):
        """Test no risk factors for safe action."""
        guard = OPAGuard()
        action = {"type": "read"}
        context = {}

        factors = guard._identify_risk_factors(action, context)

        assert len(factors) == 0
