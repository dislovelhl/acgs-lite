"""Constraint-engine abstractions for optional token-level constrained decoding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from acgs_lite._meta import CONSTITUTIONAL_HASH

if TYPE_CHECKING:
    from acgs_lite.constitution import Constitution


class ConstraintEngine(Protocol):
    """Protocol for token-level constrained decoding engines."""

    def start(self) -> None:
        """Initialize engine state before decoding."""

    def compute_mask(self, token_ids: list[int]) -> list[bool]:
        """Return the allowed-token mask for the next decoding step."""

    def is_complete(self, token_ids: list[int]) -> bool:
        """Return whether the current token sequence satisfies the constraint."""


class LLGuidanceEngine:
    """Adapter around the optional llguidance runtime."""

    def __init__(self, schema: dict[str, Any], *, source: str) -> None:
        self.schema = schema
        self.source = source
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._backend: Any | None = None

    @classmethod
    def from_json_schema(cls, schema: dict[str, Any]) -> LLGuidanceEngine:
        return cls(schema, source="json_schema")

    @classmethod
    def from_regex(cls, pattern: str) -> LLGuidanceEngine:
        return cls(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "string",
                "pattern": pattern,
            },
            source="regex",
        )

    @classmethod
    def from_constitution(cls, constitution: Constitution) -> LLGuidanceEngine:
        return cls(constitution.to_response_schema(), source="constitution")

    def _load_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        try:
            import llguidance  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "llguidance is not installed. Install with: pip install acgs-lite[llguidance]"
            ) from exc

        if hasattr(llguidance, "JsonSchemaConstraint"):
            self._backend = llguidance.JsonSchemaConstraint(self.schema)
        elif hasattr(llguidance, "from_json_schema"):
            self._backend = llguidance.from_json_schema(self.schema)
        else:  # pragma: no cover - defensive against upstream API drift
            raise RuntimeError("llguidance does not expose a supported JSON Schema interface")
        return self._backend

    def start(self) -> None:
        backend = self._load_backend()
        start = getattr(backend, "start", None)
        if callable(start):
            start()

    def compute_mask(self, token_ids: list[int]) -> list[bool]:
        backend = self._load_backend()
        compute_mask = getattr(backend, "compute_mask", None)
        if not callable(compute_mask):  # pragma: no cover - defensive
            raise RuntimeError("llguidance backend does not expose compute_mask()")
        return list(compute_mask(token_ids))

    def is_complete(self, token_ids: list[int]) -> bool:
        backend = self._load_backend()
        is_complete = getattr(backend, "is_complete", None)
        if callable(is_complete):
            return bool(is_complete(token_ids))
        return False


class InMemoryConstraintEngine:
    """In-memory stub for unit tests and pure-Python callers."""

    def __init__(
        self,
        *,
        mask: list[bool] | None = None,
        complete: bool = False,
    ) -> None:
        self.mask = list(mask) if mask is not None else []
        self.complete = complete
        self.save_calls: list[dict[str, Any]] = []
        self.started = False

    def start(self) -> None:
        self.started = True
        self.save_calls.append({"method": "start"})

    def compute_mask(self, token_ids: list[int]) -> list[bool]:
        self.save_calls.append({"method": "compute_mask", "token_ids": list(token_ids)})
        return list(self.mask)

    def is_complete(self, token_ids: list[int]) -> bool:
        self.save_calls.append({"method": "is_complete", "token_ids": list(token_ids)})
        return self.complete


__all__ = ["ConstraintEngine", "InMemoryConstraintEngine", "LLGuidanceEngine"]
