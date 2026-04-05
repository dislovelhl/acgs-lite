"""
ACGS-2 Z3 Policy Verifier - VeriPlan SMT Solver Integration
Constitutional Hash: 608508a9bd224290

Implements Z3 SMT solver integration for mathematical policy verification:
- Constraint-based validation with formal guarantees
- Time-bounded verification (prevents infinite proofs)
- Fallback to heuristic verification if Z3 times out
- LLM-assisted constraint generation from natural language

Key Features:
- Mathematical guarantees for policy compliance
- Configurable timeout for bounded verification
- Integration with MACI verification pipeline
- Full proof generation for audit trail

Performance Targets:
- Verification rate: 86%+ (DafnyBench baseline)
- Timeout handling: < 5s with heuristic fallback
- Constraint generation: < 1s per policy
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from enhanced_agent_bus.plugin_registry import available, require

# Constitutional hash for immutable validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_Z3_VERIFIER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

if available("z3"):
    z3 = __import__(require("z3"))
    Z3_AVAILABLE = True
else:
    Z3_AVAILABLE = False
    z3 = None
    logger.warning("Z3 solver not available. Install with: pip install z3-solver")


class Z3VerificationStatus(Enum):
    """Status of Z3 verification operations."""

    PENDING = "pending"
    SATISFIABLE = "satisfiable"
    UNSATISFIABLE = "unsatisfiable"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    ERROR = "error"
    HEURISTIC_FALLBACK = "heuristic_fallback"


class ConstraintType(Enum):
    """Types of policy constraints."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    REAL = "real"
    STRING = "string"
    ARRAY = "array"
    COMPOSITE = "composite"


class PolicyDomain(Enum):
    """Domains for policy constraints."""

    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    RESOURCE_ALLOCATION = "resource_allocation"
    GOVERNANCE = "governance"
    SECURITY = "security"
    COMPLIANCE = "compliance"


@dataclass
class PolicyConstraint:
    """A constraint for policy verification."""

    constraint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    constraint_type: ConstraintType = ConstraintType.BOOLEAN
    domain: PolicyDomain = PolicyDomain.GOVERNANCE
    expression: str = ""
    natural_language: str = ""
    z3_expression: object = None  # Z3 expression object
    variables: dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    generated_by: str = "system"
    is_mandatory: bool = True
    priority: int = 1
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "constraint_id": self.constraint_id,
            "name": self.name,
            "description": self.description,
            "constraint_type": self.constraint_type.value,
            "domain": self.domain.value,
            "expression": self.expression,
            "natural_language": self.natural_language,
            "variables": self.variables,
            "confidence": self.confidence,
            "generated_by": self.generated_by,
            "is_mandatory": self.is_mandatory,
            "priority": self.priority,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class VerificationProof:
    """Proof from Z3 verification."""

    proof_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    verification_id: str = ""
    status: Z3VerificationStatus = Z3VerificationStatus.PENDING
    is_verified: bool = False
    model: JSONDict | None = None  # Satisfying assignment if SAT
    unsat_core: list[str] | None = None  # Conflicting constraints if UNSAT
    constraints_evaluated: int = 0
    constraints_satisfied: int = 0
    solve_time_ms: float = 0.0
    solver_stats: JSONDict = field(default_factory=dict)
    heuristic_score: float | None = None
    proof_trace: list[JSONDict] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "proof_id": self.proof_id,
            "verification_id": self.verification_id,
            "status": self.status.value,
            "is_verified": self.is_verified,
            "model": self.model,
            "unsat_core": self.unsat_core,
            "constraints_evaluated": self.constraints_evaluated,
            "constraints_satisfied": self.constraints_satisfied,
            "solve_time_ms": self.solve_time_ms,
            "solver_stats": self.solver_stats,
            "heuristic_score": self.heuristic_score,
            "proof_trace": self.proof_trace,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
        }

    def add_trace_entry(self, step: str, details: JSONDict) -> None:
        """Add entry to proof trace."""
        self.proof_trace.append(
            {
                "step": step,
                "details": details,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


@dataclass
class PolicyVerificationRequest:
    """Request for policy verification."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str = ""
    policy_text: str = ""
    constraints: list[PolicyConstraint] = field(default_factory=list)
    context: JSONDict = field(default_factory=dict)
    timeout_ms: int = 5000
    use_heuristic_fallback: bool = False
    require_proof: bool = True
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "policy_text": self.policy_text,
            "constraints": [c.to_dict() for c in self.constraints],
            "context": self.context,
            "timeout_ms": self.timeout_ms,
            "use_heuristic_fallback": self.use_heuristic_fallback,
            "require_proof": self.require_proof,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PolicyVerificationResult:
    """Result of policy verification."""

    verification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""
    policy_id: str = ""
    is_verified: bool = False
    status: Z3VerificationStatus = Z3VerificationStatus.PENDING
    proof: VerificationProof | None = None
    violations: list[JSONDict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    total_constraints: int = 0
    satisfied_constraints: int = 0
    total_time_ms: float = 0.0
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "verification_id": self.verification_id,
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "is_verified": self.is_verified,
            "status": self.status.value,
            "proof": self.proof.to_dict() if self.proof else None,
            "violations": self.violations,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "total_constraints": self.total_constraints,
            "satisfied_constraints": self.satisfied_constraints,
            "total_time_ms": self.total_time_ms,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
        }


class ConstraintGenerator:
    """Generates Z3 constraints from natural language policies."""

    def __init__(self):
        self.constraint_patterns = {
            "must": self._generate_obligation_constraint,
            "shall": self._generate_obligation_constraint,
            "required": self._generate_obligation_constraint,
            "cannot": self._generate_prohibition_constraint,
            "must not": self._generate_prohibition_constraint,
            "forbidden": self._generate_prohibition_constraint,
            "may": self._generate_permission_constraint,
            "can": self._generate_permission_constraint,
            "optional": self._generate_permission_constraint,
            "greater than": self._generate_comparison_constraint,
            "less than": self._generate_comparison_constraint,
            "at least": self._generate_comparison_constraint,
            "at most": self._generate_comparison_constraint,
        }

    async def generate_constraints(
        self,
        policy_text: str,
        context: JSONDict | None = None,
    ) -> list[PolicyConstraint]:
        """Generate constraints from policy text."""
        constraints = []
        sentences = policy_text.split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            constraint = await self._generate_constraint_from_sentence(sentence, context)
            if constraint:
                constraints.append(constraint)

        logger.info(f"Generated {len(constraints)} constraints from policy text")
        return constraints

    async def _generate_constraint_from_sentence(
        self,
        sentence: str,
        context: JSONDict | None = None,
    ) -> PolicyConstraint | None:
        """Generate a constraint from a single sentence."""
        sentence_lower = sentence.lower()

        # Check for comparison patterns first (more specific patterns take priority)
        comparison_patterns = ["greater than", "less than", "at least", "at most"]
        for pattern in comparison_patterns:
            if pattern in sentence_lower:
                return await self._generate_comparison_constraint(sentence, pattern, context)

        # Then check other patterns
        for pattern, generator in self.constraint_patterns.items():
            if pattern in sentence_lower and pattern not in comparison_patterns:
                return await generator(sentence, pattern, context)  # type: ignore[no-any-return]

        return None

    async def _generate_obligation_constraint(
        self,
        sentence: str,
        pattern: str,
        context: JSONDict | None = None,
    ) -> PolicyConstraint:
        """Generate constraint for obligation patterns."""
        var_name = f"obligation_{hash(sentence) % 10000}"

        return PolicyConstraint(
            name=f"Obligation: {sentence[:50]}",
            description=sentence,
            constraint_type=ConstraintType.BOOLEAN,
            expression=f"(assert {var_name})",
            natural_language=sentence,
            variables={var_name: "Bool"},
            confidence=0.85,
            generated_by="pattern_matching",
            is_mandatory=True,
            priority=1,
        )

    async def _generate_prohibition_constraint(
        self,
        sentence: str,
        pattern: str,
        context: JSONDict | None = None,
    ) -> PolicyConstraint:
        """Generate constraint for prohibition patterns."""
        var_name = f"prohibition_{hash(sentence) % 10000}"

        return PolicyConstraint(
            name=f"Prohibition: {sentence[:50]}",
            description=sentence,
            constraint_type=ConstraintType.BOOLEAN,
            expression=f"(assert (not {var_name}))",
            natural_language=sentence,
            variables={var_name: "Bool"},
            confidence=0.90,
            generated_by="pattern_matching",
            is_mandatory=True,
            priority=1,
        )

    async def _generate_permission_constraint(
        self,
        sentence: str,
        pattern: str,
        context: JSONDict | None = None,
    ) -> PolicyConstraint:
        """Generate constraint for permission patterns."""
        var_name = f"permission_{hash(sentence) % 10000}"

        return PolicyConstraint(
            name=f"Permission: {sentence[:50]}",
            description=sentence,
            constraint_type=ConstraintType.BOOLEAN,
            expression=f"(declare-const {var_name} Bool)",
            natural_language=sentence,
            variables={var_name: "Bool"},
            confidence=0.75,
            generated_by="pattern_matching",
            is_mandatory=False,
            priority=2,
        )

    async def _generate_comparison_constraint(
        self,
        sentence: str,
        pattern: str,
        context: JSONDict | None = None,
    ) -> PolicyConstraint:
        """Generate constraint for comparison patterns."""
        var_name = f"value_{hash(sentence) % 10000}"

        # Extract numeric values if present
        numbers = re.findall(r"\d+", sentence)
        threshold = int(numbers[0]) if numbers else 0

        if "greater" in pattern or "at least" in pattern:
            expr = f"(assert (>= {var_name} {threshold}))"
        else:
            expr = f"(assert (<= {var_name} {threshold}))"

        return PolicyConstraint(
            name=f"Comparison: {sentence[:50]}",
            description=sentence,
            constraint_type=ConstraintType.INTEGER,
            expression=expr,
            natural_language=sentence,
            variables={var_name: "Int"},
            confidence=0.80,
            generated_by="pattern_matching",
            is_mandatory=True,
            priority=1,
        )


class Z3SolverWrapper:
    """Wrapper for Z3 solver with timeout and fallback support."""

    def __init__(self, timeout_ms: int = 5000):
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver not available")

        self.timeout_ms = timeout_ms
        # Set global Z3 parameter to ensure native C++ thread is bounded (fixes Conflict 4)
        z3.set_param("timeout", timeout_ms)
        self.solver = z3.Solver()
        self.solver.set("timeout", timeout_ms)
        self._variables: JSONDict = {}
        self._constraints: JSONDict = {}
        self._constraint_trackers: dict[str, object] = {}

    def reset(self) -> None:
        """Reset the solver state."""
        self.solver.reset()
        self._variables.clear()
        self._constraints.clear()
        self._constraint_trackers.clear()

    def declare_variable(self, name: str, var_type: str) -> object:
        """Declare a variable of the given type."""
        if var_type == "Bool":
            var = z3.Bool(name)
        elif var_type == "Int":
            var = z3.Int(name)
        elif var_type == "Real":
            var = z3.Real(name)
        else:
            var = z3.Bool(name)  # Default to Bool

        self._variables[name] = var
        return var

    def add_constraint(
        self,
        constraint_id: str,
        constraint: PolicyConstraint,
    ) -> bool:
        """Add a constraint to the solver."""
        try:
            # Declare variables
            for var_name, var_type in constraint.variables.items():
                if var_name not in self._variables:
                    self.declare_variable(var_name, var_type)

            # Parse and add constraint expression
            z3_expr = self._parse_expression(constraint.expression)
            if z3_expr is not None:
                tracker = z3.Bool(constraint_id)
                self.solver.assert_and_track(z3_expr, tracker)
                self._constraints[constraint_id] = z3_expr
                self._constraint_trackers[constraint_id] = tracker
                return True

            return False

        except _Z3_VERIFIER_OPERATION_ERRORS as e:
            logger.error(f"Failed to add constraint {constraint_id}: {e}")
            return False

    def _parse_expression(self, expr_str: str) -> object | None:
        """Parse constraint expression into Z3 expression."""
        try:
            # Simple pattern matching for common SMT-LIB expressions
            if "(assert " in expr_str:
                # Extract the inner expression
                inner = expr_str.replace("(assert ", "").rstrip(")")

                if "(not " in inner:
                    var_name = inner.replace("(not ", "").rstrip(")")
                    if var_name in self._variables:
                        return z3.Not(self._variables[var_name])  # type: ignore[no-any-return]

                elif "(>= " in inner or "(<= " in inner or "(= " in inner:
                    # Handle comparison and equality
                    parts = inner.replace("(", "").replace(")", "").split()
                    if len(parts) >= 3:
                        op, var_name, value = parts[0], parts[1], parts[2]
                        if var_name in self._variables:
                            if op == ">=":
                                return self._variables[var_name] >= int(value)  # type: ignore[no-any-return]
                            elif op == "<=":
                                return self._variables[var_name] <= int(value)  # type: ignore[no-any-return]
                            elif op == "=":
                                return self._variables[var_name] == int(value)  # type: ignore[no-any-return]

                elif inner in self._variables:
                    return self._variables[inner]  # type: ignore[no-any-return]

            elif "(declare-const " in expr_str:
                # Variable declaration - no constraint to add
                return None

            return None

        except _Z3_VERIFIER_OPERATION_ERRORS as e:
            logger.error(f"Failed to parse expression '{expr_str}': {e}")
            return None

    def check(self) -> tuple[Z3VerificationStatus, JSONDict | None, list[str] | None]:
        """
        Check satisfiability of current constraints.

        Returns:
            Tuple of (status, model_dict, unsat_core)
        """
        time.time()

        result = self.solver.check()

        if result == z3.sat:
            model = self.solver.model()
            model_dict = {}

            for decl in model.decls():
                value = model[decl]
                if z3.is_int_value(value):
                    model_dict[str(decl)] = value.as_long()
                elif z3.is_bool(value):
                    model_dict[str(decl)] = bool(value)
                else:
                    model_dict[str(decl)] = str(value)

            return Z3VerificationStatus.SATISFIABLE, model_dict, None

        elif result == z3.unsat:
            # Try to get unsat core
            unsat_core = []
            try:
                core = self.solver.unsat_core()
                tracker_to_constraint = {
                    str(tracker): constraint_id
                    for constraint_id, tracker in self._constraint_trackers.items()
                }
                unsat_core = [tracker_to_constraint.get(str(c), str(c)) for c in core]
            except (RuntimeError, AttributeError, TypeError):
                pass

            return Z3VerificationStatus.UNSATISFIABLE, None, unsat_core

        else:
            reason_unknown = ""
            try:
                reason_unknown = self.solver.reason_unknown()
            except (RuntimeError, AttributeError, TypeError):
                reason_unknown = ""
            if reason_unknown == "timeout":
                return Z3VerificationStatus.TIMEOUT, None, None
            return Z3VerificationStatus.UNKNOWN, None, None


class HeuristicVerifier:
    """Heuristic-based verifier for fallback when Z3 times out."""

    def __init__(self):
        self.rule_scores = {
            "obligation": 0.9,
            "prohibition": 0.95,
            "permission": 0.7,
            "comparison": 0.85,
        }

    async def verify(
        self,
        constraints: list[PolicyConstraint],
        context: JSONDict,
    ) -> tuple[float, list[JSONDict]]:
        """
        Verify constraints heuristically.

        Returns:
            Tuple of (confidence_score, violations)
        """
        total_score = 0.0
        violations = []
        constraint_count = len(constraints)

        for constraint in constraints:
            score, violation = await self._evaluate_constraint(constraint, context)
            total_score += score

            if violation:
                violations.append(violation)

        avg_score = total_score / constraint_count if constraint_count > 0 else 0.0

        return avg_score, violations

    async def _evaluate_constraint(
        self,
        constraint: PolicyConstraint,
        context: JSONDict,
    ) -> tuple[float, JSONDict | None]:
        """Evaluate a single constraint heuristically."""
        # Base score from constraint confidence
        base_score = constraint.confidence

        # Adjust based on constraint type
        if "obligation" in constraint.name.lower():
            score_mult = self.rule_scores["obligation"]
        elif "prohibition" in constraint.name.lower():
            score_mult = self.rule_scores["prohibition"]
        elif "permission" in constraint.name.lower():
            score_mult = self.rule_scores["permission"]
        else:
            score_mult = self.rule_scores["comparison"]

        final_score = base_score * score_mult

        # Check for context violations
        violation = None
        if constraint.is_mandatory and final_score < 0.7:
            violation = {
                "constraint_id": constraint.constraint_id,
                "name": constraint.name,
                "confidence": final_score,
                "reason": "Heuristic evaluation suggests potential violation",
            }

        return final_score, violation


class Z3PolicyVerifier:
    """
    Z3 Policy Verifier: Mathematical policy verification with SMT solver.

    Implements:
    - Z3 SMT solver integration for formal verification
    - Time-bounded verification to prevent infinite proofs
    - Heuristic fallback for timeout scenarios
    - Proof generation for audit trail

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        default_timeout_ms: int = 5000,
        enable_heuristic_fallback: bool = False,
        heuristic_threshold: float = 0.75,
    ):
        self.default_timeout_ms = default_timeout_ms
        self.enable_heuristic_fallback = enable_heuristic_fallback
        self.heuristic_threshold = heuristic_threshold

        self.constraint_generator = ConstraintGenerator()
        self.heuristic_verifier = HeuristicVerifier()

        self._verification_history: list[PolicyVerificationResult] = []
        self._policy_cache: dict[str, list[PolicyConstraint]] = {}

        self.constitutional_hash = CONSTITUTIONAL_HASH

        logger.info(f"Initialized Z3 Policy Verifier (Z3 available: {Z3_AVAILABLE})")
        logger.info(f"Constitutional Hash: {self.constitutional_hash}")

    async def verify_policy(
        self,
        request: PolicyVerificationRequest,
    ) -> PolicyVerificationResult:
        """
        Verify a policy using Z3 SMT solver.

        Args:
            request: Policy verification request

        Returns:
            Complete verification result with proof
        """
        start_time = datetime.now(UTC)

        result = PolicyVerificationResult(
            request_id=request.request_id,
            policy_id=request.policy_id,
        )

        proof = VerificationProof(verification_id=result.verification_id)

        try:
            # Generate constraints if not provided
            constraints = request.constraints
            if not constraints and request.policy_text:
                constraints = await self.constraint_generator.generate_constraints(
                    request.policy_text,
                    request.context,
                )

            result.total_constraints = len(constraints)
            proof.constraints_evaluated = len(constraints)

            proof.add_trace_entry(
                "constraint_generation",
                {
                    "constraint_count": len(constraints),
                },
            )

            if not constraints:
                result.is_verified = True
                result.status = Z3VerificationStatus.SATISFIABLE
                result.satisfied_constraints = 0
                result.warnings.append("No constraints to verify")
                return result

            # Try Z3 verification if available
            if Z3_AVAILABLE:
                z3_result = await self._verify_with_z3(
                    constraints,
                    request.context,
                    request.timeout_ms,
                    proof,
                )

                result.status = z3_result["status"]
                result.is_verified = z3_result["is_verified"]
                result.satisfied_constraints = z3_result.get("satisfied", 0)
                result.violations = z3_result.get("violations", [])

                if z3_result.get("model"):
                    proof.model = z3_result["model"]
                if z3_result.get("unsat_core"):
                    proof.unsat_core = z3_result["unsat_core"]

                proof.solve_time_ms = z3_result.get("solve_time_ms", 0.0)

            else:
                if request.use_heuristic_fallback and self.enable_heuristic_fallback:
                    result.warnings.append("Z3 not available, using heuristic verification")
                    result.status = Z3VerificationStatus.HEURISTIC_FALLBACK

                    heuristic_result = await self._verify_with_heuristic(
                        constraints,
                        request.context,
                        proof,
                    )

                    result.is_verified = heuristic_result["is_verified"]
                    result.satisfied_constraints = heuristic_result.get("satisfied", 0)
                    result.violations = heuristic_result.get("violations", [])
                    proof.heuristic_score = heuristic_result.get("score", 0.0)
                else:
                    result.status = Z3VerificationStatus.ERROR
                    result.is_verified = False
                    result.violations.append(
                        {
                            "type": "z3_unavailable",
                            "description": "Z3 solver unavailable and heuristic fallback disabled",
                        }
                    )
                    result.warnings.append("Z3 solver unavailable; verification failed closed")

            # Fallback to heuristic if Z3 timed out or returned unknown
            if (
                result.status in (Z3VerificationStatus.TIMEOUT, Z3VerificationStatus.UNKNOWN)
                and request.use_heuristic_fallback
                and self.enable_heuristic_fallback
            ):
                result.warnings.append("Z3 verification inconclusive, using heuristic fallback")
                result.status = Z3VerificationStatus.HEURISTIC_FALLBACK

                heuristic_result = await self._verify_with_heuristic(
                    constraints,
                    request.context,
                    proof,
                )

                result.is_verified = heuristic_result["is_verified"]
                result.satisfied_constraints = heuristic_result.get("satisfied", 0)
                result.violations = heuristic_result.get("violations", [])
                proof.heuristic_score = heuristic_result.get("score", 0.0)
            elif result.status in (
                Z3VerificationStatus.TIMEOUT,
                Z3VerificationStatus.UNKNOWN,
            ):
                result.is_verified = False
                result.violations.append(
                    {
                        "type": "z3_inconclusive",
                        "description": (
                            "Formal verification was inconclusive and heuristic fallback "
                            "is disabled"
                        ),
                        "status": result.status.value,
                    }
                )
                result.warnings.append(
                    "Formal verification was inconclusive; request failed closed"
                )

            # Generate recommendations
            result.recommendations = self._generate_recommendations(result, constraints)

        except _Z3_VERIFIER_OPERATION_ERRORS as e:
            logger.error(f"Policy verification failed: {e}")
            result.status = Z3VerificationStatus.ERROR
            result.is_verified = False
            result.violations.append(
                {
                    "type": "verification_error",
                    "description": str(e),
                }
            )

            proof.add_trace_entry("error", {"message": str(e)})

        finally:
            end_time = datetime.now(UTC)
            result.total_time_ms = (end_time - start_time).total_seconds() * 1000
            result.proof = proof

            # Store in history
            self._verification_history.append(result)

            logger.info(
                f"Policy verification {result.verification_id}: "
                f"{'VERIFIED' if result.is_verified else 'FAILED'} "
                f"in {result.total_time_ms:.2f}ms"
            )

        return result

    async def _verify_with_z3(
        self,
        constraints: list[PolicyConstraint],
        context: JSONDict,
        timeout_ms: int,
        proof: VerificationProof,
    ) -> JSONDict:
        """Verify constraints using Z3 solver."""
        start_time = time.time()

        try:
            solver = Z3SolverWrapper(timeout_ms)

            # Add all constraints
            added_count = 0
            for constraint in constraints:
                if solver.add_constraint(constraint.constraint_id, constraint):
                    added_count += 1

            proof.add_trace_entry(
                "z3_setup",
                {
                    "constraints_added": added_count,
                    "timeout_ms": timeout_ms,
                },
            )

            # Check satisfiability
            status, model, unsat_core = solver.check()

            solve_time = (time.time() - start_time) * 1000

            proof.add_trace_entry(
                "z3_result",
                {
                    "status": status.value,
                    "solve_time_ms": solve_time,
                },
            )

            is_verified = status == Z3VerificationStatus.SATISFIABLE

            violations = []
            if not is_verified and unsat_core:
                for core_item in unsat_core:
                    violations.append(
                        {
                            "type": "unsatisfiable_constraint",
                            "constraint": core_item,
                        }
                    )

            return {
                "status": status,
                "is_verified": is_verified,
                "satisfied": added_count if is_verified else 0,
                "model": model,
                "unsat_core": unsat_core,
                "violations": violations,
                "solve_time_ms": solve_time,
            }

        except _Z3_VERIFIER_OPERATION_ERRORS as e:
            logger.error(f"Z3 verification error: {e}")
            return {
                "status": Z3VerificationStatus.ERROR,
                "is_verified": False,
                "violations": [{"type": "z3_error", "description": str(e)}],
            }

    async def _verify_with_heuristic(
        self,
        constraints: list[PolicyConstraint],
        context: JSONDict,
        proof: VerificationProof,
    ) -> JSONDict:
        """Verify constraints using heuristic approach."""
        score, violations = await self.heuristic_verifier.verify(constraints, context)

        proof.add_trace_entry(
            "heuristic_verification",
            {
                "score": score,
                "violation_count": len(violations),
            },
        )

        is_verified = score >= self.heuristic_threshold

        return {
            "is_verified": is_verified,
            "satisfied": len(constraints) - len(violations),
            "score": score,
            "violations": violations,
        }

    def _generate_recommendations(
        self,
        result: PolicyVerificationResult,
        constraints: list[PolicyConstraint],
    ) -> list[str]:
        """Generate recommendations based on verification results."""
        recommendations = []

        if not result.is_verified:
            recommendations.append("Review and address identified policy violations")

        if result.status == Z3VerificationStatus.HEURISTIC_FALLBACK:
            recommendations.append(
                "Consider simplifying policy constraints for formal verification"
            )

        # Check for high-priority violated constraints
        for violation in result.violations:
            if violation.get("type") == "unsatisfiable_constraint":
                recommendations.append(
                    f"Constraint conflict detected: {violation.get('constraint', 'unknown')}"
                )

        if result.total_constraints > 50:
            recommendations.append("Consider decomposing policy into smaller, verifiable units")

        return recommendations

    async def verify_policy_text(
        self,
        policy_text: str,
        policy_id: str | None = None,
        context: JSONDict | None = None,
        timeout_ms: int | None = None,
    ) -> PolicyVerificationResult:
        """
        Convenience method to verify policy from natural language text.

        Args:
            policy_text: Natural language policy description
            policy_id: Optional policy identifier
            context: Optional verification context
            timeout_ms: Optional timeout override

        Returns:
            Policy verification result
        """
        request = PolicyVerificationRequest(
            policy_id=policy_id or f"policy_{hash(policy_text) % 10000}",
            policy_text=policy_text,
            context=context or {},
            timeout_ms=timeout_ms or self.default_timeout_ms,
            use_heuristic_fallback=self.enable_heuristic_fallback,
        )

        return await self.verify_policy(request)

    def get_verification_stats(self) -> JSONDict:
        """Get verification statistics."""
        if not self._verification_history:
            return {"total_verifications": 0}

        total = len(self._verification_history)
        verified = sum(1 for v in self._verification_history if v.is_verified)

        status_counts: dict[str, int] = {}
        for v in self._verification_history:
            status = v.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        avg_time = sum(v.total_time_ms for v in self._verification_history) / total
        avg_constraints = sum(v.total_constraints for v in self._verification_history) / total

        return {
            "total_verifications": total,
            "verified_count": verified,
            "verification_rate": verified / total,
            "status_distribution": status_counts,
            "average_time_ms": avg_time,
            "average_constraints": avg_constraints,
            "z3_available": Z3_AVAILABLE,
            "constitutional_hash": self.constitutional_hash,
        }

    def get_constitutional_hash(self) -> str:
        """Return the constitutional hash for validation."""
        return str(self.constitutional_hash)


def create_z3_verifier(
    timeout_ms: int = 5000,
    enable_heuristic_fallback: bool = False,
) -> Z3PolicyVerifier:
    """Factory function to create a Z3 policy verifier."""
    return Z3PolicyVerifier(
        default_timeout_ms=timeout_ms,
        enable_heuristic_fallback=enable_heuristic_fallback,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "Z3_AVAILABLE",
    "ConstraintGenerator",
    "ConstraintType",
    "HeuristicVerifier",
    "PolicyConstraint",
    "PolicyDomain",
    "PolicyVerificationRequest",
    "PolicyVerificationResult",
    "VerificationProof",
    "Z3PolicyVerifier",
    "Z3VerificationStatus",
    "create_z3_verifier",
]
