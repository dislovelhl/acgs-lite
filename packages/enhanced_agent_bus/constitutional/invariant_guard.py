"""
ACGS-2 Enhanced Agent Bus - Constitutional Invariant Guard
Constitutional Hash: cdd01ef066bc6cf2

Three focused components for invariant enforcement (per spec panel review):
- InvariantClassifier: stateless path-based classification
- ProposalInvariantValidator: amendment proposal validation
- RuntimeMutationGuard: runtime mutation protection

Failure modes (per Nygard review): fail-closed on all error paths.
"""

from __future__ import annotations

from enhanced_agent_bus.observability.structured_logging import get_logger

from .invariants import (
    ChangeClassification,
    InvariantDefinition,
    InvariantManifest,
    InvariantScope,
)

logger = get_logger(__name__)

__all__ = [
    "ConstitutionalInvariantViolation",
    "InvariantClassifier",
    "ProposalInvariantValidator",
    "RuntimeMutationGuard",
]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ConstitutionalInvariantViolation(Exception):
    """Raised when a change would violate a constitutional invariant."""

    def __init__(self, classification: ChangeClassification, message: str = ""):
        self.classification = classification
        super().__init__(message or classification.reason or "Invariant violation")


# ---------------------------------------------------------------------------
# InvariantClassifier — stateless
# ---------------------------------------------------------------------------


class InvariantClassifier:
    """Classifies proposed changes against the invariant manifest.

    Path matching uses exact match or prefix match (dot-separated).
    For example, protected path ``maci`` matches ``maci``, ``maci.role_assignment``,
    and ``maci.separation_of_powers``.

    Fail-closed: if the manifest has no invariants, every change is blocked.
    """

    def __init__(self, manifest: InvariantManifest) -> None:
        self._manifest = manifest
        self._path_index: dict[str, list[InvariantDefinition]] = self._build_path_index()

    # -- public API --------------------------------------------------------

    def classify_change(self, affected_paths: list[str]) -> ChangeClassification:
        """Classify *affected_paths* against the invariant manifest.

        Returns a :class:`ChangeClassification` indicating whether the change
        touches invariants, which ones, whether it is blocked, and whether
        refoundation is required.
        """
        if not self._manifest.invariants:
            logger.warning("invariant_classifier.empty_manifest", action="block_all")
            return ChangeClassification(
                touches_invariants=True,
                touched_invariant_ids=[],
                blocked=True,
                requires_refoundation=False,
                reason="Empty invariant manifest — fail-closed: all changes blocked",
            )

        try:
            return self._do_classify(affected_paths)
        except Exception:
            logger.exception("invariant_classifier.error", affected_paths=affected_paths)
            return ChangeClassification(
                touches_invariants=True,
                touched_invariant_ids=[],
                blocked=True,
                requires_refoundation=False,
                reason="Classification error — fail-closed",
            )

    # -- internals ---------------------------------------------------------

    def _build_path_index(self) -> dict[str, list[InvariantDefinition]]:
        """Build a lookup from protected path prefix to invariant definitions."""
        index: dict[str, list[InvariantDefinition]] = {}
        for inv in self._manifest.invariants:
            for path in inv.protected_paths:
                index.setdefault(path, []).append(inv)
        return index

    def _do_classify(self, affected_paths: list[str]) -> ChangeClassification:
        matched_ids: list[str] = []
        has_hard_or_meta = False

        for change_path in affected_paths:
            for protected_path, definitions in self._path_index.items():
                if self._path_matches(change_path, protected_path):
                    for defn in definitions:
                        if defn.invariant_id not in matched_ids:
                            matched_ids.append(defn.invariant_id)
                        if defn.scope in (InvariantScope.HARD, InvariantScope.META):
                            has_hard_or_meta = True

        if not matched_ids:
            return ChangeClassification(
                touches_invariants=False,
                touched_invariant_ids=[],
                blocked=False,
                requires_refoundation=False,
                reason=None,
            )

        if has_hard_or_meta:
            return ChangeClassification(
                touches_invariants=True,
                touched_invariant_ids=matched_ids,
                blocked=True,
                requires_refoundation=True,
                reason=(
                    f"Change touches HARD/META invariants: {matched_ids}. Refoundation required."
                ),
            )

        return ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=matched_ids,
            blocked=False,
            requires_refoundation=False,
            reason=f"Change touches SOFT invariants: {matched_ids}. Allowed with review.",
        )

    @staticmethod
    def _path_matches(change_path: str, protected_path: str) -> bool:
        """Return True if *change_path* matches *protected_path*.

        Matching rules:
        - Exact match: ``maci`` == ``maci``
        - Dot-prefix match: ``maci.role_assignment`` starts with ``maci.``
        - Slash-prefix match: ``maci/enforcer.py`` starts with ``maci/``
        """
        if change_path == protected_path:
            return True
        if change_path.startswith(protected_path + "."):
            return True
        if change_path.startswith(protected_path + "/"):
            return True
        return False


# ---------------------------------------------------------------------------
# ProposalInvariantValidator
# ---------------------------------------------------------------------------


class ProposalInvariantValidator:
    """Validates amendment proposals against invariants.

    Intended to be wired into the proposal engine so that every amendment
    is checked before it enters the deliberation pipeline.
    """

    def __init__(self, manifest: InvariantManifest) -> None:
        self._manifest = manifest
        self._classifier = InvariantClassifier(manifest)

    @property
    def invariant_hash(self) -> str:
        """Public accessor for the manifest's invariant hash."""
        return self._manifest.invariant_hash

    async def validate_proposal(
        self,
        proposed_changes: dict,
        affected_paths: list[str],
    ) -> ChangeClassification:
        """Validate a proposal against invariants.

        1. Classify which invariants are affected.
        2. If HARD/META touched -> raise :class:`ConstitutionalInvariantViolation`.
        3. If SOFT touched -> return classification with ``touches_invariants=True``.
        4. If none touched -> return clean classification.

        Fail-closed: any error during validation rejects the proposal.
        """
        try:
            classification = self._classifier.classify_change(affected_paths)
        except Exception:
            logger.exception(
                "proposal_invariant_validator.error",
                affected_paths=affected_paths,
            )
            fail_classification = ChangeClassification(
                touches_invariants=True,
                touched_invariant_ids=[],
                blocked=True,
                requires_refoundation=False,
                reason="Validation error — fail-closed",
            )
            raise ConstitutionalInvariantViolation(fail_classification) from None

        if classification.blocked:
            logger.warning(
                "proposal_invariant_validator.blocked",
                touched_ids=classification.touched_invariant_ids,
                reason=classification.reason,
            )
            raise ConstitutionalInvariantViolation(classification)

        if classification.touches_invariants:
            logger.info(
                "proposal_invariant_validator.soft_touch",
                touched_ids=classification.touched_invariant_ids,
            )

        return classification


# ---------------------------------------------------------------------------
# RuntimeMutationGuard
# ---------------------------------------------------------------------------

# Roles that may only emit recommendations, never direct writes.
_RECOMMENDATION_ONLY_ROLES = frozenset({"sdpc", "adaptive_governance"})


class RuntimeMutationGuard:
    """Guards runtime mutations against invariant-protected paths.

    SDPC and adaptive governance agents can only *recommend* changes to
    protected paths; direct writes are blocked.
    """

    def __init__(self, manifest: InvariantManifest) -> None:
        self._manifest = manifest
        self._classifier = InvariantClassifier(manifest)

    def validate_mutation(
        self,
        target_path: str,
        operation: str,
        actor_role: str,
    ) -> None:
        """Check whether a runtime mutation is allowed.

        Raises :class:`ConstitutionalInvariantViolation` if:
        - *target_path* is protected by a HARD or META invariant, or
        - *actor_role* is a recommendation-only role writing to a protected path.
        """
        classification = self._classifier.classify_change([target_path])

        # HARD/META invariants block all actors unconditionally.
        if classification.blocked:
            logger.warning(
                "runtime_mutation_guard.blocked",
                target_path=target_path,
                operation=operation,
                actor_role=actor_role,
                reason=classification.reason,
            )
            raise ConstitutionalInvariantViolation(
                classification,
                (
                    f"Runtime mutation blocked: {actor_role} attempted "
                    f"'{operation}' on protected path '{target_path}'"
                ),
            )

        # Recommendation-only roles cannot directly write even to SOFT paths.
        if classification.touches_invariants and actor_role in _RECOMMENDATION_ONLY_ROLES:
            blocked_classification = ChangeClassification(
                touches_invariants=True,
                touched_invariant_ids=classification.touched_invariant_ids,
                blocked=True,
                requires_refoundation=False,
                reason=(
                    f"Role '{actor_role}' may only recommend changes to "
                    f"invariant-protected paths, not write directly."
                ),
            )
            logger.warning(
                "runtime_mutation_guard.role_blocked",
                target_path=target_path,
                operation=operation,
                actor_role=actor_role,
            )
            raise ConstitutionalInvariantViolation(blocked_classification)

        logger.debug(
            "runtime_mutation_guard.allowed",
            target_path=target_path,
            operation=operation,
            actor_role=actor_role,
        )
