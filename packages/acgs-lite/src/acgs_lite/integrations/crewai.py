"""ACGS-Lite CrewAI Integration.

Adds constitutional governance to CrewAI agents by wrapping task execution
with input/output validation.

Usage::

    from acgs_lite.integrations.crewai import GovernedCrew

    governed = GovernedCrew(crew)
    result = governed.kickoff()

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from crewai import Agent, Crew, Task  # noqa: F401

    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


class GovernedCrew:
    """Wrapper around a CrewAI Crew that validates inputs and final output.

    String inputs are validated before kickoff. The final crew result is
    validated after completion. Violations are logged to the audit trail.

    Note: intermediate task outputs between CrewAI agents are not validated
    by this wrapper. For per-task governance, wrap individual agent callbacks.

    Args:
        crew: The CrewAI Crew instance to govern.
        constitution: Constitutional rules. Defaults to ``Constitution.default()``.
        agent_id: Identifier for audit trail entries.
        strict: If True, raise on violations. If False, log warnings.
    """

    def __init__(
        self,
        crew: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "crewai-crew",
        strict: bool = False,
    ) -> None:
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "The 'crewai' package is required. Install with: pip install acgs-lite[crewai]"
            )

        self._crew = crew
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id

    def kickoff(self, inputs: dict[str, Any] | None = None) -> Any:
        """Run the crew with governance validation on outputs.

        Validates each task's raw output string against the constitution.
        In non-strict mode (default), violations are logged but execution
        continues. In strict mode, a ``ConstitutionalViolationError`` is raised.
        """
        # Validate inputs if provided
        if inputs:
            for key, value in inputs.items():
                if isinstance(value, str):
                    self.engine.validate(value, agent_id=f"{self.agent_id}:input:{key}")

        result = self._crew.kickoff(inputs=inputs)

        # Validate final output
        output_text = str(result) if result is not None else ""
        if output_text:
            validation = self.engine.validate(
                output_text, agent_id=f"{self.agent_id}:output"
            )
            if not validation.valid:
                logger.warning(
                    "CrewAI output triggered governance violations: %s",
                    [v.rule_id for v in validation.violations],
                )

        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
