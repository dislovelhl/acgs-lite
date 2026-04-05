"""
Tool Privilege Middleware for ACGS-2 Pipeline.

Implements Progent-inspired least-privilege enforcement for tool calls.
Each MACI role is mapped to a deterministic allowlist; any tool call
outside the allowlist — or explicitly denied — is blocked before execution.

Key properties:
- Deterministic: no LLM judgment, always fires the same way
- Non-intrusive: wraps the pipeline; does not touch agent internals
- Fail-closed: unknown roles and unresolved guards default to block
- Constitutional immutability: modify_constitutional_hash is hard-denied for ALL roles

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

from ..maci_enforcement import MACIRole
from ..pipeline.context import PipelineContext
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig

logger = get_logger(__name__)
# ---------------------------------------------------------------------------
# Policy primitives
# ---------------------------------------------------------------------------

# Tool names that map to constitutional hash modification — globally forbidden.
_CONSTITUTIONAL_MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "modify_constitutional_hash",
        "rotate_constitutional_hash",
        "update_constitutional_hash",
        "set_constitutional_hash",
        "override_constitutional_hash",
    }
)

# Tool names that represent execution of governed actions.
# MACI EXECUTOR role requires 2-of-3 consensus before any of these.
_HIGH_IMPACT_EXECUTION_TOOLS: frozenset[str] = frozenset(
    {
        "execute_action",
        "deliver_message",
        "apply_policy_change",
        "commit_governance_decision",
    }
)


@dataclass(frozen=True)
class ToolCallPolicy:
    """
    Progent-inspired per-role tool privilege specification.

    Attributes:
        role: The MACI role this policy governs.
        allowed_tools: Frozenset of permitted tool names. Unlisted tools are
            denied by default (principle of least privilege).
        denied_tools: Frozenset of explicitly forbidden tool names. Checked
            before allowed_tools for defence-in-depth.
        guards: List of callables (context → bool). If any guard returns False,
            the tool call is blocked even when in the allowlist.
        deny_fallback: Action taken on deny — one of "block", "route_to_hitl",
            "reject_with_reason". Default is "block".
    """

    role: MACIRole
    allowed_tools: frozenset[str]
    denied_tools: frozenset[str] = field(default_factory=frozenset)
    guards: tuple[Callable[[PipelineContext], bool], ...] = field(default_factory=tuple)
    deny_fallback: str = "block"


# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------


def _requires_constitutional_validation(ctx: PipelineContext) -> bool:
    """Tool call permitted only after constitutional hash has been verified."""
    return ctx.constitutional_validated


def _requires_maci_consensus(ctx: PipelineContext) -> bool:
    """High-impact execution requires MACI 2-of-3 consensus on context."""
    if ctx.maci_result is None:
        return False
    consensus = getattr(ctx.maci_result, "consensus_ratio", None)
    if consensus is None:
        return False
    return float(consensus) >= 0.67


# ---------------------------------------------------------------------------
# MACI role → tool policy map
#
# Aligned with the role-action matrix in maci_enforcement.py:
#   EXECUTIVE    → PROPOSE, SYNTHESIZE, QUERY
#   LEGISLATIVE  → EXTRACT_RULES, SYNTHESIZE, QUERY
#   JUDICIAL     → VALIDATE, AUDIT, QUERY, EMERGENCY_COOLDOWN
#   MONITOR      → MONITOR_ACTIVITY, QUERY
#   AUDITOR      → AUDIT, QUERY
#   CONTROLLER   → ENFORCE_CONTROL, QUERY
#   IMPLEMENTER  → SYNTHESIZE, QUERY
# ---------------------------------------------------------------------------

MACI_TOOL_POLICIES: dict[MACIRole, ToolCallPolicy] = {
    MACIRole.EXECUTIVE: ToolCallPolicy(
        role=MACIRole.EXECUTIVE,
        allowed_tools=frozenset(
            {
                "propose_message",
                "synthesize_response",
                "read_policy",
                "read_context",
                "read_audit",
                "query_knowledge",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "validate_message", "write_audit"}),
        guards=(_requires_constitutional_validation,),
        deny_fallback="reject_with_reason",
    ),
    MACIRole.LEGISLATIVE: ToolCallPolicy(
        role=MACIRole.LEGISLATIVE,
        allowed_tools=frozenset(
            {
                "extract_rules",
                "synthesize_policy",
                "read_policy",
                "read_context",
                "read_audit",
                "query_knowledge",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "validate_message", "write_audit"}),
        guards=(_requires_constitutional_validation,),
        deny_fallback="reject_with_reason",
    ),
    MACIRole.JUDICIAL: ToolCallPolicy(
        role=MACIRole.JUDICIAL,
        allowed_tools=frozenset(
            {
                "validate_message",
                "audit_decision",
                "query_knowledge",
                "read_policy",
                "read_context",
                "read_audit",
                "emergency_cooldown",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"propose_message", "execute_action", "apply_policy_change"}),
        # JUDICIAL validation requires hash to be verified first
        guards=(_requires_constitutional_validation,),
        deny_fallback="route_to_hitl",
    ),
    MACIRole.MONITOR: ToolCallPolicy(
        role=MACIRole.MONITOR,
        allowed_tools=frozenset(
            {
                "monitor_activity",
                "query_knowledge",
                "read_context",
                "read_audit",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "write_audit", "modify_policy", "validate_message"}),
        deny_fallback="block",
    ),
    MACIRole.AUDITOR: ToolCallPolicy(
        role=MACIRole.AUDITOR,
        allowed_tools=frozenset(
            {
                "audit_decision",
                "read_audit",
                "query_knowledge",
                "read_policy",
                "read_context",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "modify_policy", "propose_message"}),
        guards=(_requires_constitutional_validation,),
        deny_fallback="block",
    ),
    MACIRole.CONTROLLER: ToolCallPolicy(
        role=MACIRole.CONTROLLER,
        allowed_tools=frozenset(
            {
                "enforce_control",
                "query_knowledge",
                "read_policy",
                "read_context",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "write_audit", "propose_message"}),
        guards=(_requires_constitutional_validation,),
        deny_fallback="route_to_hitl",
    ),
    MACIRole.IMPLEMENTER: ToolCallPolicy(
        role=MACIRole.IMPLEMENTER,
        allowed_tools=frozenset(
            {
                "synthesize_response",
                "query_knowledge",
                "read_context",
                "read_policy",
            }
        ),
        denied_tools=_CONSTITUTIONAL_MUTATION_TOOLS
        | frozenset({"execute_action", "validate_message", "write_audit", "modify_policy"}),
        guards=(_requires_constitutional_validation,),
        deny_fallback="block",
    ),
}


# ---------------------------------------------------------------------------
# Enforcement result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrivilegeDecision:
    """Result of a tool privilege check.

    Attributes:
        permitted: True if the tool call is allowed.
        reason: Human-readable reason (logged and surfaced in audit trail).
        fallback: Configured deny_fallback action from the policy.
    """

    permitted: bool
    reason: str
    fallback: str = "block"


# ---------------------------------------------------------------------------
# Enforcer (stateless, importable independently of middleware)
# ---------------------------------------------------------------------------


class ToolPrivilegeEnforcer:
    """
    Stateless enforcer that checks tool calls against MACI role policies.

    Intended for use both inside ToolPrivilegeMiddleware and directly in
    unit tests or other enforcement points.
    """

    def __init__(self, policies: dict[MACIRole, ToolCallPolicy] | None = None) -> None:
        self._policies = policies if policies is not None else MACI_TOOL_POLICIES

    def check(
        self,
        tool_name: str,
        role: MACIRole,
        ctx: PipelineContext,
        *,
        tenant_id: str | None = None,
        mcp_allowlist: frozenset[str] | None = None,
    ) -> PrivilegeDecision:
        """
        Evaluate whether `role` may invoke `tool_name` given `ctx`.

        Evaluation order (defence in depth):
        1. Constitutional immutability hard-deny (highest priority)
        2. Explicit deny list in the role's policy
        3. Guard predicates
        4. MCP allowlist check (tenant-aware, INTERSECTION-merged)
        5. Pipeline allowlist (default-deny for anything not explicitly permitted)

        Args:
            tool_name: Name of the tool being requested.
            role: MACI role of the requesting agent.
            ctx: Pipeline context with constitutional validation state.
            tenant_id: Optional tenant ID for structured audit logging.
            mcp_allowlist: Optional pre-resolved MCP allowlist (from
                resolve_effective_allowlist). When provided, MCP tools
                are checked against this set in addition to pipeline tools.
        """
        _tenant = tenant_id or getattr(ctx.message, "tenant_id", "default")

        # 1. Constitutional immutability — applies to ALL roles, always
        if tool_name in _CONSTITUTIONAL_MUTATION_TOOLS:
            msg = (
                f"constitutional_immutability_violation: "
                f"role={role.value} attempted tool={tool_name!r}; "
                f"constitutional hash {CONSTITUTIONAL_HASH} is immutable"  # pragma: allowlist secret
            )
            logger.error(
                "tool_access_denied",
                decision="DENY",
                reason="constitutional_immutability",
                tool=tool_name,
                role=role.value,
                tenant_id=_tenant,
                fallback="block_with_p1_alert",
            )
            return PrivilegeDecision(permitted=False, reason=msg, fallback="block_with_p1_alert")

        policy = self._policies.get(role)
        if policy is None:
            reason = f"unknown_maci_role:{role!r} — no policy registered; defaulting to deny"
            logger.warning(
                "tool_access_denied",
                decision="DENY",
                reason="unknown_role",
                tool=tool_name,
                role=repr(role),
                tenant_id=_tenant,
                fallback="block",
            )
            return PrivilegeDecision(permitted=False, reason=reason, fallback="block")

        # 2. Explicit deny list
        if tool_name in policy.denied_tools:
            reason = f"role_denied: role={role.value} tool={tool_name!r} is in explicit deny list"
            logger.warning(
                "tool_access_denied",
                decision="DENY",
                reason="explicit_deny",
                tool=tool_name,
                role=role.value,
                tenant_id=_tenant,
                fallback=policy.deny_fallback,
            )
            return PrivilegeDecision(permitted=False, reason=reason, fallback=policy.deny_fallback)

        # 3. Guard predicates
        for guard in policy.guards:
            if not guard(ctx):
                reason = (
                    f"guard_failed: role={role.value} tool={tool_name!r} "
                    f"guard={guard.__name__!r} returned False"
                )
                logger.warning(
                    "tool_access_denied",
                    decision="DENY",
                    reason="guard_failed",
                    tool=tool_name,
                    role=role.value,
                    tenant_id=_tenant,
                    guard=guard.__name__,
                    fallback=policy.deny_fallback,
                )
                return PrivilegeDecision(
                    permitted=False, reason=reason, fallback=policy.deny_fallback
                )

        # 4. MCP allowlist check (tenant-aware INTERSECTION merge)
        if mcp_allowlist is not None and tool_name not in policy.allowed_tools:
            # Tool is not a pipeline tool — check against MCP allowlist
            if tool_name in mcp_allowlist:
                logger.info(
                    "tool_access_permitted",
                    decision="PERMIT",
                    reason="mcp_allowlist",
                    tool=tool_name,
                    role=role.value,
                    tenant_id=_tenant,
                )
                return PrivilegeDecision(
                    permitted=True,
                    reason=f"mcp_permitted: role={role.value} tool={tool_name!r}",
                    fallback=policy.deny_fallback,
                )
            # Not in MCP allowlist either — fall through to default-deny below

        # 5. Pipeline allowlist (default-deny for anything not explicitly permitted)
        if tool_name in policy.allowed_tools:
            logger.info(
                "tool_access_permitted",
                decision="PERMIT",
                reason="pipeline_allowlist",
                tool=tool_name,
                role=role.value,
                tenant_id=_tenant,
            )
            return PrivilegeDecision(
                permitted=True,
                reason=f"permitted: role={role.value} tool={tool_name!r}",
                fallback=policy.deny_fallback,
            )

        reason = (
            f"not_in_allowlist: role={role.value} tool={tool_name!r} "
            f"is not in the role's allowed_tools set"
        )
        logger.warning(
            "tool_access_denied",
            decision="DENY",
            reason="not_in_allowlist",
            tool=tool_name,
            role=role.value,
            tenant_id=_tenant,
            fallback=policy.deny_fallback,
        )
        return PrivilegeDecision(permitted=False, reason=reason, fallback=policy.deny_fallback)


# ---------------------------------------------------------------------------
# Pipeline middleware
# ---------------------------------------------------------------------------


class ToolPrivilegeMiddleware(BaseMiddleware):
    """
    Pipeline middleware that enforces Progent-style tool privilege policies.

    Reads `context.maci_role` and `context.message.requested_tool` (if set).
    When a tool call is present and the role policy denies it, the pipeline
    is short-circuited via `context.set_early_result()` with a blocked
    ValidationResult.

    If the message carries no `requested_tool`, the middleware is a no-op
    and passes control to the next middleware unchanged.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        enforcer: ToolPrivilegeEnforcer | None = None,
    ) -> None:
        super().__init__(config or MiddlewareConfig(timeout_ms=10, fail_closed=True))
        self._enforcer = enforcer or ToolPrivilegeEnforcer()

    async def process(self, context: PipelineContext) -> PipelineContext:
        context.add_middleware("ToolPrivilegeMiddleware")

        # Use formalized requested_tool field (C-5), with getattr fallback
        # for backward compatibility with messages that lack the field.
        tool_name: str | None = getattr(context.message, "requested_tool", None)
        if not tool_name:
            # No tool call in this message — pass through
            return await self._call_next(context)

        maci_role_str: str | None = context.maci_role
        if not maci_role_str:
            # Role not yet resolved — cannot enforce; fail-closed
            logger.warning(
                "ToolPrivilegeMiddleware: maci_role not set on context for tool=%r; "
                "blocking as fail-closed.",
                tool_name,
            )
            result = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            result.add_error("tool_privilege: maci_role unresolved — fail-closed block")
            context.set_early_result(result)
            return context

        try:
            role = MACIRole.parse(maci_role_str)
        except ValueError:
            logger.error(
                "ToolPrivilegeMiddleware: unrecognised maci_role=%r for tool=%r; blocking.",
                maci_role_str,
                tool_name,
            )
            result = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            result.add_error(f"tool_privilege: unrecognised role {maci_role_str!r}")
            context.set_early_result(result)
            return context

        # Resolve tenant-scoped MCP allowlist if available
        mcp_allowlist: frozenset[str] | None = None
        tenant_id: str | None = getattr(context.message, "tenant_id", None)
        tenant_overrides: dict[str, list[str]] | None = getattr(
            context, "tenant_tool_allowlist_overrides", None
        )
        if (
            True
        ):  # Always resolve MCP allowlist — system defaults apply even without tenant overrides
            # Always resolve MCP allowlist — system defaults apply even without tenant overrides
            from .tool_privilege_policy import resolve_effective_allowlist

            mcp_allowlist = resolve_effective_allowlist(role, tenant_overrides=tenant_overrides)

        decision = self._enforcer.check(
            tool_name,
            role,
            context,
            tenant_id=tenant_id,
            mcp_allowlist=mcp_allowlist,
        )
        if not decision.permitted:
            result = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            result.add_error(decision.reason)
            result.metadata["tool_privilege_fallback"] = decision.fallback
            result.metadata["tool_name"] = tool_name
            result.metadata["maci_role"] = maci_role_str

            # Constitutional mutation attempts warrant a P1 alert in metadata
            if decision.fallback == "block_with_p1_alert":
                result.metadata["alert_level"] = "P1"
                result.metadata["alert_reason"] = "constitutional_immutability_violation"

            if decision.fallback == "route_to_hitl":
                # Signal the pipeline to route to HITL rather than hard-block
                result.metadata["route_to_hitl"] = True

            context.set_early_result(result)
            return context

        return await self._call_next(context)
