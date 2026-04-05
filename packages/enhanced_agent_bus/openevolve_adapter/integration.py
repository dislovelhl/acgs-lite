"""
OpenEvolve Governance Adapter — MessageProcessor Integration
Constitutional Hash: 608508a9bd224290

Provides ``EvolutionMessageHandler`` — a handler that plugs into
``MessageProcessor`` via ``register_handler`` to process
``MessageType.GOVERNANCE_REQUEST`` messages that carry evolution candidates.

The handler:
1. Deserialises an ``EvolutionCandidate`` from the message payload.
2. Runs the three-stage ``CascadeEvaluator`` pipeline.
3. If the cascade passes, runs the ``RolloutController`` gate.
4. Returns a ``ValidationResult`` with structured metadata understood by
   the existing bus infrastructure.

Wire-up::

    from enhanced_agent_bus.openevolve_adapter.integration import (
        EvolutionMessageHandler,
        wire_into_processor,
    )

    handler = EvolutionMessageHandler(
        verifier=my_verifier,
        # optional: cascade_evaluator, rollout_controller
    )
    wire_into_processor(processor, handler)

Message payload contract (``AgentMessage.metadata``)::

    {
        "candidate_id":           str,
        "constitutional_hash":    str,          # must equal 608508a9bd224290
        "risk_tier":              str,          # "low"|"medium"|"high"|"critical"
        "proposed_rollout_stage": str,          # "canary"|"shadow"|"partial"|"full"
        "performance_score":      float,        # 0.0 – 1.0
        "verification_payload": {
            "validator_id":       str,
            "verified_at":        str,          # ISO-8601
            "constitutional_hash": str,
            "syntax_valid":       bool,
            "policy_compliant":   bool,
            "safety_score":       float,
            "notes":              str           # optional
        },
        "mutation_trace": [                     # optional, default []
            {"operator": str, "parent_id": str, "description": str}
        ],
        "fitness_inputs": {}                    # optional, default {}
    }
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from enhanced_agent_bus.observability.structured_logging import get_logger

from .candidate import (
    EvolutionCandidate,
    MutationRecord,
    RiskTier,
    RolloutStage,
    VerificationPayload,
)
from .cascade import CascadeEvaluator
from .evolver import ConstitutionalVerifier
from .rollout import RolloutController

if TYPE_CHECKING:
    from enhanced_agent_bus.message_processor import MessageProcessor

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "608508a9bd224290"  # pragma: allowlist secret


def _build_validation_result(
    *,
    is_valid: bool,
    errors: list[str],
    metadata: dict[str, Any],
) -> Any:
    """Lazy import of ValidationResult to avoid circular imports at module load."""
    try:
        from enhanced_agent_bus.models import ValidationResult

        return ValidationResult(is_valid=is_valid, errors=errors, metadata=metadata)
    except ImportError:
        # Minimal stub for unit-testing without the full bus installed
        class _VR:
            def __init__(self, **kw: Any) -> None:
                self.__dict__.update(kw)

        return _VR(is_valid=is_valid, errors=errors, metadata=metadata)


def _deserialise_candidate(meta: dict[str, Any]) -> EvolutionCandidate:
    """
    Build an ``EvolutionCandidate`` from the message metadata dict.

    Raises:
        KeyError, ValueError: If required fields are missing or invalid.
    """
    vp_raw: dict[str, Any] = meta["verification_payload"]
    vp = VerificationPayload(
        validator_id=vp_raw["validator_id"],
        verified_at=vp_raw.get("verified_at", datetime.now(UTC).isoformat()),
        constitutional_hash=vp_raw["constitutional_hash"],
        syntax_valid=bool(vp_raw["syntax_valid"]),
        policy_compliant=bool(vp_raw["policy_compliant"]),
        safety_score=float(vp_raw["safety_score"]),
        notes=vp_raw.get("notes", ""),
    )

    trace_raw: list[dict[str, Any]] = meta.get("mutation_trace", [])
    trace = [
        MutationRecord(
            operator=r["operator"],
            parent_id=r["parent_id"],
            description=r.get("description", ""),
            timestamp=r.get("timestamp", datetime.now(UTC).isoformat()),
        )
        for r in trace_raw
    ]

    return EvolutionCandidate(
        candidate_id=meta["candidate_id"],
        mutation_trace=trace,
        fitness_inputs=meta.get("fitness_inputs", {}),
        verification_payload=vp,
        constitutional_hash=meta["constitutional_hash"],
        risk_tier=RiskTier(meta["risk_tier"]),
        proposed_rollout_stage=RolloutStage(meta["proposed_rollout_stage"]),
        metadata={
            k: v
            for k, v in meta.items()
            if k
            not in {
                "candidate_id",
                "constitutional_hash",
                "risk_tier",
                "proposed_rollout_stage",
                "performance_score",
                "verification_payload",
                "mutation_trace",
                "fitness_inputs",
            }
        },
    )


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class EvolutionMessageHandler:
    """
    ``MessageProcessor``-compatible handler for governed evolution candidates.

    Registered against ``MessageType.GOVERNANCE_REQUEST``; messages that do NOT
    carry an ``"evolution_candidate": true`` flag in metadata are skipped and
    passed through as valid (allowing non-evolution governance messages to flow
    through unaffected).

    Args:
        verifier: External :class:`ConstitutionalVerifier` — injected per MACI rules.
        cascade_evaluator: Pre-built :class:`CascadeEvaluator` (constructed from
            *verifier* if not supplied).
        rollout_controller: Pre-built :class:`RolloutController` (new instance if
            not supplied).
    """

    def __init__(
        self,
        verifier: ConstitutionalVerifier,
        *,
        cascade_evaluator: CascadeEvaluator | None = None,
        rollout_controller: RolloutController | None = None,
    ) -> None:
        self._cascade = cascade_evaluator or CascadeEvaluator(verifier)
        self._rollout = rollout_controller or RolloutController()
        self._counts: dict[str, int] = {
            "received": 0,
            "skipped": 0,
            "cascade_passed": 0,
            "cascade_failed": 0,
            "gate_passed": 0,
            "gate_failed": 0,
            "deserialise_errors": 0,
        }

    async def __call__(self, msg: Any) -> Any:
        """
        Process one ``AgentMessage``.

        Compatible with the ``MessageProcessor`` handler signature:
        ``async def handler(msg: AgentMessage) -> ValidationResult``.
        """
        self._counts["received"] += 1
        meta: dict[str, Any] = getattr(msg, "metadata", {}) or {}

        # Only handle messages explicitly flagged as evolution candidates
        if not meta.get("evolution_candidate"):
            self._counts["skipped"] += 1
            return _build_validation_result(
                is_valid=True,
                errors=[],
                metadata={"evolution_handler": "skipped_not_an_evolution_message"},
            )

        # --- Deserialise ---
        try:
            candidate = _deserialise_candidate(meta)
        except (KeyError, ValueError, TypeError) as exc:
            self._counts["deserialise_errors"] += 1
            logger.warning(
                "Evolution candidate deserialisation failed",
                message_id=getattr(msg, "message_id", "?"),
                error=str(exc),
            )
            return _build_validation_result(
                is_valid=False,
                errors=[f"Candidate deserialisation error: {exc}"],
                metadata={"evolution_handler": "deserialise_error"},
            )

        performance_score = float(meta.get("performance_score", 0.0))

        # --- Cascade evaluation ---
        cascade_result = await self._cascade.evaluate(
            candidate, performance_score=performance_score
        )

        if not cascade_result.passed:
            self._counts["cascade_failed"] += 1
            logger.info(
                "Evolution candidate rejected by cascade",
                candidate_id=candidate.candidate_id,
                exit_stage=cascade_result.exit_stage.value,
                reason=cascade_result.rejection_reason,
            )
            return _build_validation_result(
                is_valid=False,
                errors=[cascade_result.rejection_reason],
                metadata={
                    "evolution_handler": "cascade_rejected",
                    "exit_stage": cascade_result.exit_stage.value,
                    "score": cascade_result.score,
                    "cascade": cascade_result.to_dict(),
                },
            )

        self._counts["cascade_passed"] += 1

        # --- Rollout gate ---
        gate_decision = self._rollout.gate(candidate)

        if not gate_decision.allowed:
            self._counts["gate_failed"] += 1
            logger.info(
                "Evolution candidate denied at rollout gate",
                candidate_id=candidate.candidate_id,
                reason=gate_decision.reason,
            )
            return _build_validation_result(
                is_valid=False,
                errors=[gate_decision.reason],
                metadata={
                    "evolution_handler": "gate_denied",
                    "gate": gate_decision.to_dict(),
                    "cascade": cascade_result.to_dict(),
                },
            )

        self._counts["gate_passed"] += 1
        logger.info(
            "Evolution candidate approved",
            candidate_id=candidate.candidate_id,
            fitness=cascade_result.score,
            rollout_stage=candidate.proposed_rollout_stage.value,
        )
        return _build_validation_result(
            is_valid=True,
            errors=[],
            metadata={
                "evolution_handler": "approved",
                "candidate_id": candidate.candidate_id,
                "fitness": cascade_result.score,
                "rollout_stage": candidate.proposed_rollout_stage.value,
                "gate_reason": gate_decision.reason,
                "cascade": cascade_result.to_dict(),
                "gate": gate_decision.to_dict(),
            },
        )

    def metrics(self) -> dict[str, Any]:
        return dict(self._counts)


# ---------------------------------------------------------------------------
# Wire-up helper
# ---------------------------------------------------------------------------


def wire_into_processor(
    processor: MessageProcessor,
    handler: EvolutionMessageHandler,
) -> None:
    """
    Register *handler* on *processor* for ``GOVERNANCE_REQUEST`` messages.

    Args:
        processor: A live :class:`~enhanced_agent_bus.message_processor.MessageProcessor`.
        handler: The :class:`EvolutionMessageHandler` to attach.

    Example::

        wire_into_processor(processor, EvolutionMessageHandler(verifier=my_verifier))
    """
    try:
        from enhanced_agent_bus.enums import MessageType
    except ImportError:
        logger.warning("MessageType not importable — skipping handler registration")
        return

    processor.register_handler(MessageType.GOVERNANCE_REQUEST, handler)
    logger.info(
        "EvolutionMessageHandler registered",
        message_type=MessageType.GOVERNANCE_REQUEST.value,
    )
