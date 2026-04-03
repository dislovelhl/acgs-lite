# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""GovernedAgent — Wrap any agent/callable in constitutional governance.

This is the main user-facing API. Wrap any agent, function, or callable
in governance with a single line of code.

Constitutional Hash: 608508a9bd224290
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
from acgs_lite.serialization import iter_governance_payloads, serialize_for_governance

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

    Validates inputs and outputs against the constitution. Structured outputs
    and keyword arguments are normalized before validation. Produces full audit
    trails. MACI role metadata is descriptive by default and becomes enforced
    only when `enforce_maci=True` is paired with `governance_action=...`.

    Usage::

        from acgs_lite import Constitution, GovernedAgent, MACIRole

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
        enforce_maci: bool = False,
    ) -> None:
        self._agent = agent
        self.agent_id = agent_id
        self.validate_output = validate_output
        self.maci_role = maci_role
        self.enforce_maci = enforce_maci
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.maci = MACIEnforcer(audit_log=self.audit_log)

        if maci_role:
            self.maci.assign_role(agent_id, maci_role)
        if self.enforce_maci and self.maci_role is None:
            raise ValueError("enforce_maci=True requires an explicit maci_role")

    def _check_maci(self, governance_action: str | None) -> None:
        if not self.enforce_maci:
            return
        if not governance_action:
            raise GovernanceError(
                "GovernedAgent with enforce_maci=True requires governance_action",
                rule_id="MACI-ACTION",
            )
        self.maci.check(self.agent_id, governance_action)

    def run(self, input: str, *, governance_action: str | None = None, **kwargs: Any) -> Any:
        """Run the wrapped agent with governance.

        1. Optionally enforce MACI role boundaries (`enforce_maci=True`)
        2. Validate the primary input and serialized keyword arguments
        3. Execute the agent
        4. Validate serialized output (if enabled)
        5. Return result with audit trail

        Raises:
            ConstitutionalViolationError: If input/output violates rules.
        """
        # Step 1: Enforce MACI boundary, when enabled
        self._check_maci(governance_action)

        # Step 2: Validate input
        context = dict(kwargs)
        if governance_action is not None:
            context["governance_action"] = governance_action
        self.engine.validate(input, agent_id=self.agent_id, context=context)
        kwargs_payload = serialize_for_governance(kwargs)
        if kwargs_payload:
            self.engine.validate(kwargs_payload, agent_id=f"{self.agent_id}:kwargs")

        # Step 3: Execute agent
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

        # Step 4: Validate output
        if self.validate_output:
            output_payload = serialize_for_governance(result)
            if output_payload:
                self.engine.validate(
                    output_payload,
                    agent_id=f"{self.agent_id}:output",
                    context={"source": "agent_output"},
                )

        return result

    async def arun(
        self,
        input: str,
        *,
        governance_action: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Async version of run()."""
        # Step 1: Enforce MACI boundary, when enabled
        self._check_maci(governance_action)

        # Step 2: Validate input
        context = dict(kwargs)
        if governance_action is not None:
            context["governance_action"] = governance_action
        self.engine.validate(input, agent_id=self.agent_id, context=context)
        kwargs_payload = serialize_for_governance(kwargs)
        if kwargs_payload:
            self.engine.validate(kwargs_payload, agent_id=f"{self.agent_id}:kwargs")

        # Step 3: Execute agent
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

        # Step 4: Validate output
        if self.validate_output:
            output_payload = serialize_for_governance(result)
            if output_payload:
                self.engine.validate(
                    output_payload,
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
            f"rules={len(self.constitution)}, "
            f"maci_role={self.maci_role.value if self.maci_role else None!r}, "
            f"enforce_maci={self.enforce_maci})"
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
            audit_mode="full",
        )

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        engine = self.engine
        agent_id = self.agent_id

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                for payload in iter_governance_payloads(*args, kwargs):
                    engine.validate(payload, agent_id=agent_id)
                result = await func(*args, **kwargs)
                output_payload = serialize_for_governance(result)
                if output_payload:
                    engine.validate(output_payload, agent_id=f"{agent_id}:output")
                return result

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                for payload in iter_governance_payloads(*args, kwargs):
                    engine.validate(payload, agent_id=agent_id)
                result = func(*args, **kwargs)
                output_payload = serialize_for_governance(result)
                if output_payload:
                    engine.validate(output_payload, agent_id=f"{agent_id}:output")
                return result

            return sync_wrapper  # type: ignore[return-value]
