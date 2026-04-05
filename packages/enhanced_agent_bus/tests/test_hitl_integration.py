"""
Tests for enhanced_agent_bus.constitutional.hitl_integration
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.constitutional.hitl_integration import (
    ApprovalChainConfig,
    ApprovalPriority,
    ConstitutionalHITLIntegration,
    HITLApprovalRequest,
    NotificationChannel,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_notification_channels(self):
        assert NotificationChannel.SLACK.value == "slack"
        assert NotificationChannel.PAGERDUTY.value == "pagerduty"
        assert NotificationChannel.TEAMS.value == "teams"

    def test_approval_priorities(self):
        assert ApprovalPriority.LOW.value == "low"
        assert ApprovalPriority.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# ApprovalChainConfig
# ---------------------------------------------------------------------------


class TestApprovalChainConfig:
    def test_default_notification_channels(self):
        config = ApprovalChainConfig(
            chain_id="test",
            name="Test",
            description="desc",
            priority=ApprovalPriority.LOW,
            required_approvals=1,
            timeout_minutes=30,
        )
        assert config.notification_channels == [NotificationChannel.SLACK]

    def test_custom_notification_channels(self):
        config = ApprovalChainConfig(
            chain_id="test",
            name="Test",
            description="desc",
            priority=ApprovalPriority.HIGH,
            required_approvals=2,
            timeout_minutes=60,
            notification_channels=[NotificationChannel.TEAMS],
        )
        assert config.notification_channels == [NotificationChannel.TEAMS]


# ---------------------------------------------------------------------------
# HITLApprovalRequest
# ---------------------------------------------------------------------------


class TestHITLApprovalRequest:
    def test_default_created_at(self):
        req = HITLApprovalRequest(
            request_id="r1",
            proposal_id="p1",
            chain_config=ApprovalChainConfig(
                chain_id="c1",
                name="C1",
                description="d",
                priority=ApprovalPriority.STANDARD,
                required_approvals=1,
                timeout_minutes=30,
            ),
            title="test",
            description="desc",
            context={},
            approval_url="http://example.com",
        )
        assert req.created_at is not None
        assert req.status == "pending"


# ---------------------------------------------------------------------------
# ConstitutionalHITLIntegration
# ---------------------------------------------------------------------------


def _make_integration(
    storage=None,
    hitl_url=None,
    notification_config=None,
    enable_notifications=False,
):
    storage = storage or MagicMock()
    return ConstitutionalHITLIntegration(
        storage=storage,
        hitl_service_url=hitl_url or "http://hitl.test:8002",
        notification_config=notification_config or {},
        enable_notifications=enable_notifications,
    )


class TestHITLIntegrationInit:
    def test_default_url(self):
        integration = _make_integration()
        assert integration.hitl_service_url == "http://hitl.test:8002"

    def test_approval_chains_initialized(self):
        integration = _make_integration()
        assert integration.high_impact_chain.required_approvals == 3
        assert integration.medium_impact_chain.required_approvals == 2
        assert integration.low_impact_chain.required_approvals == 1


class TestDetermineApprovalChain:
    def test_high_impact(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.impact_score = 0.9
        chain = integration._determine_approval_chain(proposal)
        assert chain.chain_id == "constitutional_high_impact"

    def test_medium_impact(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.impact_score = 0.6
        chain = integration._determine_approval_chain(proposal)
        assert chain.chain_id == "constitutional_medium_impact"

    def test_low_impact(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.impact_score = 0.3
        chain = integration._determine_approval_chain(proposal)
        assert chain.chain_id == "constitutional_low_impact"

    def test_none_impact_defaults_to_medium(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.impact_score = None
        chain = integration._determine_approval_chain(proposal)
        assert chain.chain_id == "constitutional_medium_impact"


class TestGenerateApprovalUrl:
    def test_default_base_url(self):
        integration = _make_integration()
        url = integration._generate_approval_url("prop_123")
        assert url == "http://hitl.test:8002/ui/approvals/constitutional/prop_123"

    def test_custom_base_url(self):
        integration = _make_integration()
        url = integration._generate_approval_url("prop_123", "https://custom.ui")
        assert url == "https://custom.ui/approvals/constitutional/prop_123"


class TestFormatImpactFactors:
    def test_empty_factors(self):
        integration = _make_integration()
        assert integration._format_impact_factors({}) == "N/A"

    def test_with_factors(self):
        integration = _make_integration()
        result = integration._format_impact_factors({"semantic": 0.5, "scope": 0.3})
        assert "semantic" in result
        assert "scope" in result


class TestFormatApprovalDescription:
    def test_high_impact_label(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.high_impact = True
        proposal.medium_impact = False
        proposal.justification = "Security fix needed"
        proposal.target_version = "1.0.0"
        proposal.new_version = "1.1.0"
        proposal.impact_score = 0.9
        proposal.requires_deliberation = True
        proposal.impact_factors = {"severity": 0.9}
        proposal.impact_recommendation = "Requires multi-approver"

        desc = integration._format_approval_description(proposal)
        assert "High" in desc
        assert "Security fix" in desc

    def test_low_impact_label(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.high_impact = False
        proposal.medium_impact = False
        proposal.justification = "Minor update to docs"
        proposal.target_version = "1.0.0"
        proposal.new_version = "1.0.1"
        proposal.impact_score = 0.2
        proposal.requires_deliberation = False
        proposal.impact_factors = {}
        proposal.impact_recommendation = None

        desc = integration._format_approval_description(proposal)
        assert "Low" in desc


class TestCreateApprovalRequest:
    @pytest.mark.asyncio
    async def test_invalid_proposal_status_raises(self):
        integration = _make_integration()
        proposal = MagicMock()
        proposal.is_proposed = False
        proposal.is_under_review = False
        proposal.status = "rejected"
        proposal.proposal_id = "p1"

        with pytest.raises(ValueError, match="cannot be submitted"):
            await integration.create_approval_request(proposal)

    @pytest.mark.asyncio
    async def test_successful_approval_request(self):
        storage = AsyncMock()
        integration = _make_integration(storage=storage, enable_notifications=False)
        integration._submit_to_hitl_service = AsyncMock(return_value={"request_id": "req_123"})

        proposal = MagicMock()
        proposal.is_proposed = True
        proposal.is_under_review = False
        proposal.proposal_id = "p1"
        proposal.impact_score = 0.6
        proposal.proposer_agent_id = "agent_1"
        proposal.metadata = {}
        proposal.new_version = "1.1.0"
        proposal.target_version = "1.0.0"
        proposal.high_impact = False
        proposal.medium_impact = True
        proposal.justification = "Important update"
        proposal.requires_deliberation = False
        proposal.impact_factors = {}
        proposal.impact_recommendation = "Review recommended"
        proposal.proposed_changes = {"x": 1}

        result = await integration.create_approval_request(proposal)

        assert result.request_id == "req_123"
        assert result.proposal_id == "p1"
        proposal.submit_for_review.assert_called_once()
        storage.save_amendment.assert_called_once()


class TestCheckApprovalStatus:
    @pytest.mark.asyncio
    async def test_returns_status_on_success(self):
        integration = _make_integration()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "approved"}
        mock_response.raise_for_status = MagicMock()
        integration.http_client = AsyncMock()
        integration.http_client.get = AsyncMock(return_value=mock_response)

        result = await integration.check_approval_status("req_1")
        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        integration = _make_integration()
        integration.http_client = AsyncMock()
        integration.http_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))

        result = await integration.check_approval_status("req_1")
        assert result is None


class TestProcessApprovalDecision:
    @pytest.mark.asyncio
    async def test_approved(self):
        storage = AsyncMock()
        proposal = MagicMock()
        storage.get_amendment = AsyncMock(return_value=proposal)

        integration = _make_integration(storage=storage)
        integration.check_approval_status = AsyncMock(
            return_value={"status": "approved", "approved_by": "human_1"}
        )

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is True
        proposal.approve.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejected(self):
        storage = AsyncMock()
        proposal = MagicMock()
        storage.get_amendment = AsyncMock(return_value=proposal)

        integration = _make_integration(storage=storage)
        integration.check_approval_status = AsyncMock(
            return_value={
                "status": "rejected",
                "rejected_by": "human_1",
                "rejection_reason": "Not needed",
            }
        )

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is False
        proposal.reject.assert_called_once()

    @pytest.mark.asyncio
    async def test_timed_out(self):
        storage = AsyncMock()
        proposal = MagicMock()
        proposal.metadata = {}
        storage.get_amendment = AsyncMock(return_value=proposal)

        integration = _make_integration(storage=storage)
        integration.check_approval_status = AsyncMock(return_value={"status": "timed_out"})

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is False
        assert proposal.metadata["hitl_timeout"] is True

    @pytest.mark.asyncio
    async def test_no_status_data(self):
        integration = _make_integration()
        integration.check_approval_status = AsyncMock(return_value=None)

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_proposal_not_found(self):
        storage = AsyncMock()
        storage.get_amendment = AsyncMock(return_value=None)

        integration = _make_integration(storage=storage)
        integration.check_approval_status = AsyncMock(return_value={"status": "approved"})

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_pending_returns_false(self):
        storage = AsyncMock()
        proposal = MagicMock()
        storage.get_amendment = AsyncMock(return_value=proposal)

        integration = _make_integration(storage=storage)
        integration.check_approval_status = AsyncMock(return_value={"status": "pending"})

        result = await integration.process_approval_decision("req_1", "prop_1")
        assert result is False


class TestNotifications:
    @pytest.mark.asyncio
    async def test_slack_without_webhook_returns_false(self):
        integration = _make_integration(notification_config={})
        result = await integration._send_slack_notification(
            {
                "request_id": "r1",
                "title": "t",
                "message": "m",
                "priority": "high",
                "approval_url": "http://x",
                "metadata": {"impact_score": 0.5, "proposal_id": "p1"},
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_pagerduty_without_key_returns_false(self):
        integration = _make_integration(notification_config={})
        result = await integration._send_pagerduty_notification(
            {
                "request_id": "r1",
                "title": "t",
                "message": "m",
                "priority": "high",
                "approval_url": "http://x",
                "metadata": {"impact_score": 0.5, "proposal_id": "p1"},
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_teams_without_webhook_returns_false(self):
        integration = _make_integration(notification_config={})
        result = await integration._send_teams_notification(
            {
                "request_id": "r1",
                "title": "t",
                "message": "m",
                "priority": "high",
                "approval_url": "http://x",
                "metadata": {"impact_score": 0.5, "proposal_id": "p1"},
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_unknown_channel_returns_false(self):
        integration = _make_integration()
        result = await integration._send_to_channel(
            MagicMock(value="unknown"),
            {"request_id": "r1"},
        )
        assert result is False


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self):
        integration = _make_integration()
        integration.http_client = AsyncMock()
        await integration.close()
        integration.http_client.aclose.assert_called_once()
