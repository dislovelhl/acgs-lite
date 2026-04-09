# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Shared MACI roles, permissions, and escalation helpers."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class MACIRole(str, Enum):
    """MACI separation of powers roles."""

    PROPOSER = "proposer"
    VALIDATOR = "validator"
    EXECUTOR = "executor"
    OBSERVER = "observer"


_UNIVERSAL_READ_ACTIONS: set[str] = {"read", "query"}

_ROLE_PERMISSIONS: dict[MACIRole, set[str]] = {
    MACIRole.PROPOSER: {"propose", "draft", "suggest", "amend"} | _UNIVERSAL_READ_ACTIONS,
    MACIRole.VALIDATOR: {"validate", "review", "audit", "verify"} | _UNIVERSAL_READ_ACTIONS,
    MACIRole.EXECUTOR: {"execute", "deploy", "apply", "run"} | _UNIVERSAL_READ_ACTIONS,
    MACIRole.OBSERVER: {"read", "query", "export", "observe"},
}

_ROLE_DENIALS: dict[MACIRole, set[str]] = {
    MACIRole.PROPOSER: {"validate", "execute", "approve"},
    MACIRole.VALIDATOR: {"propose", "execute", "deploy"},
    MACIRole.EXECUTOR: {"validate", "propose", "approve"},
    MACIRole.OBSERVER: {"propose", "validate", "execute", "deploy", "approve"},
}


def _is_action_permitted(action: str, *, allowed: set[str], denied: set[str]) -> bool:
    """Return True only for canonical, explicitly allowed action verbs."""
    action_lower = action.lower().strip()
    return action_lower not in denied and action_lower in allowed


class ActionRiskTier(str, Enum):
    """Risk tier for an agent action, used for workflow routing decisions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def escalation_path(self) -> str:
        """Recommended escalation path for this risk tier."""
        return _ESCALATION_PATHS[self]


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
    """Granular escalation tiers combining action risk + context risk + severity."""

    TIER_0_AUTO = "tier_0_auto"
    TIER_1_NOTIFY = "tier_1_notify"
    TIER_2_REVIEW = "tier_2_review"
    TIER_3_URGENT = "tier_3_urgent"
    TIER_4_BLOCK = "tier_4_block"


def recommend_escalation(
    severity: str,
    context_risk_score: float = 0.0,
    action_risk_tier: str = "low",
) -> dict[str, Any]:
    """Recommend an escalation tier combining severity + context + action risk."""
    severity_weight = {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(severity.lower(), 0)
    action_weight = {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(
        action_risk_tier.lower(), 0
    )
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


__all__ = [
    "ActionRiskTier",
    "EscalationTier",
    "MACIRole",
    "_CRITICAL_RISK_RE",
    "_ESCALATION_PATHS",
    "_HIGH_RISK_RE",
    "_MEDIUM_RISK_RE",
    "_ROLE_DENIALS",
    "_ROLE_PERMISSIONS",
    "_UNIVERSAL_READ_ACTIONS",
    "_is_action_permitted",
    "recommend_escalation",
]
