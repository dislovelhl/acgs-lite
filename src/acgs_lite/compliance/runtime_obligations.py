"""Runtime compliance obligations — bridging assessment frameworks to enforcement.

Maps framework article refs to actionable runtime obligations that GovernedAgent
enforces post-decision. Blocking obligations prevent ALLOW without satisfaction;
advisory obligations appear in CDP records but do not block.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ObligationType(StrEnum):
    """Runtime obligations extracted from compliance framework article refs."""

    # Blocking — prevent ALLOW without explicit satisfaction
    HITL_REQUIRED = "hitl_required"  # Human-in-the-loop approval required
    PHI_GUARD = "phi_guard"  # PHI/PII must be screened before output
    CONSENT_CHECK = "consent_check"  # Data subject consent must be verified

    # Advisory — logged in CDP, do not block by default
    EXPLAINABILITY = "explainability"  # Decision explanation must be logged
    AUDIT_REQUIRED = "audit_required"  # Enhanced audit trail required
    BIAS_CHECK = "bias_check"  # Algorithmic bias assessment required
    COOL_OFF = "cool_off"  # Time-gated rate-limiting (gambling/finance)
    SPEND_LIMIT = "spend_limit"  # Spending/wager limit enforcement


class ObligationSeverity(StrEnum):
    """Severity tier of the obligation."""

    BLOCKING = "blocking"  # Prevents ALLOW without explicit satisfaction
    ADVISORY = "advisory"  # Logged in CDP; does not block


# Severity assignment for each obligation type
_OBLIGATION_SEVERITY: dict[ObligationType, ObligationSeverity] = {
    ObligationType.HITL_REQUIRED: ObligationSeverity.BLOCKING,
    ObligationType.PHI_GUARD: ObligationSeverity.BLOCKING,
    ObligationType.CONSENT_CHECK: ObligationSeverity.BLOCKING,
    ObligationType.EXPLAINABILITY: ObligationSeverity.ADVISORY,
    ObligationType.AUDIT_REQUIRED: ObligationSeverity.ADVISORY,
    ObligationType.BIAS_CHECK: ObligationSeverity.ADVISORY,
    ObligationType.COOL_OFF: ObligationSeverity.ADVISORY,
    ObligationType.SPEND_LIMIT: ObligationSeverity.ADVISORY,
}


@dataclass(frozen=True)
class RuntimeObligation:
    """A runtime compliance obligation derived from a framework article ref.

    Attributes:
        obligation_type: The kind of obligation (from ObligationType).
        framework_id: Source compliance framework (e.g. "eu_ai_act", "hipaa").
        article_ref: The specific article reference (e.g. "EU-AIA Art.14(1)").
        description: Human-readable explanation of what is required.
        satisfied: Whether the obligation has been satisfied for this decision.
        severity: BLOCKING or ADVISORY (derived from obligation_type).
        metadata: Additional context (e.g. threshold values, domain-specific info).
    """

    obligation_type: ObligationType
    framework_id: str
    article_ref: str
    description: str
    satisfied: bool = False
    severity: ObligationSeverity = ObligationSeverity.ADVISORY
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_type": self.obligation_type.value,
            "framework_id": self.framework_id,
            "article_ref": self.article_ref,
            "description": self.description,
            "satisfied": self.satisfied,
            "severity": self.severity.value,
            "metadata": self.metadata,
        }

    @property
    def is_blocking(self) -> bool:
        """Return True if this obligation blocks ALLOW when unsatisfied."""
        return self.severity == ObligationSeverity.BLOCKING

    def satisfy(self, *, evidence: str = "") -> RuntimeObligation:
        """Return a new RuntimeObligation marked as satisfied."""
        new_meta = {**self.metadata, "satisfied_evidence": evidence} if evidence else self.metadata
        return RuntimeObligation(
            obligation_type=self.obligation_type,
            framework_id=self.framework_id,
            article_ref=self.article_ref,
            description=self.description,
            satisfied=True,
            severity=self.severity,
            metadata=new_meta,
        )


def make_obligation(
    obligation_type: ObligationType,
    framework_id: str,
    article_ref: str,
    description: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeObligation:
    """Factory helper: create an unsatisfied RuntimeObligation with correct severity."""
    return RuntimeObligation(
        obligation_type=obligation_type,
        framework_id=framework_id,
        article_ref=article_ref,
        description=description,
        satisfied=False,
        severity=_OBLIGATION_SEVERITY.get(obligation_type, ObligationSeverity.ADVISORY),
        metadata=metadata or {},
    )
