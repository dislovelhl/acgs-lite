"""PolicyBackend ABC — pluggable policy evaluation for ACGS.

Constitutional Hash: 608508a9bd224290

Backends evaluate governance rules against actions. The default
HeuristicBackend uses the existing GovernanceEngine matcher.
CedarBackend (in acgs.cedar) provides embedded Cedar evaluation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    """Result of a policy evaluation."""

    allowed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    backend: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyBackend(ABC):
    """Abstract base for policy evaluation backends."""

    @abstractmethod
    def evaluate(
        self,
        action: str,
        *,
        agent_id: str = "anonymous",
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate an action against loaded policies.

        Returns PolicyDecision with allowed=True/False and any violations.
        Must be fail-closed: errors return allowed=False.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g., 'heuristic', 'cedar')."""


class HeuristicBackend(PolicyBackend):
    """Default backend using GovernanceEngine's built-in matcher.

    This wraps the existing acgs_lite engine so it conforms to
    the PolicyBackend interface.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def evaluate(
        self,
        action: str,
        *,
        agent_id: str = "anonymous",
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        result = self._engine.validate(action, agent_id=agent_id, context=context)
        return PolicyDecision(
            allowed=result.valid,
            violations=[
                {
                    "rule_id": v.rule_id,
                    "rule_text": v.rule_text,
                    "severity": v.severity.value,
                    "category": v.category,
                }
                for v in result.violations
            ],
            latency_ms=result.latency_ms,
            backend="heuristic",
        )

    @property
    def name(self) -> str:
        return "heuristic"
