"""
Temporal Policy Middleware for ACGS-2 Pipeline.

Enforces Agent-C-inspired temporal ordering constraints via OPA.
Calls OPAClient.evaluate_with_history() for every governance action
(any message with a `requested_tool` in the governed set) before
passing to downstream middleware.

On OPA deny or error: pipeline short-circuits with is_valid=False (fail-closed).
On OPA allow: action label is appended to ctx.action_history and processing
continues.

Constitutional Hash: 608508a9bd224290
NIST 800-53 AC-3, AU-9
"""

from __future__ import annotations

import time
from dataclasses import dataclass

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

from ..opa_client import get_opa_client
from ..pipeline.context import PipelineContext
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig

logger = get_logger(__name__)
# Actions for which temporal ordering is evaluated.
# All others (e.g., read-only queries) are passed through without OPA call.
_GOVERNED_ACTIONS: frozenset[str] = frozenset(
    {
        "modify_policy",
        "apply_policy_change",
        "update_policy",
        "execute_action",
        "commit_governance_decision",
        "approve_message",
        "reject_message",
        "deliver_message",
        "audit_decision",
        "write_audit",
        "extract_rules",
    }
)


@dataclass
class GovernanceRule:
    """A temporal governance rule with optional TTL.

    Attributes:
        rule_id: Unique identifier for this rule.
        action: Governed action this rule applies to.
        created_at: Timestamp when the rule was created.
        ttl_seconds: Time-to-live in seconds. None = no expiry.
        policy_path: OPA policy path for evaluation.

    Constitutional Hash: 608508a9bd224290
    """

    rule_id: str
    action: str
    created_at: float
    ttl_seconds: int | None = None
    policy_path: str = "data.acgs.temporal.allow"

    def is_expired(self, now: float | None = None) -> bool:
        """Check if this rule has expired based on TTL.

        Args:
            now: Current timestamp. Uses time.time() if None.

        Returns:
            True if rule has expired, False otherwise.
        """
        if self.ttl_seconds is None:
            return False
        if now is None:
            now = time.time()
        return now > self.created_at + self.ttl_seconds


class TemporalPolicyMiddleware(BaseMiddleware):
    """
    Middleware that evaluates temporal ordering constraints via OPA
    before each governed pipeline action.

    Reads:
        ctx.message.requested_tool  — action label to check
        ctx.action_history          — completed actions in this session
        ctx.impact_score            — used by OPA rules (e.g., HITL threshold)
        ctx.constitutional_validated — passed to OPA input

    Writes:
        ctx.action_history          — appends action label on allow
        ctx.early_result            — set to is_valid=False on deny

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: MiddlewareConfig | None = None) -> None:
        super().__init__(config or MiddlewareConfig(timeout_ms=50, fail_closed=True))
        self._governance_rules: dict[str, GovernanceRule] = {}

    def register_governance_rule(self, rule: GovernanceRule) -> None:
        """Register a governance rule with optional TTL."""
        self._governance_rules[rule.rule_id] = rule

    def enforce_rule(self, rule: GovernanceRule, now: float | None = None) -> ValidationResult:
        """Enforce a governance rule, checking TTL.

        Fail-closed semantics: expired rules produce an explicit
        DENY (is_valid=False), never a silent pass-through.

        Args:
            rule: The governance rule to enforce.
            now: Current timestamp. Uses time.time() if None.

        Returns:
            ValidationResult with is_valid=True (PERMIT) or
            is_valid=False (DENY) if the rule has expired.

        Constitutional Hash: 608508a9bd224290
        """
        if now is None:
            now = time.time()

        if rule.is_expired(now):
            vr = ValidationResult(
                is_valid=False,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            vr.add_error(
                f"temporal_ttl: rule {rule.rule_id!r} expired "
                f"(ttl={rule.ttl_seconds}s, age="
                f"{now - rule.created_at:.0f}s); fail-closed"
            )
            logger.warning(
                "TemporalPolicyMiddleware: TTL EXPIRED — rule=%r ttl=%rs age=%.0fs",
                rule.rule_id,
                rule.ttl_seconds,
                now - rule.created_at,
            )
            return vr

        return ValidationResult(
            is_valid=True,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def process(self, context: PipelineContext) -> PipelineContext:
        context.add_middleware("TemporalPolicyMiddleware")

        action: str | None = getattr(context.message, "requested_tool", None)
        if not action or action not in _GOVERNED_ACTIONS:
            # No governed action in this message — pass through unchanged.
            return await self._call_next(context)

        # --- TTL enforcement on registered governance rules ---
        now = time.time()
        for rule in self._governance_rules.values():
            if rule.action == action:
                ttl_result = self.enforce_rule(rule, now)
                if not ttl_result.is_valid:
                    context.set_early_result(ttl_result)
                    return context

        input_data = {
            "action": action,
            "impact_score": context.impact_score,
            "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        }

        try:
            opa = get_opa_client()
            result = await opa.evaluate_with_history(
                input_data=input_data,
                action_history=list(context.action_history),
                policy_path="data.acgs.temporal.allow",
            )
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            logger.error(
                "TemporalPolicyMiddleware: OPA call failed for action=%r — blocking (fail-closed): %s",
                action,
                exc,
            )
            vr = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            vr.add_error(
                f"temporal_policy: OPA unavailable for action={action!r}; fail-closed block"
            )
            context.set_early_result(vr)
            return context

        if not result.get("allowed", False):
            reason = result.get("reason", "temporal ordering violation")
            logger.warning(
                "TemporalPolicyMiddleware: BLOCKED — action=%r reason=%r",
                action,
                reason,
            )
            vr = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            vr.add_error(f"temporal:{reason}")
            vr.metadata["temporal_violations"] = result.get("metadata", {})
            context.set_early_result(vr)
            return context

        # Permitted — record action in history and continue.
        context.action_history.append(action)
        logger.debug(
            "TemporalPolicyMiddleware: ALLOWED — action=%r history=%r",
            action,
            context.action_history,
        )
        return await self._call_next(context)
