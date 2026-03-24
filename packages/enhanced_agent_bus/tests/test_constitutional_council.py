"""Tests for ConstitutionalCouncilService signature verification."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from enhanced_agent_bus.constitutional.council import (
    CONSTITUTIONAL_HASH,
    ConstitutionalCouncilService,
)


def _proposal_payload(request: SimpleNamespace) -> str:
    import json
    from hashlib import sha256

    changes_canonical = json.dumps(request.proposed_changes, sort_keys=True, separators=(",", ":"))
    payload_digest = sha256(changes_canonical.encode()).hexdigest()
    return f"{request.proposer_agent_id}:{payload_digest}:{request.justification}:{CONSTITUTIONAL_HASH}"


def _sign_payload(private_key: ed25519.Ed25519PrivateKey, payload: str) -> str:
    return private_key.sign(payload.encode()).hex()


async def test_submit_proposal_rejects_invalid_proposer_signature(monkeypatch):
    voting_service = AsyncMock()
    proposal_engine = AsyncMock()
    service = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members={"proposer-1": "00" * 32},
    )

    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"k": "v"},
        justification="Valid justification text",
    )

    with pytest.raises(PermissionError, match="Invalid proposer signature"):
        await service.submit_proposal(request, proposer_signature="deadbeef")


async def test_submit_proposal_accepts_valid_proposer_signature(monkeypatch):
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )

    proposal = SimpleNamespace(id="proposal-1", proposal_id="proposal-1")
    proposal_engine = AsyncMock()
    proposal_engine.create_proposal.return_value = SimpleNamespace(proposal=proposal)

    voting_service = AsyncMock()
    voting_service.create_election.return_value = "election-1"

    class DummyMessageType:
        GOVERNANCE_REQUEST = "governance_request"

    class DummyAgentMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    import enhanced_agent_bus.constitutional.council as council_module

    monkeypatch.setattr(council_module, "AgentMessage", DummyAgentMessage)
    monkeypatch.setattr(council_module, "MessageType", DummyMessageType)

    service = ConstitutionalCouncilService(
        voting_service=voting_service,
        proposal_engine=proposal_engine,
        council_members={"proposer-1": public_key},
    )

    request = SimpleNamespace(
        proposer_agent_id="proposer-1",
        proposed_changes={"policy": {"max_risk": "high"}},
        justification="Increase constitutional guardrails safely",
    )

    signature = _sign_payload(private_key, _proposal_payload(request))
    election_id = await service.submit_proposal(request, proposer_signature=signature)

    assert election_id == "election-1"
    proposal_engine.create_proposal.assert_awaited_once()
    voting_service.create_election.assert_awaited_once()
