"""Backward-compatible Z3 adapter shim for legacy verification callers.

This module keeps the historic adapter API used by tests and older call-sites,
while sharing canonical constants and Z3 availability with
``enhanced_agent_bus.verification_layer.z3_policy_verifier``.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
    CONSTITUTIONAL_HASH,
    Z3_AVAILABLE,
    HeuristicVerifier,
    z3,
)

logger = get_logger(__name__)

_Z3_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)
_DECLARATION_PATTERN = re.compile(r"\(declare-const (\w+) (\w+)\)")
_RESERVED_LOGIC_WORDS = {"and", "or", "not", "true", "false"}


@dataclass
class Z3Constraint:
    """Legacy Z3 constraint payload."""

    name: str
    expression: str
    natural_language: str
    confidence: float
    generated_by: str = "llm"
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)


@dataclass
class Z3VerificationResult:
    """Legacy verification result payload."""

    is_sat: bool
    model: JSONDict | None = None
    unsat_core: list[str] | None = None
    constraints_used: list[str] | None = None
    solve_time_ms: float = 0.0
    solver_stats: JSONDict | None = None
    alternative_paths: list[JSONDict] | None = None

    def __post_init__(self) -> None:
        if self.constraints_used is None:
            self.constraints_used = []
        if self.solver_stats is None:
            self.solver_stats = {}
        if self.alternative_paths is None:
            self.alternative_paths = []


@dataclass
class ConstitutionalPolicy:
    """Legacy policy object returned by constitutional verification."""

    id: str
    natural_language: str
    z3_constraints: list[Z3Constraint]
    verification_result: Z3VerificationResult | None = None
    is_verified: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime | None = None
    verified_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


class Z3SolverAdapter:
    """Legacy solver wrapper with tracked constraints and model enumeration."""

    def __init__(self, timeout_ms: int = 5000):
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver not available. Install with: pip install z3-solver")

        self.timeout_ms = timeout_ms
        self.solver = z3.Solver()
        self.solver.set("timeout", timeout_ms)
        self.named_constraints: dict[str, z3.ExprRef] = {}
        self.constraint_trackers: dict[str, z3.BoolRef] = {}
        self.constraint_history: list[Z3Constraint] = []

    def reset_solver(self) -> None:
        """Reset tracked solver state without clearing history."""
        self.solver.reset()
        self.named_constraints.clear()
        self.constraint_trackers.clear()

    def add_constraint(self, name: str, constraint: z3.ExprRef, metadata: Z3Constraint) -> None:
        """Add a named constraint and keep enough metadata for unsat reporting."""
        tracker = z3.Bool(name)
        self.named_constraints[name] = constraint
        self.constraint_trackers[name] = tracker
        self.constraint_history.append(metadata)
        self.solver.assert_and_track(constraint, tracker)

    async def async_check_sat(
        self, find_multiple: bool = False, max_paths: int = 5
    ) -> Z3VerificationResult:
        await asyncio.sleep(0)
        return self.check_sat(find_multiple, max_paths)

    def check_sat(self, find_multiple: bool = False, max_paths: int = 5) -> Z3VerificationResult:
        """Check satisfiability, optionally enumerating additional models."""
        import time

        started = time.time()
        result = self.solver.check()
        solve_time_ms = (time.time() - started) * 1000

        if result == z3.sat:
            model = self.solver.model()
            model_dict = self._model_to_dict(model)
            alternative_paths: list[JSONDict] = []
            if find_multiple:
                alternative_paths.append(model_dict)
                alternative_paths.extend(self._find_alternative_paths(model, max_paths))
            return Z3VerificationResult(
                is_sat=True,
                model=model_dict,
                constraints_used=self.get_constraint_names(),
                solve_time_ms=solve_time_ms,
                solver_stats={
                    "decls": len(model.decls()),
                    "paths_found": len(alternative_paths),
                },
                alternative_paths=alternative_paths,
            )

        if result == z3.unsat:
            return Z3VerificationResult(
                is_sat=False,
                unsat_core=self._get_unsat_core(),
                constraints_used=self.get_constraint_names(),
                solve_time_ms=solve_time_ms,
            )

        return Z3VerificationResult(
            is_sat=False,
            constraints_used=self.get_constraint_names(),
            solve_time_ms=solve_time_ms,
            solver_stats={"result": "unknown"},
        )

    def _find_alternative_paths(self, model: z3.ModelRef, max_paths: int) -> list[JSONDict]:
        """Enumerate additional satisfying models by blocking prior assignments."""
        alternative_paths: list[JSONDict] = []
        self.solver.push()
        try:
            current_model = model
            for _ in range(max_paths - 1):
                blockers = [
                    decl() != current_model[decl]
                    for decl in current_model.decls()
                    if decl.arity() == 0
                ]
                if not blockers:
                    break
                self.solver.add(z3.Or(blockers))
                if self.solver.check() != z3.sat:
                    break
                current_model = self.solver.model()
                alternative_paths.append(self._model_to_dict(current_model))
        finally:
            self.solver.pop()
        return alternative_paths

    def _get_unsat_core(self) -> list[str]:
        try:
            return [str(item) for item in self.solver.unsat_core()]
        except _Z3_ADAPTER_OPERATION_ERRORS as exc:
            logger.error(f"Unsat core collection failed: {exc}")
            return []

    def _model_to_dict(self, model: z3.ModelRef) -> JSONDict:
        model_dict: JSONDict = {}
        for decl in model.decls():
            value = model[decl]
            if z3.is_int_value(value):
                model_dict[str(decl)] = value.as_long()
            elif z3.is_bool(value):
                model_dict[str(decl)] = z3.is_true(value)
            else:
                model_dict[str(decl)] = str(value)
        return model_dict

    def get_constraint_names(self) -> list[str]:
        return list(self.named_constraints.keys())


class LLMAssistedZ3Adapter:
    """Legacy natural-language-to-Z3 adapter kept stable for old tests/callers."""

    _POLICY_KEYWORDS = (
        ("obligation", ("must", "shall", "required", "prohibited"), "high"),
        ("permission", ("may", "can", "optional"), "medium"),
        ("prohibition", ("cannot", "must not", "forbidden"), "high"),
    )

    def __init__(self, max_refinements: int = 3, timeout_ms: int = 5000):
        self.max_refinements = max_refinements
        self.z3_solver = Z3SolverAdapter(timeout_ms=timeout_ms)
        self.generation_history: list[JSONDict] = []
        self.heuristic_verifier = HeuristicVerifier()

    async def natural_language_to_constraints(
        self, policy_text: str, context: JSONDict | None = None
    ) -> list[Z3Constraint]:
        constraints: list[Z3Constraint] = []
        for element in self._extract_policy_elements(policy_text):
            constraint = await self._generate_single_constraint(element, context)
            if constraint is not None:
                constraints.append(constraint)
                self.generation_history.append(
                    {
                        "name": constraint.name,
                        "type": element["type"],
                        "generated_by": constraint.generated_by,
                    }
                )
        return constraints

    def _extract_policy_elements(self, policy_text: str) -> list[JSONDict]:
        elements: list[JSONDict] = []
        for sentence in (part.strip() for part in policy_text.split(".")):
            if not sentence:
                continue
            lowered = sentence.lower()
            for policy_type, keywords, priority in self._POLICY_KEYWORDS:
                if any(word in lowered for word in keywords):
                    elements.append({"type": policy_type, "text": sentence, "priority": priority})
                    break
        return elements

    async def _generate_single_constraint(
        self, element: JSONDict, context: JSONDict | None = None
    ) -> Z3Constraint | None:
        text = element["text"]
        if " or " in text.lower() or " and " in text.lower():
            expression = self._build_logic_expression(text)
            if expression:
                return Z3Constraint(
                    name=f"logicgraph_{hash(text) % 10000}",
                    expression=expression,
                    natural_language=text,
                    confidence=0.9,
                    generated_by="logicgraph_generator",
                )

        policy_type = element["type"]
        if policy_type == "obligation" and "must" in text.lower():
            return self._simple_constraint(text, "policy", True, 0.8)
        if policy_type == "prohibition" and any(
            phrase in text.lower() for phrase in ("cannot", "must not")
        ):
            return self._simple_constraint(text, "prohibit", False, 0.9)
        return None

    def _simple_constraint(
        self, text: str, prefix: str, asserted_value: bool, confidence: float
    ) -> Z3Constraint:
        var_name = f"{prefix}_{hash(text) % 1000}"
        assertion = var_name if asserted_value else f"(not {var_name})"
        return Z3Constraint(
            name=f"constraint_{hash(text) % 10000}",
            expression=f"(declare-const {var_name} Bool)\n(assert {assertion})",
            natural_language=text,
            confidence=confidence,
            generated_by="pattern_matching",
        )

    def _build_logic_expression(self, text: str) -> str | None:
        stripped = text.lower().replace("access is allowed if ", "").replace(".", "").strip()

        def nl_to_smt(fragment: str) -> str:
            fragment = fragment.strip()
            while (
                fragment.startswith("(")
                and fragment.endswith(")")
                and self._is_balanced(fragment[1:-1])
            ):
                fragment = fragment[1:-1].strip()
            for op in (" and ", " or "):
                parts = self._split_by_op(fragment, op)
                if len(parts) > 1:
                    return f"({op.strip()} {' '.join(nl_to_smt(part) for part in parts)})"
            return (
                fragment.replace("user is ", "")
                .replace("resource is ", "")
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
            )

        try:
            smt_body = nl_to_smt(stripped)
        except _Z3_ADAPTER_OPERATION_ERRORS as exc:
            logger.warning(f"Complex generation failed for '{text}': {exc}")
            return None

        variables = sorted(
            {
                token
                for token in re.findall(r"\b\w+\b", smt_body)
                if token not in _RESERVED_LOGIC_WORDS
            }
        )
        declarations = "\n".join(f"(declare-const {name} Bool)" for name in variables)
        return f"{declarations}\n(assert {smt_body})"

    async def verify_policy_constraints(
        self, constraints: list[Z3Constraint], find_multiple: bool = False
    ) -> Z3VerificationResult:
        self.z3_solver.reset_solver()
        for constraint in constraints:
            try:
                z3_expr = self._parse_z3_expression(constraint.expression)
                if z3_expr is not None:
                    self.z3_solver.add_constraint(constraint.name, z3_expr, constraint)
            except _Z3_ADAPTER_OPERATION_ERRORS as exc:
                logger.warning(f"Failed to parse constraint {constraint.name}: {exc}")
        return await self.z3_solver.async_check_sat(find_multiple=find_multiple)

    def _parse_z3_expression(self, expr_str: str) -> z3.ExprRef | None:
        try:
            declarations: dict[str, z3.ExprRef] = {}
            assertions: list[str] = []
            for raw_line in expr_str.strip().splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if match := _DECLARATION_PATTERN.fullmatch(line):
                    name, type_name = match.groups()
                    declarations[name] = z3.Bool(name) if type_name == "Bool" else z3.Int(name)
                elif line.startswith("(assert") and line.endswith(")"):
                    assertions.append(line[7:-1].strip())
            if not assertions:
                return None

            def parse(fragment: str) -> z3.ExprRef:
                fragment = fragment.strip()
                if fragment == "true":
                    return z3.BoolVal(True)
                if fragment == "false":
                    return z3.BoolVal(False)
                if fragment in declarations:
                    return declarations[fragment]
                if re.fullmatch(r"\w+", fragment):
                    return z3.Bool(fragment)
                if not (fragment.startswith("(") and fragment.endswith(")")):
                    raise ValueError(f"Cannot parse expression: {fragment}")
                parts = self._split_balanced(fragment[1:-1].strip())
                if not parts:
                    raise ValueError("Empty expression")
                op, args = parts[0], [parse(part) for part in parts[1:]]
                if op == "and":
                    return z3.And(*args)
                if op == "or":
                    return z3.Or(*args)
                if op == "not" and len(args) == 1:
                    return z3.Not(args[0])
                if op == "==" and len(args) == 2:
                    return args[0] == args[1]
                if op == "!=" and len(args) == 2:
                    return args[0] != args[1]
                raise ValueError(f"Unsupported operator: {op}")

            parsed = [parse(assertion) for assertion in assertions]
            return parsed[0] if len(parsed) == 1 else z3.And(*parsed)
        except _Z3_ADAPTER_OPERATION_ERRORS as exc:
            logger.warning(f"Failed to parse Z3 expression '{expr_str}': {exc}")
            return None

    def _is_balanced(self, text: str) -> bool:
        depth = 0
        for char in text:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if depth < 0:
                return False
        return depth == 0

    def _split_by_op(self, text: str, operator: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        index = 0
        while index < len(text):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if depth == 0 and text[index:].startswith(operator):
                parts.append(text[start:index])
                start = index + len(operator)
                index = start
                continue
            index += 1
        parts.append(text[start:])
        return parts

    def _split_balanced(self, text: str) -> list[str]:
        parts: list[str] = []
        current: list[str] = []
        depth = 0
        for char in text:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char.isspace() and depth == 0:
                if current:
                    parts.append("".join(current))
                    current.clear()
            else:
                current.append(char)
        if current:
            parts.append("".join(current))
        return parts

    # Backward-compatible aliases for legacy helper names used by older callers.
    def _split_by_operator(self, text: str, operator: str) -> list[str]:
        return self._split_by_op(text, operator)

    def _parse_balanced_expression(self, text: str) -> list[str]:
        return self._split_balanced(text)

    async def refine_constraints(
        self,
        constraints: list[Z3Constraint],
        verification_result: Z3VerificationResult,
        max_iterations: int = 3,
    ) -> list[Z3Constraint]:
        if verification_result.is_sat:
            return constraints

        refined = constraints.copy()
        for iteration in range(min(max_iterations, self.max_refinements)):
            if not verification_result.unsat_core:
                break
            problematic = set(verification_result.unsat_core)
            refined = [
                Z3Constraint(
                    name=item.name,
                    expression=item.expression,
                    natural_language=item.natural_language,
                    confidence=max(0.1, item.confidence - 0.1),
                    generated_by=f"refined_{iteration}",
                )
                if item.name in problematic
                else item
                for item in refined
            ]
            verification_result = await self.verify_policy_constraints(refined)
            if verification_result.is_sat:
                break
        return refined


class ConstitutionalZ3Verifier:
    """Legacy high-level policy verifier built on the compatibility adapter."""

    def __init__(self):
        self.llm_adapter = LLMAssistedZ3Adapter()
        self.verified_policies: dict[str, ConstitutionalPolicy] = {}

    async def verify_constitutional_policy(
        self,
        policy_id: str,
        natural_language_policy: str,
        context: JSONDict | None = None,
        find_multiple: bool = False,
    ) -> ConstitutionalPolicy:
        constraints = await self.llm_adapter.natural_language_to_constraints(
            natural_language_policy, context
        )
        verification_result = await self.llm_adapter.verify_policy_constraints(
            constraints, find_multiple=find_multiple
        )
        if not verification_result.is_sat:
            constraints = await self.llm_adapter.refine_constraints(
                constraints, verification_result
            )
            verification_result = await self.llm_adapter.verify_policy_constraints(
                constraints, find_multiple=find_multiple
            )
        policy = ConstitutionalPolicy(
            id=policy_id,
            natural_language=natural_language_policy,
            z3_constraints=constraints,
            verification_result=verification_result,
            is_verified=verification_result.is_sat,
            verified_at=datetime.now(UTC) if verification_result.is_sat else None,
        )
        self.verified_policies[policy_id] = policy
        return policy

    async def verify_policy_compliance(self, policy_id: str, decision_context: JSONDict) -> bool:
        policy = self.verified_policies.get(policy_id)
        return bool(policy and policy.is_verified)

    def get_constitutional_hash(self) -> str:
        return CONSTITUTIONAL_HASH  # type: ignore[no-any-return]

    def get_verification_stats(self) -> JSONDict:
        total_policies = len(self.verified_policies)
        verified_policies = sum(
            1 for policy in self.verified_policies.values() if policy.is_verified
        )
        return {
            "total_policies": total_policies,
            "verified_policies": verified_policies,
            "verification_rate": verified_policies / total_policies if total_policies else 0.0,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


async def verify_policy_formally(
    policy_text: str, policy_id: str | None = None
) -> ConstitutionalPolicy:
    verifier = ConstitutionalZ3Verifier()
    return await verifier.verify_constitutional_policy(
        policy_id or f"policy_{hash(policy_text) % 10000}",
        policy_text,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalPolicy",
    "ConstitutionalZ3Verifier",
    "HeuristicVerifier",
    "LLMAssistedZ3Adapter",
    "Z3Constraint",
    "Z3SolverAdapter",
    "Z3VerificationResult",
    "Z3_AVAILABLE",
    "verify_policy_formally",
]
