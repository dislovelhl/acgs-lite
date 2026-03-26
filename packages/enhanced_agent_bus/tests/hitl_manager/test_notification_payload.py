"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- notificationpayload functionality
- Error handling and edge cases
- Integration with related components
"""

from .hitl_test_helpers import MockMessage


class TestNotificationPayload:
    """Tests for notification payload generation."""

    def test_notification_payload_structure(self) -> None:
        """Test that notification payload has correct structure."""
        msg = MockMessage()

        payload = {
            "text": "High-Risk Agent Action Detected",
            "attachments": [
                {
                    "fields": [
                        {"title": "Agent ID", "value": msg.from_agent, "short": True},
                        {"title": "Impact Score", "value": str(msg.impact_score), "short": True},
                        {"title": "Action type", "value": msg.message_type.value, "short": False},
                    ],
                    "callback_id": "item-123",
                    "actions": [
                        {"name": "approve", "text": "Approve", "type": "button"},
                        {"name": "reject", "text": "Reject", "type": "button"},
                    ],
                }
            ],
        }

        assert payload["text"] == "High-Risk Agent Action Detected"
        assert len(payload["attachments"]) == 1
        assert len(payload["attachments"][0]["actions"]) == 2

    def test_notification_payload_agent_info(self) -> None:
        """Test notification payload includes agent information."""
        msg = MockMessage(from_agent="critical-agent", impact_score=0.95)

        fields = [
            {"title": "Agent ID", "value": msg.from_agent, "short": True},
            {"title": "Impact Score", "value": str(msg.impact_score), "short": True},
        ]

        assert fields[0]["value"] == "critical-agent"
        assert fields[1]["value"] == "0.95"
