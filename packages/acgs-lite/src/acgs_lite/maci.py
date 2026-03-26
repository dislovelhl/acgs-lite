# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""MACI — Separation of Powers for AI Agents.

Enforces that Proposers, Validators, and Executors cannot cross boundaries.
An agent that proposes an action cannot also validate it. An agent that
validates cannot execute. This prevents any single agent from having
unchecked power.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.errors import MACIViolationError


class MACIRole(str, Enum):
    """MACI separation of powers roles."""

    PROPOSER = "proposer"  # Suggests governance actions
    VALIDATOR = "validator"  # Verifies constitutional compliance
    EXECUTOR = "executor"  # Executes approved actions
    OBSERVER = "observer"  # Read-only audit access


# Actions each role is allowed to perform
_ROLE_PERMISSIONS: dict[MACIRole, set[str]] = {
    MACIRole.PROPOSER: {"propose", "draft", "suggest", "amend"},
    MACIRole.VALIDATOR: {"validate", "review", "audit", "verify"},
    MACIRole.EXECUTOR: {"execute", "deploy", "apply", "run"},
    MACIRole.OBSERVER: {"read", "query", "export", "observe"},
}

# What each role is explicitly forbidden from doing
_ROLE_DENIALS: dict[MACIRole, set[str]] = {
    MACIRole.PROPOSER: {"validate", "execute", "approve"},
    MACIRole.VALIDATOR: {"propose", "execute", "deploy"},
    MACIRole.EXECUTOR: {"validate", "propose", "approve"},
    MACIRole.OBSERVER: {"propose", "validate", "execute", "deploy", "approve"},
}


class ActionRiskTier(str, Enum):
    """exp91: Risk tier for an agent action, used for workflow routing decisions.

    Downstream orchestrators use this to determine escalation path and
    required approval level without needing to inspect rule details.
    """

    LOW = "low"  # Routine action, no special handling
    MEDIUM = "medium"  # Warrants logging and supervisor notification
    HIGH = "high"  # Requires human review before execution
    CRITICAL = "critical"  # Hard block; escalate immediately to governance lead

    @property
    def escalation_path(self) -> str:
        """Recommended escalation path for this risk tier."""
        return _ESCALATION_PATHS[self]


# Pre-compiled pattern sets for fast risk classification (exp91)
# Ordered from highest to lowest specificity
_CRITICAL_RISK_RE = re.compile(
    r"self.?validat|bypass.{0,20}(validation|governance|constitution)|"
    r"self.?approv|auto.?approv|skip.{0,20}(hash|check|audit)|"
    r"unauthoriz|escalate.{0,10}privileg|admin.{0,10}override|"
    r"disable.{0,20}(logging|audit|governance)|"
    r"(password|secret.?key|api.?key|private.?key)",
    re.IGNORECASE,
)

_HIGH_RISK_RE = re.compile(
    r"(propose|submit|amend).{0,30}(constitution|governance|policy)|"
    r"(delete|drop|truncate|remove).{0,20}(data|table|record|user)|"
    r"(grant|revoke).{0,20}(access|permission|role)|"
    r"deploy.{0,30}(production|live|staging)|"
    r"(override|force.?push|reset.?hard)",
    re.IGNORECASE,
)

_MEDIUM_RISK_RE = re.compile(
    r"(modify|update|change).{0,30}(config|setting|rule|policy)|"
    r"(create|add).{0,20}(user|agent|role)|"
    r"(export|share).{0,20}(data|report|log)|"
    r"schedule.{0,30}(job|task|workflow)",
    re.IGNORECASE,
)

_ESCALATION_PATHS: dict[ActionRiskTier, str] = {
    ActionRiskTier.LOW: "auto_approve",
    ActionRiskTier.MEDIUM: "supervisor_notify",
    ActionRiskTier.HIGH: "human_review_queue",
    ActionRiskTier.CRITICAL: "governance_lead_immediate",
}


class EscalationTier(str, Enum):
    """exp95: Granular escalation tiers combining action risk + context risk + severity.

    Downstream workflow orchestrators use this to determine the exact
    approval workflow, SLA, and notification channel for a governance event.
    """

    TIER_0_AUTO = "tier_0_auto"  # Auto-approve, log only
    TIER_1_NOTIFY = "tier_1_notify"  # Approve + notify supervisor async
    TIER_2_REVIEW = "tier_2_review"  # Queue for human review (24h SLA)
    TIER_3_URGENT = "tier_3_urgent"  # Immediate human review (1h SLA)
    TIER_4_BLOCK = "tier_4_block"  # Hard block, governance lead escalation


def recommend_escalation(
    severity: str,
    context_risk_score: float = 0.0,
    action_risk_tier: str = "low",
) -> dict[str, Any]:
    """exp95: Recommend an escalation tier combining severity + context + action risk.

    Produces a single, actionable escalation recommendation from three
    independent governance signals. Downstream orchestrators call this once
    per governance event to determine handling without implementing their
    own severity/risk matrix.

    Args:
        severity: Rule severity ("critical", "high", "medium", "low").
        context_risk_score: 0.0-1.0 from score_context_risk().
        action_risk_tier: ActionRiskTier value from classify_action_risk().

    Returns:
        dict with keys:
            - ``tier``: EscalationTier value string
            - ``sla``: recommended response time
            - ``requires_human``: bool
            - ``rationale``: brief explanation of why this tier was selected
    """
    # Compute a combined risk score (0–3 scale)
    severity_weight = {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(severity.lower(), 0)
    action_weight = {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(
        action_risk_tier.lower(), 0
    )
    # context_risk_score is 0.0–1.0, scale to 0–3
    combined = severity_weight + action_weight + (context_risk_score * 3)

    if combined >= 7:
        tier = EscalationTier.TIER_4_BLOCK
        sla = "immediate"
        rationale = "critical severity + high-risk context/action"
    elif combined >= 5:
        tier = EscalationTier.TIER_3_URGENT
        sla = "1h"
        rationale = "high severity or critical action in risky context"
    elif combined >= 3:
        tier = EscalationTier.TIER_2_REVIEW
        sla = "24h"
        rationale = "medium severity with elevated context risk"
    elif combined >= 1:
        tier = EscalationTier.TIER_1_NOTIFY
        sla = "async"
        rationale = "low-medium risk, supervisor awareness sufficient"
    else:
        tier = EscalationTier.TIER_0_AUTO
        sla = "none"
        rationale = "low risk across all dimensions"

    return {
        "tier": tier.value,
        "sla": sla,
        "requires_human": combined >= 3,
        "rationale": rationale,
    }


class MACIEnforcer:
    """Enforces MACI separation of powers.

    Tracks which agents have which roles and prevents role violations.

    Usage::

        enforcer = MACIEnforcer()
        enforcer.assign_role("agent-1", MACIRole.PROPOSER)
        enforcer.assign_role("agent-2", MACIRole.VALIDATOR)

        # This works:
        enforcer.check("agent-1", "propose")

        # This raises MACIViolationError:
        enforcer.check("agent-1", "validate")
    """

    def __init__(self, *, audit_log: AuditLog | None = None) -> None:
        self._roles: dict[str, MACIRole] = {}
        self.audit_log = audit_log if audit_log is not None else AuditLog()

    def assign_role(self, agent_id: str, role: MACIRole) -> None:
        """Assign a MACI role to an agent."""
        self._roles[agent_id] = role
        self.audit_log.record(
            AuditEntry(
                id=f"maci-assign-{agent_id}",
                type="maci_assign",
                agent_id=agent_id,
                action=f"assigned role: {role.value}",
                valid=True,
                metadata={"role": role.value},
            )
        )

    def get_role(self, agent_id: str) -> MACIRole | None:
        """Get an agent's MACI role."""
        return self._roles.get(agent_id)

    def check(self, agent_id: str, action: str) -> bool:
        """Check if an agent is allowed to perform an action.

        Args:
            agent_id: The agent attempting the action.
            action: The action verb (e.g., "validate", "propose", "execute").

        Returns:
            True if allowed.

        Raises:
            MACIViolationError: If the action violates separation of powers.
        """
        role = self._roles.get(agent_id)

        if role is None:
            # Unassigned agents can only observe
            role = MACIRole.OBSERVER

        action_lower = action.lower()
        denied = _ROLE_DENIALS.get(role, set())

        if action_lower in denied:
            self.audit_log.record(
                AuditEntry(
                    id=f"maci-deny-{agent_id}",
                    type="maci_check",
                    agent_id=agent_id,
                    action=action,
                    valid=False,
                    violations=["MACI"],
                    metadata={"role": role.value, "denied_action": action_lower},
                )
            )
            raise MACIViolationError(
                f"MACI violation: {role.value} cannot {action_lower}. "
                f"Role {role.value} is denied: {', '.join(sorted(denied))}",
                actor_role=role.value,
                attempted_action=action_lower,
            )

        self.audit_log.record(
            AuditEntry(
                id=f"maci-allow-{agent_id}",
                type="maci_check",
                agent_id=agent_id,
                action=action,
                valid=True,
                metadata={"role": role.value},
            )
        )
        return True

    def check_no_self_validation(
        self,
        proposer_id: str,
        validator_id: str,
    ) -> bool:
        """Ensure proposer and validator are different agents.

        The golden rule: agents NEVER validate their own output.
        """
        if proposer_id == validator_id:
            self.audit_log.record(
                AuditEntry(
                    id=f"maci-self-{proposer_id}",
                    type="maci_check",
                    agent_id=proposer_id,
                    action="self-validation attempt",
                    valid=False,
                    violations=["MACI-SELF"],
                    metadata={"proposer": proposer_id, "validator": validator_id},
                )
            )
            raise MACIViolationError(
                f"MACI violation: Agent {proposer_id} cannot validate its own proposals. "
                "Use an independent validator.",
                actor_role="proposer+validator",
                attempted_action="self-validate",
            )
        return True

    @property
    def role_assignments(self) -> dict[str, str]:
        """Return current role assignments."""
        return {k: v.value for k, v in self._roles.items()}

    def summary(self) -> dict[str, Any]:
        """Return MACI enforcement summary."""
        entries = self.audit_log.query(entry_type="maci_check")
        denied = [e for e in entries if not e.valid]
        return {
            "agents": len(self._roles),
            "roles": self.role_assignments,
            "checks_total": len(entries),
            "checks_denied": len(denied),
            "separation_integrity": len(denied) == 0 or all(not e.valid for e in denied),
        }

    def classify_action_risk(self, action: str) -> dict[str, Any]:
        """exp91: Classify an action's risk tier for workflow routing.

        Returns a dict with risk_tier, escalation_path, and matched_signal
        so downstream orchestrators can route governance decisions to the
        correct approval workflow without inspecting rule internals.

        Args:
            action: The action text to classify.

        Returns:
            dict with keys:
                - ``risk_tier``: ActionRiskTier value string
                - ``escalation_path``: recommended escalation route
                - ``matched_signal``: the pattern or keyword that triggered the tier
                  (empty string for LOW tier)

        Example::

            enforcer.classify_action_risk("deploy to production")
            # {"risk_tier": "high", "escalation_path": "human_review_queue",
            #  "matched_signal": "deploy.{0,30}(production|live|staging)"}
        """
        if m := _CRITICAL_RISK_RE.search(action):
            tier = ActionRiskTier.CRITICAL
            signal = m.group(0)
        elif m := _HIGH_RISK_RE.search(action):
            tier = ActionRiskTier.HIGH
            signal = m.group(0)
        elif m := _MEDIUM_RISK_RE.search(action):
            tier = ActionRiskTier.MEDIUM
            signal = m.group(0)
        else:
            tier = ActionRiskTier.LOW
            signal = ""

        return {
            "risk_tier": tier.value,
            "escalation_path": tier.escalation_path,
            "matched_signal": signal,
        }


class DomainScopedRole:
    """exp169: Domain-scoped MACI role assignment with cross-domain isolation.

    Binds a :class:`MACIRole` to one or more governance domains (e.g.,
    ``finance``, ``healthcare``, ``security``). An agent with a domain-scoped
    role can only perform actions within its assigned domains — cross-domain
    actions are blocked, preventing lateral movement between governance areas.

    This implements multi-tenancy partitioning for MACI: a ``finance-proposer``
    cannot propose governance actions in the ``healthcare`` domain, even though
    they hold the PROPOSER role.

    Usage::

        from acgs_lite.maci import DomainScopedRole, MACIRole, DomainRoleRegistry

        registry = DomainRoleRegistry()
        registry.assign("agent-finance-01", MACIRole.PROPOSER, domains=["finance"])
        registry.assign("agent-health-01",  MACIRole.VALIDATOR, domains=["healthcare"])
        registry.assign("agent-ops-01",     MACIRole.EXECUTOR,  domains=["finance", "ops"])

        # Finance proposer cannot validate in healthcare
        result = registry.check("agent-finance-01", "validate", domain="healthcare")
        assert result["allowed"] is False

        # Finance proposer can propose in finance
        result = registry.check("agent-finance-01", "propose", domain="finance")
        assert result["allowed"] is True

    """

    __slots__ = ("agent_id", "role", "domains")

    def __init__(self, agent_id: str, role: MACIRole, domains: list[str]) -> None:
        self.agent_id = agent_id
        self.role = role
        self.domains = list(domains)  # copy to prevent mutation

    def can_act_in(self, domain: str) -> bool:
        """Return True if this scoped role covers *domain*."""
        if not self.domains:
            return True  # empty = unrestricted (backward compat)
        return domain.lower() in (d.lower() for d in self.domains)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "domains": self.domains,
        }

    def __repr__(self) -> str:
        return (
            f"DomainScopedRole(agent={self.agent_id!r}, "
            f"role={self.role.value!r}, domains={self.domains!r})"
        )


class DomainRoleRegistry:
    """exp169: Registry of domain-scoped MACI role assignments.

    Enforces both role-action rules (from :class:`MACIEnforcer`) and
    domain isolation: agents can only act within their assigned governance
    domains. Cross-domain violations are caught before reaching rule evaluation.

    Usage::

        registry = DomainRoleRegistry()
        registry.assign("agent-01", MACIRole.PROPOSER, domains=["finance"])
        result = registry.check("agent-01", "propose", domain="finance")
        # {"allowed": True, "reason": "role and domain check passed", ...}

        result = registry.check("agent-01", "propose", domain="healthcare")
        # {"allowed": False, "reason": "cross-domain violation: ...", ...}

        report = registry.isolation_report()
        # Summary of domain boundaries and role distribution
    """

    __slots__ = ("_assignments",)

    def __init__(self) -> None:
        self._assignments: dict[str, DomainScopedRole] = {}

    def assign(self, agent_id: str, role: MACIRole, *, domains: list[str]) -> None:
        """Assign a domain-scoped role to an agent.

        Args:
            agent_id: Unique agent identifier.
            role: MACI role to assign.
            domains: Domains this agent is permitted to operate in.
                     Empty list means unrestricted (all domains).
        """
        self._assignments[agent_id] = DomainScopedRole(agent_id, role, domains)

    def get(self, agent_id: str) -> DomainScopedRole | None:
        """Return the scoped role for *agent_id*, or None if unregistered."""
        return self._assignments.get(agent_id)

    def check(self, agent_id: str, action: str, *, domain: str = "") -> dict[str, Any]:
        """Check whether *agent_id* may perform *action* in *domain*.

        Applies two checks in order:
        1. Domain scope: is the agent assigned to this domain?
        2. Role-action: does the agent's MACI role permit this action?

        Args:
            agent_id: The agent requesting the action.
            action: Action verb (e.g. ``"propose"``, ``"validate"``).
            domain: Governance domain for the action (e.g. ``"finance"``).
                    Empty string means global / no domain restriction.

        Returns:
            dict with:
                - ``allowed``: bool
                - ``reason``: explanation string
                - ``agent_id``: agent identifier
                - ``action``: action checked
                - ``domain``: domain checked
                - ``role``: the agent's MACI role (or None)
        """
        scoped = self._assignments.get(agent_id)
        base: dict[str, Any] = {
            "agent_id": agent_id,
            "action": action,
            "domain": domain,
            "role": scoped.role.value if scoped else None,
        }

        # Unknown agent
        if scoped is None:
            return {**base, "allowed": False, "reason": f"agent {agent_id!r} not registered"}

        # Domain scope check
        if domain and not scoped.can_act_in(domain):
            return {
                **base,
                "allowed": False,
                "reason": (
                    f"cross-domain violation: agent {agent_id!r} ({scoped.role.value}) "
                    f"is scoped to {scoped.domains} but tried to act in {domain!r}"
                ),
            }

        # Role-action check (uses _ROLE_DENIALS)
        action_lower = action.lower()
        denials = _ROLE_DENIALS.get(scoped.role, set())
        for denied in denials:
            if denied in action_lower:
                return {
                    **base,
                    "allowed": False,
                    "reason": (
                        f"role violation: {scoped.role.value!r} is forbidden from {denied!r}"
                    ),
                }

        return {**base, "allowed": True, "reason": "role and domain check passed"}

    def isolation_report(self) -> dict[str, Any]:
        """Return a summary of domain isolation across all registered agents.

        Returns:
            dict with:
                - ``total_agents``: total registered agents
                - ``domains``: unique domains in use
                - ``role_distribution``: {role: count} mapping
                - ``agents``: list of agent assignment dicts
                - ``cross_domain_risk``: agents with unrestricted domain access (empty domains)
        """
        roles: dict[str, int] = {}
        domains: set[str] = set()
        cross_domain_risk: list[str] = []

        for scoped in self._assignments.values():
            roles[scoped.role.value] = roles.get(scoped.role.value, 0) + 1
            for d in scoped.domains:
                domains.add(d)
            if not scoped.domains:
                cross_domain_risk.append(scoped.agent_id)

        return {
            "total_agents": len(self._assignments),
            "domains": sorted(domains),
            "role_distribution": roles,
            "agents": [s.to_dict() for s in self._assignments.values()],
            "cross_domain_risk": cross_domain_risk,
        }

    def __len__(self) -> int:
        return len(self._assignments)

    def __repr__(self) -> str:
        return f"DomainRoleRegistry({len(self._assignments)} agents)"


class DerivedRole:
    """exp170: Virtual MACI role composing permissions from multiple base roles.

    A derived role inherits the allowed actions from all its parent roles
    but retains any explicit denials from any parent. This enables fine-grained
    role composition without modifying the core MACI role taxonomy.

    Rules of composition:
    - Permissions: union of all parent role permissions
    - Denials: union of all parent role denials (denials from any parent apply)
    - A derived action cannot appear in BOTH permissions and denials —
      denials always win (least-privilege principle).

    Usage::

        from acgs_lite.maci import DerivedRole, MACIRole

        # Senior reviewer: can both propose AND validate (elevated trust)
        senior = DerivedRole(
            name="senior-reviewer",
            base_roles=[MACIRole.PROPOSER, MACIRole.VALIDATOR],
            deny_override={"execute", "deploy"},  # still cannot execute
        )

        print(senior.can_perform("propose"))   # True
        print(senior.can_perform("validate"))  # True
        print(senior.can_perform("execute"))   # False (deny_override)

        check = senior.check("validate")
        # {"action": "validate", "allowed": True, "source": "inherited:validator"}

    """

    __slots__ = ("name", "base_roles", "deny_override", "_permissions", "_denials")

    def __init__(
        self,
        name: str,
        base_roles: list[MACIRole],
        *,
        deny_override: set[str] | None = None,
        allow_override: set[str] | None = None,
    ) -> None:
        """Create a derived role from a list of base roles.

        Args:
            name: Human-readable name for this derived role.
            base_roles: MACI roles whose permissions are inherited.
            deny_override: Additional actions to deny (on top of base denials).
            allow_override: Additional actions to explicitly allow (added after
                            computing composed denials — use sparingly).
        """
        self.name = name
        self.base_roles = list(base_roles)
        self.deny_override: set[str] = deny_override or set()

        # Build composed permission / denial sets
        # Permissions: union of all base role permissions
        composed_perms: set[str] = set()
        for role in base_roles:
            composed_perms |= _ROLE_PERMISSIONS.get(role, set())

        # Denials: only deny_override + actions denied by ALL base roles
        # (cross-role denials don't apply if another base role explicitly permits it)
        if base_roles:
            shared_denials: set[str] = _ROLE_DENIALS.get(base_roles[0], set()).copy()
            for role in base_roles[1:]:
                shared_denials &= _ROLE_DENIALS.get(role, set())
        else:
            shared_denials = set()

        composed_denials: set[str] = set(self.deny_override) | shared_denials

        # allow_override explicitly punches through denials
        if allow_override:
            composed_denials -= allow_override
            composed_perms |= allow_override

        # Least-privilege: deny_override and shared denials win over permissions
        self._permissions: frozenset[str] = frozenset(composed_perms - composed_denials)
        self._denials: frozenset[str] = frozenset(composed_denials)

    @property
    def permissions(self) -> frozenset[str]:
        return self._permissions

    @property
    def denials(self) -> frozenset[str]:
        return self._denials

    def can_perform(self, action: str) -> bool:
        """Return True if this derived role may perform *action*.

        Checks against computed permissions (denials always win).

        Args:
            action: Action verb to check (e.g. ``"propose"``, ``"validate"``).

        Returns:
            True if the action is permitted.
        """
        action_lower = action.lower()
        # Explicit denial check first
        for denied in self._denials:
            if denied in action_lower:
                return False
        # Permission check
        return any(perm in action_lower for perm in self._permissions)

    def check(self, action: str) -> dict[str, Any]:
        """Check *action* and return a structured verdict with source attribution.

        Args:
            action: Action verb to evaluate.

        Returns:
            dict with:
                - ``action``: the evaluated action
                - ``allowed``: bool
                - ``derived_role``: this role's name
                - ``base_roles``: list of base role names
                - ``source``: ``"denied:<source>"`` or ``"inherited:<role>"`` or ``"not_found"``
        """
        action_lower = action.lower()
        # Denial check with source attribution
        for denied in self._denials:
            if denied in action_lower:
                # Attribute to deny_override or base role
                source = "denied:override" if denied in self.deny_override else "denied:base"
                return {
                    "action": action,
                    "allowed": False,
                    "derived_role": self.name,
                    "base_roles": [r.value for r in self.base_roles],
                    "source": source,
                }
        # Permission check with source attribution
        for role in self.base_roles:
            if any(perm in action_lower for perm in _ROLE_PERMISSIONS.get(role, set())):
                return {
                    "action": action,
                    "allowed": True,
                    "derived_role": self.name,
                    "base_roles": [r.value for r in self.base_roles],
                    "source": f"inherited:{role.value}",
                }
        return {
            "action": action,
            "allowed": False,
            "derived_role": self.name,
            "base_roles": [r.value for r in self.base_roles],
            "source": "not_found",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_roles": [r.value for r in self.base_roles],
            "permissions": sorted(self._permissions),
            "denials": sorted(self._denials),
        }

    def __repr__(self) -> str:
        return f"DerivedRole(name={self.name!r}, bases={[r.value for r in self.base_roles]!r})"


class DelegationGrant:
    """exp176: Revocable authority delegation for governance domains.

    Models a formal grant of governance authority from a grantor to a
    grantee, scoped to specific rule categories, actions, and delegation
    depth. Enables hierarchical governance: e.g. "security team owns
    SAFE-* rules" or "compliance officer delegates audit-read to intern
    for 7 days".

    Attributes:
        grant_id: Unique identifier (e.g. ``"DLG-00001"``).
        grantor_id: Agent/user granting authority.
        grantee_id: Agent/user receiving authority.
        scopes: List of category/action patterns this grant covers.
        max_depth: How many times the grantee can re-delegate (0 = cannot).
        depth: Current delegation depth (0 = original grant).
        parent_grant_id: If this is a sub-delegation, the parent grant ID.
        created_at: ISO-8601 creation timestamp.
        expires_at: ISO-8601 expiry (empty string = no expiry).
        revoked: Whether the grant has been revoked.
        revoked_at: ISO-8601 revocation timestamp.
        revocation_reason: Human-readable reason for revocation.
        metadata: Arbitrary extension data.
    """

    __slots__ = (
        "grant_id",
        "grantor_id",
        "grantee_id",
        "scopes",
        "max_depth",
        "depth",
        "parent_grant_id",
        "created_at",
        "expires_at",
        "revoked",
        "revoked_at",
        "revocation_reason",
        "metadata",
    )

    def __init__(
        self,
        *,
        grant_id: str,
        grantor_id: str,
        grantee_id: str,
        scopes: list[str],
        max_depth: int = 0,
        depth: int = 0,
        parent_grant_id: str = "",
        created_at: str = "",
        expires_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.grant_id = grant_id
        self.grantor_id = grantor_id
        self.grantee_id = grantee_id
        self.scopes = list(scopes)
        self.max_depth = max_depth
        self.depth = depth
        self.parent_grant_id = parent_grant_id
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked = False
        self.revoked_at = ""
        self.revocation_reason = ""
        self.metadata = metadata or {}

    def is_expired(self, at: str | None = None) -> bool:
        if not self.expires_at:
            return False
        from datetime import datetime, timezone

        ts = at or datetime.now(timezone.utc).isoformat()
        return ts >= self.expires_at

    def is_active(self, at: str | None = None) -> bool:
        return not self.revoked and not self.is_expired(at)

    def covers_scope(self, scope: str) -> bool:
        scope_lower = scope.lower()
        for s in self.scopes:
            s_lower = s.lower()
            if s_lower == "*" or s_lower == scope_lower:
                return True
            if s_lower.endswith("*") and scope_lower.startswith(s_lower[:-1]):
                return True
        return False

    def can_redelegate(self) -> bool:
        return self.depth < self.max_depth

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "grantor_id": self.grantor_id,
            "grantee_id": self.grantee_id,
            "scopes": self.scopes,
            "max_depth": self.max_depth,
            "depth": self.depth,
            "parent_grant_id": self.parent_grant_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
            "is_active": self.is_active(),
            "can_redelegate": self.can_redelegate(),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        status = "revoked" if self.revoked else ("active" if self.is_active() else "expired")
        return (
            f"DelegationGrant({self.grant_id!r}, "
            f"{self.grantor_id!r}→{self.grantee_id!r}, "
            f"scopes={self.scopes!r}, {status})"
        )


class DelegationRegistry:
    """exp176: Registry for managing governance authority delegations.

    Tracks who has delegated what governance authority to whom, with
    scope constraints, depth limits, cascade revocation, and full
    audit trail. Integrates with MACI roles for authorization checks.

    Usage::

        from acgs_lite.maci import DelegationRegistry

        registry = DelegationRegistry()

        grant = registry.delegate(
            grantor_id="ciso",
            grantee_id="security-lead",
            scopes=["SAFE-*", "PII-*"],
            max_depth=1,
            expires_at="2026-06-01T00:00:00+00:00",
        )

        sub = registry.redelegate(
            parent_grant_id=grant.grant_id,
            grantee_id="security-analyst",
            scopes=["SAFE-*"],
        )

        assert registry.check_authority("security-lead", scope="SAFE-001")
        assert registry.check_authority("security-analyst", scope="SAFE-002")

        registry.revoke(grant.grant_id, reason="Rotation")
        # Cascade: sub-delegation also revoked

    """

    __slots__ = ("_grants", "_counter", "_history")

    def __init__(self) -> None:
        self._grants: dict[str, DelegationGrant] = {}
        self._counter: int = 0
        self._history: list[dict[str, Any]] = []

    def _next_id(self) -> str:
        self._counter += 1
        return f"DLG-{self._counter:05d}"

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def delegate(
        self,
        *,
        grantor_id: str,
        grantee_id: str,
        scopes: list[str],
        max_depth: int = 0,
        expires_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DelegationGrant:
        """Create a new delegation grant.

        Args:
            grantor_id: Agent/user granting authority.
            grantee_id: Agent/user receiving authority.
            scopes: Category/action patterns (e.g. ``["SAFE-*"]``).
            max_depth: How many times the grantee can re-delegate.
            expires_at: ISO-8601 expiry timestamp (empty = no expiry).
            metadata: Optional extension data.

        Returns:
            The newly created DelegationGrant.

        Raises:
            ValueError: If grantor delegates to self.
        """
        if grantor_id == grantee_id:
            raise ValueError("Cannot delegate authority to self")
        if not scopes:
            raise ValueError("Delegation must specify at least one scope")

        grant = DelegationGrant(
            grant_id=self._next_id(),
            grantor_id=grantor_id,
            grantee_id=grantee_id,
            scopes=scopes,
            max_depth=max_depth,
            depth=0,
            created_at=self._now(),
            expires_at=expires_at,
            metadata=metadata,
        )
        self._grants[grant.grant_id] = grant
        self._history.append(
            {
                "action": "delegate",
                "grant_id": grant.grant_id,
                "grantor_id": grantor_id,
                "grantee_id": grantee_id,
                "scopes": scopes,
                "timestamp": grant.created_at,
            }
        )
        return grant

    def redelegate(
        self,
        *,
        parent_grant_id: str,
        grantee_id: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
    ) -> DelegationGrant:
        """Sub-delegate authority from an existing grant.

        The sub-delegation is constrained to a subset of the parent's
        scopes and inherits depth + 1.

        Args:
            parent_grant_id: The parent grant to sub-delegate from.
            grantee_id: New recipient of delegated authority.
            scopes: Subset of parent scopes (defaults to parent's scopes).
            expires_at: Expiry (cannot exceed parent's expiry).

        Returns:
            A new DelegationGrant with depth = parent.depth + 1.

        Raises:
            KeyError: If parent grant not found.
            ValueError: If parent cannot re-delegate or scope violation.
        """
        parent = self._get(parent_grant_id)
        if not parent.is_active():
            raise ValueError(f"Parent grant {parent_grant_id!r} is not active")
        if not parent.can_redelegate():
            raise ValueError(
                f"Grant {parent_grant_id!r} cannot re-delegate "
                f"(depth={parent.depth}, max_depth={parent.max_depth})"
            )
        if parent.grantee_id == grantee_id:
            raise ValueError("Cannot re-delegate to the same grantee")

        effective_scopes = scopes if scopes is not None else list(parent.scopes)
        for s in effective_scopes:
            if not parent.covers_scope(s.rstrip("*")):
                raise ValueError(
                    f"Scope {s!r} is not covered by parent grant "
                    f"{parent_grant_id!r} (scopes={parent.scopes!r})"
                )

        effective_expiry = expires_at
        if parent.expires_at and (not effective_expiry or effective_expiry > parent.expires_at):
            effective_expiry = parent.expires_at

        grant = DelegationGrant(
            grant_id=self._next_id(),
            grantor_id=parent.grantee_id,
            grantee_id=grantee_id,
            scopes=effective_scopes,
            max_depth=parent.max_depth,
            depth=parent.depth + 1,
            parent_grant_id=parent_grant_id,
            created_at=self._now(),
            expires_at=effective_expiry,
        )
        self._grants[grant.grant_id] = grant
        self._history.append(
            {
                "action": "redelegate",
                "grant_id": grant.grant_id,
                "parent_grant_id": parent_grant_id,
                "grantor_id": parent.grantee_id,
                "grantee_id": grantee_id,
                "scopes": effective_scopes,
                "depth": grant.depth,
                "timestamp": grant.created_at,
            }
        )
        return grant

    def revoke(self, grant_id: str, *, reason: str = "", cascade: bool = True) -> int:
        """Revoke a delegation grant.

        Args:
            grant_id: The grant to revoke.
            reason: Human-readable reason.
            cascade: If True, also revoke all sub-delegations.

        Returns:
            Number of grants revoked (including cascaded).

        Raises:
            KeyError: If grant not found.
        """
        grant = self._get(grant_id)
        if grant.revoked:
            return 0

        now = self._now()
        grant.revoked = True
        grant.revoked_at = now
        grant.revocation_reason = reason
        revoked_count = 1

        self._history.append(
            {
                "action": "revoke",
                "grant_id": grant_id,
                "reason": reason,
                "timestamp": now,
            }
        )

        if cascade:
            for child in self._grants.values():
                if child.parent_grant_id == grant_id and not child.revoked:
                    revoked_count += self.revoke(
                        child.grant_id,
                        reason=f"Cascade: parent {grant_id} revoked",
                        cascade=True,
                    )

        return revoked_count

    def check_authority(
        self,
        agent_id: str,
        *,
        scope: str,
        at: str | None = None,
    ) -> dict[str, Any]:
        """Check if an agent has delegated authority over a scope.

        Args:
            agent_id: The agent to check.
            scope: The category/action to check authority for.
            at: ISO-8601 timestamp for temporal check (default: now).

        Returns:
            dict with ``authorized`` (bool), matching ``grant_id``,
            ``grantor_id``, ``depth``, and ``delegation_chain``.
        """
        for grant in self._grants.values():
            if grant.grantee_id == agent_id and grant.is_active(at) and grant.covers_scope(scope):
                chain = self._build_chain(grant.grant_id)
                return {
                    "authorized": True,
                    "grant_id": grant.grant_id,
                    "grantor_id": grant.grantor_id,
                    "scope": scope,
                    "depth": grant.depth,
                    "delegation_chain": chain,
                }
        return {
            "authorized": False,
            "grant_id": "",
            "grantor_id": "",
            "scope": scope,
            "depth": -1,
            "delegation_chain": [],
        }

    def grants_for(self, agent_id: str) -> list[DelegationGrant]:
        return [g for g in self._grants.values() if g.grantee_id == agent_id and g.is_active()]

    def grants_by(self, agent_id: str) -> list[DelegationGrant]:
        return [g for g in self._grants.values() if g.grantor_id == agent_id and g.is_active()]

    def delegation_tree(self) -> dict[str, Any]:
        """Return the full delegation hierarchy as a tree.

        Returns:
            dict with ``roots`` (top-level grants) each containing
            nested ``children`` sub-delegations, plus ``summary`` stats.
        """
        children_map: dict[str, list[str]] = {}
        for g in self._grants.values():
            if g.parent_grant_id:
                children_map.setdefault(g.parent_grant_id, []).append(g.grant_id)

        def _build_node(gid: str) -> dict[str, Any]:
            g = self._grants[gid]
            node: dict[str, Any] = {
                "grant_id": gid,
                "grantor_id": g.grantor_id,
                "grantee_id": g.grantee_id,
                "scopes": g.scopes,
                "depth": g.depth,
                "active": g.is_active(),
            }
            kids = children_map.get(gid, [])
            if kids:
                node["children"] = [_build_node(c) for c in kids]
            return node

        roots = [g.grant_id for g in self._grants.values() if not g.parent_grant_id]

        active_count = sum(1 for g in self._grants.values() if g.is_active())
        max_depth = max((g.depth for g in self._grants.values()), default=0)

        return {
            "roots": [_build_node(r) for r in roots],
            "summary": {
                "total_grants": len(self._grants),
                "active_grants": active_count,
                "max_depth": max_depth,
                "unique_grantors": len({g.grantor_id for g in self._grants.values()}),
                "unique_grantees": len({g.grantee_id for g in self._grants.values()}),
            },
        }

    def summary(self) -> dict[str, Any]:
        active = sum(1 for g in self._grants.values() if g.is_active())
        revoked = sum(1 for g in self._grants.values() if g.revoked)
        expired = sum(1 for g in self._grants.values() if g.is_expired() and not g.revoked)
        by_scope: dict[str, int] = {}
        for g in self._grants.values():
            if g.is_active():
                for s in g.scopes:
                    by_scope[s] = by_scope.get(s, 0) + 1

        return {
            "total": len(self._grants),
            "active": active,
            "revoked": revoked,
            "expired": expired,
            "by_scope": by_scope,
            "history_entries": len(self._history),
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def _get(self, grant_id: str) -> DelegationGrant:
        try:
            return self._grants[grant_id]
        except KeyError:
            raise KeyError(f"Grant {grant_id!r} not found") from None

    def _build_chain(self, grant_id: str) -> list[str]:
        chain: list[str] = []
        current_id = grant_id
        seen: set[str] = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            grant = self._grants.get(current_id)
            if not grant:
                break
            chain.append(current_id)
            current_id = grant.parent_grant_id
        chain.reverse()
        return chain

    def __len__(self) -> int:
        return len(self._grants)

    def __repr__(self) -> str:
        active = sum(1 for g in self._grants.values() if g.is_active())
        return f"DelegationRegistry({len(self._grants)} grants, {active} active)"
