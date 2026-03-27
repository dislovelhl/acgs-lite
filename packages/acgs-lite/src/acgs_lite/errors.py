# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""ACGS-Lite error types."""


class GovernanceError(Exception):
    """Base error for all ACGS-Lite governance failures."""

    __slots__ = ("rule_id",)

    def __init__(self, message: str, *, rule_id: str | None = None) -> None:
        self.rule_id = rule_id
        super().__init__(message)


class ConstitutionalViolationError(GovernanceError):
    """Raised when an action violates a constitutional rule."""

    __slots__ = ("severity", "action")

    def __init__(
        self,
        message: str,
        *,
        rule_id: str,
        severity: str = "high",
        action: str = "",
    ) -> None:
        # Bypass GovernanceError.__init__ to save one Python call frame:
        # set the GovernanceError slot directly, then call Exception.__init__.
        self.rule_id = rule_id
        self.severity = severity
        self.action = action
        Exception.__init__(self, message)


class MACIViolationError(GovernanceError):
    """Raised when MACI separation of powers is violated.

    Example: A Proposer trying to validate their own proposal.
    """

    __slots__ = ("actor_role", "attempted_action")

    def __init__(
        self,
        message: str,
        *,
        actor_role: str,
        attempted_action: str,
    ) -> None:
        self.actor_role = actor_role
        self.attempted_action = attempted_action
        super().__init__(message, rule_id="MACI")
