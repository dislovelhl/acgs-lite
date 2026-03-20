"""MACI — Separation of Powers for AI Agents.

Enforces that Proposers, Validators, and Executors cannot cross boundaries.
An agent that proposes an action cannot also validate it. An agent that
validates cannot execute. This prevents any single agent from having
unchecked power.

Constitutional Hash: cdd01ef066bc6cf2
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
        context_risk_score: 0.0–1.0 from score_context_risk().
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
