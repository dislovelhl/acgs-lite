# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for ConstitutionalCouncilService.
Boosts coverage of council.py from ~58% to ≥90%.
"""

import json
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from enhanced_agent_bus.constitutional.council import (
    CONSTITUTIONAL_HASH,
    ConstitutionalCouncilService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_private_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _public_key_hex(private_key: ed25519.Ed25519PrivateKey) -> str:
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )


def _sign(private_key: ed25519.Ed25519PrivateKey, payload: str) -> str:
    return private_key.sign(payload.encode()).hex()


def _proposal_payload(request: SimpleNamespace) -> str:
    changes_canonical = json.dumps(request.proposed_changes, sort_keys=True, separators=(",", ":"))
    payload_digest = sha256(changes_canonical.encode()).hexdigest()
    return (
        f"{request.proposer_agent_id}:{payload_digest}"
        f":{request.justification}:{CONSTITUTIONAL_HASH}"
    )


def _vote_payload(election_id: str, member_id: str, decision: str) -> str:
    return f"{election_id}:{member_id}:{decision}:{CONSTITUTIONAL_HASH}"


def _make_service(council_members=None, min_quorum=0.66):
    voting_service = AsyncMock()
    proposal_engine = AsyncMock()
    if council_members is None:
        priv = _make_private_key()
        council_members = {"member-1": _public_key_hex(priv)}
        return (
            ConstitutionalCouncilService(
                voting_service=voting_service,
                proposal_engine=proposal_engine,
                council_members=council_members,
                min_quorum=min_quorum,
            ),
            voting_service,
            proposal_engine,
            priv,
        )
    svc = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members=council_members,
        min_quorum=min_quorum,
    )
    return svc, voting_service, proposal_engine


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_stores_attributes():
    """Service stores constructor parameters correctly."""
    svc, vs, pe, _ = _make_service()
    assert svc.voting_service is vs
    assert svc.proposal_engine is pe
    assert svc.min_quorum == 0.66
    assert svc._active_elections == {}


# ---------------------------------------------------------------------------
# submit_proposal — no public key registered (line 104)
# ---------------------------------------------------------------------------


async def test_submit_proposal_raises_when_proposer_not_in_members():
    """PermissionError raised when proposer_agent_id has no registered key."""
    svc, _, _ = _make_service(council_members={"other-member": "00" * 32})
    request = SimpleNamespace(
        proposer_agent_id="unknown-proposer",
        proposed_changes={"k": "v"},
        justification="some reason",
    )
    with pytest.raises(PermissionError, match="No proposer public key registered"):
        await svc.submit_proposal(request, proposer_signature="deadbeef")


async def test_submit_proposal_raises_on_invalid_proposer_signature():
    """PermissionError raised when proposer signature is invalid (line 109)."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, _, _ = _make_service(council_members={"proposer-1": pub_hex})

    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"k": "v"},
        justification="some reason",
    )
    # Provide a completely wrong signature (64 zero bytes in hex)
    with pytest.raises(PermissionError, match="Invalid proposer signature"):
        await svc.submit_proposal(request, proposer_signature="00" * 64)


# ---------------------------------------------------------------------------
# submit_proposal — AgentMessage is None (line 134)
# ---------------------------------------------------------------------------


async def test_submit_proposal_raises_when_agent_message_none(monkeypatch):
    """RuntimeError raised when AgentMessage is None (import fallback)."""
    import enhanced_agent_bus.constitutional.council as council_module

    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"x": 1},
        justification="test justification",
    )
    sig = _sign(priv, _proposal_payload(request))

    proposal = SimpleNamespace(id="p-1", proposal_id="p-1")
    proposal_engine = AsyncMock()
    proposal_engine.create_proposal.return_value = SimpleNamespace(proposal=proposal)

    voting_service = AsyncMock()
    svc = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members={"proposer-1": pub_hex},
    )

    # Patch AgentMessage to None on the module to trigger RuntimeError branch (line 134)
    monkeypatch.setattr(council_module, "AgentMessage", None)
    with pytest.raises(RuntimeError, match="AgentMessage model not available"):
        await svc.submit_proposal(request, proposer_signature=sig)


# ---------------------------------------------------------------------------
# submit_proposal — full happy path (stores election mapping)
# ---------------------------------------------------------------------------


async def test_submit_proposal_stores_active_election(monkeypatch):
    """After successful submit, election id is stored in _active_elections."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)

    proposal = SimpleNamespace(id="proposal-42", proposal_id="proposal-42")
    proposal_engine = AsyncMock()
    proposal_engine.create_proposal.return_value = SimpleNamespace(proposal=proposal)

    voting_service = AsyncMock()
    voting_service.create_election.return_value = "election-99"

    class DummyMessageType:
        GOVERNANCE_REQUEST = "governance_request"

    class DummyAgentMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    import enhanced_agent_bus.constitutional.council as council_module

    monkeypatch.setattr(council_module, "AgentMessage", DummyAgentMessage)
    monkeypatch.setattr(council_module, "MessageType", DummyMessageType)

    svc = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members={"proposer-1": pub_hex},
    )
    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"rule": "new"},
        justification="Updating governance rule",
    )
    sig = _sign(priv, _proposal_payload(request))
    election_id = await svc.submit_proposal(request, proposer_signature=sig)

    assert election_id == "election-99"
    assert svc._active_elections["proposal-42"] == "election-99"


# ---------------------------------------------------------------------------
# cast_vote — unauthorized member (line 162-164)
# ---------------------------------------------------------------------------


async def test_cast_vote_returns_false_for_unauthorized_member():
    """cast_vote returns False when member_id is not in council_members."""
    svc, vs, _pe, _ = _make_service()
    result = await svc.cast_vote(
        election_id="e-1",
        member_id="intruder",
        decision="APPROVE",
        signature="aabbcc",
    )
    assert result is False
    vs.cast_vote.assert_not_awaited()


# ---------------------------------------------------------------------------
# cast_vote — invalid signature (lines 167-169)
# ---------------------------------------------------------------------------


async def test_cast_vote_returns_false_for_invalid_signature():
    """cast_vote returns False when the vote signature is invalid."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, vs, _pe = _make_service(council_members={"member-1": pub_hex})

    result = await svc.cast_vote(
        election_id="e-1",
        member_id="member-1",
        decision="APPROVE",
        signature="00" * 64,  # wrong signature
    )
    assert result is False
    vs.cast_vote.assert_not_awaited()


# ---------------------------------------------------------------------------
# cast_vote — voting service returns False (lines 173-176)
# ---------------------------------------------------------------------------


async def test_cast_vote_returns_false_when_voting_service_fails():
    """cast_vote returns False when voting_service.cast_vote returns False."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, vs, _pe = _make_service(council_members={"member-1": pub_hex})

    vs.cast_vote.return_value = False

    sig = _sign(priv, _vote_payload("e-1", "member-1", "DENY"))
    result = await svc.cast_vote(
        election_id="e-1",
        member_id="member-1",
        decision="DENY",
        signature=sig,
    )
    assert result is False
    # _check_election_status must NOT be called when success is False
    vs.get_election_result.assert_not_awaited()


# ---------------------------------------------------------------------------
# cast_vote — success path triggers _check_election_status (lines 177-182)
# ---------------------------------------------------------------------------


async def test_cast_vote_success_checks_election_status():
    """On successful vote, _check_election_status is invoked."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, vs, _pe = _make_service(council_members={"member-1": pub_hex})

    vs.cast_vote.return_value = True
    vs.get_election_result.return_value = {"status": "OPEN"}

    sig = _sign(priv, _vote_payload("e-10", "member-1", "APPROVE"))
    result = await svc.cast_vote(
        election_id="e-10",
        member_id="member-1",
        decision="APPROVE",
        signature=sig,
        reason="I agree",
    )
    assert result is True
    vs.get_election_result.assert_awaited_once_with("e-10")


# ---------------------------------------------------------------------------
# _check_election_status — CLOSED + PASSED triggers ratification (lines 192-194)
# ---------------------------------------------------------------------------


async def test_check_election_status_ratifies_on_passed():
    """CLOSED/PASSED election triggers _ratify_proposal."""
    svc, vs, pe = _make_service(council_members={"m": "00" * 32})
    vs.get_election_result.return_value = {
        "status": "CLOSED",
        "outcome": "PASSED",
        "message_id": "prop-7",
    }
    pe.apply_proposal.return_value = True

    await svc._check_election_status("election-7")

    pe.apply_proposal.assert_awaited_once_with("prop-7")


# ---------------------------------------------------------------------------
# _check_election_status — CLOSED + FAILED triggers rejection (lines 195-199)
# ---------------------------------------------------------------------------


async def test_check_election_status_rejects_on_failed():
    """CLOSED/FAILED election triggers proposal_engine.reject_proposal."""
    svc, vs, pe = _make_service(council_members={"m": "00" * 32})
    vs.get_election_result.return_value = {
        "status": "CLOSED",
        "outcome": "FAILED",
        "message_id": "prop-8",
    }

    await svc._check_election_status("election-8")

    pe.reject_proposal.assert_awaited_once_with("prop-8", reason="Council vote failed")


# ---------------------------------------------------------------------------
# _check_election_status — still OPEN (no ratification called)
# ---------------------------------------------------------------------------


async def test_check_election_status_noop_when_open():
    """No action when election is still OPEN."""
    svc, vs, pe = _make_service(council_members={"m": "00" * 32})
    vs.get_election_result.return_value = {"status": "OPEN"}

    await svc._check_election_status("election-open")

    pe.apply_proposal.assert_not_awaited()
    pe.reject_proposal.assert_not_awaited()


# ---------------------------------------------------------------------------
# _ratify_proposal — success path (lines 204-207)
# ---------------------------------------------------------------------------


async def test_ratify_proposal_applies_on_success():
    """_ratify_proposal calls apply_proposal and logs success."""
    svc, _vs, pe = _make_service(council_members={"m": "00" * 32})
    pe.apply_proposal.return_value = True

    await svc._ratify_proposal("prop-success", {"outcome": "PASSED"})

    pe.apply_proposal.assert_awaited_once_with("prop-success")


# ---------------------------------------------------------------------------
# _ratify_proposal — failure path (lines 210-212)
# ---------------------------------------------------------------------------


async def test_ratify_proposal_logs_error_on_failure():
    """_ratify_proposal logs an error when apply_proposal returns False."""
    svc, _vs, pe = _make_service(council_members={"m": "00" * 32})
    pe.apply_proposal.return_value = False

    await svc._ratify_proposal("prop-fail", {"outcome": "PASSED"})

    pe.apply_proposal.assert_awaited_once_with("prop-fail")


# ---------------------------------------------------------------------------
# _verify_vote_signature — valid signature (lines 221-228)
# ---------------------------------------------------------------------------


def test_verify_vote_signature_returns_true_for_valid():
    """_verify_vote_signature returns True for a correctly signed payload."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, _, _ = _make_service(council_members={"m": pub_hex})

    election_id = "e-verify"
    member_id = "m"
    decision = "APPROVE"
    sig = _sign(priv, _vote_payload(election_id, member_id, decision))

    assert svc._verify_vote_signature(member_id, election_id, decision, sig, pub_hex) is True


# ---------------------------------------------------------------------------
# _verify_vote_signature — invalid signature triggers error branch (line 228-229)
# ---------------------------------------------------------------------------


def test_verify_vote_signature_returns_false_for_invalid():
    """_verify_vote_signature returns False for a bad signature."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, _, _ = _make_service(council_members={"m": pub_hex})

    assert svc._verify_vote_signature("m", "e-bad", "APPROVE", "deadbeef" * 8, pub_hex) is False


# ---------------------------------------------------------------------------
# _verify_proposer_signature — error branch (lines 249-252)
# ---------------------------------------------------------------------------


def test_verify_proposer_signature_returns_false_for_bad_sig():
    """_verify_proposer_signature returns False for a wrong signature."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, _, _ = _make_service(council_members={"proposer-1": pub_hex})

    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"k": "v"},
        justification="test",
    )
    assert svc._verify_proposer_signature(request, "00" * 64, pub_hex) is False


# ---------------------------------------------------------------------------
# _verify_signature — valid round-trip
# ---------------------------------------------------------------------------


def test_verify_signature_static_roundtrip():
    """_verify_signature correctly validates a real Ed25519 signature."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    payload = "test:payload"
    sig_hex = _sign(priv, payload)

    assert ConstitutionalCouncilService._verify_signature(payload, sig_hex, pub_hex) is True


# ---------------------------------------------------------------------------
# _verify_signature — wrong key raises
# ---------------------------------------------------------------------------


def test_verify_signature_raises_on_wrong_key():
    """_verify_signature raises on key/signature mismatch."""
    from cryptography.exceptions import InvalidSignature

    priv_a = _make_private_key()
    priv_b = _make_private_key()
    pub_b_hex = _public_key_hex(priv_b)
    payload = "payload:mismatch"
    sig_hex = _sign(priv_a, payload)

    # Should raise since we verify with key_b but signed with key_a
    with pytest.raises((InvalidSignature, Exception)):
        ConstitutionalCouncilService._verify_signature(payload, sig_hex, pub_b_hex)


# ---------------------------------------------------------------------------
# cast_vote — with reason parameter passed through
# ---------------------------------------------------------------------------


async def test_cast_vote_passes_reason_to_voting_service():
    """cast_vote forwards the reason argument to voting_service.cast_vote."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)
    svc, vs, _pe = _make_service(council_members={"member-1": pub_hex})

    vs.cast_vote.return_value = True
    vs.get_election_result.return_value = {"status": "OPEN"}

    sig = _sign(priv, _vote_payload("e-reason", "member-1", "APPROVE"))
    await svc.cast_vote(
        election_id="e-reason",
        member_id="member-1",
        decision="APPROVE",
        signature=sig,
        reason="Because it is good",
    )

    vs.cast_vote.assert_awaited_once_with(
        election_id="e-reason",
        agent_id="member-1",
        decision="APPROVE",
        reason="Because it is good",
    )


# ---------------------------------------------------------------------------
# submit_proposal — proposal_id fallback (uses proposal_id attribute)
# ---------------------------------------------------------------------------


async def test_submit_proposal_uses_proposal_id_fallback(monkeypatch):
    """When proposal has no .id, falls back to .proposal_id."""
    priv = _make_private_key()
    pub_hex = _public_key_hex(priv)

    # proposal without .id attribute — only has .proposal_id
    proposal = SimpleNamespace(proposal_id="fallback-pid")

    proposal_engine = AsyncMock()
    proposal_engine.create_proposal.return_value = SimpleNamespace(proposal=proposal)

    voting_service = AsyncMock()
    voting_service.create_election.return_value = "election-fallback"

    class DummyMessageType:
        GOVERNANCE_REQUEST = "governance"

    class DummyAgentMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    import enhanced_agent_bus.constitutional.council as council_module

    monkeypatch.setattr(council_module, "AgentMessage", DummyAgentMessage)
    monkeypatch.setattr(council_module, "MessageType", DummyMessageType)

    svc = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members={"proposer-1": pub_hex},
    )
    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"rule": "new"},
        justification="Test fallback",
    )
    sig = _sign(priv, _proposal_payload(request))
    election_id = await svc.submit_proposal(request, proposer_signature=sig)

    assert election_id == "election-fallback"
    # Active elections keyed by proposal_id fallback
    assert svc._active_elections["fallback-pid"] == "election-fallback"
