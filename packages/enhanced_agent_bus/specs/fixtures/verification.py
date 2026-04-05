"""
ACGS-2 Verification Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for MACI role enforcement and Z3 verification testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class SelfValidationError(ACGSBaseError):
    """Raised when an agent attempts to validate its own output."""

    http_status_code = 403
    error_code = "SELF_VALIDATION_ERROR"

    def __init__(self, agent: str, action: str):
        self.agent = agent
        self.action = action
        super().__init__(
            f"Agent '{agent}' cannot {action} its own output (Gödel bypass)",
            details={"agent": agent, "action": action},
        )


class RoleViolationError(ACGSBaseError):
    """Raised when an agent attempts an action outside its role."""

    http_status_code = 403
    error_code = "ROLE_VIOLATION_ERROR"

    def __init__(self, agent: str, role: str, action: str):
        self.agent = agent
        self.role = role
        self.action = action
        super().__init__(
            f"Agent '{agent}' ({role}) cannot perform '{action}'",
            details={"agent": agent, "role": role, "action": action},
        )


class MACIRole(Enum):
    """MACI Framework roles (separation of powers)."""

    EXECUTIVE = "executive"  # Proposes decisions
    LEGISLATIVE = "legislative"  # Extracts rules
    JUDICIAL = "judicial"  # Validates decisions


@dataclass
class MACIAgent:
    """
    An agent in the MACI framework.

    Implements role-based access control to prevent Gödel bypass attacks.
    """

    name: str
    role: MACIRole
    outputs: list[str] = field(default_factory=list)

    def propose(self, content: str) -> str:
        """
        Propose a decision (Executive only).

        Args:
            content: Decision content

        Returns:
            Output ID

        Raises:
            RoleViolationError: If agent is not Executive
        """
        if self.role != MACIRole.EXECUTIVE:
            raise RoleViolationError(self.name, self.role.value, "propose")

        output_id = f"{self.name}:{len(self.outputs)}"
        self.outputs.append(output_id)
        return output_id

    def validate(self, output_id: str, target_agent: "MACIAgent" | None = None) -> bool:
        """
        Validate an output (Judicial only).

        Args:
            output_id: ID of output to validate
            target_agent: Agent that produced the output

        Returns:
            True if valid

        Raises:
            RoleViolationError: If agent is not Judicial
            SelfValidationError: If validating own output
        """
        if self.role != MACIRole.JUDICIAL:
            raise RoleViolationError(self.name, self.role.value, "validate")

        # Check for self-validation (Gödel bypass)
        if output_id in self.outputs:
            raise SelfValidationError(self.name, "validate")

        # Check target agent role
        if target_agent:
            if target_agent.role == MACIRole.JUDICIAL:
                raise RoleViolationError(self.name, self.role.value, "validate judicial outputs")

        return True

    def extract_rules(self, content: str) -> list[str]:
        """
        Extract rules from content (Legislative only).

        Args:
            content: Content to extract rules from

        Returns:
            List of extracted rules

        Raises:
            RoleViolationError: If agent is not Legislative
        """
        if self.role != MACIRole.LEGISLATIVE:
            raise RoleViolationError(self.name, self.role.value, "extract_rules")

        # Mock rule extraction
        return [f"rule_{i}" for i in range(3)]


@dataclass
class MACIFramework:
    """
    Complete MACI framework with separation of powers.

    Implements the verification layer's role enforcement.
    """

    executive_agent: MACIAgent = field(
        default_factory=lambda: MACIAgent("executive", MACIRole.EXECUTIVE)
    )
    legislative_agent: MACIAgent = field(
        default_factory=lambda: MACIAgent("legislative", MACIRole.LEGISLATIVE)
    )
    judicial_agent: MACIAgent = field(
        default_factory=lambda: MACIAgent("judicial", MACIRole.JUDICIAL)
    )
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def get_agent(self, role: str) -> MACIAgent:
        """Get agent by role name."""
        role_map = {
            "executive": self.executive_agent,
            "legislative": self.legislative_agent,
            "judicial": self.judicial_agent,
        }
        return role_map[role]


class Z3Result(Enum):
    """Z3 solver result types."""

    SAT = "sat"
    UNSAT = "unsat"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class Z3VerificationResult:
    """Result of Z3 verification."""

    sat: bool
    result: Z3Result
    model: JSONDict | None = None
    unsat_core: list[str] | None = None
    time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "sat": self.sat,
            "result": self.result.value,
            "model": self.model,
            "unsat_core": self.unsat_core,
            "time_ms": self.time_ms,
            "constitutional_hash": self.constitutional_hash,
        }


class SpecZ3SolverContext:
    """
    Z3 solver context for specification testing.

    Provides mock verification behavior matching spec requirements.
    """

    def __init__(self):
        self.verification_log: list[Z3VerificationResult] = []
        self.timeout_ms: float = 1000.0
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def verify(self, constraint_str: str) -> Z3VerificationResult:
        """
        Verify constraints using Z3 (mock implementation for specs).

        Args:
            constraint_str: Constraint expression string

        Returns:
            Z3VerificationResult with SAT/UNSAT determination
        """
        # Parse constraint for spec behavior
        result = self._evaluate_constraint(constraint_str)
        self.verification_log.append(result)
        return result

    def _evaluate_constraint(self, constraint_str: str) -> Z3VerificationResult:
        """Evaluate constraint based on spec rules."""
        constraint_str = constraint_str.strip().lower()

        # Handle explicit true/false
        if constraint_str == "true":
            return Z3VerificationResult(
                sat=True,
                result=Z3Result.SAT,
                model={},
            )
        elif constraint_str == "false":
            return Z3VerificationResult(
                sat=False,
                result=Z3Result.UNSAT,
                unsat_core=["c1"],
            )

        # Handle contradiction patterns
        if "x = x + 1" in constraint_str:
            return Z3VerificationResult(
                sat=False,
                result=Z3Result.UNSAT,
                unsat_core=["c1"],
            )

        # Handle range contradictions (x > 10 AND x < 5)
        if ">" in constraint_str and "<" in constraint_str:
            # Simple check for contradictory ranges
            if "x > 10" in constraint_str and "x < 5" in constraint_str:
                return Z3VerificationResult(
                    sat=False,
                    result=Z3Result.UNSAT,
                    unsat_core=["c1", "c2"],
                )

        # Handle satisfiable range constraints (x > 0 AND x < 10)
        if "x > 0" in constraint_str and "x < 10" in constraint_str:
            return Z3VerificationResult(
                sat=True,
                result=Z3Result.SAT,
                model={"x": 5},
            )

        # Default to SAT for simple constraints
        return Z3VerificationResult(
            sat=True,
            result=Z3Result.SAT,
            model={},
        )

    def reset(self) -> None:
        """Clear verification log."""
        self.verification_log.clear()


@pytest.fixture
def maci_framework() -> MACIFramework:
    """
    Fixture providing a MACI framework for spec testing.

    Use in tests verifying role separation:
        def test_executive_proposes(maci_framework):
            output = maci_framework.executive_agent.propose("decision")
            assert output is not None

        def test_executive_cannot_validate(maci_framework):
            with pytest.raises(RoleViolationError):
                maci_framework.executive_agent.validate("output:1")
    """
    return MACIFramework()


@pytest.fixture
def z3_solver_context() -> SpecZ3SolverContext:
    """
    Fixture providing a Z3 solver context for spec testing.

    Use in tests verifying Z3 behavior:
        def test_satisfiable(z3_solver_context):
            result = z3_solver_context.verify("x > 0 AND x < 10")
            assert result.sat is True
    """
    return SpecZ3SolverContext()


def execute_action(
    agent: MACIAgent,
    action: str,
    target: str | None,
) -> object:
    """
    Helper to execute MACI agent actions for spec testing.

    Args:
        agent: The MACI agent
        action: Action to execute (propose, validate, extract_rules)
        target: Target for validation (own, executive, judicial)

    Returns:
        Action result

    Raises:
        RoleViolationError: If action violates role
        SelfValidationError: If self-validation attempted
    """
    if action == "propose":
        return agent.propose("test_content")
    elif action == "validate":
        if target == "own":
            # Create an output and try to validate it
            output_id = f"{agent.name}:self"
            agent.outputs.append(output_id)
            return agent.validate(output_id)
        elif target == "executive":
            return agent.validate("executive:0")
        elif target == "judicial":
            # Create mock judicial agent
            judicial = MACIAgent("judicial_other", MACIRole.JUDICIAL)
            return agent.validate("judicial:0", judicial)
        else:
            return agent.validate("other:0")
    elif action == "extract_rules":
        return agent.extract_rules("content")
    else:
        raise ValueError(f"Unknown action: {action}")
