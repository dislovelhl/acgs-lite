"""
Tests for Constitutional Invariant Guard
Constitutional Hash: 608508a9bd224290

Covers InvariantClassifier, ProposalInvariantValidator, RuntimeMutationGuard,
ConstitutionalInvariantViolation, and fail-closed behaviour.
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.constitutional.invariant_guard import (
    ConstitutionalInvariantViolation,
    InvariantClassifier,
    ProposalInvariantValidator,
    RuntimeMutationGuard,
)
from enhanced_agent_bus.constitutional.invariants import (
    ChangeClassification,
    InvariantDefinition,
    InvariantManifest,
    InvariantScope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_manifest(invariants: list[InvariantDefinition] | None = None) -> InvariantManifest:
    return InvariantManifest(
        manifest_version="1.0.0",
        constitutional_hash="608508a9bd224290",
        invariants=invariants or [],
    )


@pytest.fixture()
def hard_invariant() -> InvariantDefinition:
    return InvariantDefinition(
        invariant_id="INV-001",
        name="MACI Separation of Powers",
        scope=InvariantScope.HARD,
        description="Agents never validate their own output",
        protected_paths=["maci", "constitutional.hash"],
    )


@pytest.fixture()
def meta_invariant() -> InvariantDefinition:
    return InvariantDefinition(
        invariant_id="INV-002",
        name="Amendment Process Integrity",
        scope=InvariantScope.META,
        description="The amendment process itself cannot be bypassed",
        protected_paths=["amendment.process", "refoundation"],
    )


@pytest.fixture()
def soft_invariant() -> InvariantDefinition:
    return InvariantDefinition(
        invariant_id="INV-003",
        name="Logging Standards",
        scope=InvariantScope.SOFT,
        description="Structured logging requirements",
        protected_paths=["logging.format", "observability.tracing"],
    )


@pytest.fixture()
def mixed_manifest(
    hard_invariant: InvariantDefinition,
    meta_invariant: InvariantDefinition,
    soft_invariant: InvariantDefinition,
) -> InvariantManifest:
    return _make_manifest([hard_invariant, meta_invariant, soft_invariant])


@pytest.fixture()
def empty_manifest() -> InvariantManifest:
    return _make_manifest([])


# ---------------------------------------------------------------------------
# InvariantClassifier
# ---------------------------------------------------------------------------


class TestInvariantClassifier:
    """Tests for the stateless InvariantClassifier."""

    def test_hard_invariant_blocks(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["maci.role_assignment"])

        assert result.touches_invariants is True
        assert "INV-001" in result.touched_invariant_ids
        assert result.blocked is True
        assert result.requires_refoundation is True

    def test_meta_invariant_blocks(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["amendment.process.voting"])

        assert result.touches_invariants is True
        assert "INV-002" in result.touched_invariant_ids
        assert result.blocked is True
        assert result.requires_refoundation is True

    def test_soft_invariant_flagged_not_blocked(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["logging.format.json"])

        assert result.touches_invariants is True
        assert "INV-003" in result.touched_invariant_ids
        assert result.blocked is False
        assert result.requires_refoundation is False

    def test_unprotected_path_clean(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["ui.theme.color"])

        assert result.touches_invariants is False
        assert result.touched_invariant_ids == []
        assert result.blocked is False

    def test_exact_path_match(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["maci"])

        assert result.touches_invariants is True
        assert "INV-001" in result.touched_invariant_ids
        assert result.blocked is True

    def test_prefix_path_match(self, mixed_manifest: InvariantManifest) -> None:
        """Ensure 'maci.role_assignment' matches protected path 'maci'."""
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["maci.role_assignment"])

        assert result.touches_invariants is True
        assert result.blocked is True

    def test_no_false_prefix_match(self, mixed_manifest: InvariantManifest) -> None:
        """'macintosh' should NOT match protected path 'maci'."""
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["macintosh"])

        assert result.touches_invariants is False
        assert result.blocked is False

    def test_multiple_paths_mixed(self, mixed_manifest: InvariantManifest) -> None:
        """Multiple paths: one SOFT, one HARD -> blocked."""
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change(["logging.format.json", "maci.enforcement"])

        assert result.touches_invariants is True
        assert "INV-001" in result.touched_invariant_ids
        assert "INV-003" in result.touched_invariant_ids
        assert result.blocked is True

    def test_empty_manifest_blocks_everything(self, empty_manifest: InvariantManifest) -> None:
        """Fail-closed: empty manifest blocks all changes."""
        classifier = InvariantClassifier(empty_manifest)
        result = classifier.classify_change(["anything"])

        assert result.blocked is True
        assert "fail-closed" in (result.reason or "").lower()

    def test_empty_affected_paths(self, mixed_manifest: InvariantManifest) -> None:
        classifier = InvariantClassifier(mixed_manifest)
        result = classifier.classify_change([])

        assert result.touches_invariants is False
        assert result.blocked is False

    def test_deduplicates_invariant_ids(self) -> None:
        """Same invariant protecting multiple paths should appear once."""
        inv = InvariantDefinition(
            invariant_id="INV-DUP",
            name="Multi-path",
            scope=InvariantScope.HARD,
            protected_paths=["a", "b"],
        )
        manifest = _make_manifest([inv])
        classifier = InvariantClassifier(manifest)
        result = classifier.classify_change(["a", "b"])

        assert result.touched_invariant_ids.count("INV-DUP") == 1


# ---------------------------------------------------------------------------
# ProposalInvariantValidator
# ---------------------------------------------------------------------------


class TestProposalInvariantValidator:
    """Tests for the async ProposalInvariantValidator."""

    async def test_hard_invariant_raises(self, mixed_manifest: InvariantManifest) -> None:
        validator = ProposalInvariantValidator(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation) as exc_info:
            await validator.validate_proposal(
                proposed_changes={"key": "value"},
                affected_paths=["maci.separation_of_powers"],
            )

        assert exc_info.value.classification.blocked is True
        assert "INV-001" in exc_info.value.classification.touched_invariant_ids

    async def test_meta_invariant_raises(self, mixed_manifest: InvariantManifest) -> None:
        validator = ProposalInvariantValidator(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation):
            await validator.validate_proposal(
                proposed_changes={},
                affected_paths=["amendment.process"],
            )

    async def test_soft_invariant_returns_classification(
        self, mixed_manifest: InvariantManifest
    ) -> None:
        validator = ProposalInvariantValidator(mixed_manifest)
        result = await validator.validate_proposal(
            proposed_changes={"format": "yaml"},
            affected_paths=["logging.format"],
        )

        assert result.touches_invariants is True
        assert result.blocked is False
        assert "INV-003" in result.touched_invariant_ids

    async def test_clean_path_returns_clean(self, mixed_manifest: InvariantManifest) -> None:
        validator = ProposalInvariantValidator(mixed_manifest)
        result = await validator.validate_proposal(
            proposed_changes={"color": "blue"},
            affected_paths=["ui.theme"],
        )

        assert result.touches_invariants is False
        assert result.blocked is False

    async def test_empty_manifest_raises(self, empty_manifest: InvariantManifest) -> None:
        """Fail-closed: empty manifest raises for any proposal."""
        validator = ProposalInvariantValidator(empty_manifest)

        with pytest.raises(ConstitutionalInvariantViolation) as exc_info:
            await validator.validate_proposal(
                proposed_changes={},
                affected_paths=["anything"],
            )

        assert exc_info.value.classification.blocked is True


# ---------------------------------------------------------------------------
# RuntimeMutationGuard
# ---------------------------------------------------------------------------


class TestRuntimeMutationGuard:
    """Tests for the RuntimeMutationGuard."""

    def test_blocks_sdpc_on_hard_path(self, mixed_manifest: InvariantManifest) -> None:
        guard = RuntimeMutationGuard(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation(
                target_path="maci.role_assignment",
                operation="write",
                actor_role="sdpc",
            )

    def test_blocks_any_role_on_hard_path(self, mixed_manifest: InvariantManifest) -> None:
        guard = RuntimeMutationGuard(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation(
                target_path="constitutional.hash.override",
                operation="update",
                actor_role="admin",
            )

    def test_blocks_sdpc_on_soft_path(self, mixed_manifest: InvariantManifest) -> None:
        """SDPC cannot write even to SOFT invariant paths."""
        guard = RuntimeMutationGuard(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation) as exc_info:
            guard.validate_mutation(
                target_path="logging.format",
                operation="write",
                actor_role="sdpc",
            )

        assert "recommend" in str(exc_info.value).lower()

    def test_blocks_adaptive_governance_on_soft_path(
        self, mixed_manifest: InvariantManifest
    ) -> None:
        guard = RuntimeMutationGuard(mixed_manifest)

        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation(
                target_path="observability.tracing",
                operation="write",
                actor_role="adaptive_governance",
            )

    def test_allows_regular_role_on_soft_path(self, mixed_manifest: InvariantManifest) -> None:
        """Regular roles can write to SOFT invariant paths."""
        guard = RuntimeMutationGuard(mixed_manifest)
        # Should not raise
        guard.validate_mutation(
            target_path="logging.format",
            operation="write",
            actor_role="admin",
        )

    def test_allows_write_to_unprotected_path(self, mixed_manifest: InvariantManifest) -> None:
        guard = RuntimeMutationGuard(mixed_manifest)
        # Should not raise
        guard.validate_mutation(
            target_path="ui.dashboard.widget",
            operation="create",
            actor_role="sdpc",
        )

    def test_empty_manifest_blocks_mutation(self, empty_manifest: InvariantManifest) -> None:
        """Fail-closed: empty manifest blocks runtime mutations."""
        guard = RuntimeMutationGuard(empty_manifest)

        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation(
                target_path="anything",
                operation="write",
                actor_role="admin",
            )


# ---------------------------------------------------------------------------
# ConstitutionalInvariantViolation
# ---------------------------------------------------------------------------


class TestConstitutionalInvariantViolation:
    def test_carries_classification(self) -> None:
        classification = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-001"],
            blocked=True,
            reason="Test reason",
        )
        exc = ConstitutionalInvariantViolation(classification)

        assert exc.classification is classification
        assert str(exc) == "Test reason"

    def test_custom_message_overrides(self) -> None:
        classification = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=[],
            blocked=True,
            reason="Default reason",
        )
        exc = ConstitutionalInvariantViolation(classification, "Custom message")

        assert str(exc) == "Custom message"

    def test_fallback_message(self) -> None:
        classification = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=[],
            blocked=True,
            reason=None,
        )
        exc = ConstitutionalInvariantViolation(classification)

        assert str(exc) == "Invariant violation"
