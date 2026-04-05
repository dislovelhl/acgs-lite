from __future__ import annotations

import hashlib
from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .governance_core import GovernanceDecision, GovernanceInput, GovernanceReceipt
from .message_processor_components import prepare_message_content_string
from .models import AgentMessage, get_enum_value
from .processing_context import MessageProcessingContext
from .validators import ValidationResult

logger = get_logger(__name__)


class GovernanceCoordinator:
    """Encapsulates governance-input construction and governance-core execution."""

    def __init__(
        self,
        *,
        governance_core_mode: str,
        constitutional_hash: str,
        require_independent_validator: bool,
        requires_independent_validation: Callable[[AgentMessage], bool],
        legacy_governance_core: object,
        swarm_governance_core: object,
        increment_failed_count: Callable[[], None],
    ) -> None:
        self._governance_core_mode = governance_core_mode
        self._constitutional_hash = constitutional_hash
        self._require_independent_validator = require_independent_validator
        self._requires_independent_validation = requires_independent_validation
        self._legacy_governance_core = legacy_governance_core
        self._swarm_governance_core = swarm_governance_core
        self._increment_failed_count = increment_failed_count
        self.shadow_matches = 0
        self.shadow_mismatches = 0
        self.shadow_errors = 0

    def sync_runtime(
        self,
        *,
        constitutional_hash: str,
        require_independent_validator: bool,
        requires_independent_validation: Callable[[AgentMessage], bool],
    ) -> None:
        self._constitutional_hash = constitutional_hash
        self._require_independent_validator = require_independent_validator
        self._requires_independent_validation = requires_independent_validation

    def build_governance_input(self, msg: AgentMessage) -> GovernanceInput:
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        producer_role = metadata.get("maci_role")
        if not isinstance(producer_role, str) or not producer_role.strip():
            security_role = (
                msg.security_context.get("maci_role")
                if isinstance(msg.security_context, dict)
                else None
            )
            producer_role = security_role if isinstance(security_role, str) else None

        validator_ids: list[str] = []
        for key in ("validated_by_agent", "independent_validator_id"):
            raw_validator = metadata.get(key)
            if isinstance(raw_validator, str) and raw_validator.strip():
                validator_ids.append(raw_validator.strip())

        content_str = prepare_message_content_string(msg)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:32]
        requires_independent_validator = (
            self._require_independent_validator and self._requires_independent_validation(msg)
        )

        return GovernanceInput(
            tenant_id=msg.tenant_id,
            trace_id=msg.message_id,
            message_id=msg.message_id,
            producer_id=msg.from_agent or "unknown-producer",
            producer_role=producer_role,
            action_type=get_enum_value(msg.message_type),
            content=content_str,
            content_hash=content_hash,
            constitutional_hash=msg.constitutional_hash,
            autonomy_tier=get_enum_value(msg.autonomy_tier) if msg.autonomy_tier else None,
            requires_independent_validator=requires_independent_validator,
            security_scan_result="passed",
            validator_ids=tuple(dict.fromkeys(validator_ids)),
        )

    async def run(self, context: MessageProcessingContext) -> ValidationResult | None:
        msg = context.message
        governance_input = self.build_governance_input(msg)
        context.governance_input = governance_input
        legacy_decision = await self._legacy_governance_core.validate_local(governance_input)
        legacy_receipt = self._legacy_governance_core.build_receipt(
            governance_input,
            legacy_decision,
        )

        selected_decision = legacy_decision
        selected_receipt = legacy_receipt
        shadow_metadata: JSONDict | None = None

        if self._governance_core_mode in {"shadow", "swarm_enforced"}:
            if self._governance_core_mode == "shadow" and not self.is_swarm_available():
                swarm_error = getattr(self._swarm_governance_core, "_constitution_error", None)
                self.shadow_errors += 1
                shadow_metadata = {
                    "mode": "shadow",
                    "status": "error",
                    "legacy_allowed": legacy_decision.allowed,
                    "swarm_allowed": None,
                    "error": swarm_error
                    if isinstance(swarm_error, str) and swarm_error
                    else "swarm unavailable",
                }
                self.store_governance_artifacts(
                    context=context,
                    decision=selected_decision,
                    receipt=selected_receipt,
                    shadow_metadata=shadow_metadata,
                )
                if selected_decision.allowed:
                    return None
                self._increment_failed_count()
                return self.build_governance_failure_result(
                    governance_input=governance_input,
                    decision=selected_decision,
                    receipt=selected_receipt,
                    shadow_metadata=shadow_metadata,
                )
            try:
                swarm_decision = await self._swarm_governance_core.validate_local(governance_input)
                peer_validation = (
                    await self._swarm_governance_core.validate_peer(governance_input)
                    if swarm_decision.allowed
                    else None
                )
                trust_score = (
                    await self._swarm_governance_core.score_governance(
                        governance_input,
                        peer_validation,
                    )
                    if swarm_decision.allowed
                    else None
                )
                swarm_decision = GovernanceDecision(
                    allowed=(
                        swarm_decision.allowed
                        and (peer_validation.approved if peer_validation is not None else True)
                    ),
                    blocking_stage=(
                        swarm_decision.blocking_stage
                        or (
                            "peer_validation"
                            if peer_validation is not None and not peer_validation.approved
                            else None
                        )
                    ),
                    reasons=(
                        swarm_decision.reasons
                        if peer_validation is None or peer_validation.approved
                        else tuple(
                            reason
                            for reason in (*swarm_decision.reasons, peer_validation.reason)
                            if reason
                        )
                    ),
                    rule_hits=swarm_decision.rule_hits,
                    peer_votes=(
                        peer_validation.to_metadata() if peer_validation is not None else {}
                    ),
                    trust_score=trust_score,
                    constitutional_hash=swarm_decision.constitutional_hash,
                    swarm_constitutional_hash=swarm_decision.swarm_constitutional_hash,
                    engine_mode=swarm_decision.engine_mode,
                )
                swarm_receipt = self._swarm_governance_core.build_receipt(
                    governance_input,
                    swarm_decision,
                )
            except (
                AttributeError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                logger.warning("Swarm governance core failed", exc_info=True)
                if self._governance_core_mode == "swarm_enforced":
                    self._increment_failed_count()
                    return self.build_governance_failure_result(
                        governance_input=governance_input,
                        decision=GovernanceDecision(
                            allowed=False,
                            blocking_stage="swarm_error",
                            reasons=(str(exc),),
                            constitutional_hash=self._constitutional_hash,
                            engine_mode="swarm",
                        ),
                        receipt=GovernanceReceipt(
                            receipt_id=f"swarm:{governance_input.message_id}",
                            engine_mode="swarm",
                            message_id=governance_input.message_id,
                            producer_id=governance_input.producer_id,
                            content_hash=governance_input.content_hash,
                            constitutional_hash=governance_input.constitutional_hash,
                            allowed=False,
                            blocking_stage="swarm_error",
                            reasons=(str(exc),),
                        ),
                    )
                self.shadow_errors += 1
                shadow_metadata = {
                    "mode": "shadow",
                    "status": "error",
                    "legacy_allowed": legacy_decision.allowed,
                    "swarm_allowed": None,
                    "error": str(exc),
                }
            else:
                parity_status = (
                    "match" if legacy_decision.allowed == swarm_decision.allowed else "mismatch"
                )
                if parity_status == "match":
                    self.shadow_matches += 1
                else:
                    self.shadow_mismatches += 1
                shadow_metadata = {
                    "mode": "shadow",
                    "status": parity_status,
                    "legacy_allowed": legacy_decision.allowed,
                    "swarm_allowed": swarm_decision.allowed,
                    "legacy_receipt": legacy_receipt.to_metadata(),
                    "swarm_receipt": swarm_receipt.to_metadata(),
                }
                if self._governance_core_mode == "swarm_enforced":
                    selected_decision = swarm_decision
                    selected_receipt = swarm_receipt

        self.store_governance_artifacts(
            context=context,
            decision=selected_decision,
            receipt=selected_receipt,
            shadow_metadata=shadow_metadata,
        )
        if selected_decision.allowed:
            return None

        self._increment_failed_count()
        return self.build_governance_failure_result(
            governance_input=governance_input,
            decision=selected_decision,
            receipt=selected_receipt,
            shadow_metadata=shadow_metadata,
        )

    def store_governance_artifacts(
        self,
        *,
        context: MessageProcessingContext,
        decision: GovernanceDecision,
        receipt: GovernanceReceipt,
        shadow_metadata: JSONDict | None,
    ) -> None:
        context.governance_decision = decision
        context.governance_receipt = receipt
        context.governance_shadow_metadata = shadow_metadata

    def attach_governance_metadata(
        self,
        *,
        context: MessageProcessingContext,
        result: ValidationResult,
    ) -> None:
        result.metadata["governance_core_mode"] = self._governance_core_mode
        decision_metadata = self._to_governance_metadata(context.governance_decision)
        receipt_metadata = self._to_governance_metadata(context.governance_receipt)
        if decision_metadata is not None:
            result.metadata["governance_decision"] = decision_metadata
        if receipt_metadata is not None:
            result.metadata["governance_receipt"] = receipt_metadata
        if isinstance(context.governance_shadow_metadata, dict):
            result.metadata["governance_shadow"] = context.governance_shadow_metadata

    @staticmethod
    def _to_governance_metadata(value: object) -> JSONDict | None:
        to_metadata = getattr(value, "to_metadata", None)
        if not callable(to_metadata):
            return None
        metadata = to_metadata()
        return metadata if isinstance(metadata, dict) else None

    def build_governance_failure_result(
        self,
        *,
        governance_input: GovernanceInput,
        decision: GovernanceDecision,
        receipt: GovernanceReceipt,
        shadow_metadata: JSONDict | None = None,
    ) -> ValidationResult:
        failure_result = ValidationResult(
            is_valid=False,
            errors=list(decision.reasons) or ["Governance validation rejected the message"],
            metadata={
                "rejection_reason": decision.blocking_stage or "governance_core_rejected",
                "rejection_stage": "governance",
                "governance_core_mode": self._governance_core_mode,
                "governance_decision": decision.to_metadata(),
                "governance_receipt": receipt.to_metadata(),
                "governance_input": {
                    "message_id": governance_input.message_id,
                    "producer_id": governance_input.producer_id,
                    "action_type": governance_input.action_type,
                    "constitutional_hash": governance_input.constitutional_hash,
                },
            },
        )
        if shadow_metadata is not None:
            failure_result.metadata["governance_shadow"] = shadow_metadata
        return failure_result

    def is_swarm_available(self) -> bool:
        return getattr(self._swarm_governance_core, "is_available", lambda: False)()

    @property
    def swarm_governance_core(self) -> object:
        return self._swarm_governance_core
