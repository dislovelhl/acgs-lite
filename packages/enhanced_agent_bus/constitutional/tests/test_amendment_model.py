"""
Tests for Constitutional Amendment Model
Constitutional Hash: 608508a9bd224290

Tests for AmendmentProposal model, status transitions, and validation.
"""

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

from ..amendment_model import AmendmentProposal, AmendmentStatus

# Constitutional validation markers
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


class TestAmendmentProposalCreation:
    """Test AmendmentProposal creation and validation."""

    def test_create_valid_proposal(self):
        """Test creating a valid amendment proposal."""
        proposal = AmendmentProposal(
            proposed_changes={"principle_1": "Updated principle text"},
            justification="This change improves governance clarity and compliance.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )

        assert proposal.proposal_id is not None
        assert proposal.status == AmendmentStatus.PROPOSED
        assert proposal.proposed_changes == {"principle_1": "Updated principle text"}
        assert proposal.justification == "This change improves governance clarity and compliance."
        assert proposal.proposer_agent_id == "agent-001"
        assert proposal.target_version == "1.0.0"
        assert proposal.metadata.get("constitutional_hash") == CONSTITUTIONAL_HASH

    def test_create_proposal_with_impact_score(self):
        """Test creating a proposal with impact score."""
        proposal = AmendmentProposal(
            proposed_changes={"critical_policy": "New policy"},
            justification="Critical policy update for security compliance.",
            proposer_agent_id="agent-002",
            target_version="1.0.0",
            impact_score=0.85,
            impact_factors={"semantic_similarity": 0.7, "permission_change": 0.9},
        )

        assert proposal.impact_score == 0.85
        assert proposal.high_impact is True
        assert proposal.medium_impact is False
        assert proposal.low_impact is False
        assert proposal.requires_deliberation is False  # Default

    def test_create_proposal_requires_justification(self):
        """Test that justification is required and validated."""
        with pytest.raises(ValueError, match="at least 10 characters"):
            AmendmentProposal(
                proposed_changes={"key": "value"},
                justification="short",  # Too short
                proposer_agent_id="agent-001",
                target_version="1.0.0",
            )

    def test_create_proposal_requires_changes(self):
        """Test that proposed_changes cannot be empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            AmendmentProposal(
                proposed_changes={},  # Empty
                justification="Valid justification that is long enough.",
                proposer_agent_id="agent-001",
                target_version="1.0.0",
            )

    def test_create_proposal_validates_version_format(self):
        """Test that version format is validated (semantic versioning pattern)."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError, match="string_pattern_mismatch"):
            AmendmentProposal(
                proposed_changes={"key": "value"},
                justification="Valid justification that is long enough.",
                proposer_agent_id="agent-001",
                target_version="invalid",  # Not semantic versioning
            )

    def test_create_proposal_with_new_version(self):
        """Test creating a proposal with new version specified."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Valid justification that is long enough.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            new_version="1.1.0",
        )

        assert proposal.new_version == "1.1.0"


class TestAmendmentStatusTransitions:
    """Test AmendmentProposal status transitions."""

    @pytest.fixture
    def proposal(self):
        """Create a basic proposal for testing."""
        return AmendmentProposal(
            proposed_changes={"principle": "Updated governance principle"},
            justification="Improving governance compliance with MACI framework.",
            proposer_agent_id="agent-executive-001",
            target_version="1.0.0",
        )

    def test_initial_status_is_proposed(self, proposal):
        """Test that initial status is PROPOSED."""
        assert proposal.status == AmendmentStatus.PROPOSED
        assert proposal.is_proposed is True
        assert proposal.is_pending is True

    def test_submit_for_review(self, proposal):
        """Test submitting proposal for review."""
        proposal.submit_for_review()

        assert proposal.status == AmendmentStatus.UNDER_REVIEW
        assert proposal.is_under_review is True
        assert proposal.is_pending is True

    def test_submit_for_review_invalid_state(self, proposal):
        """Test submitting for review from invalid state."""
        proposal.status = AmendmentStatus.APPROVED

        with pytest.raises(ACGSValidationError, match="PROPOSED status"):
            proposal.submit_for_review()

    def test_approve_proposal(self, proposal):
        """Test approving a proposal."""
        proposal.submit_for_review()
        proposal.approve(approver_id="judicial-agent-001", approver_role="judicial")

        assert proposal.status == AmendmentStatus.APPROVED
        assert proposal.is_approved is True
        assert proposal.reviewed_at is not None
        assert len(proposal.approval_chain) == 1
        assert proposal.approval_chain[0]["approver_id"] == "judicial-agent-001"
        assert proposal.approval_chain[0]["approver_role"] == "judicial"
        assert proposal.approval_chain[0]["decision"] == "approved"

    def test_approve_invalid_state(self, proposal):
        """Test approving from invalid state."""
        with pytest.raises(ACGSValidationError, match="UNDER_REVIEW status"):
            proposal.approve(approver_id="agent-001")

    def test_reject_proposal(self, proposal):
        """Test rejecting a proposal."""
        proposal.submit_for_review()
        proposal.reject(
            reviewer_id="judicial-agent-002",
            reason="Proposal violates constitutional principle 3.",
            reviewer_role="judicial",
        )

        assert proposal.status == AmendmentStatus.REJECTED
        assert proposal.is_rejected is True
        assert proposal.is_final is True
        assert proposal.rejection_reason == "Proposal violates constitutional principle 3."
        assert len(proposal.approval_chain) == 1
        assert proposal.approval_chain[0]["decision"] == "rejected"

    def test_reject_invalid_state(self, proposal):
        """Test rejecting from invalid state."""
        with pytest.raises(ACGSValidationError, match="UNDER_REVIEW status"):
            proposal.reject(reviewer_id="agent-001", reason="Invalid")

    def test_activate_proposal(self, proposal):
        """Test activating an approved proposal."""
        proposal.submit_for_review()
        proposal.approve(approver_id="judicial-001")

        metrics_before = {
            "violations_rate": 0.01,
            "latency_p99": 2.5,
            "health_score": 0.95,
        }
        proposal.activate(governance_metrics_before=metrics_before)

        assert proposal.status == AmendmentStatus.ACTIVE
        assert proposal.is_active is True
        assert proposal.activated_at is not None
        assert proposal.governance_metrics_before == metrics_before

    def test_activate_invalid_state(self, proposal):
        """Test activating from invalid state."""
        with pytest.raises(ACGSValidationError, match="APPROVED status"):
            proposal.activate()

    def test_rollback_proposal(self, proposal):
        """Test rolling back an active proposal."""
        proposal.submit_for_review()
        proposal.approve(approver_id="judicial-001")
        proposal.activate()

        metrics_after = {
            "violations_rate": 0.05,  # Increased
            "latency_p99": 5.0,  # Increased
            "health_score": 0.75,  # Decreased
        }
        proposal.rollback(
            reason="Governance degradation detected: violations rate increased by 400%.",
            governance_metrics_after=metrics_after,
        )

        assert proposal.status == AmendmentStatus.ROLLED_BACK
        assert proposal.is_rolled_back is True
        assert proposal.is_final is True
        assert proposal.rolled_back_at is not None
        assert "degradation" in proposal.rollback_reason.lower()
        assert proposal.governance_metrics_after == metrics_after

    def test_rollback_invalid_state(self, proposal):
        """Test rolling back from invalid state."""
        with pytest.raises(ACGSValidationError, match="ACTIVE status"):
            proposal.rollback(reason="Invalid")

    def test_withdraw_proposal(self, proposal):
        """Test withdrawing a pending proposal."""
        proposal.withdraw()

        assert proposal.status == AmendmentStatus.WITHDRAWN
        assert proposal.is_withdrawn is True
        assert proposal.is_final is True

    def test_withdraw_under_review(self, proposal):
        """Test withdrawing a proposal under review."""
        proposal.submit_for_review()
        proposal.withdraw()

        assert proposal.status == AmendmentStatus.WITHDRAWN

    def test_withdraw_invalid_state(self, proposal):
        """Test withdrawing from non-pending state."""
        proposal.submit_for_review()
        proposal.approve(approver_id="agent-001")

        with pytest.raises(ACGSValidationError, match="pending proposals"):
            proposal.withdraw()


class TestAmendmentImpactAnalysis:
    """Test impact score properties and analysis."""

    def test_high_impact_threshold(self):
        """Test high impact detection (>= 0.8)."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="High impact change requiring deliberation.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            impact_score=0.85,
        )

        assert proposal.high_impact is True
        assert proposal.medium_impact is False
        assert proposal.low_impact is False

    def test_medium_impact_threshold(self):
        """Test medium impact detection (0.5-0.8)."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Medium impact change requiring review.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            impact_score=0.65,
        )

        assert proposal.high_impact is False
        assert proposal.medium_impact is True
        assert proposal.low_impact is False

    def test_low_impact_threshold(self):
        """Test low impact detection (< 0.5)."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Low impact change for minor updates.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            impact_score=0.3,
        )

        assert proposal.high_impact is False
        assert proposal.medium_impact is False
        assert proposal.low_impact is True

    def test_no_impact_score(self):
        """Test behavior when no impact score is set."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Change without impact analysis.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )

        assert proposal.impact_score is None
        assert proposal.high_impact is False
        assert proposal.medium_impact is False
        assert proposal.low_impact is False


class TestAmendmentMetricsDelta:
    """Test governance metrics delta calculation."""

    def test_calculate_metrics_delta(self):
        """Test calculating metrics delta between before and after."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Change with governance metrics tracking.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            governance_metrics_before={
                "violations_rate": 0.01,
                "latency_p99": 2.5,
                "health_score": 0.95,
            },
            governance_metrics_after={
                "violations_rate": 0.03,
                "latency_p99": 3.5,
                "health_score": 0.85,
            },
        )

        delta = proposal.calculate_metrics_delta()

        assert delta["violations_rate"] == pytest.approx(0.02)
        assert delta["latency_p99"] == pytest.approx(1.0)
        assert delta["health_score"] == pytest.approx(-0.10)

    def test_calculate_metrics_delta_no_before(self):
        """Test metrics delta with no before metrics."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Change without before metrics.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )

        delta = proposal.calculate_metrics_delta()
        assert delta == {}

    def test_calculate_metrics_delta_no_after(self):
        """Test metrics delta with no after metrics."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Change without after metrics.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            governance_metrics_before={"violations_rate": 0.01},
        )

        delta = proposal.calculate_metrics_delta()
        assert delta == {}


class TestAmendmentSerialization:
    """Test AmendmentProposal serialization."""

    def test_to_dict(self):
        """Test converting proposal to dictionary."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Serialization test proposal.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            impact_score=0.75,
        )

        data = proposal.to_dict()

        assert data["proposal_id"] == proposal.proposal_id
        assert data["proposed_changes"] == {"key": "value"}
        assert data["justification"] == "Serialization test proposal."
        assert data["proposer_agent_id"] == "agent-001"
        assert data["target_version"] == "1.0.0"
        assert data["impact_score"] == 0.75
        assert data["status"] == "proposed"
        assert "constitutional_hash" in data["metadata"]

    def test_repr(self):
        """Test string representation."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Representation test proposal.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )

        repr_str = repr(proposal)

        assert "AmendmentProposal" in repr_str
        assert proposal.proposal_id in repr_str
        assert "1.0.0" in repr_str
        assert "proposed" in repr_str


class TestConstitutionalHashEnforcement:
    """Test constitutional hash enforcement in proposals."""

    def test_constitutional_hash_in_metadata(self):
        """Test that constitutional hash is always in metadata."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Constitutional hash enforcement test.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )

        assert proposal.metadata.get("constitutional_hash") == CONSTITUTIONAL_HASH

    def test_constitutional_hash_preserved_with_custom_metadata(self):
        """Test constitutional hash is preserved with custom metadata."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Custom metadata with constitutional hash.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            metadata={"custom_key": "custom_value"},
        )

        assert proposal.metadata.get("constitutional_hash") == CONSTITUTIONAL_HASH
        assert proposal.metadata.get("custom_key") == "custom_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
