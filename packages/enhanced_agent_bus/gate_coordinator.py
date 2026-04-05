from __future__ import annotations

from collections.abc import Awaitable, Callable

from .message_processor_components import (
    enforce_autonomy_tier_rules,
    run_message_validation_gates,
)
from .models import AgentMessage, MessageType
from .processing_context import MessageProcessingContext
from .validators import ValidationResult


class GateCoordinator:
    """Encapsulates pre-processing gates before deeper governance/verification work."""

    def __init__(
        self,
        *,
        require_independent_validator: bool,
        independent_validator_threshold: float,
        security_scanner: object,
        record_agent_workflow_event: Callable[..., None],
        increment_failed_count: Callable[[], None],
        advisory_blocked_types: frozenset[str],
    ) -> None:
        self._require_independent_validator = require_independent_validator
        self._independent_validator_threshold = independent_validator_threshold
        self._security_scanner = security_scanner
        self._record_agent_workflow_event = record_agent_workflow_event
        self._increment_failed_count = increment_failed_count
        self._advisory_blocked_types = advisory_blocked_types

    def sync_runtime(
        self,
        *,
        require_independent_validator: bool,
        independent_validator_threshold: float,
        security_scanner: object,
        record_agent_workflow_event: Callable[..., None],
    ) -> None:
        self._require_independent_validator = require_independent_validator
        self._independent_validator_threshold = independent_validator_threshold
        self._security_scanner = security_scanner
        self._record_agent_workflow_event = record_agent_workflow_event

    async def perform_security_scan(self, msg: AgentMessage) -> ValidationResult | None:
        security_res = await self._security_scanner.scan(msg)
        if security_res:
            self._increment_failed_count()
            return security_res  # type: ignore[no-any-return]
        return None

    def requires_independent_validation(self, msg: AgentMessage) -> bool:
        impact_score = getattr(msg, "impact_score", 0.0)
        if impact_score is None:
            impact_score = 0.0
        if impact_score >= self._independent_validator_threshold:
            return True
        return msg.message_type in {
            MessageType.CONSTITUTIONAL_VALIDATION,
            MessageType.GOVERNANCE_REQUEST,
        }

    def enforce_independent_validator_gate(self, msg: AgentMessage) -> ValidationResult | None:
        if not self._require_independent_validator:
            return None
        if not self.requires_independent_validation(msg):
            return None
        self._record_agent_workflow_event(
            event_type="intervention",
            msg=msg,
            reason="independent_validator_required",
        )

        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        validator_id = metadata.get("validated_by_agent") or metadata.get(
            "independent_validator_id"
        )
        validation_stage = metadata.get("validation_stage")

        if not isinstance(validator_id, str) or not validator_id.strip():
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_missing",
            )
            return ValidationResult(
                is_valid=False,
                errors=["Independent validator metadata is required for this message"],
                metadata={"rejection_reason": "independent_validator_missing"},
            )

        if validator_id == msg.from_agent:
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_self_validation",
            )
            return ValidationResult(
                is_valid=False,
                errors=["Independent validator must not be the originating agent"],
                metadata={"rejection_reason": "independent_validator_self_validation"},
            )

        if validation_stage is not None and validation_stage != "independent":
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_invalid_stage",
            )
            return ValidationResult(
                is_valid=False,
                errors=[
                    "validation_stage must be 'independent' when validator evidence is present"
                ],
                metadata={"rejection_reason": "independent_validator_invalid_stage"},
            )
        return None

    def enforce_autonomy_tier(self, msg: AgentMessage) -> ValidationResult | None:
        return enforce_autonomy_tier_rules(
            msg=msg,
            advisory_blocked_types=self._advisory_blocked_types,
        )

    def detect_prompt_injection(self, msg: AgentMessage) -> ValidationResult | None:
        return self._security_scanner.detect_prompt_injection(msg)  # type: ignore[no-any-return]

    async def run(
        self,
        context: MessageProcessingContext,
        governance_runner: Callable[[MessageProcessingContext], Awaitable[ValidationResult | None]],
    ) -> ValidationResult | None:
        msg = context.message
        gate_result = await run_message_validation_gates(
            msg=msg,
            autonomy_gate=self.enforce_autonomy_tier,
            security_scan=self.perform_security_scan,
            independent_validator_gate=self.enforce_independent_validator_gate,
            prompt_injection_gate=self.detect_prompt_injection,
            increment_failure=self._increment_failed_count,
        )
        if gate_result is not None:
            return gate_result
        return await governance_runner(context)
