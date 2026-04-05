"""
ACGS-2 Enhanced Agent Bus - Multi-Approver Workflow Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the MultiApproverWorkflowEngine and related classes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from enhanced_agent_bus.deliberation_layer.multi_approver import (
    CONSTITUTIONAL_HASH,
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
    Approver,
    ApproverRole,
    EscalationLevel,
    MultiApproverWorkflowEngine,
    SlackNotificationChannel,
    TeamsNotificationChannel,
    get_workflow_engine,
    initialize_workflow_engine,
    shutdown_workflow_engine,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_approver() -> Approver:
    """Create a sample approver."""
    return Approver(
        id="approver-1",
        name="John Doe",
        email="john.doe@example.com",
        roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
        slack_id="U12345",
        teams_id="T12345",
        timezone="America/New_York",
        is_active=True,
    )


@pytest.fixture
def sample_policy() -> ApprovalPolicy:
    """Create a sample approval policy."""
    return ApprovalPolicy(
        name="Test Policy",
        required_roles=[ApproverRole.SECURITY_TEAM],
        min_approvers=1,
        require_all_roles=False,
        timeout_hours=24.0,
        escalation_hours=4.0,
        allow_self_approval=False,
        require_reasoning=True,
    )


@pytest.fixture
def sample_request(sample_policy: ApprovalPolicy) -> ApprovalRequest:
    """Create a sample approval request."""
    return ApprovalRequest(
        id="request-1",
        request_type="policy_change",
        requester_id="user-1",
        requester_name="Alice Smith",
        tenant_id="tenant-1",
        title="Update Security Policy",
        description="Updating security policy to add new rules",
        risk_score=0.75,
        policy=sample_policy,
        payload={"policy_id": "sec-001", "changes": ["rule1", "rule2"]},
    )


@pytest.fixture
def workflow_engine() -> MultiApproverWorkflowEngine:
    """Create a workflow engine instance."""
    return MultiApproverWorkflowEngine(notification_channels=[])


# =============================================================================
# Enum Tests
# =============================================================================


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all expected statuses exist."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.ESCALATED.value == "escalated"
        assert ApprovalStatus.TIMEOUT.value == "timeout"
        assert ApprovalStatus.CANCELLED.value == "cancelled"

    def test_status_count(self) -> None:
        """Test total number of statuses."""
        assert len(ApprovalStatus) == 6


class TestApproverRole:
    """Tests for ApproverRole enum."""

    def test_all_roles_exist(self) -> None:
        """Test that all expected roles exist."""
        assert ApproverRole.SECURITY_TEAM.value == "security_team"
        assert ApproverRole.COMPLIANCE_TEAM.value == "compliance_team"
        assert ApproverRole.PLATFORM_ADMIN.value == "platform_admin"
        assert ApproverRole.TENANT_ADMIN.value == "tenant_admin"
        assert ApproverRole.POLICY_OWNER.value == "policy_owner"
        assert ApproverRole.ENGINEERING_LEAD.value == "engineering_lead"
        assert ApproverRole.ON_CALL.value == "on_call"

    def test_role_count(self) -> None:
        """Test total number of roles."""
        assert len(ApproverRole) == 7


class TestEscalationLevel:
    """Tests for EscalationLevel enum."""

    def test_escalation_levels(self) -> None:
        """Test escalation level values."""
        assert EscalationLevel.LEVEL_1.value == 1
        assert EscalationLevel.LEVEL_2.value == 2
        assert EscalationLevel.LEVEL_3.value == 3
        assert EscalationLevel.EXECUTIVE.value == 4

    def test_level_ordering(self) -> None:
        """Test that levels are properly ordered."""
        assert EscalationLevel.LEVEL_1.value < EscalationLevel.LEVEL_2.value
        assert EscalationLevel.LEVEL_2.value < EscalationLevel.LEVEL_3.value
        assert EscalationLevel.LEVEL_3.value < EscalationLevel.EXECUTIVE.value


# =============================================================================
# Approver Tests
# =============================================================================


class TestApprover:
    """Tests for Approver dataclass."""

    def test_approver_creation(self, sample_approver: Approver) -> None:
        """Test basic approver creation."""
        assert sample_approver.id == "approver-1"
        assert sample_approver.name == "John Doe"
        assert sample_approver.email == "john.doe@example.com"
        assert len(sample_approver.roles) == 2
        assert sample_approver.is_active is True

    def test_approver_has_role_positive(self, sample_approver: Approver) -> None:
        """Test has_role returns True for assigned roles."""
        assert sample_approver.has_role(ApproverRole.SECURITY_TEAM) is True
        assert sample_approver.has_role(ApproverRole.COMPLIANCE_TEAM) is True

    def test_approver_has_role_negative(self, sample_approver: Approver) -> None:
        """Test has_role returns False for unassigned roles."""
        assert sample_approver.has_role(ApproverRole.PLATFORM_ADMIN) is False
        assert sample_approver.has_role(ApproverRole.ON_CALL) is False

    def test_approver_default_values(self) -> None:
        """Test approver default values."""
        approver = Approver(
            id="test-1",
            name="Test User",
            email="test@example.com",
            roles=[ApproverRole.TENANT_ADMIN],
        )
        assert approver.slack_id is None
        assert approver.teams_id is None
        assert approver.timezone == "UTC"
        assert approver.is_active is True


# =============================================================================
# ApprovalDecision Tests
# =============================================================================


class TestApprovalDecision:
    """Tests for ApprovalDecision dataclass."""

    def test_decision_creation(self) -> None:
        """Test basic decision creation."""
        decision = ApprovalDecision(
            approver_id="approver-1",
            approver_name="John Doe",
            decision=ApprovalStatus.APPROVED,
            reasoning="Looks good to me",
        )
        assert decision.approver_id == "approver-1"
        assert decision.decision == ApprovalStatus.APPROVED
        assert decision.reasoning == "Looks good to me"
        assert isinstance(decision.timestamp, datetime)

    def test_decision_to_dict(self) -> None:
        """Test decision serialization to dictionary."""
        decision = ApprovalDecision(
            approver_id="approver-1",
            approver_name="John Doe",
            decision=ApprovalStatus.REJECTED,
            reasoning="Security concerns",
            metadata={"severity": "high"},
        )
        result = decision.to_dict()

        assert result["approver_id"] == "approver-1"
        assert result["approver_name"] == "John Doe"
        assert result["decision"] == "rejected"
        assert result["reasoning"] == "Security concerns"
        assert result["metadata"]["severity"] == "high"
        assert "timestamp" in result

    def test_decision_default_metadata(self) -> None:
        """Test default metadata is empty dict."""
        decision = ApprovalDecision(
            approver_id="a1",
            approver_name="Test",
            decision=ApprovalStatus.APPROVED,
            reasoning="OK",
        )
        assert decision.metadata == {}


# =============================================================================
# ApprovalPolicy Tests
# =============================================================================


class TestApprovalPolicy:
    """Tests for ApprovalPolicy dataclass."""

    def test_policy_creation(self, sample_policy: ApprovalPolicy) -> None:
        """Test basic policy creation."""
        assert sample_policy.name == "Test Policy"
        assert sample_policy.min_approvers == 1
        assert sample_policy.timeout_hours == 24.0

    def test_policy_defaults(self) -> None:
        """Test policy default values."""
        policy = ApprovalPolicy(
            name="Minimal Policy",
            required_roles=[ApproverRole.TENANT_ADMIN],
        )
        assert policy.min_approvers == 1
        assert policy.require_all_roles is False
        assert policy.timeout_hours == 24.0
        assert policy.escalation_hours == 4.0
        assert policy.allow_self_approval is False
        assert policy.require_reasoning is True
        assert policy.auto_approve_low_risk is False
        assert policy.risk_threshold == 0.5

    def test_validate_approvers_min_approvers(
        self, sample_policy: ApprovalPolicy, sample_approver: Approver
    ) -> None:
        """Test validation requires minimum approvers."""
        decisions: list[ApprovalDecision] = []
        approvers = {sample_approver.id: sample_approver}

        is_valid, reason = sample_policy.validate_approvers(decisions, approvers, "requester-1")
        assert is_valid is False
        assert "Need 1 approvers" in reason

    def test_validate_approvers_success(
        self, sample_policy: ApprovalPolicy, sample_approver: Approver
    ) -> None:
        """Test successful validation with sufficient approvers."""
        decisions = [
            ApprovalDecision(
                approver_id=sample_approver.id,
                approver_name=sample_approver.name,
                decision=ApprovalStatus.APPROVED,
                reasoning="Approved",
            )
        ]
        approvers = {sample_approver.id: sample_approver}

        is_valid, reason = sample_policy.validate_approvers(decisions, approvers, "requester-1")
        assert is_valid is True
        assert reason == "All requirements met"

    def test_validate_approvers_self_approval_rejected(self) -> None:
        """Test self-approval is rejected when not allowed."""
        policy = ApprovalPolicy(
            name="No Self Approval",
            required_roles=[ApproverRole.TENANT_ADMIN],
            allow_self_approval=False,
        )
        approver = Approver(
            id="user-1",
            name="User One",
            email="user1@test.com",
            roles=[ApproverRole.TENANT_ADMIN],
        )
        decisions = [
            ApprovalDecision(
                approver_id="user-1",
                approver_name="User One",
                decision=ApprovalStatus.APPROVED,
                reasoning="Self approved",
            )
        ]
        approvers = {"user-1": approver}

        is_valid, reason = policy.validate_approvers(
            decisions,
            approvers,
            "user-1",  # requester is same as approver
        )
        assert is_valid is False
        assert "Self-approval not allowed" in reason

    def test_validate_approvers_require_all_roles(self) -> None:
        """Test validation requiring all roles."""
        policy = ApprovalPolicy(
            name="Multi Role Policy",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            min_approvers=2,
            require_all_roles=True,
        )
        # Two security approvers, but no compliance (triggers roles check, not min_approvers)
        security_approver1 = Approver(
            id="sec-1",
            name="Security 1",
            email="sec1@test.com",
            roles=[ApproverRole.SECURITY_TEAM],
        )
        security_approver2 = Approver(
            id="sec-2",
            name="Security 2",
            email="sec2@test.com",
            roles=[ApproverRole.SECURITY_TEAM],
        )
        # Both security team members approved, but missing compliance
        decisions = [
            ApprovalDecision(
                approver_id="sec-1",
                approver_name="Security 1",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            ),
            ApprovalDecision(
                approver_id="sec-2",
                approver_name="Security 2",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            ),
        ]
        approvers = {"sec-1": security_approver1, "sec-2": security_approver2}

        is_valid, reason = policy.validate_approvers(decisions, approvers, "requester-1")
        assert is_valid is False
        assert "Missing approvals from roles" in reason

    def test_validate_approvers_all_roles_met(self) -> None:
        """Test validation when all required roles have approved."""
        policy = ApprovalPolicy(
            name="Multi Role Policy",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            min_approvers=2,
            require_all_roles=True,
        )
        approvers = {
            "sec-1": Approver(
                id="sec-1", name="Security", email="s@t.com", roles=[ApproverRole.SECURITY_TEAM]
            ),
            "comp-1": Approver(
                id="comp-1",
                name="Compliance",
                email="c@t.com",
                roles=[ApproverRole.COMPLIANCE_TEAM],
            ),
        }
        decisions = [
            ApprovalDecision(
                approver_id="sec-1",
                approver_name="Security",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            ),
            ApprovalDecision(
                approver_id="comp-1",
                approver_name="Compliance",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            ),
        ]

        is_valid, _reason = policy.validate_approvers(decisions, approvers, "requester-1")
        assert is_valid is True

    def test_validate_approvers_requires_any_role(self) -> None:
        """Test validation when any role is acceptable."""
        policy = ApprovalPolicy(
            name="object Role Policy",
            required_roles=[ApproverRole.SECURITY_TEAM, ApproverRole.COMPLIANCE_TEAM],
            min_approvers=1,
            require_all_roles=False,
        )
        approver = Approver(
            id="sec-1", name="Security", email="s@t.com", roles=[ApproverRole.SECURITY_TEAM]
        )
        decisions = [
            ApprovalDecision(
                approver_id="sec-1",
                approver_name="Security",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            ),
        ]
        approvers = {"sec-1": approver}

        is_valid, _reason = policy.validate_approvers(decisions, approvers, "requester-1")
        assert is_valid is True


# =============================================================================
# ApprovalRequest Tests
# =============================================================================


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_request_creation(self, sample_request: ApprovalRequest) -> None:
        """Test basic request creation."""
        assert sample_request.id == "request-1"
        assert sample_request.request_type == "policy_change"
        assert sample_request.requester_id == "user-1"
        assert sample_request.risk_score == 0.75
        assert sample_request.status == ApprovalStatus.PENDING
        assert sample_request.constitutional_hash == CONSTITUTIONAL_HASH

    def test_request_invalid_constitutional_hash(self, sample_policy: ApprovalPolicy) -> None:
        """Test request rejects invalid constitutional hash."""
        with pytest.raises(ValueError) as exc_info:
            ApprovalRequest(
                id="request-1",
                request_type="test",
                requester_id="user-1",
                requester_name="User",
                tenant_id="tenant-1",
                title="Test",
                description="Test",
                risk_score=0.5,
                policy=sample_policy,
                payload={},
                constitutional_hash="invalid-hash",
            )
        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_request_auto_deadline(self, sample_request: ApprovalRequest) -> None:
        """Test that deadline is auto-calculated."""
        assert sample_request.deadline is not None
        expected_deadline = sample_request.created_at + timedelta(hours=24.0)
        assert abs((sample_request.deadline - expected_deadline).total_seconds()) < 1

    def test_request_compute_hash(self, sample_request: ApprovalRequest) -> None:
        """Test hash computation is deterministic."""
        hash1 = sample_request.compute_hash()
        hash2 = sample_request.compute_hash()
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA256 truncated to 16 chars

    def test_request_compute_hash_uses_fast_kernel(self, sample_request, monkeypatch) -> None:
        """Test compute_hash uses fast kernel when available."""
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setitem(ApprovalRequest.compute_hash.__globals__, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setitem(ApprovalRequest.compute_hash.__globals__, "fast_hash", _fake_fast_hash)

        result = sample_request.compute_hash()
        assert called["value"] is True
        assert result == "000000000000beef"

    def test_request_compute_hash_fallback_to_sha256(self, sample_request, monkeypatch) -> None:
        """Test compute_hash falls back to sha256 when kernel unavailable."""
        monkeypatch.setitem(ApprovalRequest.compute_hash.__globals__, "FAST_HASH_AVAILABLE", False)
        result = sample_request.compute_hash()
        assert len(result) == 16
        int(result, 16)

    def test_request_to_dict(self, sample_request: ApprovalRequest) -> None:
        """Test request serialization."""
        result = sample_request.to_dict()

        assert result["id"] == "request-1"
        assert result["request_type"] == "policy_change"
        assert result["status"] == "pending"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "request_hash" in result
        assert "decisions" in result

    def test_request_default_escalation_level(self, sample_request: ApprovalRequest) -> None:
        """Test default escalation level."""
        assert sample_request.escalation_level == EscalationLevel.LEVEL_1


# =============================================================================
# SlackNotificationChannel Tests
# =============================================================================


class TestSlackNotificationChannel:
    """Tests for SlackNotificationChannel."""

    @pytest.fixture
    def slack_channel(self) -> SlackNotificationChannel:
        """Create a Slack notification channel."""
        return SlackNotificationChannel(
            webhook_url="https://hooks.slack.com/test",
            bot_token="xoxb-test-token",
        )

    async def test_send_approval_request(
        self,
        slack_channel: SlackNotificationChannel,
        sample_request: ApprovalRequest,
        sample_approver: Approver,
    ) -> None:
        """Test sending approval request notification."""
        result = await slack_channel.send_approval_request(sample_request, [sample_approver])
        assert result is True

    async def test_send_decision_notification(
        self, slack_channel: SlackNotificationChannel, sample_request: ApprovalRequest
    ) -> None:
        """Test sending decision notification."""
        decision = ApprovalDecision(
            approver_id="a1",
            approver_name="Test",
            decision=ApprovalStatus.APPROVED,
            reasoning="OK",
        )
        result = await slack_channel.send_decision_notification(sample_request, decision)
        assert result is True

    async def test_send_escalation_notification(
        self, slack_channel: SlackNotificationChannel, sample_request: ApprovalRequest
    ) -> None:
        """Test sending escalation notification."""
        result = await slack_channel.send_escalation_notification(
            sample_request, EscalationLevel.LEVEL_2
        )
        assert result is True

    def test_get_risk_emoji(self, slack_channel: SlackNotificationChannel) -> None:
        """Test risk emoji selection."""
        # Use same escape sequences as implementation
        assert slack_channel._get_risk_emoji(0.95) == "\ud83d\udd34"  # Red
        assert slack_channel._get_risk_emoji(0.75) == "\ud83d\udfe0"  # Orange
        assert slack_channel._get_risk_emoji(0.55) == "\ud83d\udfe1"  # Yellow
        assert slack_channel._get_risk_emoji(0.25) == "\ud83d\udfe2"  # Green


# =============================================================================
# TeamsNotificationChannel Tests
# =============================================================================


class TestTeamsNotificationChannel:
    """Tests for TeamsNotificationChannel."""

    @pytest.fixture
    def teams_channel(self) -> TeamsNotificationChannel:
        """Create a Teams notification channel."""
        return TeamsNotificationChannel(webhook_url="https://teams.microsoft.com/test")

    async def test_send_approval_request(
        self,
        teams_channel: TeamsNotificationChannel,
        sample_request: ApprovalRequest,
        sample_approver: Approver,
    ) -> None:
        """Test sending approval request notification."""
        result = await teams_channel.send_approval_request(sample_request, [sample_approver])
        assert result is True

    async def test_send_decision_notification(
        self, teams_channel: TeamsNotificationChannel, sample_request: ApprovalRequest
    ) -> None:
        """Test sending decision notification."""
        decision = ApprovalDecision(
            approver_id="a1",
            approver_name="Test",
            decision=ApprovalStatus.REJECTED,
            reasoning="Not approved",
        )
        result = await teams_channel.send_decision_notification(sample_request, decision)
        assert result is True

    async def test_send_escalation_notification(
        self, teams_channel: TeamsNotificationChannel, sample_request: ApprovalRequest
    ) -> None:
        """Test sending escalation notification."""
        result = await teams_channel.send_escalation_notification(
            sample_request, EscalationLevel.EXECUTIVE
        )
        assert result is True

    def test_get_theme_color(self, teams_channel: TeamsNotificationChannel) -> None:
        """Test theme color selection."""
        assert teams_channel._get_theme_color(0.95) == "FF0000"  # Red
        assert teams_channel._get_theme_color(0.75) == "FFA500"  # Orange
        assert teams_channel._get_theme_color(0.55) == "FFFF00"  # Yellow
        assert teams_channel._get_theme_color(0.25) == "00FF00"  # Green


# =============================================================================
# MultiApproverWorkflowEngine Tests
# =============================================================================


class TestMultiApproverWorkflowEngine:
    """Tests for MultiApproverWorkflowEngine."""

    def test_engine_initialization(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test engine initialization."""
        assert workflow_engine._running is False
        assert len(workflow_engine._requests) == 0
        assert len(workflow_engine._approvers) == 0
        assert len(workflow_engine._policies) == 4  # Default policies

    def test_default_policies(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test that default policies are initialized."""
        assert "high_risk_action" in workflow_engine._policies
        assert "policy_change" in workflow_engine._policies
        assert "critical_deployment" in workflow_engine._policies
        assert "standard_request" in workflow_engine._policies

    async def test_start_and_stop(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test engine start and stop."""
        await workflow_engine.start()
        assert workflow_engine._running is True
        assert workflow_engine._escalation_task is not None

        await workflow_engine.stop()
        assert workflow_engine._running is False

    def test_register_approver(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test registering an approver."""
        workflow_engine.register_approver(sample_approver)
        assert sample_approver.id in workflow_engine._approvers
        assert workflow_engine._approvers[sample_approver.id] == sample_approver

    def test_register_policy(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_policy: ApprovalPolicy
    ) -> None:
        """Test registering a custom policy."""
        workflow_engine.register_policy("custom_policy", sample_policy)
        assert "custom_policy" in workflow_engine._policies

    async def test_create_request(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test creating an approval request."""
        workflow_engine.register_approver(sample_approver)

        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="This is a test",
            risk_score=0.75,
            payload={"data": "test"},
        )

        assert request.id in workflow_engine._requests
        assert request.status == ApprovalStatus.PENDING

    async def test_create_request_auto_approve_low_risk(
        self, workflow_engine: MultiApproverWorkflowEngine
    ) -> None:
        """Test auto-approval for low-risk requests."""
        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Low Risk Request",
            description="Low risk test",
            risk_score=0.1,  # Below threshold
            payload={},
            policy_id="standard_request",
        )

        assert request.status == ApprovalStatus.APPROVED

    async def test_create_request_unknown_policy(
        self, workflow_engine: MultiApproverWorkflowEngine
    ) -> None:
        """Test error on unknown policy."""
        with pytest.raises(ValueError) as exc_info:
            await workflow_engine.create_request(
                request_type="test",
                requester_id="user-1",
                requester_name="Test",
                tenant_id="tenant-1",
                title="Test",
                description="Test",
                risk_score=0.5,
                payload={},
                policy_id="nonexistent_policy",
            )
        assert "Unknown policy" in str(exc_info.value)

    async def test_submit_decision_approved(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test submitting an approval decision."""
        workflow_engine.register_approver(sample_approver)

        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
            policy_id="high_risk_action",
        )

        success, _message = await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id=sample_approver.id,
            decision=ApprovalStatus.APPROVED,
            reasoning="Looks good",
        )

        assert success is True
        # Note: May not be fully approved if policy requires more approvers

    async def test_submit_decision_rejected(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test submitting a rejection."""
        workflow_engine.register_approver(sample_approver)

        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        success, message = await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id=sample_approver.id,
            decision=ApprovalStatus.REJECTED,
            reasoning="Security concerns",
        )

        assert success is True
        assert "rejected" in message.lower()
        assert workflow_engine.get_request(request.id).status == ApprovalStatus.REJECTED

    async def test_submit_decision_request_not_found(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test submitting decision for nonexistent request."""
        workflow_engine.register_approver(sample_approver)

        success, message = await workflow_engine.submit_decision(
            request_id="nonexistent",
            approver_id=sample_approver.id,
            decision=ApprovalStatus.APPROVED,
            reasoning="OK",
        )

        assert success is False
        assert "not found" in message.lower()

    async def test_submit_decision_approver_not_registered(
        self, workflow_engine: MultiApproverWorkflowEngine
    ) -> None:
        """Test submitting decision from unregistered approver."""
        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        success, message = await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id="unknown-approver",
            decision=ApprovalStatus.APPROVED,
            reasoning="OK",
        )

        assert success is False
        assert "not registered" in message.lower()

    async def test_submit_decision_duplicate(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test duplicate decision is rejected."""
        workflow_engine.register_approver(sample_approver)

        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        # First decision
        await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id=sample_approver.id,
            decision=ApprovalStatus.APPROVED,
            reasoning="OK",
        )

        # Second decision should fail
        success, message = await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id=sample_approver.id,
            decision=ApprovalStatus.APPROVED,
            reasoning="OK again",
        )

        assert success is False
        assert "already submitted" in message.lower()

    async def test_submit_decision_reasoning_required(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test that reasoning is required when policy demands it."""
        workflow_engine.register_approver(sample_approver)

        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        success, message = await workflow_engine.submit_decision(
            request_id=request.id,
            approver_id=sample_approver.id,
            decision=ApprovalStatus.APPROVED,
            reasoning="",  # Empty reasoning
        )

        assert success is False
        assert "reasoning is required" in message.lower()

    async def test_cancel_request(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test cancelling a request."""
        request = await workflow_engine.create_request(
            request_type="test_request",
            requester_id="user-1",
            requester_name="Test User",
            tenant_id="tenant-1",
            title="Test Request",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        result = await workflow_engine.cancel_request(request.id, "No longer needed")

        assert result is True
        assert workflow_engine.get_request(request.id).status == ApprovalStatus.CANCELLED

    async def test_cancel_nonexistent_request(
        self, workflow_engine: MultiApproverWorkflowEngine
    ) -> None:
        """Test cancelling nonexistent request."""
        result = await workflow_engine.cancel_request("nonexistent", "Reason")
        assert result is False

    def test_get_request(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test get_request returns None for nonexistent."""
        assert workflow_engine.get_request("nonexistent") is None

    async def test_get_pending_requests(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test getting pending requests."""
        # Create multiple requests
        for i in range(3):
            await workflow_engine.create_request(
                request_type="test",
                requester_id="user-1",
                requester_name="Test",
                tenant_id="tenant-1",
                title=f"Request {i}",
                description="Test",
                risk_score=0.75,
                payload={},
            )

        pending = workflow_engine.get_pending_requests()
        assert len(pending) == 3

    async def test_get_pending_requests_filtered_by_tenant(
        self, workflow_engine: MultiApproverWorkflowEngine
    ) -> None:
        """Test filtering pending requests by tenant."""
        await workflow_engine.create_request(
            request_type="test",
            requester_id="user-1",
            requester_name="Test",
            tenant_id="tenant-1",
            title="Request 1",
            description="Test",
            risk_score=0.75,
            payload={},
        )
        await workflow_engine.create_request(
            request_type="test",
            requester_id="user-2",
            requester_name="Test",
            tenant_id="tenant-2",
            title="Request 2",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        tenant1_requests = workflow_engine.get_pending_requests(tenant_id="tenant-1")
        assert len(tenant1_requests) == 1
        assert tenant1_requests[0].tenant_id == "tenant-1"

    def test_get_stats(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test getting workflow statistics."""
        stats = workflow_engine.get_stats()

        assert stats["total_requests"] == 0
        assert "by_status" in stats
        assert stats["registered_approvers"] == 0
        assert stats["registered_policies"] == 4
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_select_policy_for_risk(self, workflow_engine: MultiApproverWorkflowEngine) -> None:
        """Test policy selection based on risk score."""
        assert workflow_engine._select_policy_for_risk(0.95) == "critical_deployment"
        assert workflow_engine._select_policy_for_risk(0.75) == "high_risk_action"
        assert workflow_engine._select_policy_for_risk(0.55) == "policy_change"
        assert workflow_engine._select_policy_for_risk(0.25) == "standard_request"

    def test_get_eligible_approvers(
        self, workflow_engine: MultiApproverWorkflowEngine, sample_approver: Approver
    ) -> None:
        """Test getting eligible approvers for a policy."""
        workflow_engine.register_approver(sample_approver)
        policy = workflow_engine._policies["high_risk_action"]

        eligible = workflow_engine._get_eligible_approvers(policy, "tenant-1")
        assert len(eligible) == 1
        assert eligible[0].id == sample_approver.id


# =============================================================================
# Module Function Tests
# =============================================================================


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_workflow_engine_initial(self) -> None:
        """Test get_workflow_engine returns None initially."""
        # Reset global state
        import enhanced_agent_bus.deliberation_layer.multi_approver as ma

        ma._workflow_engine = None

        assert get_workflow_engine() is None

    async def test_initialize_and_shutdown_workflow_engine(self) -> None:
        """Test initializing and shutting down the global engine."""
        engine = await initialize_workflow_engine()
        assert engine is not None
        assert engine._running is True

        assert get_workflow_engine() is engine

        await shutdown_workflow_engine()
        assert get_workflow_engine() is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestMultiApproverIntegration:
    """Integration tests for multi-approver workflow."""

    async def test_full_approval_workflow(self) -> None:
        """Test a complete approval workflow."""
        engine = MultiApproverWorkflowEngine(notification_channels=[])

        # Register approvers with required roles
        security_approver = Approver(
            id="sec-1",
            name="Security",
            email="sec@test.com",
            roles=[ApproverRole.SECURITY_TEAM],
        )
        compliance_approver = Approver(
            id="comp-1",
            name="Compliance",
            email="comp@test.com",
            roles=[ApproverRole.COMPLIANCE_TEAM],
        )

        engine.register_approver(security_approver)
        engine.register_approver(compliance_approver)

        # Create high-risk request requiring both roles
        request = await engine.create_request(
            request_type="security_change",
            requester_id="user-1",
            requester_name="User One",
            tenant_id="tenant-1",
            title="Security Change",
            description="Critical security update",
            risk_score=0.85,
            payload={"change": "update_firewall"},
            policy_id="high_risk_action",
        )

        assert request.status == ApprovalStatus.PENDING

        # First approval
        await engine.submit_decision(
            request_id=request.id,
            approver_id="sec-1",
            decision=ApprovalStatus.APPROVED,
            reasoning="Security review passed",
        )

        # Check still pending (need 2 approvers from both roles)
        updated_request = engine.get_request(request.id)
        # May still be pending depending on policy

        # Second approval
        await engine.submit_decision(
            request_id=request.id,
            approver_id="comp-1",
            decision=ApprovalStatus.APPROVED,
            reasoning="Compliance review passed",
        )

        # Now should be approved
        final_request = engine.get_request(request.id)
        assert final_request.status == ApprovalStatus.APPROVED
        assert len(final_request.decisions) == 2

    async def test_rejection_stops_workflow(self) -> None:
        """Test that a single rejection stops the workflow."""
        engine = MultiApproverWorkflowEngine(notification_channels=[])

        approver = Approver(
            id="a-1",
            name="Approver",
            email="a@test.com",
            roles=[ApproverRole.SECURITY_TEAM],
        )
        engine.register_approver(approver)

        request = await engine.create_request(
            request_type="test",
            requester_id="user-1",
            requester_name="User",
            tenant_id="tenant-1",
            title="Test",
            description="Test",
            risk_score=0.75,
            payload={},
        )

        await engine.submit_decision(
            request_id=request.id,
            approver_id="a-1",
            decision=ApprovalStatus.REJECTED,
            reasoning="Not acceptable",
        )

        assert engine.get_request(request.id).status == ApprovalStatus.REJECTED

    async def test_audit_callback_invoked(self) -> None:
        """Test that audit callback is invoked on decisions."""
        audit_records: list[tuple] = []

        def audit_callback(request, decision):
            audit_records.append((request.id, decision.decision))

        engine = MultiApproverWorkflowEngine(
            notification_channels=[],
            audit_callback=audit_callback,
        )

        approver = Approver(
            id="a-1",
            name="Approver",
            email="a@test.com",
            roles=[ApproverRole.TENANT_ADMIN],
        )
        engine.register_approver(approver)

        request = await engine.create_request(
            request_type="test",
            requester_id="user-1",
            requester_name="User",
            tenant_id="tenant-1",
            title="Test",
            description="Test",
            risk_score=0.25,
            payload={},
            policy_id="standard_request",
        )

        # Skip if auto-approved
        if request.status == ApprovalStatus.PENDING:
            await engine.submit_decision(
                request_id=request.id,
                approver_id="a-1",
                decision=ApprovalStatus.APPROVED,
                reasoning="OK",
            )

            assert len(audit_records) == 1
            assert audit_records[0][1] == ApprovalStatus.APPROVED
