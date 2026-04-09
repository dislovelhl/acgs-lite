"""Optional SMT-based constitution verification helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from acgs_lite.constitution import Constitution, Rule

_NO_WARNINGS: tuple[str, ...] = ()
_UNSET = object()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Verification outcome for a single constitutional rule."""

    rule_id: str
    satisfiable: bool
    contradiction: bool
    warnings: tuple[str, ...] = _NO_WARNINGS


class Z3VerificationGate:
    """Best-effort SMT gate for critical constitutional rules."""

    def __init__(self, *, z3_module: Any = _UNSET) -> None:
        self._z3 = self._load_z3() if z3_module is _UNSET else z3_module

    @staticmethod
    def _load_z3() -> Any | None:
        try:
            return importlib.import_module("z3")
        except ImportError:
            return None

    @property
    def available(self) -> bool:
        return self._z3 is not None

    def check(self, rule: Rule, constitution: Constitution) -> VerificationResult:
        warnings: list[str] = []
        contradiction = any(
            candidate.id == rule.id and candidate.severity != rule.severity
            for candidate in constitution.rules
            if candidate is not rule
        )

        if not rule.keywords:
            warnings.append("rule has no keywords; SMT verification skipped")

        if self._z3 is None:
            warnings.append("z3-solver not installed; SMT verification skipped")
            return VerificationResult(
                rule_id=rule.id,
                satisfiable=True,
                contradiction=contradiction,
                warnings=tuple(warnings),
            )

        if not rule.keywords:
            return VerificationResult(
                rule_id=rule.id,
                satisfiable=True,
                contradiction=contradiction,
                warnings=tuple(warnings),
            )

        solver = self._z3.Solver()
        keyword_symbols = [self._z3.Bool(f"kw_{index}") for index, _ in enumerate(rule.keywords)]
        solver.add(self._z3.Or(*keyword_symbols))
        satisfiable = solver.check() == self._z3.sat
        return VerificationResult(
            rule_id=rule.id,
            satisfiable=satisfiable,
            contradiction=contradiction,
            warnings=tuple(warnings),
        )


class NullVerificationGate:
    """No-op formal verification gate."""

    def check(self, rule: Rule, constitution: Constitution) -> VerificationResult:
        del constitution
        return VerificationResult(
            rule_id=rule.id,
            satisfiable=True,
            contradiction=False,
            warnings=_NO_WARNINGS,
        )
