"""Agent DNA — embedded constitutional governance co-processor.

Every agent carries an immutable constitutional validator that intercepts
outputs before they leave. Governance is local (443ns), not networked.
No central bus needed. Scales to 800+ agents with O(1) governance cost.
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

from acgs_lite import (
    Constitution,
    ConstitutionalViolationError,
    GovernanceEngine,
    MACIEnforcer,
    MACIRole,
    Rule,
)

F = TypeVar("F", bound=Callable[..., Any])


class DNADisabledError(RuntimeError):
    """Raised when validate() is called on a disabled AgentDNA."""


@dataclass(frozen=True, slots=True)
class DNAValidationResult:
    """Result of a DNA validation check."""

    valid: bool
    action: str
    violations: tuple[str, ...] = ()
    latency_ns: int = 0
    constitutional_hash: str = ""


@dataclass
class AgentDNA:
    """Constitutional co-processor embedded in every agent.

    Validates inputs and outputs locally using the ACGS Rust engine.
    No network calls. No central bus. O(1) per validation.

    Usage:
        dna = AgentDNA.from_rules([...])
        dna = AgentDNA.from_yaml("constitution.yaml")
        dna = AgentDNA(constitution=my_constitution)

        # Validate explicitly
        result = dna.validate("some action")

        # Or use as decorator
        @dna.govern
        def my_agent(input: str) -> str: ...
    """

    constitution: Constitution
    agent_id: str = "anonymous"
    maci_role: MACIRole | None = None
    strict: bool = True
    validate_output: bool = True
    _engine: GovernanceEngine = field(init=False, repr=False)
    _maci: MACIEnforcer | None = field(init=False, repr=False, default=None)
    _call_count: int = field(init=False, repr=False, default=0)
    _violation_count: int = field(init=False, repr=False, default=0)
    _total_latency_ns: int = field(init=False, repr=False, default=0)
    _disabled: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_engine", GovernanceEngine(self.constitution, strict=self.strict)
        )
        if self.maci_role is not None:
            enforcer = MACIEnforcer()
            enforcer.assign_role(self.agent_id, self.maci_role)
            object.__setattr__(self, "_maci", enforcer)

    @classmethod
    def from_rules(
        cls,
        rules: list[Rule],
        *,
        name: str = "agent-dna",
        agent_id: str = "anonymous",
        maci_role: MACIRole | None = None,
        strict: bool = True,
        validate_output: bool = True,
    ) -> AgentDNA:
        """Create DNA from a list of rules."""
        return cls(
            constitution=Constitution.from_rules(rules, name=name),
            agent_id=agent_id,
            maci_role=maci_role,
            strict=strict,
            validate_output=validate_output,
        )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        *,
        agent_id: str = "anonymous",
        maci_role: MACIRole | None = None,
        strict: bool = True,
        validate_output: bool = True,
    ) -> AgentDNA:
        """Create DNA from a YAML constitution file."""
        return cls(
            constitution=Constitution.from_yaml(path),
            agent_id=agent_id,
            maci_role=maci_role,
            strict=strict,
            validate_output=validate_output,
        )

    @classmethod
    def default(
        cls,
        *,
        agent_id: str = "anonymous",
        maci_role: MACIRole | None = None,
        validate_output: bool = True,
    ) -> AgentDNA:
        """Create DNA with the default ACGS constitution."""
        return cls(
            constitution=Constitution.default(),
            agent_id=agent_id,
            maci_role=maci_role,
            validate_output=validate_output,
        )

    def disable(self) -> None:
        """Kill switch — disable all constitutional validation.

        While disabled, validate() raises DNADisabledError.
        EU AI Act Art. 14(3): human-initiated halt capability.
        """
        object.__setattr__(self, "_disabled", True)

    def enable(self) -> None:
        """Re-enable constitutional validation after a halt."""
        object.__setattr__(self, "_disabled", False)

    @property
    def is_disabled(self) -> bool:
        """Whether this DNA co-processor is currently disabled."""
        return self._disabled

    @property
    def hash(self) -> str:
        """Constitutional hash — must match across all swarm agents."""
        return self.constitution.hash

    @property
    def stats(self) -> dict[str, Any]:
        """Governance statistics."""
        return {
            "agent_id": self.agent_id,
            "constitutional_hash": self.hash,
            "maci_role": self.maci_role.value if self.maci_role else None,
            "calls": self._call_count,
            "violations": self._violation_count,
            "avg_latency_ns": (
                self._total_latency_ns // self._call_count
                if self._call_count > 0
                else 0
            ),
        }

    def validate(self, action: str) -> DNAValidationResult:
        """Validate an action against the embedded constitution.

        In strict mode, raises ConstitutionalViolationError on critical violations.
        In non-strict mode, returns result with violations listed.

        Raises:
            DNADisabledError: If the DNA co-processor has been disabled via kill switch.
        """
        if self._disabled:
            raise DNADisabledError(
                f"Agent {self.agent_id} DNA is disabled — all actions blocked"
            )
        start = time.perf_counter_ns()
        try:
            result = self._engine.validate(action)
            elapsed = time.perf_counter_ns() - start
            self._call_count += 1
            self._total_latency_ns += elapsed
            violations = tuple(
                f"{v.rule_id}: {v.rule_text}" for v in result.violations
            )
            if violations:
                self._violation_count += 1
            return DNAValidationResult(
                valid=result.valid,
                action=action,
                violations=violations,
                latency_ns=elapsed,
                constitutional_hash=self.hash,
            )
        except ConstitutionalViolationError:
            elapsed = time.perf_counter_ns() - start
            self._call_count += 1
            self._violation_count += 1
            self._total_latency_ns += elapsed
            raise

    def check_maci(self, action_type: str) -> None:
        """Verify MACI role permits this action type.

        Raises MACIViolationError if the agent's role cannot perform the action.
        """
        if self._maci is not None:
            self._maci.check(self.agent_id, action_type)

    def govern(self, fn: F) -> F:
        """Decorator that wraps a function with constitutional DNA validation.

        Validates input before execution and output after.
        """
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                input_str = _extract_input(args, kwargs)
                self.validate(input_str)
                result = await fn(*args, **kwargs)
                if self.validate_output:
                    output_str = _extract_output(result)
                    if output_str:
                        self.validate(output_str)
                return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            input_str = _extract_input(args, kwargs)
            self.validate(input_str)
            result = fn(*args, **kwargs)
            if self.validate_output:
                output_str = _extract_output(result)
                if output_str:
                    self.validate(output_str)
            return result

        return sync_wrapper  # type: ignore[return-value]


def constitutional_dna(
    fn: F | None = None,
    *,
    constitution: Constitution | None = None,
    rules: list[Rule] | None = None,
    yaml_path: str | Path | None = None,
    agent_id: str = "anonymous",
    maci_role: MACIRole | None = None,
    strict: bool = True,
    validate_output: bool = True,
) -> F | Callable[[F], F]:
    """Decorator that embeds constitutional DNA into any callable.

    Usage:
        @constitutional_dna
        def my_agent(input: str) -> str: ...

        @constitutional_dna(rules=[...], agent_id="worker-01")
        def my_agent(input: str) -> str: ...

        @constitutional_dna(yaml_path="governance.yaml")
        async def my_agent(input: str) -> str: ...
    """

    def _build_dna() -> AgentDNA:
        if constitution is not None:
            return AgentDNA(
                constitution=constitution,
                agent_id=agent_id,
                maci_role=maci_role,
                strict=strict,
                validate_output=validate_output,
            )
        if rules is not None:
            return AgentDNA.from_rules(
                rules,
                agent_id=agent_id,
                maci_role=maci_role,
                strict=strict,
                validate_output=validate_output,
            )
        if yaml_path is not None:
            return AgentDNA.from_yaml(
                yaml_path,
                agent_id=agent_id,
                maci_role=maci_role,
                strict=strict,
                validate_output=validate_output,
            )
        return AgentDNA.default(
            agent_id=agent_id,
            maci_role=maci_role,
            validate_output=validate_output,
        )

    def decorator(f: F) -> F:
        dna = _build_dna()
        governed = dna.govern(f)
        governed._dna = dna  # type: ignore[attr-defined]
        return governed

    if fn is not None:
        return decorator(fn)
    return decorator


def _extract_input(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extract the input string from function arguments."""
    if "input" in kwargs:
        return str(kwargs["input"])
    if "prompt" in kwargs:
        return str(kwargs["prompt"])
    if args:
        return str(args[0])
    return ""


def _extract_output(result: Any) -> str:
    """Extract validatable string from any output type.

    Handles str, dict, list, and objects with custom __str__.
    Prevents C1: non-string outputs bypassing validation.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return json.dumps(result, default=str)
    if isinstance(result, (list, tuple)):
        return json.dumps(result, default=str)
    if result is None:
        return ""
    if type(result).__str__ is not object.__str__:
        return str(result)
    return ""
