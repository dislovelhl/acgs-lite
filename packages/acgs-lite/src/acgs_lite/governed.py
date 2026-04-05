# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
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
import uuid
from collections.abc import Callable, Iterable
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

_MAX_RETRIES_LIMIT = 10

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.circuit_breaker import GovernanceCircuitBreaker
from acgs_lite.constitution import Constitution
from acgs_lite.constitution.refusal_reasoning import RefusalReasoningEngine
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError, GovernanceError
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


@runtime_checkable
class CapabilityProfileProtocol(Protocol):
    """Minimal capability profile surface used by GovernedAgent."""

    model_id: str
    provider_type: str


class CapabilityRegistryProtocol(Protocol):
    """Minimal capability registry surface used by GovernedAgent."""

    def get_all_profiles(self, active_only: bool = True) -> Iterable[CapabilityProfileProtocol]: ...


class GetCapabilityRegistryProtocol(Protocol):
    """Lazy capability registry loader."""

    def __call__(self) -> CapabilityRegistryProtocol: ...


class AttachResponseFormatProtocol(Protocol):
    """Lazy constrained-output hook."""

    def __call__(
        self,
        execution_kwargs: dict[str, Any],
        constitution: Constitution,
        capability_profile: CapabilityProfileProtocol | None,
    ) -> dict[str, Any]: ...


class _NoOpCapabilityRegistry:
    def get_all_profiles(self, active_only: bool = True) -> Iterable[CapabilityProfileProtocol]:
        return ()


def _noop_get_capability_registry() -> CapabilityRegistryProtocol:
    return _NoOpCapabilityRegistry()


def _noop_attach_response_format(
    execution_kwargs: dict[str, Any],
    constitution: Constitution,
    capability_profile: CapabilityProfileProtocol | None,
) -> dict[str, Any]:
    return execution_kwargs


def _load_get_capability_registry() -> GetCapabilityRegistryProtocol:
    try:
        from enhanced_agent_bus.llm_adapters.capability_matrix import get_capability_registry
    except ImportError:
        return _noop_get_capability_registry
    return cast(GetCapabilityRegistryProtocol, get_capability_registry)


def _load_attach_response_format() -> AttachResponseFormatProtocol:
    try:
        from enhanced_agent_bus.llm_adapters.constrained_output import attach_response_format
    except ImportError:
        return _noop_attach_response_format
    return cast(AttachResponseFormatProtocol, attach_response_format)


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
        max_retries: int = 0,
        circuit_breaker: GovernanceCircuitBreaker | None = None,
    ) -> None:
        self._agent = agent
        self.agent_id = agent_id
        self.validate_output = validate_output
        self.maci_role = maci_role
        self.enforce_maci = enforce_maci
        self.max_retries = min(max(0, max_retries), _MAX_RETRIES_LIMIT)
        self._circuit_breaker = circuit_breaker
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.maci = MACIEnforcer(audit_log=self.audit_log)
        self._refusal_engine = RefusalReasoningEngine(self.constitution)

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

    def _build_retry_prompt(
        self,
        original_input: str,
        error: ConstitutionalViolationError,
        attempt: int,
    ) -> str:
        """Build a remediation prompt from violation details.

        Only trusted content (rule IDs, rule text from the constitution) is
        used as top-level instructions.  User-controlled text (original_input)
        is truncated and quoted to reduce prompt-injection surface.
        """
        rule_id = error.rule_id or "UNKNOWN"
        # Look up the canonical rule text from the constitution (trusted source)
        rule_text = ""
        for r in self.constitution.rules:
            if r.id == rule_id:
                rule_text = r.text
                break

        decision = self._refusal_engine.reason_refusal(
            action=error.action or original_input,
            triggered_rule_ids=[rule_id] if rule_id != "UNKNOWN" else [],
        )
        parts = [
            f"[GOVERNANCE RETRY {attempt}] Your previous output violated constitutional rule {rule_id}.",
            f"Rule: {rule_text}" if rule_text else f"Rule ID: {rule_id}",
        ]
        if decision.suggestions:
            parts.append("Suggestions to produce a compliant response:")
            for s in decision.suggestions:
                parts.append(f"  - {s.rationale}")
        # Truncate and quote user-controlled input to limit injection surface.
        # Escape triple-quote sequences to prevent prompt breakout.
        safe_input = original_input[:200].replace('"""', '\\"\\"\\""')
        parts.append(f'Original request (quoted): """{safe_input}"""')
        parts.append("Please provide a response that complies with all governance rules.")
        return "\n".join(parts)

    def _execute_agent(self, input: str, **kwargs: Any) -> Any:
        """Execute the underlying agent (sync)."""
        if hasattr(self._agent, "run"):
            return self._agent.run(input, **kwargs)
        elif callable(self._agent):
            return self._agent(input, **kwargs)
        else:
            raise GovernanceError(
                f"Agent of type {type(self._agent).__name__} is not callable "
                "and has no .run() method",
                rule_id="AGENT-PROTOCOL",
            )

    def _resolve_capability_profile(
        self,
        explicit_profile: CapabilityProfileProtocol | None,
    ) -> CapabilityProfileProtocol | None:
        if explicit_profile is not None:
            return explicit_profile

        for attr_name in ("capability_profile", "provider_capability_profile"):
            profile = getattr(self._agent, attr_name, None)
            if profile is not None:
                return cast(CapabilityProfileProtocol, profile)

        provider_name_getter = getattr(self._agent, "get_provider_name", None)
        provider_name = provider_name_getter() if callable(provider_name_getter) else None
        if provider_name is None:
            provider_name = getattr(self._agent, "provider_type", None)

        model = getattr(self._agent, "model", None)
        if not isinstance(model, str):
            return None

        capability_registry = _load_get_capability_registry()()
        for profile in capability_registry.get_all_profiles(active_only=False):
            if profile.model_id != model:
                continue
            if isinstance(provider_name, str) and profile.provider_type != provider_name:
                continue
            return profile
        return None

    def _prepare_execution_kwargs(
        self, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        execution_kwargs = dict(kwargs)
        explicit_profile = cast(
            CapabilityProfileProtocol | None,
            execution_kwargs.pop("capability_profile", None),
        )
        if explicit_profile is None:
            explicit_profile = cast(
                CapabilityProfileProtocol | None,
                execution_kwargs.pop("provider_capability_profile", None),
            )

        if self.validate_output:
            capability_profile = self._resolve_capability_profile(explicit_profile)
            execution_kwargs = _load_attach_response_format()(
                execution_kwargs,
                self.constitution,
                capability_profile,
            )

        governance_kwargs = {
            key: value for key, value in execution_kwargs.items() if key != "response_format"
        }
        return execution_kwargs, governance_kwargs

    def _validate_output(self, result: Any) -> None:
        """Validate agent output against constitution. Raises on violation."""
        if not self.validate_output:
            return
        output_payload = serialize_for_governance(result)
        if output_payload:
            self.engine.validate(
                output_payload,
                agent_id=f"{self.agent_id}:output",
                context={"source": "agent_output"},
            )

    def run(self, input: str, *, governance_action: str | None = None, **kwargs: Any) -> Any:
        """Run the wrapped agent with governance.

        1. Optionally enforce MACI role boundaries (`enforce_maci=True`)
        2. Validate the primary input and serialized keyword arguments
        3. Execute the agent
        4. Validate serialized output (if enabled)
        5. On output violation with ``max_retries > 0``, re-invoke the agent
           with a remediation prompt (up to ``max_retries`` times)
        6. Return result with audit trail

        Raises:
            ConstitutionalViolationError: If input/output violates rules
                after all retries are exhausted.
            GovernanceHaltError: If the circuit breaker is tripped.
        """
        # Step 0: Check circuit breaker (Article 14 kill-switch)
        if self._circuit_breaker is not None:
            self._circuit_breaker.check()

        # Step 1: Enforce MACI boundary, when enabled
        self._check_maci(governance_action)
        execution_kwargs, governance_kwargs = self._prepare_execution_kwargs(kwargs)

        # Step 2: Validate input (no retries for input violations)
        context = dict(governance_kwargs)
        if governance_action is not None:
            context["governance_action"] = governance_action
        self.engine.validate(input, agent_id=self.agent_id, context=context)
        kwargs_payload = serialize_for_governance(governance_kwargs)
        if kwargs_payload:
            self.engine.validate(kwargs_payload, agent_id=f"{self.agent_id}:kwargs")

        # Step 3: Execute agent
        result = self._execute_agent(input, **execution_kwargs)

        # Step 4: Validate output with retry loop
        last_error: ConstitutionalViolationError | None = None
        for attempt in range(1, self.max_retries + 2):  # 1-indexed, includes original
            try:
                self._validate_output(result)
                return result
            except ConstitutionalViolationError as exc:
                last_error = exc
                retries_remaining = self.max_retries - attempt + 1
                if retries_remaining <= 0:
                    raise
                # Audit the retry attempt
                self.audit_log.record(
                    AuditEntry(
                        id=f"retry-{self.agent_id}-{attempt}-{uuid.uuid4().hex[:8]}",
                        type="output_retry",
                        agent_id=self.agent_id,
                        action=f"retry:output_violation:{attempt}",
                        valid=False,
                        violations=[exc.rule_id or "UNKNOWN"],
                        constitutional_hash=self.engine._const_hash,
                        metadata={
                            "attempt": attempt,
                            "retries_after_this": retries_remaining - 1,
                            "rule_id": exc.rule_id,
                        },
                    )
                )
                retry_prompt = self._build_retry_prompt(input, exc, attempt)
                result = self._execute_agent(retry_prompt, **execution_kwargs)

        # Should not reach here, but fail-closed
        if last_error is not None:
            raise last_error
        return result

    async def _aexecute_agent(self, input: str, **kwargs: Any) -> Any:
        """Execute the underlying agent (async)."""
        if hasattr(self._agent, "arun"):
            return await self._agent.arun(input, **kwargs)
        elif hasattr(self._agent, "run"):
            if inspect.iscoroutinefunction(self._agent.run):
                return await self._agent.run(input, **kwargs)
            else:
                return await asyncio.to_thread(self._agent.run, input, **kwargs)
        elif callable(self._agent):
            if inspect.iscoroutinefunction(self._agent):
                return await self._agent(input, **kwargs)
            else:
                return await asyncio.to_thread(self._agent, input, **kwargs)
        else:
            raise GovernanceError(
                f"Agent of type {type(self._agent).__name__} is not callable",
                rule_id="AGENT-PROTOCOL",
            )

    async def arun(
        self,
        input: str,
        *,
        governance_action: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Async version of run() with output-violation retry support."""
        # Step 1: Enforce MACI boundary, when enabled
        self._check_maci(governance_action)
        execution_kwargs, governance_kwargs = self._prepare_execution_kwargs(kwargs)

        # Step 2: Validate input (no retries for input violations)
        context = dict(governance_kwargs)
        if governance_action is not None:
            context["governance_action"] = governance_action
        self.engine.validate(input, agent_id=self.agent_id, context=context)
        kwargs_payload = serialize_for_governance(governance_kwargs)
        if kwargs_payload:
            self.engine.validate(kwargs_payload, agent_id=f"{self.agent_id}:kwargs")

        # Step 3: Execute agent
        result = await self._aexecute_agent(input, **execution_kwargs)

        # Step 4: Validate output with retry loop
        last_error: ConstitutionalViolationError | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                self._validate_output(result)
                return result
            except ConstitutionalViolationError as exc:
                last_error = exc
                retries_remaining = self.max_retries - attempt + 1
                if retries_remaining <= 0:
                    raise
                self.audit_log.record(
                    AuditEntry(
                        id=f"retry-{self.agent_id}-{attempt}-{uuid.uuid4().hex[:8]}",
                        type="output_retry",
                        agent_id=self.agent_id,
                        action=f"retry:output_violation:{attempt}",
                        valid=False,
                        violations=[exc.rule_id or "UNKNOWN"],
                        constitutional_hash=self.engine._const_hash,
                        metadata={
                            "attempt": attempt,
                            "retries_after_this": retries_remaining - 1,
                            "rule_id": exc.rule_id,
                        },
                    )
                )
                retry_prompt = self._build_retry_prompt(input, exc, attempt)
                result = await self._aexecute_agent(retry_prompt, **execution_kwargs)

        if last_error is not None:
            raise last_error
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
