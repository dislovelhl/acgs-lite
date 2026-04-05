"""
ACGS-2 Constitutional Council Service
Constitutional Hash: 608508a9bd224290

Manages the ratification of high-risk policy changes through a
distributed multi-signature voting process.
"""

from __future__ import annotations

import json
from hashlib import sha256

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from cryptography.exceptions import InvalidSignature
except ImportError:
    InvalidSignature = ValueError  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus.core_models import MessageType
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
except ImportError:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    AgentMessage = None  # type: ignore[misc, assignment]
    MessageType = None  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus.deliberation_layer.voting_service import (
        Vote,
        VotingService,
        VotingStrategy,
    )
except ImportError:
    VotingService = None  # type: ignore[misc, assignment]
    VotingStrategy = None  # type: ignore[misc, assignment]
    Vote = None  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus.constitutional.proposal_engine import (
        AmendmentProposalEngine,
        ProposalRequest,
    )
except ImportError:
    AmendmentProposalEngine = None  # type: ignore[misc, assignment]
    ProposalRequest = None  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus.bundle_registry import BundleManifest
except ImportError:
    BundleManifest = None  # type: ignore[misc, assignment]

logger = get_logger(__name__)
SIGNATURE_VERIFICATION_ERRORS = (
    InvalidSignature,
    RuntimeError,
    TypeError,
    ValueError,
)


class ConstitutionalCouncilService:
    """
    Service managing the Constitutional Council's ratification process.

    Responsibilities:
    - Receive amendment/policy proposals
    - Initiate voting elections with authorized council members
    - Collect and verify cryptographic signatures
    - Ratify and enact passed proposals
    """

    def __init__(
        self,
        voting_service: object,
        proposal_engine: object,
        council_members: dict[str, str],  # member_id -> Ed25519 public_key_hex
        min_quorum: float = 0.66,  # 2/3 supermajority by default
    ):
        self.voting_service = voting_service
        self.proposal_engine = proposal_engine
        self.council_members = council_members
        self.min_quorum = min_quorum

        # ML-DSA-65 keys: member_id -> ML-DSA-65 public_key_hex (populated via register_ml_dsa_key)
        self.council_pqc_keys: dict[str, str] = {}

        # Mapping of proposal_id -> election_id
        self._active_elections: dict[str, str] = {}

    def register_ml_dsa_key(self, member_id: str, ml_dsa_public_key_hex: str) -> None:
        """Register an ML-DSA-65 public key for a council member.

        The member must already have an Ed25519 key in ``council_members``.  Both
        keys coexist during the transition window; once all members have PQC keys
        the classical Ed25519 path will be removed.

        Args:
            member_id:              Identifier of the council member.
            ml_dsa_public_key_hex:  Hex-encoded ML-DSA-65 public key bytes.
        """
        if member_id not in self.council_members:
            raise ValueError(
                f"Cannot register PQC key: member '{member_id}' is not a known council member"
            )
        self.council_pqc_keys[member_id] = ml_dsa_public_key_hex
        logger.info(f"ML-DSA-65 key registered for council member {member_id}")

    async def submit_proposal(self, request: object, proposer_signature: str) -> str:
        """
        Submit a new proposal for Council ratification.

        Args:
            request: The proposal request
            proposer_signature: Signature of the proposer verifying authenticity

        Returns:
            election_id: The ID of the started election
        """
        proposer_public_key = self.council_members.get(request.proposer_agent_id)
        if proposer_public_key is None:
            raise PermissionError(
                f"No proposer public key registered for {request.proposer_agent_id}"
            )

        if not self._verify_proposer_signature(request, proposer_signature, proposer_public_key):
            raise PermissionError("Invalid proposer signature")

        # 1. Create proposal via engine (validates content & MACI)
        response = await self.proposal_engine.create_proposal(request)
        proposal = response.proposal

        # 2. Create election
        # We wrap the proposal in a mock message structure if needed by VotingService
        # or we just pass the ID if VotingService supported generic payloads (it expects AgentMessage currently)

        # Mock message for voting service compatibility
        message = (
            AgentMessage(
                message_id=getattr(proposal, "id", proposal.proposal_id),  # type: ignore[attr-defined]
                from_agent=request.proposer_agent_id,
                content={"text": request.justification},  # content expects dict
                message_type=MessageType.GOVERNANCE_REQUEST,  # type: ignore[attr-defined]  # Use appropriate enum
                tenant_id="constitutional",  # Global scope
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            if AgentMessage
            else None
        )

        if not message:
            raise RuntimeError("AgentMessage model not available")

        # 3. Start election with Council members
        election_id = await self.voting_service.create_election(
            message=message,
            participants=list(self.council_members.keys()),
            timeout=86400 * 3,  # 3 days default for constitutional changes
            participant_weights={m: 1.0 for m in self.council_members},
        )

        self._active_elections[getattr(proposal, "id", proposal.proposal_id)] = election_id  # type: ignore[attr-defined]
        logger.info(
            f"Started Council election {election_id} for proposal {getattr(proposal, 'id', proposal.proposal_id)}"
        )  # type: ignore[attr-defined]

        return election_id  # type: ignore[no-any-return]

    async def cast_vote(
        self,
        election_id: str,
        member_id: str,
        decision: str,  # "APPROVE" or "DENY"
        signature: str,
        reason: str | None = None,
        key_type: str = "Ed25519",  # "Ed25519" | "ML-DSA-65"
    ) -> bool:
        """
        Cast a cryptographically signed vote.

        Args:
            key_type: Algorithm used to sign the vote.  Pass "ML-DSA-65" when the
                      member's PQC key was used; defaults to "Ed25519" for the
                      classical transition window.
        """
        if member_id not in self.council_members:
            logger.warning(f"Unauthorized vote attempt by {member_id}")
            return False

        # Select the appropriate public key based on the algorithm used
        if key_type == "ML-DSA-65":
            public_key = self.council_pqc_keys.get(member_id)
            if public_key is None:
                logger.warning(f"No ML-DSA-65 key registered for {member_id}")
                return False
        else:
            public_key = self.council_members[member_id]

        if not self._verify_vote_signature(
            member_id, election_id, decision, signature, public_key, key_type
        ):
            logger.warning(f"Invalid signature for vote by {member_id}")
            return False

        # Cast vote via voting service
        success = await self.voting_service.cast_vote(
            election_id=election_id, agent_id=member_id, decision=decision, reason=reason
        )  # type: ignore[call-arg]

        if success:
            logger.info(f"Vote accepted from {member_id} for election {election_id}: {decision}")

            # Check for early closure
            await self._check_election_status(election_id)

        return success  # type: ignore[no-any-return]

    async def _check_election_status(self, election_id: str):
        """Check if election is concluded and trigger ratification if passed."""
        result = await self.voting_service.get_election_result(election_id)  # type: ignore[attr-defined]

        if result["status"] == "CLOSED":
            proposal_id = result.get("message_id")

            if result["outcome"] == "PASSED":
                logger.info(f"Election {election_id} passed. Ratifying proposal {proposal_id}...")
                await self._ratify_proposal(proposal_id, result)
            else:
                logger.info(f"Election {election_id} failed/rejected.")
                await self.proposal_engine.reject_proposal(  # type: ignore[attr-defined]
                    proposal_id, reason="Council vote failed"
                )

    async def _ratify_proposal(self, proposal_id: str, _election_result: JSONDict):
        """Execute the ratification of a passed proposal."""
        # 1. Apply the change via Proposal Engine
        success = await self.proposal_engine.apply_proposal(proposal_id)  # type: ignore[attr-defined]

        if success:
            logger.info(f"Proposal {proposal_id} successfully ratified and applied.")

            # 2. Log ratification evidence (could be added to blockchain here)
            # await self.audit_client.log_ratification(...)
        else:
            logger.error(f"Failed to apply ratified proposal {proposal_id}")

    def _verify_vote_signature(
        self,
        member_id: str,
        election_id: str,
        decision: str,
        signature: str,
        public_key: str,
        key_type: str = "Ed25519",
    ) -> bool:
        """
        Verify a vote signature.
        Payload format: "{election_id}:{member_id}:{decision}:{constitutional_hash}"
        """
        try:
            payload = f"{election_id}:{member_id}:{decision}:{CONSTITUTIONAL_HASH}"
            return self._verify_signature(
                payload=payload, signature=signature, public_key=public_key, key_type=key_type
            )
        except SIGNATURE_VERIFICATION_ERRORS as e:
            logger.error(f"Signature verification error: {e}")
            return False

    def _verify_proposer_signature(
        self,
        request: object,
        signature: str,
        public_key: str,
    ) -> bool:
        """Verify proposer signature over canonical proposal payload."""
        try:
            changes_canonical = json.dumps(
                request.proposed_changes, sort_keys=True, separators=(",", ":")
            )
            payload_digest = sha256(changes_canonical.encode()).hexdigest()
            payload = (
                f"{request.proposer_agent_id}:{payload_digest}:"
                f"{request.justification}:{CONSTITUTIONAL_HASH}"
            )
            return self._verify_signature(
                payload=payload, signature=signature, public_key=public_key
            )
        except SIGNATURE_VERIFICATION_ERRORS as e:
            logger.error(f"Proposer signature verification error: {e}")
            return False

    @staticmethod
    def _verify_signature(
        payload: str, signature: str, public_key: str, key_type: str = "Ed25519"
    ) -> bool:
        """Verify a signature over *payload*.

        Args:
            payload:    UTF-8 string that was signed.
            signature:  Hex-encoded signature bytes.
            public_key: Hex-encoded public key bytes.
            key_type:   Algorithm identifier — "Ed25519" (default) or "ML-DSA-65".
        """
        if key_type == "ML-DSA-65":
            import warnings

            import oqs

            pub_key_bytes = bytes.fromhex(public_key)
            sig_bytes = bytes.fromhex(signature)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with oqs.Signature("ML-DSA-65") as verifier:
                    return bool(verifier.verify(payload.encode(), sig_bytes, pub_key_bytes))
        else:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            pub_key_bytes = bytes.fromhex(public_key)
            pub_key_obj = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_bytes)
            sig_bytes = bytes.fromhex(signature)
            pub_key_obj.verify(sig_bytes, payload.encode())
            return True
