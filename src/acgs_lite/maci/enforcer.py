# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""MACI role enforcement runtime.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.errors import MACIViolationError

from .roles import (
    _CRITICAL_RISK_RE,
    _HIGH_RISK_RE,
    _MEDIUM_RISK_RE,
    _ROLE_DENIALS,
    _ROLE_PERMISSIONS,
    ActionRiskTier,
    MACIRole,
    _is_action_permitted,
)


class MACIEnforcer:
    """Enforces MACI separation of powers."""

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
        """Check if an agent is allowed to perform an action."""
        role = self._roles.get(agent_id)

        if role is None:
            role = MACIRole.OBSERVER

        action_lower = action.lower()
        allowed = _ROLE_PERMISSIONS.get(role, set())
        denied = _ROLE_DENIALS.get(role, set())

        if not _is_action_permitted(action, allowed=allowed, denied=denied):
            self.audit_log.record(
                AuditEntry(
                    id=f"maci-deny-{agent_id}",
                    type="maci_check",
                    agent_id=agent_id,
                    action=action,
                    valid=False,
                    violations=["MACI"],
                    metadata={
                        "role": role.value,
                        "denied_action": action_lower,
                        "allowed_actions": sorted(allowed),
                    },
                )
            )
            raise MACIViolationError(
                f"MACI violation: {role.value} cannot {action_lower}. "
                f"Role {role.value} may only: {', '.join(sorted(allowed))}",
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
        """Ensure proposer and validator are different agents."""
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
        """Classify an action's risk tier for workflow routing."""
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


__all__ = ["MACIEnforcer"]
