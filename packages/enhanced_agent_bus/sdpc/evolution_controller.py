from __future__ import annotations

from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType
from enhanced_agent_bus.observability.structured_logging import get_logger

# Import invariant guard for mutation protection
try:
    from enhanced_agent_bus.constitutional.invariant_guard import (
        ConstitutionalInvariantViolation,
        RuntimeMutationGuard,
    )
    from enhanced_agent_bus.constitutional.invariants import get_default_manifest
except ImportError:
    RuntimeMutationGuard = None  # type: ignore[assignment,misc]
    ConstitutionalInvariantViolation = None  # type: ignore[assignment,misc]
    get_default_manifest = None  # type: ignore[assignment]

logger = get_logger(__name__)

_MUTATIONS = {
    IntentType.FACTUAL.value: "MUTATION: Extreme Grounding enforced. Cross-verify every date and location.",
    IntentType.REASONING.value: "MUTATION: Chain-of-Thought verified. Explicitly list logical dependencies between steps.",
    IntentType.CREATIVE.value: "MUTATION: Tone Adjustment. Ensure higher variety in sentence structure and imagery.",
    IntentType.GENERAL.value: "MUTATION: Conciseness. Reduce verbosity and focus on direct answers.",
}


class EvolutionController:
    def __init__(self, failure_threshold: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.failure_history = {intent.value: 0 for intent in IntentType}
        self.dynamic_mutations = {intent.value: [] for intent in IntentType}
        self._mutation_guard: RuntimeMutationGuard | None = None  # type: ignore[valid-type]
        if RuntimeMutationGuard is not None and get_default_manifest is not None:
            try:
                self._mutation_guard = RuntimeMutationGuard(get_default_manifest())
            except Exception:
                logger.warning("SDPC: failed to initialize RuntimeMutationGuard")
                self._mutation_guard = None

    def record_feedback(self, intent: IntentType, verification_results: dict[str, bool]) -> None:
        if all(verification_results.values()):
            self.failure_history[intent.value] = 0
            logger.info("SDPC feedback success for %s", intent.value)
            return
        self.failure_history[intent.value] += 1
        logger.info("SDPC feedback failure for %s", intent.value)
        if self.failure_history[intent.value] >= self.failure_threshold:
            self._trigger_mutation(intent)

    def _trigger_mutation(self, intent: IntentType) -> None:
        # Check invariant guard before applying mutation
        if self._mutation_guard is not None:
            try:
                self._mutation_guard.validate_mutation(
                    f"sdpc.mutations.{intent.value}", "write", "sdpc"
                )
            except ConstitutionalInvariantViolation as exc:
                logger.warning(
                    "SDPC mutation blocked by invariant guard for %s: %s",
                    intent.value,
                    str(exc),
                )
                self.failure_history[intent.value] = 0
                return

        new_instruction = _MUTATIONS.get(
            intent.value, "MUTATION: Adhere strictly to user constraints."
        )
        if new_instruction not in self.dynamic_mutations.setdefault(intent.value, []):
            self.dynamic_mutations[intent.value].append(new_instruction)
        self.failure_history[intent.value] = 0
        logger.info("SDPC mutation triggered for %s", intent.value)

    def get_mutations(self, intent: IntentType) -> list[str]:
        return list(self.dynamic_mutations.get(intent.value, []))

    def reset_mutations(self, intent: IntentType | None = None) -> None:
        if intent is None:
            for key in list(self.dynamic_mutations.keys()):
                self.dynamic_mutations[key] = []
                self.failure_history[key] = 0
            return
        self.dynamic_mutations[intent.value] = []
        self.failure_history[intent.value] = 0
