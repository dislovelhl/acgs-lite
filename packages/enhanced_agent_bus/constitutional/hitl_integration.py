"""
ACGS-2 Enhanced Agent Bus - HITL Integration for Constitutional Amendments
Constitutional Hash: 608508a9bd224290

Integrates constitutional amendment proposals with HITL (Human-In-The-Loop)
approval chains, supporting multi-approver workflows, notifications, and
timeout escalation.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from enum import Enum

import httpx

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .amendment_model import AmendmentProposal
from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]

logger = get_logger(__name__)
_HITL_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    httpx.HTTPError,
)


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    TEAMS = "teams"


class ApprovalPriority(str, Enum):
    """Approval priority levels for HITL requests."""

    LOW = "low"
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalChainConfig:
    """Configuration for an approval chain.

    Constitutional Hash: 608508a9bd224290
    """

    chain_id: str
    name: str
    description: str
    priority: ApprovalPriority
    required_approvals: int
    timeout_minutes: int
    escalation_enabled: bool = True
    notification_channels: list[NotificationChannel] = None

    def __post_init__(self):
        if self.notification_channels is None:
            self.notification_channels = [NotificationChannel.SLACK]


@dataclass
class HITLApprovalRequest:
    """HITL approval request for constitutional amendments.

    Constitutional Hash: 608508a9bd224290
    """

    request_id: str
    proposal_id: str
    chain_config: ApprovalChainConfig
    title: str
    description: str
    context: JSONDict
    approval_url: str
    status: str = "pending"
    created_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


class ConstitutionalHITLIntegration:
    """Integration service for constitutional amendments with HITL approval chains.

    This service:
    - Creates approval requests in HITL service for constitutional amendments
    - Configures multi-approver chains for high-impact amendments (impact >= 0.8)
    - Configures single approver for low-impact amendments (impact < 0.5)
    - Sends notifications via Slack/PagerDuty/Teams
    - Handles timeout escalation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        storage: ConstitutionalStorageService,
        hitl_service_url: str | None = None,
        notification_config: JSONDict | None = None,
        enable_notifications: bool = True,
    ):
        """Initialize HITL integration service.

        Args:
            storage: ConstitutionalStorageService instance
            hitl_service_url: URL of HITL approvals service (default: http://localhost:8002)
            notification_config: Configuration for notification providers
            enable_notifications: Whether to send notifications
        """
        self.storage = storage
        self.hitl_service_url = hitl_service_url or "http://localhost:8002"
        self.notification_config = notification_config or {}
        self.enable_notifications = enable_notifications
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        # Default approval chain configurations
        self._init_approval_chains()

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] ConstitutionalHITLIntegration initialized "
            f"(HITL URL: {self.hitl_service_url}, Notifications: {self.enable_notifications})"
        )

    def _init_approval_chains(self):
        """Initialize default approval chain configurations."""
        # High-impact amendments (>= 0.8): Multi-approver chain
        self.high_impact_chain = ApprovalChainConfig(
            chain_id="constitutional_high_impact",
            name="Constitutional Amendment - High Impact",
            description="Multi-approver chain for high-impact constitutional amendments",
            priority=ApprovalPriority.CRITICAL,
            required_approvals=3,  # Requires 3 approvals
            timeout_minutes=120,  # 2 hours per step
            escalation_enabled=True,
            notification_channels=[
                NotificationChannel.SLACK,
                NotificationChannel.PAGERDUTY,
            ],
        )

        # Medium-impact amendments (0.5-0.8): Standard chain
        self.medium_impact_chain = ApprovalChainConfig(
            chain_id="constitutional_medium_impact",
            name="Constitutional Amendment - Medium Impact",
            description="Standard approval chain for medium-impact amendments",
            priority=ApprovalPriority.HIGH,
            required_approvals=2,  # Requires 2 approvals
            timeout_minutes=60,  # 1 hour per step
            escalation_enabled=True,
            notification_channels=[NotificationChannel.SLACK],
        )

        # Low-impact amendments (< 0.5): Single approver
        self.low_impact_chain = ApprovalChainConfig(
            chain_id="constitutional_low_impact",
            name="Constitutional Amendment - Low Impact",
            description="Single approver for low-impact constitutional amendments",
            priority=ApprovalPriority.STANDARD,
            required_approvals=1,  # Single approver
            timeout_minutes=30,  # 30 minutes
            escalation_enabled=True,
            notification_channels=[NotificationChannel.SLACK],
        )

    async def create_approval_request(
        self, proposal: AmendmentProposal, approval_url_base: str | None = None
    ) -> HITLApprovalRequest:
        """Create HITL approval request for constitutional amendment.

        This method:
        1. Determines appropriate approval chain based on impact score
        2. Creates approval request in HITL service
        3. Sends notifications to configured channels
        4. Returns approval request details

        Args:
            proposal: AmendmentProposal to create approval request for
            approval_url_base: Base URL for approval web interface

        Returns:
            HITLApprovalRequest with request details

        Raises:
            ValueError: If proposal is not in valid state
            httpx.HTTPError: If HITL service communication fails
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Creating HITL approval request for "
            f"proposal {proposal.proposal_id}"
        )

        # Validate proposal status
        if not proposal.is_proposed and not proposal.is_under_review:
            raise ValueError(
                f"Proposal {proposal.proposal_id} cannot be submitted for HITL approval "
                f"(current status: {proposal.status})"
            )

        # Determine approval chain based on impact score
        chain_config = self._determine_approval_chain(proposal)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Selected approval chain: {chain_config.chain_id} "
            f"(impact_score={proposal.impact_score})"
        )

        # Generate approval URL
        approval_url = self._generate_approval_url(proposal.proposal_id, approval_url_base)

        # Create HITL approval request payload
        hitl_request_payload = {
            "decision_id": proposal.proposal_id,
            "tenant_id": proposal.metadata.get("tenant_id", "default"),
            "requested_by": proposal.proposer_agent_id,
            "title": f"Constitutional Amendment: {proposal.new_version or 'TBD'}",
            "description": self._format_approval_description(proposal),
            "priority": chain_config.priority.value,
            "context": {
                "proposal_id": proposal.proposal_id,
                "target_version": proposal.target_version,
                "new_version": proposal.new_version,
                "impact_score": proposal.impact_score,
                "requires_deliberation": proposal.requires_deliberation,
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "proposed_changes": proposal.proposed_changes,
                "justification": proposal.justification,
                "approval_url": approval_url,
            },
            "chain_id": chain_config.chain_id,
        }

        # Submit to HITL service
        try:
            response = await self._submit_to_hitl_service(hitl_request_payload)
            request_id = response.get("request_id")

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Created HITL approval request: "
                f"{request_id} for proposal {proposal.proposal_id}"
            )

        except _HITL_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to create HITL approval request: {e}")
            raise

        # Create approval request object
        approval_request = HITLApprovalRequest(
            request_id=request_id,
            proposal_id=proposal.proposal_id,
            chain_config=chain_config,
            title=hitl_request_payload["title"],
            description=hitl_request_payload["description"],
            context=hitl_request_payload["context"],
            approval_url=approval_url,
        )

        # Update proposal status to UNDER_REVIEW
        if proposal.is_proposed:
            proposal.submit_for_review()
            await self.storage.save_amendment(proposal)

        # Send notifications
        if self.enable_notifications:
            await self._send_notifications(approval_request, proposal)

        return approval_request

    async def check_approval_status(self, request_id: str) -> JSONDict | None:
        """Check the status of an HITL approval request.

        Args:
            request_id: HITL approval request ID

        Returns:
            dict with approval status, or None if not found
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Checking HITL approval status for request {request_id}"
        )

        try:
            url = f"{self.hitl_service_url}/api/v1/approvals/{request_id}"
            response = await self.http_client.get(url)
            response.raise_for_status()

            status_data = response.json()
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Approval request {request_id} status: "
                f"{status_data.get('status')}"
            )

            return status_data

        except httpx.HTTPError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to check approval status: {e}")
            return None

    async def process_approval_decision(self, request_id: str, proposal_id: str) -> bool:
        """Process approval decision from HITL service.

        This method checks the HITL approval status and updates the
        amendment proposal accordingly.

        Args:
            request_id: HITL approval request ID
            proposal_id: Amendment proposal ID

        Returns:
            True if proposal was approved, False otherwise
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Processing approval decision for "
            f"request {request_id}, proposal {proposal_id}"
        )

        # Check approval status
        status_data = await self.check_approval_status(request_id)
        if not status_data:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] No status data for request {request_id}")
            return False

        # Get proposal
        proposal = await self.storage.get_amendment(proposal_id)
        if not proposal:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Proposal {proposal_id} not found")
            return False

        # Process based on status
        hitl_status = status_data.get("status")

        if hitl_status == "approved":
            # Approve proposal
            approver_id = status_data.get("approved_by", "hitl_system")
            proposal.approve(approver_id=approver_id, approver_role="judicial")
            await self.storage.save_amendment(proposal)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Proposal {proposal_id} approved "
                f"via HITL request {request_id}"
            )
            return True

        elif hitl_status == "rejected":
            # Reject proposal
            reviewer_id = status_data.get("rejected_by", "hitl_system")
            reason = status_data.get("rejection_reason", "Rejected via HITL approval")
            proposal.reject(reviewer_id=reviewer_id, reason=reason, reviewer_role="judicial")
            await self.storage.save_amendment(proposal)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Proposal {proposal_id} rejected "
                f"via HITL request {request_id}"
            )
            return False

        elif hitl_status == "timed_out":
            # Handle timeout
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] HITL approval request {request_id} "
                f"timed out for proposal {proposal_id}"
            )
            # Optionally update proposal metadata
            proposal.metadata["hitl_timeout"] = True
            await self.storage.save_amendment(proposal)
            return False

        else:
            # Still pending or other status
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] HITL approval request {request_id} "
                f"still pending (status: {hitl_status})"
            )
            return False

    def _determine_approval_chain(self, proposal: AmendmentProposal) -> ApprovalChainConfig:
        """Determine appropriate approval chain based on impact score.

        Args:
            proposal: AmendmentProposal to evaluate

        Returns:
            ApprovalChainConfig for the appropriate chain
        """
        impact_score = proposal.impact_score or 0.5  # Default to medium

        if impact_score >= 0.8:
            # High impact - multi-approver chain
            return self.high_impact_chain  # type: ignore[no-any-return]
        elif impact_score >= 0.5:
            # Medium impact - standard chain
            return self.medium_impact_chain  # type: ignore[no-any-return]
        else:
            # Low impact - single approver
            return self.low_impact_chain  # type: ignore[no-any-return]

    def _format_approval_description(self, proposal: AmendmentProposal) -> str:
        """Format approval description for HITL request.

        Args:
            proposal: AmendmentProposal to format

        Returns:
            Formatted description string
        """
        impact_level = (
            "High" if proposal.high_impact else ("Medium" if proposal.medium_impact else "Low")
        )

        description = f"""
**Constitutional Amendment Proposal**

**Justification:** {proposal.justification}

**Target Version:** {proposal.target_version}
**New Version:** {proposal.new_version or "TBD"}
**Impact Level:** {impact_level} (Score: {proposal.impact_score:.3f})
**Requires Deliberation:** {"Yes" if proposal.requires_deliberation else "No"}

**Impact Factors:**
{self._format_impact_factors(proposal.impact_factors)}

**Recommendation:** {proposal.impact_recommendation or "N/A"}

**Constitutional Hash:** {CONSTITUTIONAL_HASH}
        """.strip()

        return description

    def _format_impact_factors(self, impact_factors: dict[str, float]) -> str:
        """Format impact factors for display.

        Args:
            impact_factors: dict of impact factor names to scores

        Returns:
            Formatted string
        """
        if not impact_factors:
            return "N/A"

        lines = []
        for factor, score in impact_factors.items():
            lines.append(f"- {factor}: {score:.3f}")

        return "\n".join(lines)

    def _generate_approval_url(self, proposal_id: str, base_url: str | None = None) -> str:
        """Generate approval URL for web interface.

        Args:
            proposal_id: Amendment proposal ID
            base_url: Base URL for approval interface

        Returns:
            Full approval URL
        """
        base = base_url or f"{self.hitl_service_url}/ui"
        return f"{base}/approvals/constitutional/{proposal_id}"

    async def _submit_to_hitl_service(self, payload: JSONDict) -> JSONDict:
        """Submit approval request to HITL service.

        Args:
            payload: Request payload

        Returns:
            Response from HITL service with request_id

        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.hitl_service_url}/api/v1/approvals"

        try:
            response = await self.http_client.post(
                url, json=payload, headers={"Content-type": "application/json"}
            )
            response.raise_for_status()

            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] HITL service request failed: {e}")
            raise

    async def _send_notifications(
        self, approval_request: HITLApprovalRequest, proposal: AmendmentProposal
    ) -> dict[str, bool]:
        """Send notifications for approval request.

        Args:
            approval_request: HITLApprovalRequest to notify about
            proposal: AmendmentProposal for context

        Returns:
            dict mapping channel names to success status
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Sending notifications for approval "
            f"request {approval_request.request_id}"
        )

        results = {}

        # Get configured notification channels
        channels = approval_request.chain_config.notification_channels

        # Prepare notification payload
        notification_payload = {
            "request_id": approval_request.request_id,
            "title": approval_request.title,
            "message": self._format_notification_message(proposal),
            "priority": approval_request.chain_config.priority.value,
            "approval_url": approval_request.approval_url,
            "metadata": {
                "proposal_id": proposal.proposal_id,
                "impact_score": proposal.impact_score,
                "target_version": proposal.target_version,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        }

        # Send to each configured channel
        for channel in channels:
            try:
                success = await self._send_to_channel(channel, notification_payload)
                results[channel.value] = success

            except _HITL_OPERATION_ERRORS as e:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Failed to send notification via {channel.value}: {e}"
                )
                results[channel.value] = False

        return results

    def _format_notification_message(self, proposal: AmendmentProposal) -> str:
        """Format notification message.

        Args:
            proposal: AmendmentProposal to format

        Returns:
            Formatted message string
        """
        impact_level = (
            "🔴 High"
            if proposal.high_impact
            else ("🟡 Medium" if proposal.medium_impact else "🟢 Low")
        )

        message = f"""
A new constitutional amendment requires your approval.

**Impact:** {impact_level} (Score: {proposal.impact_score:.3f})
**Version:** {proposal.target_version} → {proposal.new_version or "TBD"}
**Justification:** {proposal.justification[:200]}...

Please review and approve/reject this amendment.
        """.strip()

        return message

    async def _send_to_channel(self, channel: NotificationChannel, payload: JSONDict) -> bool:
        """Send notification to specific channel.

        Args:
            channel: NotificationChannel to send to
            payload: Notification payload

        Returns:
            True if successful, False otherwise
        """
        # In a real implementation, this would integrate with actual
        # notification providers (Slack, PagerDuty, Teams).
        # For now, we'll simulate the notification.

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Sending notification to {channel.value} "
            f"for request {payload['request_id']}"
        )

        try:
            # Simulate notification send
            # In production, this would call the actual notification service API
            if channel == NotificationChannel.SLACK:
                return await self._send_slack_notification(payload)
            elif channel == NotificationChannel.PAGERDUTY:
                return await self._send_pagerduty_notification(payload)
            elif channel == NotificationChannel.TEAMS:
                return await self._send_teams_notification(payload)
            else:
                logger.warning(f"[{CONSTITUTIONAL_HASH}] Unknown notification channel: {channel}")
                return False

        except _HITL_OPERATION_ERRORS as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Notification send failed for channel {channel.value}: {e}"
            )
            return False

    async def _send_slack_notification(self, payload: JSONDict) -> bool:
        """Send Slack notification.

        Args:
            payload: Notification payload

        Returns:
            True if successful
        """
        webhook_url = self.notification_config.get("slack", {}).get("webhook_url")

        if not webhook_url:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Slack webhook URL not configured")
            return False

        try:
            slack_payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🏛️ {payload['title']}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": payload["message"]},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Priority:* {payload['priority'].upper()}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Impact:* {payload['metadata']['impact_score']:.3f}",
                            },
                        ],
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Review Amendment",
                                },
                                "style": "primary",
                                "url": payload["approval_url"],
                            }
                        ],
                    },
                ],
            }

            response = await self.http_client.post(webhook_url, json=slack_payload)
            response.raise_for_status()

            logger.info(f"[{CONSTITUTIONAL_HASH}] Slack notification sent successfully")
            return True

        except _HITL_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Slack notification failed: {e}")
            return False

    async def _send_pagerduty_notification(self, payload: JSONDict) -> bool:
        """Send PagerDuty notification.

        Args:
            payload: Notification payload

        Returns:
            True if successful
        """
        integration_key = self.notification_config.get("pagerduty", {}).get("integration_key")

        if not integration_key:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] PagerDuty integration key not configured")
            return False

        try:
            # PagerDuty Events API v2
            pd_payload = {
                "routing_key": integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": payload["title"],
                    "severity": ("critical" if payload["priority"] == "critical" else "warning"),
                    "source": "ACGS-2 Constitutional Amendments",
                    "custom_details": {
                        "proposal_id": payload["metadata"]["proposal_id"],
                        "impact_score": payload["metadata"]["impact_score"],
                        "approval_url": payload["approval_url"],
                    },
                },
            }

            response = await self.http_client.post(
                "https://events.pagerduty.com/v2/enqueue", json=pd_payload
            )
            response.raise_for_status()

            logger.info(f"[{CONSTITUTIONAL_HASH}] PagerDuty notification sent successfully")
            return True

        except _HITL_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] PagerDuty notification failed: {e}")
            return False

    async def _send_teams_notification(self, payload: JSONDict) -> bool:
        """Send Microsoft Teams notification.

        Args:
            payload: Notification payload

        Returns:
            True if successful
        """
        webhook_url = self.notification_config.get("teams", {}).get("webhook_url")

        if not webhook_url:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Teams webhook URL not configured")
            return False

        try:
            # Teams Adaptive Card format
            teams_payload = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {
                            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                            "type": "AdaptiveCard",
                            "version": "1.2",
                            "body": [
                                {
                                    "type": "TextBlock",
                                    "text": payload["title"],
                                    "weight": "Bolder",
                                    "size": "Medium",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": payload["message"],
                                    "wrap": True,
                                },
                                {
                                    "type": "FactSet",
                                    "facts": [
                                        {
                                            "title": "Priority",
                                            "value": payload["priority"].upper(),
                                        },
                                        {
                                            "title": "Impact Score",
                                            "value": f"{payload['metadata']['impact_score']:.3f}",
                                        },
                                    ],
                                },
                            ],
                            "actions": [
                                {
                                    "type": "Action.OpenUrl",
                                    "title": "Review Amendment",
                                    "url": payload["approval_url"],
                                }
                            ],
                        },
                    }
                ],
            }

            response = await self.http_client.post(webhook_url, json=teams_payload)
            response.raise_for_status()

            logger.info(f"[{CONSTITUTIONAL_HASH}] Teams notification sent successfully")
            return True

        except _HITL_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Teams notification failed: {e}")
            return False

    async def close(self):
        """Cleanup resources."""
        await self.http_client.aclose()
        logger.info(f"[{CONSTITUTIONAL_HASH}] ConstitutionalHITLIntegration closed")
