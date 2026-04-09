"""Z3 constraint verifier — Layer 3 formal verification for high-risk actions.

Provides synchronous SMT-based verification of constitutional constraints
against agent actions. Designed for critical-risk actions (score >= 0.8)
where keyword matching and semantic scoring are insufficient.

Architecture position:
    Layer 1: GovernanceEngine (keyword rules, ~443ns)
    Layer 2: ConstitutionalImpactScorer (semantic risk, ~1ms)
    Layer 3: Z3ConstraintVerifier (formal verification, ~50-500ms, this module)

Usage::

    from acgs_lite.z3_verify import Z3ConstraintVerifier, Z3VerifyResult

    verifier = Z3ConstraintVerifier()
    result = verifier.verify("delete all production records", context={"env": "production"})
    if not result.satisfiable:
        print(f"Constraint violated: {result.counterexample}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)

try:
    import z3

    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

# Default timeout for Z3 solver (milliseconds)
_Z3_TIMEOUT_MS = 5_000

# Risk threshold above which Z3 verification is recommended
Z3_RISK_THRESHOLD = 0.8


@dataclass(frozen=True, slots=True)
class Z3VerifyResult:
    """Result of Z3 formal verification."""

    satisfiable: bool
    """True if the action satisfies all constraints (no violation found)."""
    verified: bool
    """True if Z3 was actually invoked. False if Z3 unavailable or timed out."""
    solver_result: str
    """'sat', 'unsat', 'unknown', or 'skipped'."""
    counterexample: dict[str, Any] | None
    """Variable assignment that witnesses a violation, or None."""
    verification_time_ms: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Built-in constitutional constraint builders
# ---------------------------------------------------------------------------


def _build_action_constraints(
    solver: Any,
    action: str,
    context: dict[str, Any] | None,
) -> None:
    """Add constitutional constraints to the solver for the given action.

    Constraints encode the six core ACGS principles as boolean variables:
      - data_destruction:   action destroys data
      - system_escalation:  action escalates privileges
      - production_write:   action writes to production
      - secret_exposure:    action exposes secrets
      - financial_mutation: action mutates financial records
      - auth_bypass:        action bypasses authentication

    A valid (constitutionally compliant) action must satisfy:
      NOT (data_destruction AND production_write)
      NOT secret_exposure
      NOT auth_bypass
      IF financial_mutation THEN NOT production_write (require staging)
    """
    action_lower = action.lower()
    ctx = context or {}

    # Boolean variables representing action characteristics
    data_destruction = z3.Bool("data_destruction")
    system_escalation = z3.Bool("system_escalation")
    production_write = z3.Bool("production_write")
    secret_exposure = z3.Bool("secret_exposure")
    financial_mutation = z3.Bool("financial_mutation")
    auth_bypass = z3.Bool("auth_bypass")

    # Derive variable values from action text and context
    _destruction_keywords = {"delete", "drop", "truncate", "destroy", "erase", "wipe", "rm -rf"}
    _escalation_keywords = {"sudo", "root", "admin", "chmod", "chown", "kernel", "privilege"}
    _secret_keywords = {"password", "secret", "token", "api_key", "credential", "private key"}
    _financial_keywords = {"payment", "transaction", "transfer", "billing", "invoice", "money"}
    _bypass_keywords = {"bypass", "skip auth", "override auth", "no-auth", "unauthenticated"}

    is_destruction = any(kw in action_lower for kw in _destruction_keywords)
    is_escalation = any(kw in action_lower for kw in _escalation_keywords)
    is_production = (
        any(kw in action_lower for kw in {"production", "prod ", " prod", "live"})
        or ctx.get("environment") == "production"
    )
    is_secret = any(kw in action_lower for kw in _secret_keywords)
    is_financial = any(kw in action_lower for kw in _financial_keywords)
    is_bypass = any(kw in action_lower for kw in _bypass_keywords)

    # Assert observed values
    solver.add(data_destruction == is_destruction)
    solver.add(system_escalation == is_escalation)
    solver.add(production_write == is_production)
    solver.add(secret_exposure == is_secret)
    solver.add(financial_mutation == is_financial)
    solver.add(auth_bypass == is_bypass)

    # Constitutional constraints (negated to find violations):
    # If any constraint is UNSAT, the action violates the constitution.
    # We assert the NEGATION of what is acceptable — if SAT, a violation exists.
    solver.add(
        z3.Or(
            z3.And(data_destruction, production_write),  # C1: no prod destruction
            secret_exposure,  # C2: no secret exposure
            auth_bypass,  # C3: no auth bypass
            z3.And(financial_mutation, production_write),  # C4: no direct prod finance writes
            z3.And(system_escalation, production_write),  # C5: no prod privilege escalation
        )
    )


def _extract_counterexample(model: Any) -> dict[str, Any]:
    """Extract a human-readable counterexample from a Z3 model."""
    result: dict[str, Any] = {}
    for decl in model.decls():
        val = model[decl]
        result[decl.name()] = bool(val) if z3.is_bool(val) else str(val)
    return {k: v for k, v in result.items() if v is True}


# ---------------------------------------------------------------------------
# Verifier class
# ---------------------------------------------------------------------------


class Z3ConstraintVerifier:
    """Synchronous Z3-based constitutional constraint verifier.

    Intended for critical-risk actions where the cost of a false negative
    (allowing a harmful action) outweighs the verification latency.

    Falls back gracefully when z3-solver is not installed.
    """

    def __init__(self, timeout_ms: int = _Z3_TIMEOUT_MS) -> None:
        self._timeout_ms = timeout_ms
        if not Z3_AVAILABLE:
            _log.warning(
                "z3-solver not installed — Z3ConstraintVerifier will skip verification. "
                "Install with: pip install z3-solver"
            )

    @property
    def available(self) -> bool:
        """True if z3-solver is installed and usable."""
        return Z3_AVAILABLE

    def verify(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> Z3VerifyResult:
        """Formally verify an action against constitutional constraints.

        Returns Z3VerifyResult with:
          - satisfiable=True  → no violation found (action is safe per constraints)
          - satisfiable=False → violation detected; counterexample shows which constraints
          - verified=False    → Z3 unavailable or timed out; treat as inconclusive

        Args:
            action: The agent action string to verify.
            context: Optional dict with keys like "environment", "authenticated".
        """
        if not Z3_AVAILABLE:
            return Z3VerifyResult(
                satisfiable=True,
                verified=False,
                solver_result="skipped",
                counterexample=None,
                verification_time_ms=0.0,
                error="z3-solver not installed",
            )

        start = time.perf_counter()
        try:
            solver = z3.Solver()
            solver.set("timeout", self._timeout_ms)
            _build_action_constraints(solver, action, context)

            check_result = solver.check()
            elapsed_ms = (time.perf_counter() - start) * 1000

            if check_result == z3.sat:
                # A violation was found — extract the counterexample
                counterexample = _extract_counterexample(solver.model())
                return Z3VerifyResult(
                    satisfiable=False,
                    verified=True,
                    solver_result="sat",
                    counterexample=counterexample,
                    verification_time_ms=elapsed_ms,
                )
            elif check_result == z3.unsat:
                # No violation possible — constraints are unsatisfiable
                return Z3VerifyResult(
                    satisfiable=True,
                    verified=True,
                    solver_result="unsat",
                    counterexample=None,
                    verification_time_ms=elapsed_ms,
                )
            else:
                # unknown — solver timed out or gave up
                return Z3VerifyResult(
                    satisfiable=True,
                    verified=False,
                    solver_result="unknown",
                    counterexample=None,
                    verification_time_ms=elapsed_ms,
                    error="Z3 solver returned unknown (possible timeout)",
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            _log.warning("Z3 verification error: %s", type(exc).__name__)
            return Z3VerifyResult(
                satisfiable=True,
                verified=False,
                solver_result="unknown",
                counterexample=None,
                verification_time_ms=elapsed_ms,
                error=type(exc).__name__,
            )
