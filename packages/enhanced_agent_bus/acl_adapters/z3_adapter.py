from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any

from .base import CONSTITUTIONAL_HASH, ACLAdapter, AdapterConfig, AdapterResult


@dataclass(slots=True)
class Z3AdapterConfig(AdapterConfig):
    z3_timeout_ms: int = 30000
    memory_limit_mb: int = 1024
    proof_enabled: bool = True
    model_enabled: bool = True
    cache_enabled: bool = True
    cache_ttl_s: int = 3600
    timeout_ms: int = 35000
    max_retries: int = 1


@dataclass(slots=True)
class Z3Request:
    formula: str
    assertions: list[str] = field(default_factory=list)
    timeout_ms: int | None = None
    get_model: bool = True
    get_proof: bool = False
    get_unsat_core: bool = False
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if self.trace_id is None:
            digest = hashlib.sha256(self.formula.encode()).hexdigest()
            self.trace_id = digest[:16]


@dataclass(slots=True)
class Z3Response:
    result: str
    model: dict[str, str] = field(default_factory=dict)
    proof: str | None = None
    unsat_core: list[str] | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def is_sat(self) -> bool:
        return self.result == "sat"

    @property
    def is_unsat(self) -> bool:
        return self.result == "unsat"

    @property
    def is_unknown(self) -> bool:
        return self.result == "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "model": self.model,
            "proof": self.proof,
            "unsat_core": self.unsat_core,
            "statistics": self.statistics,
            "constitutional_hash": self.constitutional_hash,
            "trace_id": self.trace_id,
        }


class Z3Adapter(ACLAdapter[Z3Request, Z3Response]):
    def __init__(self, name: str = "z3", config: Z3AdapterConfig | None = None) -> None:
        self.z3_config = config or Z3AdapterConfig()
        super().__init__(name=name, config=self.z3_config)
        self._z3_available = self._check_z3_available()

    def _check_z3_available(self) -> bool:
        try:
            import z3  # noqa: F401

            return True
        except ImportError:
            return False

    async def _execute(self, request: Z3Request) -> Z3Response:
        if not self._z3_available:
            return Z3Response(
                result="unknown",
                statistics={"reason": "z3_not_available"},
                trace_id=request.trace_id,
            )
        return await asyncio.to_thread(self._run_z3_sync, request)

    def _run_z3_sync(self, request: Z3Request) -> Z3Response:
        try:
            import z3

            solver = z3.Solver()
            try:
                solver.set("memory_max_size", self.z3_config.memory_limit_mb)
            except Exception:
                pass
            solver.set("timeout", request.timeout_ms or self.z3_config.z3_timeout_ms)

            for chunk in [request.formula, *request.assertions]:
                parsed = z3.parse_smt2_string(chunk)
                if isinstance(parsed, list):
                    solver.add(*parsed)
                else:
                    solver.add(parsed)

            check_result = solver.check()
            stats = self._extract_stats(solver)
            if check_result == getattr(z3, "sat", "sat"):
                model: dict[str, str] = {}
                if request.get_model:
                    try:
                        model_obj = solver.model()
                        for decl in model_obj.decls():
                            model[str(decl.name())] = str(model_obj[decl])
                    except Exception:
                        model = {}
                return Z3Response(
                    result="sat", model=model, statistics=stats, trace_id=request.trace_id
                )

            if check_result == getattr(z3, "unsat", "unsat"):
                proof = None
                unsat_core: list[str] | None = None
                if request.get_proof:
                    try:
                        proof = str(solver.proof())
                    except Exception:
                        proof = "proof_unavailable"
                if request.get_unsat_core:
                    try:
                        unsat_core = [str(item) for item in solver.unsat_core()]
                    except Exception:
                        unsat_core = []
                return Z3Response(
                    result="unsat",
                    proof=proof,
                    unsat_core=unsat_core,
                    statistics=stats,
                    trace_id=request.trace_id,
                )
            return Z3Response(result="unknown", statistics=stats, trace_id=request.trace_id)
        except Exception as exc:
            reason = "parse_error" if "parse" in str(exc).lower() else f"z3_error:{exc}"
            return Z3Response(
                result="unknown", statistics={"reason": reason}, trace_id=request.trace_id
            )

    def _extract_stats(self, solver: Any) -> dict[str, Any]:
        try:
            stats = solver.statistics()
            length = len(stats)
            return {str(index): stats.get_key_value(index) for index in range(length)}
        except Exception:
            return {}

    def _validate_response(self, response: Z3Response) -> bool:
        return response.result in {"sat", "unsat", "unknown"}

    def _get_cache_key(self, request: Z3Request) -> str:
        payload = "|".join([request.formula, *request.assertions])
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_fallback_response(self, request: Z3Request) -> Z3Response | None:
        return Z3Response(
            result="unknown",
            statistics={"reason": "fallback"},
            trace_id=request.trace_id,
        )


async def check_satisfiability(
    formula: str,
    assertions: list[str] | None = None,
    adapter: Z3Adapter | None = None,
) -> AdapterResult[Z3Response]:
    z3_adapter = adapter or Z3Adapter()
    return await z3_adapter.call(Z3Request(formula=formula, assertions=assertions or []))


async def prove_property(
    formula: str,
    context_assertions: list[str] | None = None,
    adapter: Z3Adapter | None = None,
) -> AdapterResult[Z3Response]:
    z3_adapter = adapter or Z3Adapter()
    request = Z3Request(
        formula=f"(assert (not {formula}))",
        assertions=context_assertions or [],
        get_model=False,
        get_proof=True,
        get_unsat_core=True,
    )
    return await z3_adapter.call(request)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "Z3Adapter",
    "Z3AdapterConfig",
    "Z3Request",
    "Z3Response",
    "check_satisfiability",
    "prove_property",
]
