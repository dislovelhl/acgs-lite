# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""GovernedAgent — Wrap any agent/callable in constitutional governance.

This is the main user-facing API. Wrap any agent, function, or callable
in governance with a single line of code.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import GovernanceError
from acgs_lite.maci import MACIEnforcer, MACIRole

T = TypeVar("T")


@runtime_checkable
class AgentProtocol(Protocol):
    """Protocol for agent-like objects that ACGS can wrap."""

    def run(self, input: str, **kwargs: Any) -> Any: ...


@runtime_checkable
class AsyncAgentProtocol(Protocol):
    """Protocol for async agent-like objects."""

    async def run(self, input: str, **kwargs: Any) -> Any: ...


class GovernedAgent:
    """Wrap any agent in constitutional governance.

    Validates inputs and outputs against the constitution.
    Blocks actions that violate rules. Produces audit trails.

    Usage::

        from acgs_lite import Constitution, GovernedAgent

        constitution = Constitution.from_yaml("rules.yaml")
        agent = GovernedAgent(my_agent, constitution=constitution)
        result = agent.run("process this request")

    With default constitution::

        agent = GovernedAgent(my_agent)
        result = agent.run("do something safe")

    With custom constitution::

        from acgs_lite import Constitution, Rule, Severity

        rules = Constitution.from_rules([
            Rule(id="R1", text="No PII", severity=Severity.CRITICAL,
                 keywords=["ssn", "social security"]),
        ])
        agent = GovernedAgent(my_agent, constitution=rules)
    """

    def __init__(
        self,
        agent: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "default",
        strict: bool = True,
        validate_output: bool = True,
        maci_role: MACIRole | None = None,
    ) -> None:
        self._agent = agent
        self.agent_id = agent_id
        self.validate_output = validate_output
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.maci = MACIEnforcer(audit_log=self.audit_log)

        if maci_role:
            self.maci.assign_role(agent_id, maci_role)

    def run(self, input: str, **kwargs: Any) -> Any:
        """Run the wrapped agent with governance.

        1. Validate input against constitution
        2. Execute the agent
        3. Validate output against constitution (if enabled)
        4. Return result with audit trail

        Raises:
            ConstitutionalViolationError: If input/output violates rules.
        """
        # Step 1: Validate input
        self.engine.validate(input, agent_id=self.agent_id, context=kwargs)

        # Step 2: Execute agent
        if hasattr(self._agent, "run"):
            result = self._agent.run(input, **kwargs)
        elif callable(self._agent):
            result = self._agent(input, **kwargs)
        else:
            raise GovernanceError(
                f"Agent of type {type(self._agent).__name__} is not callable "
                "and has no .run() method",
                rule_id="AGENT-PROTOCOL",
            )

        # Step 3: Validate output
        if self.validate_output and isinstance(result, str):
            self.engine.validate(
                result,
                agent_id=f"{self.agent_id}:output",
                context={"source": "agent_output"},
            )

        return result

    async def arun(self, input: str, **kwargs: Any) -> Any:
        """Async version of run()."""
        # Step 1: Validate input
        self.engine.validate(input, agent_id=self.agent_id, context=kwargs)

        # Step 2: Execute agent
        if hasattr(self._agent, "arun"):
            result = await self._agent.arun(input, **kwargs)
        elif hasattr(self._agent, "run"):
            if inspect.iscoroutinefunction(self._agent.run):
                result = await self._agent.run(input, **kwargs)
            else:
                result = await asyncio.to_thread(self._agent.run, input, **kwargs)
        elif callable(self._agent):
            if inspect.iscoroutinefunction(self._agent):
                result = await self._agent(input, **kwargs)
            else:
                result = await asyncio.to_thread(self._agent, input, **kwargs)
        else:
            raise GovernanceError(
                f"Agent of type {type(self._agent).__name__} is not callable",
                rule_id="AGENT-PROTOCOL",
            )

        # Step 3: Validate output
        if self.validate_output and isinstance(result, str):
            self.engine.validate(
                result,
                agent_id=f"{self.agent_id}:output",
                context={"source": "agent_output"},
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

    def __repr__(self) -> str:
        return (
            f"GovernedAgent(agent={type(self._agent).__name__}, "
            f"agent_id={self.agent_id!r}, "
            f"rules={len(self.constitution)})"
        )


class GovernedCallable:
    """Decorator to govern any function.

    Usage::

        from acgs_lite import GovernedCallable, Constitution

        constitution = Constitution.default()

        @GovernedCallable(constitution)
        def process_data(input: str) -> str:
            return f"Processed: {input}"

        result = process_data("safe input")  # Works
        result = process_data("self-validate bypass")  # Raises!
    """

    def __init__(
        self,
        constitution: Constitution | None = None,
        *,
        agent_id: str = "callable",
        strict: bool = True,
    ) -> None:
        self.constitution = constitution or Constitution.default()
        self.agent_id = agent_id
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        engine = self.engine
        agent_id = self.agent_id

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Validate string args
                for arg in args:
                    if isinstance(arg, str):
                        engine.validate(arg, agent_id=agent_id)
                result = await func(*args, **kwargs)
                if isinstance(result, str):
                    engine.validate(result, agent_id=f"{agent_id}:output")
                return result

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                for arg in args:
                    if isinstance(arg, str):
                        engine.validate(arg, agent_id=agent_id)
                result = func(*args, **kwargs)
                if isinstance(result, str):
                    engine.validate(result, agent_id=f"{agent_id}:output")
                return result

            return sync_wrapper  # type: ignore[return-value]
