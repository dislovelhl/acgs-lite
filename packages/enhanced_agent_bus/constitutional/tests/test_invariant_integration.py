"""
Integration tests for constitutional invariant system wiring.
Constitutional Hash: 608508a9bd224290

Tests:
- ProposalInvariantValidator wired into AmendmentProposalEngine
- RuntimeMutationGuard wired into SDPC EvolutionController
- AmendmentProposal invariant fields
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.invariant_guard import (
    ConstitutionalInvariantViolation,
    RuntimeMutationGuard,
)
from enhanced_agent_bus.constitutional.invariants import (
    InvariantManifest,
    InvariantScope,
    get_default_manifest,
)
from enhanced_agent_bus.constitutional.proposal_engine import (
    AmendmentProposalEngine,
    ProposalRequest,
    ProposalValidationError,
)
from enhanced_agent_bus.constitutional.version_model import ConstitutionalVersion
from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType
from enhanced_agent_bus.sdpc.evolution_controller import EvolutionController

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_storage(
    active_version: ConstitutionalVersion | None = None,
) -> MagicMock:
    """Create a mock ConstitutionalStorageService with sensible defaults."""
    storage = MagicMock()
    if active_version is None:
        active_version = ConstitutionalVersion(
            version_id="v-test-001",
            version="1.0.0",
            constitutional_hash="608508a9bd224290",
            content={"principles": ["be safe"], "enforcement": {"mode": "strict"}},
            predecessor_version=None,
            status="active",
        )
    storage.get_active_version = AsyncMock(return_value=active_version)
    storage.save_amendment = AsyncMock()
    return storage


# ---------------------------------------------------------------------------
# Task A: Proposal engine invariant integration
# ---------------------------------------------------------------------------


class TestProposalEngineInvariantIntegration:
    """Verify that ProposalInvariantValidator is wired into the proposal engine."""

    async def test_protected_path_raises_proposal_validation_error(self) -> None:
        """Changes to a MACI-protected path must be rejected."""
        storage = _make_mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={
                "maci/enforcer.py": {"role_check": "disabled"},
            },
            justification="Testing invariant enforcement on protected MACI path",
            proposer_agent_id="agent-test-001",
            target_version="1.0.0",
        )

        with pytest.raises(ProposalValidationError, match="[Ii]nvariant"):
            await engine.create_proposal(request)

    async def test_unprotected_path_succeeds(self) -> None:
        """Changes to an unprotected path must proceed normally."""
        storage = _make_mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={
                "operational.threshold": 0.85,
            },
            justification="Adjusting operational threshold for better performance",
            proposer_agent_id="agent-test-002",
            target_version="1.0.0",
        )

        response = await engine.create_proposal(request)
        assert response.proposal is not None
        assert response.proposal.status == AmendmentStatus.PROPOSED

    async def test_invariant_hash_populated_on_proposal(self) -> None:
        """Created proposals should carry the invariant_hash from the manifest."""
        storage = _make_mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"config.logging_level": "debug"},
            justification="Increase logging verbosity for debugging purposes",
            proposer_agent_id="agent-test-003",
            target_version="1.0.0",
        )

        response = await engine.create_proposal(request)
        manifest = get_default_manifest()
        assert response.proposal.invariant_hash == manifest.invariant_hash


# ---------------------------------------------------------------------------
# Task B: SDPC evolution controller invariant integration
# ---------------------------------------------------------------------------


class TestSDPCEvolutionControllerInvariantIntegration:
    """Verify that RuntimeMutationGuard is wired into the SDPC EvolutionController."""

    def test_protected_mutation_skipped(self) -> None:
        """Mutations targeting a protected path should be logged and skipped."""
        controller = EvolutionController(failure_threshold=1)

        # Manually set the guard with a manifest that protects the mutation path
        manifest = get_default_manifest()
        # The default manifest protects paths like "maci/enforcer.py", etc.
        # The SDPC guard checks "sdpc.mutations.<intent>" paths — these are NOT
        # in the default protected paths. To test blocking, we install a custom guard
        # that will block sdpc mutation paths.
        from enhanced_agent_bus.constitutional.invariants import (
            EnforcementMode,
            InvariantDefinition,
        )

        blocking_manifest = InvariantManifest(
            constitutional_hash="608508a9bd224290",
            invariants=[
                InvariantDefinition(
                    invariant_id="INV-TEST-SDPC",
                    name="Block SDPC mutations",
                    scope=InvariantScope.HARD,
                    description="Test invariant blocking sdpc mutations",
                    protected_paths=["sdpc.mutations.factual"],
                    enforcement_modes=[EnforcementMode.RUNTIME],
                ),
            ],
        )
        controller._mutation_guard = RuntimeMutationGuard(blocking_manifest)

        # Trigger enough failures to cause a mutation
        controller.record_feedback(
            IntentType.FACTUAL,
            {"accuracy": False},
        )

        # The mutation should have been skipped — no dynamic mutations recorded
        assert controller.get_mutations(IntentType.FACTUAL) == []
        # failure_history should be reset
        assert controller.failure_history[IntentType.FACTUAL.value] == 0

    def test_unprotected_mutation_proceeds(self) -> None:
        """Mutations targeting an unprotected path should proceed normally."""
        controller = EvolutionController(failure_threshold=1)
        # The default manifest does not protect "sdpc.mutations.*" paths,
        # so mutations should go through with the default guard.

        controller.record_feedback(
            IntentType.FACTUAL,
            {"accuracy": False},
        )

        mutations = controller.get_mutations(IntentType.FACTUAL)
        assert len(mutations) == 1
        assert "MUTATION" in mutations[0]

    def test_mutation_guard_absent_proceeds(self) -> None:
        """If the mutation guard is None, mutations should proceed normally."""
        controller = EvolutionController(failure_threshold=1)
        controller._mutation_guard = None

        controller.record_feedback(
            IntentType.CREATIVE,
            {"quality": False},
        )

        mutations = controller.get_mutations(IntentType.CREATIVE)
        assert len(mutations) == 1


# ---------------------------------------------------------------------------
# Task C: AmendmentProposal invariant fields
# ---------------------------------------------------------------------------


class TestAmendmentProposalInvariantFields:
    """Verify that AmendmentProposal carries invariant tracking fields."""

    def test_default_invariant_fields(self) -> None:
        """New proposals should have default empty invariant fields."""
        proposal = AmendmentProposal(
            proposed_changes={"some_key": "some_value"},
            justification="Test proposal with default invariant fields",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
        )
        assert proposal.invariant_hash is None
        assert proposal.invariant_impact == []
        assert proposal.requires_refoundation is False

    def test_invariant_fields_populated(self) -> None:
        """Proposals should accept explicit invariant field values."""
        proposal = AmendmentProposal(
            proposed_changes={"another_key": "value"},
            justification="Test proposal with explicit invariant tracking data",
            proposer_agent_id="agent-002",
            target_version="2.0.0",
            invariant_hash="abc123def456",
            invariant_impact=["INV-001", "INV-003"],
            requires_refoundation=True,
        )
        assert proposal.invariant_hash == "abc123def456"
        assert proposal.invariant_impact == ["INV-001", "INV-003"]
        assert proposal.requires_refoundation is True

    def test_invariant_fields_in_dict_output(self) -> None:
        """Invariant fields should appear in to_dict() output."""
        proposal = AmendmentProposal(
            proposed_changes={"key": "value"},
            justification="Test serialization of invariant fields to dict",
            proposer_agent_id="agent-003",
            target_version="1.0.0",
            invariant_hash="hash123",
            invariant_impact=["INV-005"],
            requires_refoundation=False,
        )
        data = proposal.to_dict()
        assert data["invariant_hash"] == "hash123"
        assert data["invariant_impact"] == ["INV-005"]
        assert data["requires_refoundation"] is False
