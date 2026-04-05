"""
Unit tests for multi_approver.py helper functions
Constitutional Hash: 608508a9bd224290

Tests extracted helper methods to ensure C901 complexity reduction
while preserving behavior.
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..multi_approver import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
    Approver,
    ApproverRole,
    MultiApproverWorkflowEngine,
)


# Fixtures
@pytest.fixture
def sample_approver() -> Approver:
    """Create a sample approver."""
    return Approver(
        id="approver-1",
        name="John Doe",
        email="john@example.com",
        roles=[ApproverRole.SECURITY_TEAM],
        slack_id="U123456",
    )


@pytest.fixture
def security_approver() -> Approver:
    """Create a security team approver."""
    return Approver(
        id="security-1",
        name="Security Lead",
        email="security@example.com",
        roles=[ApproverRole.SECURITY_TEAM],
    )


@pytest.fixture
def compliance_approver() -> Approver:
    """Create a compliance team approver."""
    return Approver(
        id="compliance-1",
        name="Compliance Officer",
        email="compliance@example.com",
        roles=[ApproverRole.COMPLIANCE_TEAM],
    )


@pytest.fixture
def platform_admin_approver() -> Approver:
    """Create a platform admin approver."""
    return Approver(
        id="admin-1",
        name="Platform Admin",
        email="admin@example.com",
        roles=[ApproverRole.PLATFORM_ADMIN, ApproverRole.POLICY_OWNER],
    )


@pytest.fixture
def multi_role_approver() -> Approver:
    """Create an approver with multiple roles."""
    return Approver(
        id="multi-1",
        name="Multi Role User",
        email="multi@example.com",
        roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
    )


@pytest.fixture
def basic_policy() -> ApprovalPolicy:
    """Create a basic approval policy."""
    return ApprovalPolicy(
        name="Basic Policy",
        required_roles=[ApproverRole.SECURITY_TEAM],
        min_approvers=1,
        require_all_roles=False,
        allow_self_approval=False,
        require_reasoning=True,
    )


@pytest.fixture
def strict_policy() -> ApprovalPolicy:
    """Create a strict approval policy requiring multiple roles."""
    return ApprovalPolicy(
        name="Strict Policy",
        required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
        min_approvers=2,
        require_all_roles=True,
        allow_self_approval=False,
        require_reasoning=True,
    )


@pytest.fixture
def flexible_policy() -> ApprovalPolicy:
    """Create a flexible policy allowing self-approval."""
    return ApprovalPolicy(
        name="Flexible Policy",
        required_roles=[ApproverRole.PLATFORM_ADMIN],
        min_approvers=1,
        require_all_roles=False,
        allow_self_approval=True,
        require_reasoning=False,
    )


@pytest.fixture
def sample_request(basic_policy: ApprovalPolicy) -> ApprovalRequest:
    """Create a sample approval request."""
    return ApprovalRequest(
        id="req-1",
        request_type="test_request",
        requester_id="user-1",
        requester_name="Test User",
        tenant_id="tenant-1",
        title="Test Request",
        description="A test approval request",
        risk_score=0.5,
        policy=basic_policy,
        payload={"action": "test"},
    )


@pytest.fixture
def approved_decision(sample_approver: Approver) -> ApprovalDecision:
    """Create an approved decision."""
    return ApprovalDecision(
        approver_id=sample_approver.id,
        approver_name=sample_approver.name,
        decision=ApprovalStatus.APPROVED,
        reasoning="Looks good to me",
        metadata={"review_time": "5min"},
    )


@pytest.fixture
def rejected_decision(sample_approver: Approver) -> ApprovalDecision:
    """Create a rejected decision."""
    return ApprovalDecision(
        approver_id=sample_approver.id,
        approver_name=sample_approver.name,
        decision=ApprovalStatus.REJECTED,
        reasoning="Security concerns",
    )


@pytest.fixture
def workflow_engine() -> MultiApproverWorkflowEngine:
    """Create a workflow engine instance."""
    engine = MultiApproverWorkflowEngine()
    return engine


@pytest.fixture
def populated_engine(
    workflow_engine: MultiApproverWorkflowEngine,
    security_approver: Approver,
    compliance_approver: Approver,
    platform_admin_approver: Approver,
) -> MultiApproverWorkflowEngine:
    """Create a workflow engine with registered approvers."""
    workflow_engine.register_approver(security_approver)
    workflow_engine.register_approver(compliance_approver)
    workflow_engine.register_approver(platform_admin_approver)
    return workflow_engine


# Tests for ApprovalPolicy._check_minimum_approvers
class TestCheckMinimumApprovers:
    """Test _check_minimum_approvers helper method."""

    def test_minimum_approvers_met(
        self, basic_policy: ApprovalPolicy, approved_decision: ApprovalDecision
    ):
        """Test that minimum approvers requirement is met."""
        result, message = basic_policy._check_minimum_approvers([approved_decision])
        assert result is True
        assert message == ""

    def test_minimum_approvers_not_met(self, basic_policy: ApprovalPolicy):
        """Test that minimum approvers requirement is not met."""
        basic_policy.min_approvers = 2
        result, message = basic_policy._check_minimum_approvers([])
        assert result is False
        assert "Need 2 approvers, got 0" in message

    def test_minimum_approvers_exactly_met(
        self, security_approver: Approver, compliance_approver: Approver
    ):
        """Test minimum approvers with exact count."""
        policy = ApprovalPolicy(
            name="Test", required_roles=[ApproverRole.SECURITY_TEAM], min_approvers=2
        )

        decisions = [
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Good",
            ),
            ApprovalDecision(
                approver_id=compliance_approver.id,
                approver_name=compliance_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Approved",
            ),
        ]

        result, message = policy._check_minimum_approvers(decisions)
        assert result is True
        assert message == ""

    def test_minimum_approvers_edge_case_zero(self, basic_policy: ApprovalPolicy):
        """Test edge case with zero minimum approvers."""
        basic_policy.min_approvers = 0
        result, message = basic_policy._check_minimum_approvers([])
        assert result is True
        assert message == ""


# Tests for ApprovalPolicy._check_self_approval
class TestCheckSelfApproval:
    """Test _check_self_approval helper method."""

    def test_self_approval_allowed(
        self, flexible_policy: ApprovalPolicy, approved_decision: ApprovalDecision
    ):
        """Test self-approval when allowed."""
        requester_id = approved_decision.approver_id  # Same as approver
        result, message = flexible_policy._check_self_approval([approved_decision], requester_id)
        assert result is True
        assert message == ""

    def test_self_approval_not_allowed(
        self, basic_policy: ApprovalPolicy, approved_decision: ApprovalDecision
    ):
        """Test self-approval when not allowed."""
        requester_id = approved_decision.approver_id  # Same as approver
        result, message = basic_policy._check_self_approval([approved_decision], requester_id)
        assert result is False
        assert "Self-approval not allowed" in message

    def test_different_approver_allowed(
        self, basic_policy: ApprovalPolicy, approved_decision: ApprovalDecision
    ):
        """Test different approver is always allowed."""
        requester_id = "different-user"
        result, message = basic_policy._check_self_approval([approved_decision], requester_id)
        assert result is True
        assert message == ""

    def test_multiple_decisions_with_self_approval(
        self,
        basic_policy: ApprovalPolicy,
        security_approver: Approver,
        compliance_approver: Approver,
    ):
        """Test multiple decisions where one is self-approval."""
        decisions = [
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Good",
            ),
            ApprovalDecision(
                approver_id="requester-id",
                approver_name="Self",
                decision=ApprovalStatus.APPROVED,
                reasoning="Self-approve",
            ),
        ]

        result, message = basic_policy._check_self_approval(decisions, "requester-id")
        assert result is False
        assert "Self-approval not allowed" in message


# Tests for ApprovalPolicy._check_required_roles
class TestCheckRequiredRoles:
    """Test _check_required_roles helper method."""

    def test_any_role_required_dispatch(
        self,
        basic_policy: ApprovalPolicy,
        approved_decision: ApprovalDecision,
        sample_approver: Approver,
    ):
        """Test that _check_required_roles dispatches to _check_any_role_required."""
        approvers_dict = {sample_approver.id: sample_approver}
        result, _message = basic_policy._check_required_roles([approved_decision], approvers_dict)
        assert result is True

    def test_all_roles_required_dispatch(
        self,
        strict_policy: ApprovalPolicy,
        approved_decision: ApprovalDecision,
        security_approver: Approver,
    ):
        """Test that _check_required_roles dispatches to _check_all_roles_required."""
        approvers_dict = {security_approver.id: security_approver}
        result, _message = strict_policy._check_required_roles([approved_decision], approvers_dict)
        assert result is False  # Missing compliance role


# Tests for ApprovalPolicy._check_all_roles_required
class TestCheckAllRolesRequired:
    """Test _check_all_roles_required helper method."""

    def test_all_roles_satisfied(
        self,
        strict_policy: ApprovalPolicy,
        security_approver: Approver,
        compliance_approver: Approver,
    ):
        """Test all required roles are satisfied."""
        decisions = [
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Security approved",
            ),
            ApprovalDecision(
                approver_id=compliance_approver.id,
                approver_name=compliance_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Compliance approved",
            ),
        ]
        approvers_dict = {
            security_approver.id: security_approver,
            compliance_approver.id: compliance_approver,
        }

        result, message = strict_policy._check_all_roles_required(decisions, approvers_dict)
        assert result is True
        assert message == ""

    def test_missing_required_role(
        self, strict_policy: ApprovalPolicy, security_approver: Approver
    ):
        """Test missing required role."""
        decisions = [
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Security approved",
            )
        ]
        approvers_dict = {security_approver.id: security_approver}

        result, message = strict_policy._check_all_roles_required(decisions, approvers_dict)
        assert result is False
        assert "Missing approvals from roles" in message
        assert "compliance_team" in message

    def test_multi_role_approver_satisfies_multiple(self, multi_role_approver: Approver):
        """Test approver with multiple roles satisfies multiple requirements."""
        policy = ApprovalPolicy(
            name="Multi Test",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            require_all_roles=True,
        )

        decisions = [
            ApprovalDecision(
                approver_id=multi_role_approver.id,
                approver_name=multi_role_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Multi-role approval",
            )
        ]
        approvers_dict = {multi_role_approver.id: multi_role_approver}

        result, message = policy._check_all_roles_required(decisions, approvers_dict)
        assert result is True
        assert message == ""

    def test_approver_not_found_in_dict(self, strict_policy: ApprovalPolicy):
        """Test when approver is not found in dictionary."""
        decisions = [
            ApprovalDecision(
                approver_id="non-existent",
                approver_name="Ghost",
                decision=ApprovalStatus.APPROVED,
                reasoning="Ghost approval",
            )
        ]
        approvers_dict = {}

        result, message = strict_policy._check_all_roles_required(decisions, approvers_dict)
        assert result is False
        assert "Missing approvals from roles" in message


# Tests for ApprovalPolicy._check_any_role_required
class TestCheckAnyRoleRequired:
    """Test _check_any_role_required helper method."""

    def test_no_required_roles(self):
        """Test when no roles are required."""
        policy = ApprovalPolicy(name="No Roles", required_roles=[])
        result, message = policy._check_any_role_required([], {})
        assert result is True
        assert message == ""

    def test_has_required_role(self, basic_policy: ApprovalPolicy, security_approver: Approver):
        """Test when approver has required role."""
        decisions = [
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Approved",
            )
        ]
        approvers_dict = {security_approver.id: security_approver}

        result, message = basic_policy._check_any_role_required(decisions, approvers_dict)
        assert result is True
        assert message == ""

    def test_no_required_role(self, basic_policy: ApprovalPolicy, compliance_approver: Approver):
        """Test when approver doesn't have required role."""
        decisions = [
            ApprovalDecision(
                approver_id=compliance_approver.id,
                approver_name=compliance_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Approved",
            )
        ]
        approvers_dict = {compliance_approver.id: compliance_approver}

        result, message = basic_policy._check_any_role_required(decisions, approvers_dict)
        assert result is False
        assert "No approver with required role" in message
        assert "security_team" in message

    def test_partial_role_match(self, multi_role_approver: Approver):
        """Test partial role match is sufficient."""
        policy = ApprovalPolicy(
            name="Multi Required",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.PLATFORM_ADMIN],
            require_all_roles=False,
        )

        decisions = [
            ApprovalDecision(
                approver_id=multi_role_approver.id,
                approver_name=multi_role_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Partial match",
            )
        ]
        approvers_dict = {multi_role_approver.id: multi_role_approver}

        result, message = policy._check_any_role_required(decisions, approvers_dict)
        assert result is True
        assert message == ""

    def test_multiple_decisions_one_valid(
        self,
        basic_policy: ApprovalPolicy,
        security_approver: Approver,
        compliance_approver: Approver,
    ):
        """Test multiple decisions where only one has required role."""
        decisions = [
            ApprovalDecision(
                approver_id=compliance_approver.id,
                approver_name=compliance_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Wrong role",
            ),
            ApprovalDecision(
                approver_id=security_approver.id,
                approver_name=security_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Right role",
            ),
        ]
        approvers_dict = {
            compliance_approver.id: compliance_approver,
            security_approver.id: security_approver,
        }

        result, message = basic_policy._check_any_role_required(decisions, approvers_dict)
        assert result is True
        assert message == ""


# Tests for MultiApproverWorkflowEngine._validate_decision_submission
class TestValidateDecisionSubmission:
    """Test _validate_decision_submission helper method."""

    def test_valid_decision_submission(self, populated_engine: MultiApproverWorkflowEngine):
        """Test valid decision submission."""
        # Create a test request
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=populated_engine._policies["standard_request"],
            payload={},
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req", "security-1", "Valid reasoning"
        )
        assert result is True
        assert message == ""

    def test_request_not_found(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation with non-existent request."""
        result, message = populated_engine._validate_decision_submission(
            "non-existent", "security-1", "Reasoning"
        )
        assert result is False
        assert "Request not found" in message

    def test_request_not_pending(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation with non-pending request."""
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=populated_engine._policies["standard_request"],
            payload={},
            status=ApprovalStatus.APPROVED,
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req", "security-1", "Reasoning"
        )
        assert result is False
        assert "Request is not pending" in message

    def test_approver_not_registered(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation with unregistered approver."""
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=populated_engine._policies["standard_request"],
            payload={},
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req", "unknown-approver", "Reasoning"
        )
        assert result is False
        assert "Approver not registered" in message

    def test_already_decided(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation when approver already decided."""
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=populated_engine._policies["standard_request"],
            payload={},
        )
        # Add existing decision
        request.decisions.append(
            ApprovalDecision(
                approver_id="security-1",
                approver_name="Security Lead",
                decision=ApprovalStatus.APPROVED,
                reasoning="Already decided",
            )
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req", "security-1", "Reasoning"
        )
        assert result is False
        assert "Approver already submitted decision" in message

    def test_reasoning_required_but_empty(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation when reasoning is required but empty."""
        policy = ApprovalPolicy(
            name="Test Policy", required_roles=[ApproverRole.SECURITY_TEAM], require_reasoning=True
        )
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=policy,
            payload={},
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req",
            "security-1",
            "   ",  # Whitespace only
        )
        assert result is False
        assert "Reasoning is required" in message

    def test_reasoning_not_required_empty_ok(self, populated_engine: MultiApproverWorkflowEngine):
        """Test validation when reasoning not required and empty."""
        policy = ApprovalPolicy(
            name="Test Policy", required_roles=[ApproverRole.SECURITY_TEAM], require_reasoning=False
        )
        request = ApprovalRequest(
            id="test-req",
            request_type="test",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test",
            description="Test request",
            risk_score=0.5,
            policy=policy,
            payload={},
        )
        populated_engine._requests["test-req"] = request

        result, message = populated_engine._validate_decision_submission(
            "test-req", "security-1", ""
        )
        assert result is True
        assert message == ""


# Tests for MultiApproverWorkflowEngine._create_approval_decision
class TestCreateApprovalDecision:
    """Test _create_approval_decision helper method."""

    def test_create_approval_decision_basic(
        self, populated_engine: MultiApproverWorkflowEngine, security_approver: Approver
    ):
        """Test basic approval decision creation."""
        decision = populated_engine._create_approval_decision(
            security_approver, ApprovalStatus.APPROVED, "Looks good", {"review_time": "10min"}
        )

        assert decision.approver_id == security_approver.id
        assert decision.approver_name == security_approver.name
        assert decision.decision == ApprovalStatus.APPROVED
        assert decision.reasoning == "Looks good"
        assert decision.metadata == {"review_time": "10min"}
        assert isinstance(decision.timestamp, datetime)

    def test_create_approval_decision_rejected(
        self, populated_engine: MultiApproverWorkflowEngine, compliance_approver: Approver
    ):
        """Test rejected decision creation."""
        decision = populated_engine._create_approval_decision(
            compliance_approver, ApprovalStatus.REJECTED, "Security concerns", None
        )

        assert decision.approver_id == compliance_approver.id
        assert decision.decision == ApprovalStatus.REJECTED
        assert decision.reasoning == "Security concerns"
        assert decision.metadata == {}

    def test_create_approval_decision_with_metadata(
        self, populated_engine: MultiApproverWorkflowEngine, platform_admin_approver: Approver
    ):
        """Test decision creation with rich metadata."""
        metadata = {
            "review_time": "2min",
            "automated": False,
            "risk_assessment": {"score": 0.3, "factors": ["low_complexity"]},
        }

        decision = populated_engine._create_approval_decision(
            platform_admin_approver, ApprovalStatus.APPROVED, "Fast approval", metadata
        )

        assert decision.metadata == metadata
        assert decision.timestamp.tzinfo == UTC

    def test_create_approval_decision_timestamp_utc(
        self, populated_engine: MultiApproverWorkflowEngine, security_approver: Approver
    ):
        """Test that timestamp is always in UTC."""
        decision = populated_engine._create_approval_decision(
            security_approver, ApprovalStatus.APPROVED, "Test", None
        )

        assert decision.timestamp.tzinfo == UTC
        # Should be very recent
        now = datetime.now(UTC)
        time_diff = abs((now - decision.timestamp).total_seconds())
        assert time_diff < 1.0  # Less than 1 second


# Tests for MultiApproverWorkflowEngine._select_policy_for_risk
class TestSelectPolicyForRisk:
    """Test _select_policy_for_risk helper method."""

    def test_critical_risk_policy(self, populated_engine: MultiApproverWorkflowEngine):
        """Test selection of critical deployment policy for highest risk."""
        policy_id = populated_engine._select_policy_for_risk(0.95)
        assert policy_id == "critical_deployment"

    def test_high_risk_policy(self, populated_engine: MultiApproverWorkflowEngine):
        """Test selection of high risk action policy."""
        policy_id = populated_engine._select_policy_for_risk(0.75)
        assert policy_id == "high_risk_action"

    def test_medium_risk_policy(self, populated_engine: MultiApproverWorkflowEngine):
        """Test selection of policy change policy for medium risk."""
        policy_id = populated_engine._select_policy_for_risk(0.60)
        assert policy_id == "policy_change"

    def test_low_risk_policy(self, populated_engine: MultiApproverWorkflowEngine):
        """Test selection of standard request policy for low risk."""
        policy_id = populated_engine._select_policy_for_risk(0.30)
        assert policy_id == "standard_request"

    def test_boundary_conditions(self, populated_engine: MultiApproverWorkflowEngine):
        """Test boundary conditions for risk score thresholds."""
        # Test exact boundaries
        assert populated_engine._select_policy_for_risk(0.90) == "critical_deployment"
        assert populated_engine._select_policy_for_risk(0.89) == "high_risk_action"

        assert populated_engine._select_policy_for_risk(0.70) == "high_risk_action"
        assert populated_engine._select_policy_for_risk(0.69) == "policy_change"

        assert populated_engine._select_policy_for_risk(0.50) == "policy_change"
        assert populated_engine._select_policy_for_risk(0.49) == "standard_request"

    def test_edge_cases_risk_scores(self, populated_engine: MultiApproverWorkflowEngine):
        """Test edge cases with extreme risk scores."""
        # Minimum risk
        assert populated_engine._select_policy_for_risk(0.0) == "standard_request"

        # Maximum risk
        assert populated_engine._select_policy_for_risk(1.0) == "critical_deployment"

        # Very small positive
        assert populated_engine._select_policy_for_risk(0.001) == "standard_request"

        # Just under 1.0
        assert populated_engine._select_policy_for_risk(0.999) == "critical_deployment"


# Integration tests for helper interactions
class TestHelperIntegrations:
    """Test how helpers work together in realistic scenarios."""

    def test_complete_validation_flow(
        self,
        populated_engine: MultiApproverWorkflowEngine,
        security_approver: Approver,
        compliance_approver: Approver,
    ):
        """Test complete validation flow using multiple helpers."""
        # Create a high-risk request requiring multiple approvers
        policy = ApprovalPolicy(
            name="Integration Test",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            min_approvers=2,
            require_all_roles=True,
            require_reasoning=True,
        )

        request = ApprovalRequest(
            id="integration-test",
            request_type="integration",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Integration Test",
            description="Testing helper integration",
            risk_score=0.8,
            policy=policy,
            payload={},
        )

        populated_engine._requests[request.id] = request

        # Test first validation - should pass
        result, _message = populated_engine._validate_decision_submission(
            request.id, security_approver.id, "Security review complete"
        )
        assert result is True

        # Create first decision
        decision1 = populated_engine._create_approval_decision(
            security_approver,
            ApprovalStatus.APPROVED,
            "Security review complete",
            {"review_duration": "15min"},
        )

        # Simulate recording the decision
        request.decisions.append(decision1)

        # Test second validation - should pass
        result, _message = populated_engine._validate_decision_submission(
            request.id, compliance_approver.id, "Compliance approved"
        )
        assert result is True

        # Create second decision
        decision2 = populated_engine._create_approval_decision(
            compliance_approver, ApprovalStatus.APPROVED, "Compliance approved", None
        )

        # Test policy validation with both decisions
        approvers_dict = {
            security_approver.id: security_approver,
            compliance_approver.id: compliance_approver,
        }

        is_valid, reason = policy.validate_approvers(
            [decision1, decision2], approvers_dict, request.requester_id
        )
        assert is_valid is True
        assert reason == "All requirements met"

    def test_policy_selection_and_validation_integration(
        self, populated_engine: MultiApproverWorkflowEngine
    ):
        """Test policy selection integrating with validation."""
        # High risk should select critical deployment policy
        high_risk_policy_id = populated_engine._select_policy_for_risk(0.95)
        assert high_risk_policy_id == "critical_deployment"

        # Verify the selected policy has appropriate requirements
        policy = populated_engine._policies[high_risk_policy_id]
        assert policy.min_approvers == 3
        assert policy.require_all_roles is True
        assert len(policy.required_roles) == 3

        # Low risk should select standard policy
        low_risk_policy_id = populated_engine._select_policy_for_risk(0.2)
        assert low_risk_policy_id == "standard_request"

        low_risk_policy = populated_engine._policies[low_risk_policy_id]
        assert low_risk_policy.min_approvers == 1
        assert low_risk_policy.auto_approve_low_risk is True

    def test_error_path_integration(
        self, populated_engine: MultiApproverWorkflowEngine, security_approver: Approver
    ):
        """Test error paths across multiple helpers."""
        # Create request that will fail various validations
        policy = ApprovalPolicy(
            name="Failing Test",
            required_roles=[ApproverRole.COMPLIANCE_TEAM],  # Security approver lacks this
            min_approvers=2,
            require_all_roles=True,
            require_reasoning=True,
            allow_self_approval=False,
        )

        request = ApprovalRequest(
            id="fail-test",
            request_type="fail",
            requester_id=security_approver.id,  # Self-approval case
            requester_name="Self Requester",
            tenant_id="tenant-1",
            title="Failing Test",
            description="Test failure modes",
            risk_score=0.7,
            policy=policy,
            payload={},
        )

        populated_engine._requests[request.id] = request

        # Decision submission should work
        result, _message = populated_engine._validate_decision_submission(
            request.id, security_approver.id, "Valid reasoning"
        )
        assert result is True

        # But policy validation should fail on multiple fronts
        decision = populated_engine._create_approval_decision(
            security_approver, ApprovalStatus.APPROVED, "Valid reasoning", None
        )

        approvers_dict = {security_approver.id: security_approver}

        is_valid, reason = policy.validate_approvers(
            [decision], approvers_dict, request.requester_id
        )
        assert is_valid is False
        # Could fail on minimum approvers, wrong role, or self-approval
        assert any(
            text in reason
            for text in ["Need 2 approvers", "Self-approval not allowed", "Missing approvals"]
        )
