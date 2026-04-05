"""Tests for constitutional.council (ConstitutionalCouncilService).

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.constitutional.council import (
    ConstitutionalCouncilService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    council_members: dict[str, str] | None = None,
    min_quorum: float = 0.66,
) -> ConstitutionalCouncilService:
    """Create a ConstitutionalCouncilService with mocked deps."""
    members = council_members or {
        "alice": "aa" * 16,
        "bob": "bb" * 16,
        "carol": "cc" * 16,
    }
    voting_service = AsyncMock()
    proposal_engine = AsyncMock()
    return ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members=members,
        min_quorum=min_quorum,
    )


def _make_request(proposer: str = "alice") -> MagicMock:
    """Create a mock proposal request."""
    req = MagicMock()
    req.proposer_agent_id = proposer
    req.proposed_changes = {"rule": "new-value"}
    req.justification = "Needed for security"
    return req


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_council_members_stored(self):
        svc = _make_service()
        assert "alice" in svc.council_members
        assert len(svc.council_members) == 3

    def test_min_quorum(self):
        svc = _make_service(min_quorum=0.75)
        assert svc.min_quorum == 0.75


# ---------------------------------------------------------------------------
# PQC Key Registration
# ---------------------------------------------------------------------------


class TestPQCKeyRegistration:
    def test_register_ml_dsa_key_success(self):
        svc = _make_service()
        svc.register_ml_dsa_key("alice", "dd" * 32)
        assert "alice" in svc.council_pqc_keys

    def test_register_ml_dsa_key_unknown_member(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="not a known council member"):
            svc.register_ml_dsa_key("unknown", "ee" * 32)


# ---------------------------------------------------------------------------
# Submit Proposal
# ---------------------------------------------------------------------------


class TestSubmitProposal:
    @pytest.mark.asyncio
    async def test_submit_proposal_unknown_proposer(self):
        svc = _make_service()
        req = _make_request(proposer="unknown-agent")
        with pytest.raises(PermissionError, match="No proposer public key"):
            await svc.submit_proposal(req, "fake-sig")

    @pytest.mark.asyncio
    async def test_submit_proposal_invalid_signature(self):
        svc = _make_service()
        req = _make_request()
        with patch.object(svc, "_verify_proposer_signature", return_value=False):
            with pytest.raises(PermissionError, match="Invalid proposer signature"):
                await svc.submit_proposal(req, "bad-sig")

    @pytest.mark.asyncio
    async def test_submit_proposal_success(self):
        svc = _make_service()
        req = _make_request()

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-1"
        mock_proposal.id = "prop-1"
        svc.proposal_engine.create_proposal.return_value = MagicMock(proposal=mock_proposal)
        svc.voting_service.create_election.return_value = "election-1"

        with patch.object(svc, "_verify_proposer_signature", return_value=True):
            with patch("enhanced_agent_bus.constitutional.council.AgentMessage") as mock_msg_cls:
                mock_msg_cls.return_value = MagicMock()
                election_id = await svc.submit_proposal(req, "valid-sig")

        assert election_id == "election-1"
        assert "prop-1" in svc._active_elections

    @pytest.mark.asyncio
    async def test_submit_proposal_no_agent_message(self):
        svc = _make_service()
        req = _make_request()

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-1"
        mock_proposal.id = "prop-1"
        svc.proposal_engine.create_proposal.return_value = MagicMock(proposal=mock_proposal)

        with patch.object(svc, "_verify_proposer_signature", return_value=True):
            with patch("enhanced_agent_bus.constitutional.council.AgentMessage", None):
                with pytest.raises(RuntimeError, match="AgentMessage model not available"):
                    await svc.submit_proposal(req, "valid-sig")


# ---------------------------------------------------------------------------
# Cast Vote
# ---------------------------------------------------------------------------


class TestCastVote:
    @pytest.mark.asyncio
    async def test_cast_vote_unauthorized(self):
        svc = _make_service()
        result = await svc.cast_vote("e1", "unknown-member", "APPROVE", "sig")
        assert result is False

    @pytest.mark.asyncio
    async def test_cast_vote_invalid_signature(self):
        svc = _make_service()
        with patch.object(svc, "_verify_vote_signature", return_value=False):
            result = await svc.cast_vote("e1", "alice", "APPROVE", "bad-sig")
        assert result is False

    @pytest.mark.asyncio
    async def test_cast_vote_success(self):
        svc = _make_service()
        svc.voting_service.cast_vote.return_value = True
        svc.voting_service.get_election_result.return_value = {"status": "OPEN"}
        with patch.object(svc, "_verify_vote_signature", return_value=True):
            result = await svc.cast_vote("e1", "alice", "APPROVE", "sig")
        assert result is True
        svc.voting_service.cast_vote.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cast_vote_with_pqc_key(self):
        svc = _make_service()
        svc.register_ml_dsa_key("bob", "dd" * 32)
        svc.voting_service.cast_vote.return_value = True
        svc.voting_service.get_election_result.return_value = {"status": "OPEN"}
        with patch.object(svc, "_verify_vote_signature", return_value=True):
            result = await svc.cast_vote("e1", "bob", "APPROVE", "sig", key_type="ML-DSA-65")
        assert result is True

    @pytest.mark.asyncio
    async def test_cast_vote_pqc_key_not_registered(self):
        svc = _make_service()
        # Don't register PQC key for alice
        result = await svc.cast_vote("e1", "alice", "APPROVE", "sig", key_type="ML-DSA-65")
        assert result is False


# ---------------------------------------------------------------------------
# Check Election Status
# ---------------------------------------------------------------------------


class TestCheckElectionStatus:
    @pytest.mark.asyncio
    async def test_election_passed_triggers_ratification(self):
        svc = _make_service()
        svc.voting_service.get_election_result.return_value = {
            "status": "CLOSED",
            "outcome": "PASSED",
            "message_id": "prop-1",
        }
        svc.proposal_engine.apply_proposal.return_value = True
        await svc._check_election_status("e1")
        svc.proposal_engine.apply_proposal.assert_awaited_once_with("prop-1")

    @pytest.mark.asyncio
    async def test_election_failed_rejects_proposal(self):
        svc = _make_service()
        svc.voting_service.get_election_result.return_value = {
            "status": "CLOSED",
            "outcome": "REJECTED",
            "message_id": "prop-1",
        }
        await svc._check_election_status("e1")
        svc.proposal_engine.reject_proposal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_election_still_open(self):
        svc = _make_service()
        svc.voting_service.get_election_result.return_value = {"status": "OPEN"}
        # Should not call apply or reject
        await svc._check_election_status("e1")
        svc.proposal_engine.apply_proposal.assert_not_awaited()
        svc.proposal_engine.reject_proposal.assert_not_awaited()


# ---------------------------------------------------------------------------
# Signature Verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    def test_verify_vote_signature_delegates(self):
        svc = _make_service()
        with patch.object(svc, "_verify_signature", return_value=True) as mock_verify:
            result = svc._verify_vote_signature("alice", "e1", "APPROVE", "sig", "pk")
            assert result is True
            mock_verify.assert_called_once()

    def test_verify_vote_signature_catches_errors(self):
        svc = _make_service()
        with patch.object(svc, "_verify_signature", side_effect=RuntimeError("bad")):
            result = svc._verify_vote_signature("alice", "e1", "APPROVE", "sig", "pk")
            assert result is False

    def test_verify_proposer_signature_delegates(self):
        svc = _make_service()
        req = _make_request()
        with patch.object(svc, "_verify_signature", return_value=True) as mock_verify:
            result = svc._verify_proposer_signature(req, "sig", "pk")
            assert result is True
            mock_verify.assert_called_once()

    def test_verify_proposer_signature_catches_errors(self):
        svc = _make_service()
        req = _make_request()
        with patch.object(svc, "_verify_signature", side_effect=ValueError("bad")):
            result = svc._verify_proposer_signature(req, "sig", "pk")
            assert result is False
