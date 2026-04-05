"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
    DefaultDeliberationActivities,
    DeliberationWorkflow,
    Vote,
)


class TestDeliberationWorkflowOptimized:
    @pytest.fixture
    def activities(self):
        return DefaultDeliberationActivities()

    async def test_collect_votes_with_mock_redis(self, activities):
        """Test collect_votes with mocked election store."""
        # Mock election store (the actual function called by collect_votes)
        mock_election_store = AsyncMock()
        mock_election_store.scan_elections = AsyncMock(return_value=["election-1"])
        mock_election_store.get_election = AsyncMock(
            return_value={
                "message_id": "msg1",
                "status": "CLOSED",  # Return CLOSED to exit the loop
                "votes": {
                    "agent1": {
                        "agent_id": "agent1",
                        "decision": "approve",
                        "reasoning": "ok",
                        "confidence": 1.0,
                        "timestamp": "2024-01-01T00:00:00+00:00",
                    }
                },
            }
        )

        with patch(
            "enhanced_agent_bus.deliberation_layer.redis_election_store.get_election_store",
            return_value=mock_election_store,
        ):
            votes = await activities.collect_votes("msg1", "req1", timeout_seconds=1)

            assert len(votes) == 1
            assert votes[0].agent_id == "agent1"
            assert votes[0].decision == "approve"

    async def test_record_audit_trail_raises_when_audit_client_errors(self, activities):
        """Audit trail recording should surface durable-write failures."""
        audit_client = Mock()
        audit_client.record = AsyncMock(side_effect=RuntimeError("audit unavailable"))
        activities._audit_client = audit_client

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await activities.record_audit_trail(
                "msg1",
                {"status": "approved", "score": 0.9},
            )

        audit_client.record.assert_awaited_once()

    async def test_record_audit_trail_falls_back_when_audit_client_unavailable(self, activities):
        """Missing audit client configuration may still use the deterministic fallback hash."""
        with patch.object(activities, "_create_audit_client", return_value=None):
            audit_hash = await activities.record_audit_trail(
                "msg1",
                {"status": "approved", "score": 0.9},
            )

        assert isinstance(audit_hash, str)
        assert len(audit_hash) == 16

    async def test_record_audit_trail_lazily_creates_default_audit_client(self, activities):
        """Default activities should lazily create the default audit client."""
        record = AsyncMock(return_value="audit-hash-1234")
        mock_client = Mock()
        mock_client.record = record

        with patch(
            "enhanced_agent_bus.audit_client.AuditClient",
            return_value=mock_client,
        ) as audit_client_cls:
            audit_hash = await activities.record_audit_trail(
                "msg1",
                {"status": "approved", "score": 0.9},
            )

        assert audit_hash == "audit-hash-1234"
        audit_client_cls.assert_called_once_with()
        record.assert_awaited_once()

    def test_workflow_determination_logic(self):
        workflow = DeliberationWorkflow("wf1")

        # Consensus reached, no human required
        assert (
            workflow._determine_approval(
                consensus_reached=True, human_decision=None, require_human=False
            )
            is True
        )

        # Consensus not reached, but human approved
        assert (
            workflow._determine_approval(
                consensus_reached=False, human_decision="approve", require_human=False
            )
            is True
        )

        # Consensus reached, but human required and not approved
        assert (
            workflow._determine_approval(
                consensus_reached=True, human_decision=None, require_human=True
            )
            is False
        )

        # Human rejected
        assert (
            workflow._determine_approval(
                consensus_reached=True, human_decision="reject", require_human=False
            )
            is False
        )

    def test_check_consensus_variants(self):
        workflow = DeliberationWorkflow("wf1")
        votes = [
            Vote(agent_id="a1", decision="approve", reasoning="", confidence=1.0),
            Vote(agent_id="a2", decision="approve", reasoning="", confidence=1.0),
            Vote(agent_id="a3", decision="reject", reasoning="", confidence=1.0),
        ]

        # 2/3 approved = 0.666... >= 0.66 threshold
        assert workflow._check_consensus(votes, required_votes=3, threshold=0.66) is True

        # Weighted votes
        weights = {"a1": 1.0, "a2": 1.0, "a3": 5.0}  # a3 has more weight
        assert (
            workflow._check_consensus(
                votes, required_votes=3, threshold=0.66, agent_weights=weights
            )
            is False
        )
