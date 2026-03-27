"""ACGS-Lite CrewAI Integration.

Wraps CrewAI Agent, Crew, and Task with constitutional governance.
Every task description is validated before execution. Every output is
validated non-blockingly after execution.

Usage::

    from crewai import Agent, Crew, Task
    from acgs_lite.integrations.crewai import GovernedCrewAgent, GovernedCrew, GovernedTask

    researcher = Agent(role="Researcher", goal="Find info", backstory="Expert")
    governed_agent = GovernedCrewAgent(researcher)

    task = Task(description="Research AI governance", expected_output="Report")
    governed_task = GovernedTask(task)

    crew = Crew(agents=[researcher], tasks=[task])
    governed_crew = GovernedCrew(crew)
    result = governed_crew.kickoff()

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
    Agent = object  # type: ignore[assignment,misc]
    Crew = object  # type: ignore[assignment,misc]
    Task = object  # type: ignore[assignment,misc]


class GovernedCrewAgent:
    """CrewAI Agent wrapper with constitutional governance.

    Validates task descriptions before the underlying agent executes them
    and validates outputs non-blockingly after execution.

    Usage::

        from crewai import Agent
        from acgs_lite.integrations.crewai import GovernedCrewAgent

        agent = Agent(role="Researcher", goal="Find info", backstory="Expert")
        governed = GovernedCrewAgent(agent)

        # Attribute access delegates to the underlying agent
        print(governed.role)  # "Researcher"
    """

    def __init__(
        self,
        agent: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "crewai-agent",
        strict: bool = True,
    ) -> None:
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required. Install with: pip install acgs[crewai]"
            )

        self._agent = agent
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying CrewAI agent."""
        return getattr(self._agent, name)

    def _validate_input(self, text: str) -> None:
        """Validate input text against the constitution (raises on violation)."""
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

    def _validate_output(self, text: str) -> None:
        """Validate output text without raising (log warnings only)."""
        if text:
            with self.engine.non_strict():
                result = self.engine.validate(text, agent_id=f"{self.agent_id}:output")
            if not result.valid:
                logger.warning(
                    "CrewAI agent output governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

    def execute_task(self, task: Any, **kwargs: Any) -> Any:
        """Execute a task with governance validation.

        Validates the task description before execution and the output after.
        """
        description = getattr(task, "description", "")
        self._validate_input(str(description))

        result = self._agent.execute_task(task, **kwargs)

        self._validate_output(str(result))
        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this agent."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


class GovernedTask:
    """CrewAI Task wrapper with constitutional governance.

    Validates the task description and expected_output against the constitution
    at construction time and delegates all other access to the underlying task.

    Usage::

        from crewai import Task
        from acgs_lite.integrations.crewai import GovernedTask

        task = Task(description="Research AI governance", expected_output="Report")
        governed = GovernedTask(task)
    """

    def __init__(
        self,
        task: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "crewai-task",
        strict: bool = True,
    ) -> None:
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required. Install with: pip install acgs[crewai]"
            )

        self._task = task
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

        # Validate task description at construction time
        description = getattr(task, "description", "")
        if description:
            self.engine.validate(str(description), agent_id=self.agent_id)

        # Validate expected_output if present
        expected_output = getattr(task, "expected_output", "")
        if expected_output:
            self.engine.validate(
                str(expected_output), agent_id=f"{self.agent_id}:expected_output"
            )

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying CrewAI task."""
        return getattr(self._task, name)

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this task."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


class GovernedCrew:
    """CrewAI Crew wrapper with constitutional governance.

    Validates all task descriptions before crew kickoff and validates
    the crew output non-blockingly after completion.

    Usage::

        from crewai import Agent, Crew, Task
        from acgs_lite.integrations.crewai import GovernedCrew

        agent = Agent(role="Researcher", goal="Find info", backstory="Expert")
        task = Task(description="Research AI governance", expected_output="Report")
        crew = Crew(agents=[agent], tasks=[task])

        governed_crew = GovernedCrew(crew)
        result = governed_crew.kickoff()
    """

    def __init__(
        self,
        crew: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "crewai-crew",
        strict: bool = True,
    ) -> None:
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required. Install with: pip install acgs[crewai]"
            )

        self._crew = crew
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying CrewAI crew."""
        return getattr(self._crew, name)

    def _validate_tasks_input(self) -> None:
        """Validate all task descriptions in the crew before execution."""
        tasks = getattr(self._crew, "tasks", []) or []
        for task in tasks:
            description = getattr(task, "description", "")
            if description:
                self.engine.validate(
                    str(description), agent_id=f"{self.agent_id}:task"
                )

    def _validate_output(self, output: Any) -> None:
        """Validate crew output without raising (log warnings only)."""
        text = str(output) if output else ""
        if text:
            with self.engine.non_strict():
                result = self.engine.validate(text, agent_id=f"{self.agent_id}:output")
            if not result.valid:
                logger.warning(
                    "CrewAI crew output governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

    def kickoff(self, **kwargs: Any) -> Any:
        """Run the crew with governance validation.

        Validates all task descriptions before kickoff and validates
        the output non-blockingly after completion.
        """
        self._validate_tasks_input()

        result = self._crew.kickoff(**kwargs)

        self._validate_output(result)
        return result

    async def akickoff(self, **kwargs: Any) -> Any:
        """Async version of kickoff() with governance validation."""
        self._validate_tasks_input()

        result = await self._crew.akickoff(**kwargs)

        self._validate_output(result)
        return result

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this crew."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
