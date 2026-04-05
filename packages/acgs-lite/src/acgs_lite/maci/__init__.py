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

from .enforcer import MACIEnforcer
from .registry import (
    DelegationGrant,
    DelegationRegistry,
    DerivedRole,
    DomainRoleRegistry,
    DomainScopedRole,
)
from .roles import (
    _CRITICAL_RISK_RE,
    _ESCALATION_PATHS,
    _HIGH_RISK_RE,
    _MEDIUM_RISK_RE,
    _ROLE_DENIALS,
    _ROLE_PERMISSIONS,
    _UNIVERSAL_READ_ACTIONS,
    ActionRiskTier,
    EscalationTier,
    MACIRole,
    _is_action_permitted,
    recommend_escalation,
)

__all__ = [
    "ActionRiskTier",
    "DelegationGrant",
    "DelegationRegistry",
    "DerivedRole",
    "DomainRoleRegistry",
    "DomainScopedRole",
    "EscalationTier",
    "MACIEnforcer",
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
